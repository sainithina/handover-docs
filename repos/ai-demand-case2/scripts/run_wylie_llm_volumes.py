#!/usr/bin/env python3
"""Wylie Hotel 100 prompts — pure LLM keyword extraction (2-3 keywords) + volumes."""

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

from case2_demand.calibration import apply_rho_eta_floors_to_calibration_dict, load_calibration  # noqa: E402
from case2_demand.config import Settings  # noqa: E402
from case2_demand.keyword_volume.dataforseo import DataForSEOASVClient, DataForSEOSVClient  # noqa: E402
import test_wylie_hotel_all_methods as wylie  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "runs" / "wylie_ngram"
OUTPUT_STEM = "wylie_hotel_llm_volumes"
SV_CACHE = REPO_ROOT / "runs" / "keyword_grounding_test" / "keyword_grounding_test.xlsx"


async def main() -> None:
    settings = Settings()
    if not settings.OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    prompts = wylie.build_prompts()
    max_keywords = int(getattr(settings, "CASE2_LLM_MAX_KEYWORDS", 3) or 3)
    ce_model = settings.CASE2_CROSS_ENCODER_MODEL
    llm_model = settings.CASE2_LLM_MODEL

    print(
        f"[run] {len(prompts)} prompts | method=llm | llm={llm_model} | "
        f"max_keywords={max_keywords} | scorer={ce_model}"
    )

    llm_results = wylie.run_llm_method(
        prompts,
        settings=settings,
        max_keywords=max_keywords,
        cross_encoder_model=ce_model,
    )

    all_keywords = sorted({kw for entries in llm_results.values() for kw, _ in entries})
    kw_counts = [len(v) for v in llm_results.values()]
    print(f"    keywords fetched: {sum(kw_counts)} total | avg {sum(kw_counts)/len(kw_counts):.1f}/prompt")

    # Try live SV; fall back to cached ngram sheet if API fails
    sv_map, asv_map, cpc_map, comp_map = {}, {}, {}, {}
    login = settings.DATAFORSEO_LOGIN or ""
    password = settings.DATAFORSEO_PASSWORD or ""
    base_url = settings.DATAFORSEO_BASE_URL or "https://api.dataforseo.com/v3"
    if login and password:
        print(f"[sv/asv] fetching {len(all_keywords)} keywords live ...")
        sv_client = DataForSEOSVClient(
            login=login, password=password, base_url=base_url, sv_source=settings.CASE2_SV_SOURCE,
        )
        asv_client = DataForSEOASVClient(login=login, password=password, base_url=base_url)
        try:
            sv_results = await sv_client.get_volume(
                all_keywords, location_code=wylie.LOCATION_CODE, language_code=wylie.LANGUAGE_CODE,
            )
            sv_map = {r.keyword: max(r.search_volume or 0, 1) for r in sv_results}
            cpc_map = {r.keyword: r.cpc for r in sv_results}
            comp_map = {r.keyword: r.competition for r in sv_results}
        except Exception as e:
            print(f"[sv] live fetch failed ({e})")
        try:
            asv_results = await asv_client.get_volume(
                all_keywords, location_code=wylie.LOCATION_CODE, language_code=wylie.LANGUAGE_CODE,
            )
            asv_map = {r.keyword: max(r.search_volume or 0, 1) for r in asv_results}
        except Exception as e:
            print(f"[asv] live fetch failed ({e})")

    if SV_CACHE.exists() and (not sv_map or not asv_map):
        print("[sv/asv] filling gaps from cached ngram SV/ASV ...")
        cache = pd.read_excel(SV_CACHE, sheet_name="ngram")[
            ["keyword", "sv", "asv", "cpc", "competition"]
        ].drop_duplicates("keyword")
        cache_sv = {r.keyword: max(float(r.sv or 0), 1) for r in cache.itertuples()}
        cache_asv = {r.keyword: max(float(r.asv or 0), 1) for r in cache.itertuples()}
        cache_cpc = {r.keyword: r.cpc for r in cache.itertuples()}
        cache_comp = {r.keyword: r.competition for r in cache.itertuples()}
        for k in all_keywords:
            if k not in sv_map:
                sv_map[k] = cache_sv.get(k, 1)
            if k not in asv_map:
                asv_map[k] = cache_asv.get(k, 1)
            if k not in cpc_map:
                cpc_map[k] = cache_cpc.get(k, "")
            if k not in comp_map:
                comp_map[k] = cache_comp.get(k, "")
        missing = [k for k in all_keywords if k not in cache_sv]
        print(f"    cache hits: {len(all_keywords) - len(missing)} | new keywords @ floor: {len(missing)}")

    cal = load_calibration(wylie.REFERENCE_CALIBRATION)
    apply_rho_eta_floors_to_calibration_dict(cal)
    beta = settings.CASE2_BETA if settings.CASE2_BETA is not None else 60.0
    hp, rho_by_keyword = wylie._build_hp_for_intent(cal, wylie.INTENT_ID, beta)

    rows = wylie.estimate_and_build_rows(
        prompts, llm_results,
        hp=hp, rho_by_keyword=rho_by_keyword,
        sv_map=sv_map, asv_map=asv_map, cpc_map=cpc_map, comp_map=comp_map,
    )
    for row in rows:
        row["importance_scorer"] = ce_model
        row["extraction_method"] = "llm"

    detail = pd.DataFrame(rows)
    prompt_order = {p["prompt"]: idx for idx, p in enumerate(prompts)}
    export_cols = ["prompt", "prompt_ai_demand_median", "keyword", "importance_score", "fusion_weight"]
    export = detail[export_cols].copy()
    export["_ord"] = export["prompt"].map(prompt_order)
    export = export.sort_values(["_ord", "fusion_weight"], ascending=[True, False]).drop(columns="_ord").reset_index(drop=True)

    summary = detail.groupby("prompt", as_index=False).agg(
        prompt_ai_demand_median=("prompt_ai_demand_median", "first"),
        keyword_count=("keyword", "count"),
    )
    summary["_ord"] = summary["prompt"].map(prompt_order)
    summary = summary.sort_values("_ord").drop(columns="_ord").reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = [
        OUTPUT_DIR / f"{OUTPUT_STEM}.xlsx",
        Path("/Users/sainithinartham/Downloads") / f"{OUTPUT_STEM}.xlsx",
    ]
    for path in paths:
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            export.to_excel(w, sheet_name="llm", index=False)
            detail.to_excel(w, sheet_name="detail", index=False)
            summary.to_excel(w, sheet_name="summary", index=False)
        print(f"Saved -> {path}")

    y = summary["prompt_ai_demand_median"]
    over3 = sum(1 for c in kw_counts if c > 3)
    print(f"Rows: {len(export)} | prompts over 3 keywords: {over3}")
    print(f"Y median: mean={y.mean():.1f}, median={y.median():.1f}, min={y.min():.2f}, max={y.max():.2f}")
    print(f"At floor (~1.1): {(y <= 1.2).sum()} ({100 * (y <= 1.2).mean():.0f}%)")


if __name__ == "__main__":
    asyncio.run(main())
