#!/usr/bin/env python3
"""
Wylie Hotel 100 prompts — ngram candidates filtered by LLM, then cross-encoder scored.

Pipeline:
  1. Generate n-gram candidates from each prompt
  2. LLM selects relevant, non-overlapping subset (no new keywords)
  3. Cross-encoder importance scoring on survivors
  4. Case2 volume estimation

Usage:
    PYTHONPATH=src python scripts/run_wylie_ngram_llm_filter.py
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
from case2_demand.keyword_extraction.ngram_llm_filter import (  # noqa: E402
    extract_ngram_llm_filtered_keywords_batch,
)
from case2_demand.keyword_volume.dataforseo import (  # noqa: E402
    DataForSEOASVClient,
    DataForSEOSVClient,
)
import test_wylie_hotel_all_methods as wylie  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "runs" / "wylie_ngram"
OUTPUT_STEM = "wylie_hotel_ngram_llm_filter_volumes"
FILTER_PROMPT = SRC_DIR / "case2_demand" / "prompts" / "keyword_filter_ngram_system.txt"
MAX_KEYWORDS = 6


def build_prompt_order(prompts: list[dict]) -> list[str]:
    return [p["prompt"] for p in prompts]


async def main() -> None:
    settings = Settings()
    login = settings.DATAFORSEO_LOGIN or ""
    password = settings.DATAFORSEO_PASSWORD or ""
    base_url = settings.DATAFORSEO_BASE_URL or "https://api.dataforseo.com/v3"
    if not login or not password:
        print("ERROR: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD not set", file=sys.stderr)
        sys.exit(1)
    if not settings.OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    prompts = wylie.build_prompts()
    prompt_texts = build_prompt_order(prompts)
    ce_model = settings.CASE2_CROSS_ENCODER_MODEL
    llm_model = settings.CASE2_LLM_MODEL

    print(
        f"[run] {len(prompts)} prompts | method=ngram+llm_filter | "
        f"llm={llm_model} | scorer={ce_model} | max_keywords={MAX_KEYWORDS}"
    )

    keyword_lists, filter_logs = extract_ngram_llm_filtered_keywords_batch(
        prompt_texts,
        api_key=settings.OPENROUTER_API_KEY or "",
        base_url=settings.OPENROUTER_BASE_URL or "https://openrouter.ai/api/v1",
        model=llm_model,
        system_prompt_path=FILTER_PROMPT,
        max_keywords=MAX_KEYWORDS,
        max_items_per_call=settings.CASE2_LLM_MAX_PROMPTS_PER_CALL,
        request_delay_sec=settings.CASE2_LLM_REQUEST_DELAY_SEC,
        cross_encoder_model=ce_model,
        timeout_sec=settings.CASE2_LLM_REQUEST_TIMEOUT_SEC,
    )

    ngram_results: dict[str, list[tuple[str, float]]] = {}
    for p, kws in zip(prompts, keyword_lists):
        ngram_results[p["prompt_id"]] = [(k.keyword, k.importance_score) for k in kws]

    fallbacks = sum(1 for log in filter_logs if log.get("used_fallback"))
    avg_in = sum(log["num_ngram_candidates"] for log in filter_logs) / max(len(filter_logs), 1)
    avg_out = sum(len(ngram_results[p["prompt_id"]]) for p in prompts) / len(prompts)
    print(f"    avg ngram candidates in: {avg_in:.1f} | avg keywords out: {avg_out:.1f} | fallbacks: {fallbacks}")

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
        row["importance_scorer"] = ce_model
        row["extraction_method"] = "ngram+llm_filter"

    detail = pd.DataFrame(rows)
    export_cols = ["prompt", "prompt_ai_demand_median", "keyword", "importance_score", "fusion_weight"]

    # Order: prompts in TOPICS order, keywords by fusion_weight desc within prompt
    prompt_order = {p: i for i, p in enumerate(prompt_texts)}
    export = detail[export_cols].copy()
    export["_prompt_ord"] = export["prompt"].map(prompt_order)
    export = export.sort_values(["_prompt_ord", "fusion_weight"], ascending=[True, False]).drop(columns="_prompt_ord").reset_index(drop=True)

    filter_df = pd.DataFrame(filter_logs)
    summary = detail.groupby("prompt", as_index=False).agg(
        prompt_ai_demand_median=("prompt_ai_demand_median", "first"),
        keyword_count=("keyword", "count"),
    )
    summary["_prompt_ord"] = summary["prompt"].map(prompt_order)
    summary = summary.sort_values("_prompt_ord").drop(columns="_prompt_ord").reset_index(drop=True)

    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths = [
        output_dir / f"{OUTPUT_STEM}.xlsx",
        Path("/Users/sainithinartham/Downloads") / f"{OUTPUT_STEM}.xlsx",
    ]
    for out_path in output_paths:
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            export.to_excel(writer, sheet_name="ngram_llm_filter", index=False)
            detail.to_excel(writer, sheet_name="detail", index=False)
            summary.to_excel(writer, sheet_name="summary", index=False)
            filter_df.to_excel(writer, sheet_name="filter_log", index=False)
        print(f"Saved -> {out_path}")

    y = summary["prompt_ai_demand_median"]
    print(f"Rows: {len(export)} | prompts: {len(summary)}")
    print(f"Y median: mean={y.mean():.1f}, median={y.median():.1f}, min={y.min():.2f}, max={y.max():.2f}")
    print(f"At floor (~1.1): {(y <= 1.2).sum()} ({100 * (y <= 1.2).mean():.0f}%)")


if __name__ == "__main__":
    asyncio.run(main())
