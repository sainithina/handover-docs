#!/usr/bin/env python3
"""
Re-estimate an existing run with importance-score keyword filtering before fusion.

Copies static artifacts into a new run directory, then refusions using the same
keyword_extractions, calibrated.json, sv_data.jsonl, and asv_data.jsonl.

For ``binary_search``: ``--levels`` is the iterative median-cutoff depth (1 or 2),
**not** the number of keywords to keep.

Usage:
  PYTHONPATH=src python scripts/refusion_importance_filter.py runs/20260617T170025Z --levels 1
  PYTHONPATH=src python scripts/refusion_importance_filter.py runs/20260617T170025Z --levels 1 --levels 2
  PYTHONPATH=src python scripts/refusion_importance_filter.py runs/20260617T170025Z --levels 2 --method binary_search
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
src_dir = project_root / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

from case2_demand.cli import run_pipeline
from case2_demand.config import Settings
from case2_demand.keyword_volume.base import KeywordVolumeResult
from case2_demand.util.io import iter_jsonl

_STATIC_ARTIFACTS = (
    "calibrated.json",
    "historical_sv_asv.json",
    "sv_data.jsonl",
    "asv_data.jsonl",
    "keyword_extractions.jsonl",
    "synthetic_prompts.jsonl",
    "company_profile.json",
    "intent_cluster_plan.json",
    "keyword_volumes.csv",
    "funnel_segment_by_prompt.json",
)


def _load_sv_results(sv_path: Path) -> list[KeywordVolumeResult]:
    results: list[KeywordVolumeResult] = []
    for row in iter_jsonl(sv_path):
        kw = row.get("keyword", "")
        if not kw:
            continue
        results.append(
            KeywordVolumeResult(
                keyword=kw,
                search_volume=row.get("search_volume"),
                cpc=row.get("cpc"),
                competition=row.get("competition"),
            )
        )
    return results


def _load_lookup(path: Path, default: float) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in iter_jsonl(path):
        kw = row.get("keyword", "")
        if kw:
            out[kw] = float(row.get("search_volume") or default)
    return out


def _load_prompt_items(prompts_path: Path) -> list[dict]:
    items: list[dict] = []
    for row in iter_jsonl(prompts_path):
        items.append(
            {
                "prompt_id": row.get("prompt_id"),
                "prompt": row.get("prompt"),
                "intent_cluster_id": row.get("intent_cluster_id"),
                "intent_cluster_name": row.get("intent_cluster_name"),
            }
        )
    return items


def _copy_static_artifacts(source_dir: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in _STATIC_ARTIFACTS:
        src = source_dir / name
        if src.is_file():
            shutil.copy2(src, dest_dir / name)


def _default_new_run_id(source_run_id: str, levels: int, method: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if method == "binary_search":
        return f"{stamp}_bs_l{levels}"
    method_slug = method.replace("_", "")
    return f"{stamp}_{method_slug}_l{levels}"


async def _run_variant(
    *,
    source_dir: Path,
    levels: int,
    method: str,
    new_run_id: str | None,
    beta: float | None,
) -> Path:
    source_run_id = source_dir.name
    run_id = new_run_id or _default_new_run_id(source_run_id, levels, method)
    runs_dir = source_dir.parent
    dest_dir = runs_dir / run_id

    if dest_dir.exists() and any(dest_dir.iterdir()):
        raise FileExistsError(f"Run directory already exists and is non-empty: {dest_dir}")

    _copy_static_artifacts(source_dir, dest_dir)

    os.environ["CASE2_RUN_ID"] = run_id
    os.environ["CASE2_RUNS_DIR"] = str(runs_dir.resolve())
    os.environ["CASE2_KEYWORD_FILTER"] = method
    os.environ["CASE2_KEYWORD_FILTER_LEVELS"] = str(levels)
    if beta is not None:
        os.environ["CASE2_BETA"] = str(beta)

    settings = Settings()
    default_vol = float(settings.CASE2_DEFAULT_MISSING_VOLUME)

    calibrated_path = dest_dir / "calibrated.json"
    sv_path = dest_dir / "sv_data.jsonl"
    asv_path = dest_dir / "asv_data.jsonl"
    extractions_path = dest_dir / "keyword_extractions.jsonl"
    prompts_path = dest_dir / "synthetic_prompts.jsonl"

    cal = json.loads(calibrated_path.read_text(encoding="utf-8"))
    location_code = int(cal.get("location_code") or 2840)
    language_code = str(cal.get("language_code") or "en")

    sv_results = _load_sv_results(sv_path)
    sv_lookup = _load_lookup(sv_path, default_vol)
    asv_lookup = _load_lookup(asv_path, default_vol)
    extractions = list(iter_jsonl(extractions_path))
    prompt_items = _load_prompt_items(prompts_path)

    company_name = None
    profile_path = dest_dir / "company_profile.json"
    if profile_path.exists():
        company_name = json.loads(profile_path.read_text(encoding="utf-8")).get("company_name")

    print(
        f"Refusion {source_run_id} -> {run_id}: "
        f"filter={method}, levels={levels}, prompts={len(prompt_items)}, keywords(SV)={len(sv_lookup)}"
    )

    await run_pipeline(
        prompt_items=prompt_items,
        company_name=company_name,
        location_code=location_code,
        language_code=language_code,
        dry_run=False,
        calibrated_from=calibrated_path,
        sv_lookup=sv_lookup,
        asv_lookup=asv_lookup,
        sv_results=sv_results,
        extractions=extractions,
    )

    note = {
        "source_run": source_run_id,
        "new_run_id": run_id,
        "keyword_filter": method,
        "binary_search_levels": levels,
        "beta": beta if beta is not None else settings.CASE2_BETA,
        "reused": [
            "keyword_extractions",
            "calibrated",
            "sv_data",
            "asv_data",
            "company_profile",
            "synthetic_prompts",
        ],
    }
    note_path = dest_dir / "refusion_importance_filter_note.json"
    note_path.write_text(json.dumps(note, indent=2) + "\n", encoding="utf-8")
    print(f"Done -> {dest_dir}")
    print(f"Wrote {note_path.name}")
    return dest_dir


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="New run with iterative binary-search median importance filter"
    )
    parser.add_argument("run_dir", type=Path, help="Source runs/<RUN_ID>")
    parser.add_argument(
        "--levels",
        type=int,
        action="append",
        dest="level_values",
        help="Binary-search median cutoff depth: 1 or 2 (repeat for multiple runs)",
    )
    parser.add_argument(
        "--method",
        default="binary_search",
        choices=("binary_search", "top_n", "median"),
        help="Filter method (default: binary_search)",
    )
    parser.add_argument(
        "--new-run-id",
        default=None,
        help="Single output run id (only when one --levels value)",
    )
    parser.add_argument(
        "--beta",
        type=float,
        default=None,
        help="Override softmax beta (default: from calibrated / settings)",
    )
    args = parser.parse_args()

    source_dir = args.run_dir.resolve()
    if not source_dir.is_dir():
        print(f"Error: not a directory: {source_dir}", file=sys.stderr)
        sys.exit(1)

    level_values = args.level_values or [1]
    for lv in level_values:
        if lv not in (1, 2):
            print("Error: --levels must be 1 or 2 for binary-search median cutoff", file=sys.stderr)
            sys.exit(1)

    if args.new_run_id and len(level_values) != 1:
        print("Error: --new-run-id only allowed with a single --levels value", file=sys.stderr)
        sys.exit(1)

    created: list[Path] = []
    for levels in level_values:
        dest = await _run_variant(
            source_dir=source_dir,
            levels=levels,
            method=args.method,
            new_run_id=args.new_run_id if len(level_values) == 1 else None,
            beta=args.beta,
        )
        created.append(dest)

    print("\nCreated runs:")
    for path in created:
        print(f"  {path}")


if __name__ == "__main__":
    asyncio.run(main())
