#!/usr/bin/env python3
"""
Run Case 2 volume estimation from custom intents + prompts JSON or CSV.

Usage:
  python scripts/run_from_intents_prompts.py inputs/tina_davies_intents_prompts.json
  python scripts/run_from_intents_prompts.py inputs/go_digit_prompts.csv --company-profile company_profiles/digit_insurance.json
  python scripts/run_from_intents_prompts.py inputs/go_digit_prompts.csv --company-profile company_profiles/digit_insurance.json --locations 2840,2826,2356
  python scripts/run_from_intents_prompts.py inputs/tina_davies_intents_prompts.json --with-calibration
  python scripts/run_from_intents_prompts.py inputs/tina_davies_intents_prompts.json --dry-run

CSV: expects a header row with cluster (or intent_cluster_name) and text (or prompt) columns
(e.g. exports from Gravton synthetic_prompt).

Input JSON format:
  {
    "company_name": "Tina Davies Professional",
    "intents": [
      {
        "intent_name": "I ❤️ INK Brow Pigments",
        "intent_id": "i_love_ink_brow_pigments",
        "prompts": ["prompt1", "prompt2", ...]
      },
      ...
    ]
  }
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path (case2_demand lives in src/)
project_root = Path(__file__).resolve().parent.parent
src_dir = project_root / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(project_root))

# Load .env from project root (DATAFORSEO_*, OPENROUTER_*, etc.)
from dotenv import load_dotenv
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)

from case2_demand.config import Settings, resolve_run_context
from case2_demand.pipeline import load_company_profile
from case2_demand.util.io import write_json, write_jsonl
from case2_demand.util.locations import parse_location_codes
from case2_demand.util.ids import make_id


def _resolve_locations(location: int | None, locations: str | None) -> list[int]:
    try:
        return parse_location_codes(location=location, locations=locations)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def _intent_slug(name: str, existing: set[str] | None = None) -> str:
    """Stable filesystem-safe id from cluster label."""
    base = re.sub(r"[^\w]+", "_", name.lower()).strip("_")
    base = (base[:48] or "intent").rstrip("_")
    if not existing:
        return base
    sid = base
    n = 2
    while sid in existing:
        suffix = f"_{n}"
        sid = (base[: 48 - len(suffix)] + suffix).rstrip("_")
        n += 1
    return sid


def load_csv_cluster_prompts(path: Path) -> dict:
    """Group rows by cluster into intents (cluster + text/prompt columns)."""
    used_ids: set[str] = set()
    groups: dict[str, list[str]] = {}
    order: list[str] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        lower_map = {((h or "").strip().lower()): h for h in reader.fieldnames}
        cluster_col = lower_map.get("cluster") or lower_map.get("intent_cluster_name") or lower_map.get("intent_cluster")
        prompt_col = lower_map.get("text") or lower_map.get("prompt") or lower_map.get("prompt_text")
        if not cluster_col or not prompt_col:
            raise ValueError(
                "CSV must include cluster (or intent_cluster_name) and text (or prompt) columns; "
                f"got: {list(reader.fieldnames)}"
            )
        for row in reader:
            cluster = (row.get(cluster_col) or "").strip()
            prompt = (row.get(prompt_col) or "").strip()
            if not cluster or not prompt:
                continue
            if cluster not in groups:
                groups[cluster] = []
                order.append(cluster)
            groups[cluster].append(prompt)
    if not groups:
        raise ValueError("No cluster/prompt rows found in CSV")

    intents = []
    for cluster_name in order:
        prompts = groups[cluster_name]
        iid = _intent_slug(cluster_name, used_ids)
        used_ids.add(iid)
        intents.append({
            "intent_name": cluster_name,
            "intent_id": iid,
            "prompts": prompts,
        })
    return {"intents": intents}


def load_intents_prompts(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "intents" not in data:
        raise ValueError("JSON must have 'intents' array")
    return data


def build_prompt_items(data: dict, company_name: str) -> list[dict]:
    """Convert intents+prompts to prompt_items format for the pipeline."""
    prompt_items = []
    used: set[str] = set()
    for intent in data["intents"]:
        raw_name = intent.get("intent_name")
        intent_id = intent.get("intent_id") or _intent_slug((raw_name or "intent").strip() or "intent", used)
        used.add(intent_id)
        intent_name = raw_name if raw_name else intent_id
        prompts = intent.get("prompts", [])
        weight = 1.0 / max(len(prompts), 1)
        for p in prompts:
            if not p or not str(p).strip():
                continue
            prompt = str(p).strip()
            pid = make_id("prm", f"{company_name}|{prompt}|{intent_id}")
            prompt_items.append({
                "prompt": prompt,
                "prompt_id": pid,
                "intent_cluster_id": intent_id,
                "intent_cluster_name": intent_name,
                "weight": weight,
            })
    return prompt_items


def build_intent_cluster_plan(data: dict) -> dict:
    """Build intent_cluster_plan.json for reference."""
    clusters = []
    used: set[str] = set()
    for intent in data["intents"]:
        raw_name = intent.get("intent_name")
        intent_id = intent.get("intent_id") or _intent_slug((raw_name or "intent").strip() or "intent", used)
        used.add(intent_id)
        intent_name = raw_name if raw_name else intent_id
        clusters.append({
            "cluster_id": intent_id,
            "name": intent_name,
            "description": f"User queries related to {intent_name}",
            "example_prompt": intent.get("prompts", [""])[0] if intent.get("prompts") else "",
            "user_mindset": f"User is researching or evaluating {intent_name}.",
        })
    return {"clusters": clusters, "rationale": "Custom intents and prompts provided by user."}


async def main():
    parser = argparse.ArgumentParser(description="Run Case 2 volume from custom intents+prompts")
    parser.add_argument("input", type=Path, help="Path to intents+prompts JSON or cluster/prompt CSV")
    parser.add_argument("--company-profile", type=Path, default=None,
                        help="Company profile JSON (default: examples/tina_davies_company_profile.json)")
    parser.add_argument("--with-calibration", action="store_true",
                        help="Fetch SV+ASV, calibrate ρ,η, then estimate")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use placeholder SV/ASV (no DataForSEO API)")
    parser.add_argument(
        "--location",
        type=int,
        default=None,
        metavar="CODE",
        help="Single DataForSEO location code (default: 2840 US if neither --location nor --locations set)",
    )
    parser.add_argument(
        "--locations",
        default=None,
        metavar="CODES",
        help="Comma-separated location codes (1–5 markets); aggregated prompt volumes are summed",
    )
    parser.add_argument("--language", default="en", help="Language code")
    parser.add_argument(
        "--keyword-extraction",
        choices=["ngram", "llm"],
        default="llm",
        help="Keyword extraction: 'llm' (Gemini via OpenRouter, default) or 'ngram'",
    )
    parser.add_argument(
        "--sv-source",
        choices=["clickstream", "google_ads"],
        default=None,
        help="SV data source (default: clickstream from CASE2_SV_SOURCE / config)",
    )
    parser.add_argument(
        "--extractions-from",
        type=Path,
        default=None,
        metavar="PATH",
        help="Reuse keyword_extractions.jsonl from a prior run (same keywords for comparison)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    suffix = args.input.suffix.lower()
    if suffix == ".csv":
        data = load_csv_cluster_prompts(args.input)
    else:
        data = load_intents_prompts(args.input)

    # Resolve company profile
    profile_path = args.company_profile
    if not profile_path:
        profile_path = project_root / "examples" / "tina_davies_company_profile.json"
    if not profile_path.exists():
        print(f"Error: Company profile not found: {profile_path}", file=sys.stderr)
        sys.exit(1)

    company = load_company_profile(profile_path)
    prompt_items = build_prompt_items(data, company.company_name)
    intent_plan = build_intent_cluster_plan(data)

    # Create new run
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    os.environ["CASE2_RUN_ID"] = run_id

    settings = Settings()
    ctx = resolve_run_context(settings)
    ctx.run_dir.mkdir(parents=True, exist_ok=True)

    # Write synthetic_prompts.jsonl
    rows = [
        {
            "prompt_id": p["prompt_id"],
            "prompt": p["prompt"],
            "intent_cluster_id": p["intent_cluster_id"],
            "intent_cluster_name": p["intent_cluster_name"],
        }
        for p in prompt_items
    ]
    write_jsonl(ctx.synthetic_prompts_path, rows)

    # Write intent_cluster_plan.json
    write_json(ctx.intent_cluster_plan_path, intent_plan)

    # Write company_profile.json
    write_json(ctx.company_profile_path, company.model_dump())

    if data.get("funnel_segment_by_prompt"):
        write_json(ctx.run_dir / "funnel_segment_by_prompt.json", data["funnel_segment_by_prompt"])

    print(f"Created run {run_id}: {len(prompt_items)} prompts across {len(data['intents'])} intents")
    print(f"Run dir: {ctx.run_dir}")

    location_codes = _resolve_locations(args.location, args.locations)
    locations_csv = ",".join(str(c) for c in location_codes) if len(location_codes) > 1 else None
    print(f"Location code(s): {', '.join(str(c) for c in location_codes)}")

    # Run pipeline via CLI
    from case2_demand.cli import _run_all_with_calibration, run_pipeline

    if args.with_calibration:
        args_obj = type("Args", (), {
            "location": location_codes[0],
            "locations": locations_csv,
            "language": args.language,
            "with_calibration": True,
            "keyword_extraction": args.keyword_extraction,
            "sv_source": args.sv_source,
        })()
        await _run_all_with_calibration(
            prompt_items=prompt_items,
            company_name=company.company_name,
            ctx=ctx,
            settings=settings,
            args=args_obj,
            extractions_from_path=args.extractions_from,
        )
    else:
        await run_pipeline(
            prompt_items=prompt_items,
            company_name=company.company_name,
            location_code=location_codes[0],
            location_codes=location_codes if len(location_codes) > 1 else None,
            language_code=args.language,
            dry_run=args.dry_run,
            keyword_extraction=args.keyword_extraction,
        )


if __name__ == "__main__":
    asyncio.run(main())
