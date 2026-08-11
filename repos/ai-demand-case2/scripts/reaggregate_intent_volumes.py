#!/usr/bin/env python3
"""
Re-aggregate intent/topic volumes from existing prompt_estimates.jsonl.

Does not refetch SV/ASV or re-run per-prompt fusion — only recomputes
intent_cluster_estimates.json, metrics.json, and insights.md.

Usage:
  PYTHONPATH=src python scripts/reaggregate_intent_volumes.py runs/20260617T170025Z
  CASE2_INTENT_VOLUME_METHOD=representative_incremental PYTHONPATH=src \\
    python scripts/reaggregate_intent_volumes.py runs/20260617T170025Z
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
src_dir = project_root / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

from case2_demand.config import Settings, resolve_run_context
from case2_demand.overlap_discount import estimate_intent_cluster_overlap_discount
from case2_demand.schemas import PromptDemandEstimate
from case2_demand.topic_volume_representative import estimate_intent_cluster_representative_incremental
from case2_demand.util.io import iter_jsonl, write_json
from case2_demand.cli import _write_run_summary


def _load_prompt_estimates(path: Path) -> list[PromptDemandEstimate]:
    rows = list(iter_jsonl(path))
    return [PromptDemandEstimate.model_validate(row) for row in rows]


def _aggregate_intents(
    prompt_estimates: list[PromptDemandEstimate],
    *,
    settings: Settings,
    extractions: list[dict],
) -> list:
    method = (settings.CASE2_INTENT_VOLUME_METHOD or "representative_incremental").strip().lower()
    alpha = float(settings.CASE2_OVERLAP_DISCOUNT_ALPHA or 0.7)
    model_name = settings.CASE2_INTENT_DEDUP_MODEL or "all-MiniLM-L6-v2"
    sim_threshold = float(settings.CASE2_INTENT_DEDUP_SIM_THRESHOLD or 0.4)

    if method == "representative_incremental":
        by_intent: dict[str, list[PromptDemandEstimate]] = {}
        for pe in prompt_estimates:
            key = pe.intent_cluster_id or "_unknown"
            by_intent.setdefault(key, []).append(pe)
        out = []
        for cluster_id, cluster_prompts in by_intent.items():
            intent_name = (
                cluster_prompts[0].intent_cluster_name or cluster_id
                if cluster_prompts
                else cluster_id
            )
            out.append(
                estimate_intent_cluster_representative_incremental(
                    cluster_id=cluster_id,
                    intent_name=str(intent_name),
                    prompt_estimates=cluster_prompts,
                    model_name=model_name,
                    sim_threshold=sim_threshold,
                    alpha=alpha,
                )
            )
        return out

    if method == "overlap_discount":
        by_intent_ext: dict[str, list[dict]] = {}
        for ext in extractions:
            key = ext.get("intent_cluster_id") or "_unknown"
            by_intent_ext.setdefault(key, []).append(ext)
        prompt_by_id = {p.prompt_id: p for p in prompt_estimates}
        out = []
        for cluster_id, exts in by_intent_ext.items():
            intent_name = (exts[0].get("intent_cluster_name") or cluster_id) if exts else cluster_id
            out.append(
                estimate_intent_cluster_overlap_discount(
                    cluster_id=cluster_id,
                    intent_name=str(intent_name),
                    extractions=exts,
                    prompt_estimates_by_id=prompt_by_id,
                    model_name=model_name,
                    alpha=alpha,
                )
            )
        return out

    raise SystemExit(
        f"reaggregate_intent_volumes supports representative_incremental and overlap_discount; got {method!r}. "
        "Use refusion_beta_for_run.py for fusion re-estimates."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-aggregate topic volumes for an existing run")
    parser.add_argument("run_dir", type=Path, help="Path to runs/<RUN_ID>")
    parser.add_argument(
        "--method",
        choices=["representative_incremental", "overlap_discount"],
        default=None,
        help="Override CASE2_INTENT_VOLUME_METHOD",
    )
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Not a directory: {run_dir}")

    os.environ["CASE2_RUN_ID"] = run_dir.name
    if args.method:
        os.environ["CASE2_INTENT_VOLUME_METHOD"] = args.method

    settings = Settings()
    ctx = resolve_run_context(settings)

    prompt_path = run_dir / "prompt_estimates.jsonl"
    extractions_path = run_dir / "keyword_extractions.jsonl"
    if not prompt_path.exists():
        raise SystemExit(f"Missing {prompt_path}")

    prompt_estimates = _load_prompt_estimates(prompt_path)
    extractions = list(iter_jsonl(extractions_path)) if extractions_path.exists() else []

    intent_estimates = _aggregate_intents(
        prompt_estimates,
        settings=settings,
        extractions=extractions,
    )

    write_json(run_dir / "intent_cluster_estimates.json", [e.model_dump() for e in intent_estimates])

    company_name = None
    profile_path = run_dir / "company_profile.json"
    if profile_path.exists():
        company_name = json.loads(profile_path.read_text(encoding="utf-8")).get("company_name")

    cal_path = run_dir / "calibrated.json"
    location_code = 2840
    language_code = "en"
    if cal_path.exists():
        cal = json.loads(cal_path.read_text(encoding="utf-8"))
        location_code = int(cal.get("location_code") or location_code)
        language_code = str(cal.get("language_code") or language_code)

    sv_source = None
    metrics_path = run_dir / "metrics.json"
    if metrics_path.exists():
        sv_source = json.loads(metrics_path.read_text(encoding="utf-8")).get("sv_source")

    _write_run_summary(
        ctx=ctx,
        company_name=company_name,
        prompt_estimates=[p.model_dump() for p in prompt_estimates],
        intent_estimates=[e.model_dump() for e in intent_estimates],
        location_codes=[location_code],
        language_code=language_code,
        sv_source=sv_source,
        settings=settings,
    )

    note = {
        "method": settings.CASE2_INTENT_VOLUME_METHOD,
        "source_run": run_dir.name,
        "reused": ["prompt_estimates.jsonl"],
        "prompt_count": len(prompt_estimates),
        "intent_cluster_count": len(intent_estimates),
    }
    (run_dir / "reaggregate_intent_note.json").write_text(json.dumps(note, indent=2) + "\n", encoding="utf-8")

    for e in intent_estimates:
        print(
            f"{e.intent_cluster_name}: Y_median={e.Y_median:,.1f} "
            f"method={e.volume_method} prompts={e.num_prompts}"
        )
        if e.representative_prompt_id:
            print(f"  rep={e.representative_prompt_id} vol={e.representative_volume:,.1f} "
                  f"incremental={float(e.incremental_volume or 0):,.1f}")
    print(f"Updated {run_dir / 'intent_cluster_estimates.json'}, insights.md, metrics.json")


if __name__ == "__main__":
    main()
