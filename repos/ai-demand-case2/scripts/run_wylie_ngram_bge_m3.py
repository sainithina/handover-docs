#!/usr/bin/env python3
"""
Wylie Hotel 100 prompts — ngram candidate extraction with BGE-M3 importance scoring.

Same ngram candidates as production (`_generate_candidate_keywords`), but relevance
is scored with BAAI/bge-m3 dense cosine similarity instead of ms-marco cross-encoder.

Usage:
    PYTHONPATH=src python scripts/run_wylie_ngram_bge_m3.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
SCRIPTS_DIR = REPO_ROOT / "scripts"
for p in (SRC_DIR, SCRIPTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from case2_demand.calibration import (  # noqa: E402
    apply_rho_eta_floors_to_calibration_dict,
    load_calibration,
)
from case2_demand.config import Settings  # noqa: E402
from case2_demand.keyword_extraction.bge_m3_scorer import (  # noqa: E402
    score_keywords_with_bge_m3_importance,
)
from case2_demand.keyword_extraction.extractor import _generate_candidate_keywords  # noqa: E402
from case2_demand.keyword_extraction.keyword_validation import is_generic_phrase  # noqa: E402
from case2_demand.keyword_volume.dataforseo import (  # noqa: E402
    DataForSEOASVClient,
    DataForSEOSVClient,
)
import test_wylie_hotel_all_methods as wylie  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "runs" / "wylie_ngram"
OUTPUT_STEM = "wylie_hotel_ngram_bge_m3_volumes"


def run_ngram_bge_m3(prompts: list[dict], *, max_keywords: int) -> dict[str, list[tuple[str, float]]]:
    print("[setup] loading BGE-M3 importance scorer (BAAI/bge-m3) ...")
    score_keywords_with_bge_m3_importance("warmup query", ["warmup keyword"], max_keywords=1)

    out: dict[str, list[tuple[str, float]]] = {}
    for i, p in enumerate(prompts, 1):
        prompt = p["prompt"]
        candidates = [c for c in _generate_candidate_keywords(prompt) if not is_generic_phrase(c)]
        if not candidates:
            out[p["prompt_id"]] = [(prompt[:50] or "general", 0.8)]
            continue
        scored = score_keywords_with_bge_m3_importance(prompt, candidates, max_keywords=max_keywords)
        if not scored:
            out[p["prompt_id"]] = [(prompt[:50], 0.7)]
        else:
            out[p["prompt_id"]] = [(k.keyword, k.importance_score) for k in scored]
        if i % 25 == 0:
            print(f"    scored {i}/{len(prompts)} prompts ...")
    return out


async def main() -> None:
    settings = Settings()
    login = settings.DATAFORSEO_LOGIN or ""
    password = settings.DATAFORSEO_PASSWORD or ""
    base_url = settings.DATAFORSEO_BASE_URL or "https://api.dataforseo.com/v3"
    if not login or not password:
        print("ERROR: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    prompts = wylie.build_prompts()
    max_keywords = settings.CASE2_MAX_KEYWORDS
    print(f"[run] {len(prompts)} prompts | method=ngram | importance_scorer=BAAI/bge-m3 | max_keywords={max_keywords}")

    ngram_results = run_ngram_bge_m3(prompts, max_keywords=max_keywords)

    all_keywords = sorted({kw for entries in ngram_results.values() for kw, _ in entries})
    print(f"[sv/asv] fetching {len(all_keywords)} keywords ...")
    sv_client = DataForSEOSVClient(
        login=login, password=password, base_url=base_url, sv_source=settings.CASE2_SV_SOURCE,
    )
    asv_client = DataForSEOASVClient(login=login, password=password, base_url=base_url)
    sv_results = await sv_client.get_volume(all_keywords, location_code=wylie.LOCATION_CODE, language_code=wylie.LANGUAGE_CODE)
    asv_results = await asv_client.get_volume(all_keywords, location_code=wylie.LOCATION_CODE, language_code=wylie.LANGUAGE_CODE)
    sv_map = {r.keyword: (r.search_volume if r.search_volume is not None else 1) for r in sv_results}
    asv_map = {r.keyword: (r.search_volume if r.search_volume is not None else 1) for r in asv_results}
    cpc_map = {r.keyword: r.cpc for r in sv_results}
    comp_map = {r.keyword: r.competition for r in sv_results}

    cal = load_calibration(wylie.REFERENCE_CALIBRATION)
    apply_rho_eta_floors_to_calibration_dict(cal)
    beta = settings.CASE2_BETA if settings.CASE2_BETA is not None else 60.0
    hp, rho_by_keyword = wylie._build_hp_for_intent(cal, wylie.INTENT_ID, beta)

    rows = wylie.estimate_and_build_rows(
        prompts, ngram_results,
        hp=hp, rho_by_keyword=rho_by_keyword,
        sv_map=sv_map, asv_map=asv_map, cpc_map=cpc_map, comp_map=comp_map,
    )
    for row in rows:
        row["importance_scorer"] = "BAAI/bge-m3"

    detail = pd.DataFrame(rows)
    export_cols = ["prompt", "prompt_ai_demand_median", "keyword", "importance_score", "fusion_weight"]
    export = detail[export_cols].sort_values(["prompt", "fusion_weight"], ascending=[True, False]).reset_index(drop=True)
    summary = detail.groupby("prompt", as_index=False).agg(
        prompt_ai_demand_median=("prompt_ai_demand_median", "first"),
        keyword_count=("keyword", "count"),
    )

    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = [
        output_dir / f"{OUTPUT_STEM}.xlsx",
        Path("/Users/sainithinartham/Downloads") / f"{OUTPUT_STEM}.xlsx",
    ]
    for out_path in output_paths:
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            export.to_excel(writer, sheet_name="ngram_bge_m3", index=False)
            detail.to_excel(writer, sheet_name="detail", index=False)
            summary.to_excel(writer, sheet_name="summary", index=False)
        print(f"Saved -> {out_path}")

    y = summary["prompt_ai_demand_median"]
    print(f"Rows: {len(export)} | prompts: {len(summary)}")
    print(f"Y median: mean={y.mean():.1f}, median={y.median():.1f}, min={y.min():.2f}, max={y.max():.2f}")
    print(f"At floor (~1.1): {(y <= 1.2).sum()} ({100 * (y <= 1.2).mean():.0f}%)")


if __name__ == "__main__":
    asyncio.run(main())
