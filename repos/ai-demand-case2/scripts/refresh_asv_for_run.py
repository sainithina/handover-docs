#!/usr/bin/env python3
"""
Re-fetch ASV for an existing Case 2 run, recalibrate, and re-estimate prompt volumes.

Use when a run completed with all-zero ASV (DataForSEO batch failure).

Usage:
  PYTHONPATH=src python scripts/refresh_asv_for_run.py runs/20260520T085606Z
  PYTHONPATH=src python scripts/refresh_asv_for_run.py runs/20260520T085606Z --location 2356 --language en
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

from dotenv import load_dotenv

env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)

from case2_demand.calibration import run_calibration, save_calibration
from case2_demand.cli import (
    _build_asv_lookup,
    _build_historical_sv_asv,
    _count_nonempty_asv_items,
    run_pipeline,
)
from case2_demand.config import Settings
from case2_demand.keyword_volume.base import KeywordVolumeResult
from case2_demand.keyword_volume.dataforseo import DataForSEOASVClient
from case2_demand.util.io import iter_jsonl, write_json, write_jsonl


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


def _load_extractions(path: Path) -> list[dict]:
    return list(iter_jsonl(path))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh ASV and re-estimate for an existing run")
    parser.add_argument("run_dir", type=Path, help="Path to runs/<RUN_ID>")
    parser.add_argument("--location", type=int, default=None, help="DataForSEO location_code")
    parser.add_argument("--language", type=str, default="en")
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        print(f"Error: not a directory: {run_dir}", file=sys.stderr)
        sys.exit(1)

    run_id = run_dir.name
    os.environ["CASE2_RUN_ID"] = run_id

    settings = Settings()
    calibrated_path = run_dir / "calibrated.json"
    location_code = args.location
    language_code = args.language
    if location_code is None and calibrated_path.exists():
        cal = json.loads(calibrated_path.read_text(encoding="utf-8"))
        location_code = cal.get("location_code", 2840)
    if location_code is None:
        location_code = 2840

    sv_path = run_dir / "sv_data.jsonl"
    if not sv_path.exists():
        print(f"Error: missing {sv_path}", file=sys.stderr)
        sys.exit(1)

    keywords = [r.keyword for r in _load_sv_results(sv_path)]
    extractions_path = run_dir / "keyword_extractions.jsonl"
    prompts_path = run_dir / "synthetic_prompts.jsonl"
    if not extractions_path.exists() or not prompts_path.exists():
        print("Error: run dir needs keyword_extractions.jsonl and synthetic_prompts.jsonl", file=sys.stderr)
        sys.exit(1)

    login = settings.DATAFORSEO_LOGIN or ""
    password = settings.DATAFORSEO_PASSWORD or ""
    if not login or not password:
        print("Error: set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD", file=sys.stderr)
        sys.exit(1)

    print(f"Refreshing ASV for {len(keywords)} keywords (run {run_id}, location={location_code})...")
    asv_client = DataForSEOASVClient(login=login, password=password)
    asv_items = await asv_client.get_volume_with_history(keywords, location_code, language_code)
    nonempty = _count_nonempty_asv_items(asv_items)
    min_asv = max(10, int(0.05 * len(keywords)))
    if nonempty < min_asv:
        print(f"Sparse ASV ({nonempty}/{len(keywords)}); retrying...")
        await asyncio.sleep(1.0)
        retry = await asv_client.get_volume_with_history(keywords, location_code, language_code)
        retry_n = _count_nonempty_asv_items(retry)
        if retry_n > nonempty:
            asv_items = retry
            nonempty = retry_n
    print(f"ASV rows with volume: {nonempty}/{len(keywords)}")

    default_vol = float(settings.CASE2_DEFAULT_MISSING_VOLUME)
    sv_results = _load_sv_results(sv_path)
    asv_lookup = _build_asv_lookup(asv_items, keywords, default_vol)
    sv_lookup = {r.keyword: float(r.search_volume or default_vol) for r in sv_results}

    asv_rows = [{"keyword": k, "search_volume": v} for k, v in asv_lookup.items()]
    write_jsonl(run_dir / "asv_data.jsonl", asv_rows)
    print(f"Wrote {run_dir / 'asv_data.jsonl'}")

    extractions = _load_extractions(extractions_path)
    rho_by_kw, calibrated_eta, rho_coeffs, sv_params_by_intent, asv_params_by_intent, residuals = await run_calibration(
        keywords=keywords,
        sv_client=None,
        asv_client=None,
        location_code=location_code,
        language_code=language_code,
        sv_results=sv_results,
        asv_items=asv_items,
        extractions=extractions,
    )
    save_calibration(
        calibrated_path,
        mu_eta=calibrated_eta.mu_eta,
        sigma_eta=calibrated_eta.sigma_eta,
        rho_coeffs=rho_coeffs,
        rho_by_keyword=rho_by_kw,
        num_samples=calibrated_eta.num_samples,
        var_u=calibrated_eta.var_u,
        residuals=residuals,
        keywords=keywords,
        location_code=location_code,
        language_code=language_code,
        sv_params_by_intent=sv_params_by_intent,
        asv_params_by_intent=asv_params_by_intent,
    )
    print(f"Recalibrated -> {calibrated_path} (η residuals: {calibrated_eta.num_samples})")

    historical_sv, historical_asv, keywords_with_history, keyword_metadata, periods_sv, periods_asv = _build_historical_sv_asv(
        sv_results, asv_items
    )
    if keywords_with_history:
        payload: dict = {
            "description": "Historical SV and ASV from DataForSEO (keywords × time periods)",
            "keywords": keywords_with_history,
            "historical_sv": historical_sv,
            "historical_asv": historical_asv,
            "keyword_metadata": keyword_metadata,
        }
        if periods_sv:
            payload["periods_sv"] = [{"year": y, "month": m} for y, m in periods_sv]
        if periods_asv:
            payload["periods_asv"] = [{"year": y, "month": m} for y, m in periods_asv]
        write_json(run_dir / "historical_sv_asv.json", payload)

    prompt_items = _load_prompt_items(prompts_path)
    company_name = None
    profile_path = run_dir / "company_profile.json"
    if profile_path.exists():
        company_name = json.loads(profile_path.read_text(encoding="utf-8")).get("company_name")

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
    print("Done. Re-export prompt_keyword_volumes.csv if needed:")
    print(f"  PYTHONPATH=src python scripts/export_prompt_keyword_volumes.py {run_dir}")


if __name__ == "__main__":
    asyncio.run(main())
