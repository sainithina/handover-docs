#!/usr/bin/env python3
"""
Re-estimate prompt/intent demand for an existing run with a new softmax beta.

Reuses keyword_extractions, calibrated.json, sv_data.jsonl, asv_data.jsonl —
no LLM extraction, calibration, or DataForSEO refetch.

Usage:
  PYTHONPATH=src python scripts/refusion_beta_for_run.py runs/20260521T062625Z --beta 20
  PYTHONPATH=src python scripts/refusion_beta_for_run.py runs/20260521T062625Z --beta 20 --suffix beta20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
src_dir = project_root / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

from case2_demand.cli import run_pipeline
from case2_demand.config import Settings
from case2_demand.keyword_volume.base import KeywordVolumeResult
from case2_demand.util.io import iter_jsonl


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


async def main() -> None:
    parser = argparse.ArgumentParser(description="Refusion with new beta on existing run data")
    parser.add_argument("run_dir", type=Path, help="Path to runs/<RUN_ID>")
    parser.add_argument("--beta", type=float, required=True, help="Softmax beta for fusion weights")
    parser.add_argument(
        "--suffix",
        type=str,
        default="",
        help="If set, write prompt_estimates{suffix}.csv etc. instead of overwriting defaults",
    )
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        print(f"Error: not a directory: {run_dir}", file=sys.stderr)
        sys.exit(1)

    run_id = run_dir.name
    os.environ["CASE2_RUN_ID"] = run_id
    os.environ["CASE2_BETA"] = str(args.beta)

    settings = Settings()
    default_vol = float(settings.CASE2_DEFAULT_MISSING_VOLUME)

    calibrated_path = run_dir / "calibrated.json"
    sv_path = run_dir / "sv_data.jsonl"
    asv_path = run_dir / "asv_data.jsonl"
    extractions_path = run_dir / "keyword_extractions.jsonl"
    prompts_path = run_dir / "synthetic_prompts.jsonl"

    for p in (calibrated_path, sv_path, asv_path, extractions_path, prompts_path):
        if not p.exists():
            print(f"Error: missing {p}", file=sys.stderr)
            sys.exit(1)

    cal = json.loads(calibrated_path.read_text(encoding="utf-8"))
    location_code = int(cal.get("location_code") or 2840)
    language_code = str(cal.get("language_code") or "en")

    sv_results = _load_sv_results(sv_path)
    sv_lookup = _load_lookup(sv_path, default_vol)
    asv_lookup = _load_lookup(asv_path, default_vol)
    extractions = list(iter_jsonl(extractions_path))
    prompt_items = _load_prompt_items(prompts_path)

    company_name = None
    profile_path = run_dir / "company_profile.json"
    if profile_path.exists():
        company_name = json.loads(profile_path.read_text(encoding="utf-8")).get("company_name")

    print(f"Refusion run {run_id}: beta={args.beta}, prompts={len(prompt_items)}, keywords(SV)={len(sv_lookup)}")

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

    if args.suffix:
        suffix = args.suffix if args.suffix.startswith("_") else f"_{args.suffix}"
        for name in (
            "prompt_estimates.jsonl",
            "prompt_estimates.csv",
            "prompt_keyword_volumes.csv",
            "intent_cluster_estimates.json",
            "metrics.json",
            "insights.md",
        ):
            src = run_dir / name
            if src.exists():
                dst = run_dir / f"{src.stem}{suffix}{src.suffix}"
                dst.write_bytes(src.read_bytes())
                print(f"Copied -> {dst.name}")

    note_path = run_dir / "refusion_note.json"
    note_path.write_text(
        json.dumps({"beta": args.beta, "source_run": run_id, "reused": ["keyword_extractions", "calibrated", "sv_data", "asv_data"]}, indent=2),
        encoding="utf-8",
    )
    print(f"Done. beta={args.beta} -> {run_dir}")
    print(f"Wrote {note_path.name}")


if __name__ == "__main__":
    asyncio.run(main())
