#!/usr/bin/env python3
"""
Sensitivity analysis for the NER + noun-phrase chunking method (method 4 in
test_wylie_hotel_all_methods.py): re-fuse each prompt's Case2 estimate after
dropping any NER-extracted keyword whose cross-encoder importance_score falls
below a minimum threshold, for threshold in {0.1, 0.2, 0.3, 0.4, 0.5}.

Motivation: the unfiltered ner_chunked sheet shows low-importance_score
candidates (e.g. "best time" at importance_score=0.001, "lower rates" at
0.0024) carrying huge SV/ASV and dominating the prompt's Y_median even though
they are barely relevant to the prompt. This mirrors the RELEVANCE_THRESHOLD
gate the grounding method already uses (0.35) — this script sweeps that same
kind of gate across 5 threshold values for the NER method specifically, so the
effect on Y_median can be inspected sheet-by-sheet.

Data reuse (no new extraction, no new API calls): every NER candidate for
every prompt already sits in the `ner_chunked` sheet of the existing workbook
(verified: max 4 keywords/prompt, well under the max_keywords=20 cap, so no
candidate was ever truncated). This script only re-runs the Case2Estimator
fusion — which depends on *which* keywords are in the set (softmax weights
are computed over the surviving set) — over that already-computed candidate
pool, filtered at each threshold. SV/ASV values are reused verbatim from the
existing sheet's `sv` / `asv` columns.

Fallback: if a threshold drops every candidate for a prompt (0 survivors),
the single highest-importance_score candidate is kept anyway (same pattern as
the grounding method's fallback) — otherwise that prompt would have an
undefined Y_median. This is flagged per-row via `kept_via_fallback=True`.

Output: adds 5 new sheets (does not remove or modify existing sheets) to the
SAME workbook used by test_wylie_hotel_all_methods.py:
    runs/keyword_grounding_test/keyword_grounding_test.xlsx
        - ner_th_0.1, ner_th_0.2, ner_th_0.3, ner_th_0.4, ner_th_0.5
        - ner_threshold_summary   (Y_median for all 5 thresholds + the
          original unfiltered ner_chunked, side by side, per prompt)

Usage:
    PYTHONPATH=src python scripts/test_ner_threshold_filtering.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from case2_demand.calibration import (  # noqa: E402
    apply_rho_eta_floors_to_calibration_dict,
    floor_sigma_a_c,
    load_calibration,
)
from case2_demand.config import Settings  # noqa: E402
from case2_demand.estimation.bayesian_sv_asv import (  # noqa: E402
    Case2Estimator,
    Case2Hyperparameters,
)

REFERENCE_CALIBRATION = REPO_ROOT / "runs" / "20260617T170025Z" / "calibrated.json"
INTENT_ID = "hospitality_wylie_hotel_atlanta"
INTENT_NAME = "Wylie Hotel Atlanta (Tapestry Collection by Hilton)"
WORKBOOK_PATH = REPO_ROOT / "runs" / "keyword_grounding_test" / "keyword_grounding_test.xlsx"

THRESHOLDS = [0.1, 0.2, 0.3, 0.4, 0.5]


def _build_hp_for_intent(cal: dict, intent_id: str, beta: float) -> tuple[Case2Hyperparameters, dict]:
    """Mirrors cli.py's _default_hp + _hp_for_intent (same as the other test scripts)."""
    import math

    defaults = dict(
        nu_c=math.log(50_000), omega_c=3.0, b_S=0.0, sigma_S_c=0.20,
        b_A=0.0, sigma_A_c=0.20, delta_c=0.20, sigma_delta=0.50,
        rho=0.25, mu_eta=0.262364, sigma_eta=0.25,
    )
    sv_params_by_intent = cal.get("sv_params_by_intent") or {}
    asv_params_by_intent = cal.get("asv_params_by_intent") or {}
    svp = sv_params_by_intent.get(intent_id) or sv_params_by_intent.get("_global")
    avp = asv_params_by_intent.get(intent_id) or asv_params_by_intent.get("_global")

    hp = Case2Hyperparameters(
        nu_c=svp["nu_c"] if svp else defaults["nu_c"],
        omega_c=svp["omega_c"] if svp else defaults["omega_c"],
        b_S=svp["b_S"] if svp else defaults["b_S"],
        sigma_S_c=svp["sigma_S_c"] if svp else defaults["sigma_S_c"],
        b_A=avp["b_A"] if avp else defaults["b_A"],
        sigma_A_c=floor_sigma_a_c(avp["sigma_A_c"] if avp else defaults["sigma_A_c"]),
        delta_c=defaults["delta_c"],
        sigma_delta=defaults["sigma_delta"],
        beta=beta,
        rho=defaults["rho"],
        mu_eta=cal.get("mu_eta", defaults["mu_eta"]),
        sigma_eta=cal.get("sigma_eta", defaults["sigma_eta"]),
    )
    rho_by_keyword = cal.get("rho_by_keyword") or {}
    return hp, rho_by_keyword


def run_threshold(
    ner_df: pd.DataFrame,
    threshold: float,
    *,
    estimator: Case2Estimator,
    rho_by_keyword: dict,
) -> pd.DataFrame:
    rows: list[dict] = []
    for prompt_id, group in ner_df.groupby("prompt_id", sort=False):
        group = group.sort_values("importance_score", ascending=False)
        kept = group[group["importance_score"] >= threshold]
        kept_via_fallback = False
        if kept.empty:
            kept = group.iloc[[0]]
            kept_via_fallback = True

        keywords = kept["keyword"].tolist()
        similarities = kept["importance_score"].tolist()
        sv_values = kept["sv"].tolist()
        asv_values = kept["asv"].tolist()

        Y_median, Y_mean, Y_std, interval, kw_estimates, weights = estimator.estimate_demand(
            prompt=kept["prompt"].iloc[0],
            keywords=keywords,
            similarities=similarities,
            sv_values=sv_values,
            asv_values=asv_values,
            rho_by_keyword=rho_by_keyword,
        )
        linear_median = sum(ke.A_median for ke in kw_estimates)
        linear_mean = sum(ke.A_mean for ke in kw_estimates)
        importance_lookup = dict(zip(keywords, similarities))
        extra_lookup = kept.set_index("keyword")[["extraction_type", "spacy_label", "cpc", "competition"]].to_dict("index")

        for ke in kw_estimates:
            extra = extra_lookup.get(ke.keyword, {})
            rows.append({
                "intent_cluster_name": INTENT_NAME,
                "intent_cluster_id": INTENT_ID,
                "topic": kept["topic"].iloc[0],
                "prompt_id": prompt_id,
                "prompt": kept["prompt"].iloc[0],
                "importance_threshold": threshold,
                "kept_via_fallback": kept_via_fallback,
                "prompt_ai_demand_median": round(Y_median, 2),
                "prompt_ai_demand_mean": round(Y_mean, 2),
                "prompt_ai_demand_linear_median": round(linear_median, 2),
                "prompt_ai_demand_linear_mean": round(linear_mean, 2),
                "keyword": ke.keyword,
                "importance_score": round(float(importance_lookup.get(ke.keyword, 0.0)), 4),
                "fusion_weight": round(float(weights.get(ke.keyword, 0.0)), 6),
                "sv": None,  # filled below via sv_asv_lookup (kept out of this loop for simplicity)
                "asv": None,
                "keyword_ai_demand_median": round(ke.A_median, 2),
                "keyword_ai_demand_mean": round(ke.A_mean, 2),
                "keyword_ai_demand_std": round(ke.variance ** 0.5, 4) if ke.variance is not None else "",
                "keyword_interval_90_low": round(ke.interval_90[0], 2) if ke.interval_90 else "",
                "keyword_interval_90_high": round(ke.interval_90[1], 2) if ke.interval_90 else "",
                "extraction_type": extra.get("extraction_type", ""),
                "spacy_label": extra.get("spacy_label", ""),
                "cpc": extra.get("cpc", ""),
                "competition": extra.get("competition", ""),
            })
    df = pd.DataFrame(rows)
    # sv/asv straight from the source rows (kept above as None placeholders to
    # avoid a fragile inline expression; fill properly here).
    sv_asv_lookup = ner_df.set_index(["prompt_id", "keyword"])[["sv", "asv"]]
    df["sv"] = df.apply(lambda r: sv_asv_lookup.loc[(r["prompt_id"], r["keyword"]), "sv"], axis=1)
    df["asv"] = df.apply(lambda r: sv_asv_lookup.loc[(r["prompt_id"], r["keyword"]), "asv"], axis=1)
    return df


def build_threshold_summary(ner_df: pd.DataFrame, threshold_dfs: dict[float, pd.DataFrame]) -> pd.DataFrame:
    prompts = ner_df[["prompt_id", "topic", "prompt"]].drop_duplicates().reset_index(drop=True)
    baseline = ner_df.groupby("prompt_id").agg(
        ner_chunked_unfiltered_y_median=("prompt_ai_demand_median", "first"),
        ner_chunked_unfiltered_keyword_count=("keyword", "count"),
    )
    out = prompts.merge(baseline, on="prompt_id", how="left")
    for threshold, df in threshold_dfs.items():
        agg = df.groupby("prompt_id").agg(
            **{
                f"th_{threshold}_y_median": ("prompt_ai_demand_median", "first"),
                f"th_{threshold}_keyword_count": ("keyword", "count"),
                f"th_{threshold}_fallback_used": ("kept_via_fallback", "first"),
            }
        )
        out = out.merge(agg, on="prompt_id", how="left")
    return out


def main() -> None:
    if not WORKBOOK_PATH.exists():
        print(f"ERROR: workbook not found: {WORKBOOK_PATH}", file=sys.stderr)
        sys.exit(1)
    if not REFERENCE_CALIBRATION.exists():
        print(f"ERROR: reference calibration not found: {REFERENCE_CALIBRATION}", file=sys.stderr)
        sys.exit(1)

    settings = Settings()
    cal = load_calibration(REFERENCE_CALIBRATION)
    apply_rho_eta_floors_to_calibration_dict(cal)
    beta = settings.CASE2_BETA if settings.CASE2_BETA is not None else 60.0
    hp, rho_by_keyword = _build_hp_for_intent(cal, INTENT_ID, beta)
    estimator = Case2Estimator(hp)

    print(f"[load] reading existing workbook: {WORKBOOK_PATH}")
    xl = pd.ExcelFile(WORKBOOK_PATH)
    existing_sheets = {name: xl.parse(name) for name in xl.sheet_names}
    ner_df = existing_sheets["ner_chunked"]
    print(f"[load] ner_chunked: {len(ner_df)} keyword rows across {ner_df['prompt_id'].nunique()} prompts")

    threshold_dfs: dict[float, pd.DataFrame] = {}
    for threshold in THRESHOLDS:
        print(f"[threshold={threshold}] re-fusing Case2 estimates ...")
        df = run_threshold(ner_df, threshold, estimator=estimator, rho_by_keyword=rho_by_keyword)
        threshold_dfs[threshold] = df
        n_fallback = df.drop_duplicates("prompt_id")["kept_via_fallback"].sum()
        print(f"    -> mean Y_median={df.drop_duplicates('prompt_id')['prompt_ai_demand_median'].mean():.2f}, "
              f"prompts needing fallback (0 survivors)={n_fallback}")

    summary_df = build_threshold_summary(ner_df, threshold_dfs)

    with pd.ExcelWriter(WORKBOOK_PATH, engine="openpyxl") as writer:
        for name, df in existing_sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
        for threshold, df in threshold_dfs.items():
            sheet_name = f"ner_th_{threshold}"
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        summary_df.to_excel(writer, sheet_name="ner_threshold_summary", index=False)

    print(f"\nSaved threshold sweep -> {WORKBOOK_PATH}")
    print("\nMean Y_median by threshold (vs unfiltered ner_chunked):")
    print(f"  unfiltered : {ner_df.drop_duplicates('prompt_id')['prompt_ai_demand_median'].mean():.2f}")
    for threshold, df in threshold_dfs.items():
        print(f"  th={threshold}     : {df.drop_duplicates('prompt_id')['prompt_ai_demand_median'].mean():.2f}")


if __name__ == "__main__":
    main()
