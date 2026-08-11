#!/usr/bin/env python3
"""Re-estimate Wylie ngram+LLM filter volumes using cached SV/ASV."""

from __future__ import annotations

import asyncio
import ast
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
from case2_demand.keyword_extraction.extractor import score_keywords_with_importance  # noqa: E402
from case2_demand.keyword_extraction.ngram_llm_filter import _enforce_candidate_subset  # noqa: E402
from case2_demand.llm.openai_client import OpenAIClient, _filter_valid_keywords  # noqa: E402
from case2_demand.schemas import KeywordWithImportance  # noqa: E402
import test_wylie_hotel_all_methods as wylie  # noqa: E402

FILTER_XLSX = REPO_ROOT / "runs" / "wylie_ngram" / "wylie_hotel_ngram_llm_filter_volumes.xlsx"
SV_SOURCE = REPO_ROOT / "runs" / "keyword_grounding_test" / "keyword_grounding_test.xlsx"
FILTER_PROMPT = SRC_DIR / "case2_demand" / "prompts" / "keyword_filter_ngram_system.txt"
OUTPUT_STEM = "wylie_hotel_ngram_llm_filter_volumes"
MAX_KEYWORDS = 6


def _parse_list(val):
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return ast.literal_eval(val)
        except Exception:
            return []
    return []


async def main() -> None:
    settings = Settings()
    prompts = wylie.build_prompts()
    prompt_texts = [p["prompt"] for p in prompts]
    prompt_order = {p: i for i, p in enumerate(prompt_texts)}

    filter_df = pd.read_excel(FILTER_XLSX, sheet_name="filter_log")
    sv_df = pd.read_excel(SV_SOURCE, sheet_name="ngram")[["keyword", "sv", "asv", "cpc", "competition"]].drop_duplicates("keyword")
    sv_map = {r.keyword: max(float(r.sv or 0), 1) for r in sv_df.itertuples()}
    asv_map = {r.keyword: max(float(r.asv or 0), 1) for r in sv_df.itertuples()}
    cpc_map = {r.keyword: r.cpc for r in sv_df.itertuples()}
    comp_map = {r.keyword: r.competition for r in sv_df.itertuples()}

    client = None
    if settings.OPENROUTER_API_KEY:
        client = OpenAIClient(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            timeout_sec=settings.CASE2_LLM_REQUEST_TIMEOUT_SEC,
        )

    ce_model = settings.CASE2_CROSS_ENCODER_MODEL
    ngram_results = {}
    logs = []

    for p, row in zip(prompts, filter_df.itertuples(index=False)):
        prompt = p["prompt"]
        candidates = _parse_list(row.ngram_candidates)
        selected = _parse_list(row.llm_selected_raw)
        kept = _parse_list(row.llm_kept)
        used_fallback = bool(row.used_fallback)

        if candidates and not kept and client is not None:
            try:
                selected = client.filter_ngram_candidates_for_prompt(
                    model=settings.CASE2_LLM_MODEL,
                    prompt=prompt,
                    candidates=candidates,
                    system_prompt_path=FILTER_PROMPT,
                    max_keywords=MAX_KEYWORDS,
                )
                kept = _enforce_candidate_subset(selected, candidates)
                used_fallback = not kept
            except Exception as e:
                print(f"  LLM retry failed for prompt, using CE fallback: {e}", flush=True)
                kept = []
                used_fallback = True

        scored_all = score_keywords_with_importance(
            prompt, candidates, model_name=ce_model, max_keywords=len(candidates),
        ) if candidates else []
        score_by_kw = {k.keyword: k.importance_score for k in scored_all}

        if not candidates:
            kws = [KeywordWithImportance(keyword=prompt[:50].lower() or "general", importance_score=0.8)]
            used_fallback = True
        elif not kept:
            used_fallback = True
            kws = _filter_valid_keywords(scored_all, prompt, max_keywords=MAX_KEYWORDS) or [scored_all[0]]
        else:
            kept_scored = [
                KeywordWithImportance(keyword=kw, importance_score=score_by_kw.get(kw, 0.5))
                for kw in kept
            ]
            kept_scored.sort(key=lambda x: x.importance_score, reverse=True)
            kws = _filter_valid_keywords(kept_scored, prompt, max_keywords=MAX_KEYWORDS) or kept_scored[:MAX_KEYWORDS]

        ngram_results[p["prompt_id"]] = [(k.keyword, k.importance_score) for k in kws]
        logs.append({
            "prompt": prompt,
            "num_ngram_candidates": len(candidates),
            "ngram_candidates": candidates,
            "llm_kept": [k.keyword for k in kws] if not used_fallback else kept,
            "llm_dropped": [c for c in candidates if c not in {k.keyword for k in kws}],
            "used_fallback": used_fallback,
        })

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
    export = detail[export_cols].copy()
    export["_ord"] = export["prompt"].map(prompt_order)
    export = export.sort_values(["_ord", "fusion_weight"], ascending=[True, False]).drop(columns="_ord").reset_index(drop=True)

    summary = detail.groupby("prompt", as_index=False).agg(
        prompt_ai_demand_median=("prompt_ai_demand_median", "first"),
        keyword_count=("keyword", "count"),
    )
    summary["_ord"] = summary["prompt"].map(prompt_order)
    summary = summary.sort_values("_ord").drop(columns="_ord").reset_index(drop=True)

    out_dir = REPO_ROOT / "runs" / "wylie_ngram"
    paths = [
        out_dir / f"{OUTPUT_STEM}.xlsx",
        Path("/Users/sainithinartham/Downloads") / f"{OUTPUT_STEM}.xlsx",
    ]
    for path in paths:
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            export.to_excel(w, sheet_name="ngram_llm_filter", index=False)
            detail.to_excel(w, sheet_name="detail", index=False)
            summary.to_excel(w, sheet_name="summary", index=False)
            pd.DataFrame(logs).to_excel(w, sheet_name="filter_log", index=False)
        print(f"Saved -> {path}")

    y = summary["prompt_ai_demand_median"]
    fb = sum(1 for log in logs if log["used_fallback"])
    print(f"Rows: {len(export)} | fallbacks: {fb}")
    print(f"Y median: mean={y.mean():.1f}, median={y.median():.1f}, min={y.min():.2f}, max={y.max():.2f}")
    print(f"At floor (~1.1): {(y <= 1.2).sum()} ({100 * (y <= 1.2).mean():.0f}%)")


if __name__ == "__main__":
    asyncio.run(main())
