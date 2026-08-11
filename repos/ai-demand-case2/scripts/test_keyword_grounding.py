#!/usr/bin/env python3
"""
Standalone TEST for one candidate fix: ground ngram-extracted keyword candidates
in DataForSEO's real search-query suggestion database (`keyword_suggestions/live`)
before computing prompt volume — instead of sending raw ngram fragments straight
to SV/ASV lookup.

This script does NOT modify the production pipeline. It only *imports* the
existing, unmodified pipeline modules:
    - keyword_extraction.extractor  (ngram candidate generation + cross-encoder scoring)
    - keyword_volume.dataforseo     (SV + ASV clients)
    - estimation.bayesian_sv_asv    (Case2Estimator fusion — untouched)

The only NEW code is the grounding step itself (`ground_seed_keyword`), which
calls a DataForSEO endpoint the pipeline doesn't currently use
(`dataforseo_labs/google/keyword_suggestions/live`).

Baseline numbers are NOT recomputed — they are read verbatim from an existing
production run (runs/20260617T170025Z/prompt_keyword_volumes.csv) for the same
prompts, so "current pipeline" truly stays untouched for this comparison.

Output: runs/keyword_grounding_test/keyword_grounding_test.xlsx
    - summary          one row per prompt: baseline vs grounded Y_median
    - baseline_ngram    baseline rows (verbatim from the reference run's CSV)
    - grounded          new grounded-method rows, same column shape + seed_ngram
    - grounding_log     per-seed grounding detail (audit trail)

Usage:
    PYTHONPATH=src python scripts/test_keyword_grounding.py
"""

from __future__ import annotations

import asyncio
import base64
import re
import sys
from pathlib import Path

import httpx
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
from case2_demand.keyword_extraction.extractor import (  # noqa: E402
    STOPWORDS as NGRAM_STOPWORDS,
    extract_keywords_with_importance,
    score_keywords_with_importance,
)
from case2_demand.keyword_volume.dataforseo import (  # noqa: E402
    DataForSEOASVClient,
    DataForSEOSVClient,
)

# ---------------------------------------------------------------------------
# Config for this test only
# ---------------------------------------------------------------------------

REFERENCE_RUN_DIR = REPO_ROOT / "runs" / "20260617T170025Z"
REFERENCE_CSV = REFERENCE_RUN_DIR / "prompt_keyword_volumes.csv"
REFERENCE_CALIBRATION = REFERENCE_RUN_DIR / "calibrated.json"
INTENT_ID = "ai_application_security"
INTENT_NAME = "AI Application Security"
OUTPUT_DIR = REPO_ROOT / "runs" / "keyword_grounding_test"

LOCATION_CODE = 2840
LANGUAGE_CODE = "en"

# New-step tunables (do not exist in the production pipeline)
TOP_N_SEEDS = 4              # how many top ngram candidates to ground per prompt
SUGGESTIONS_PER_SEED = 20    # DataForSEO keyword_suggestions `limit` per seed
RELEVANCE_THRESHOLD = 0.35   # min cross-encoder score (prompt, suggestion) to keep
MAX_GROUNDED_KEYWORDS = 8    # cap fused keywords per prompt (parity with ngram output size)

# Unique test prompts (user pasted duplicates; keyword/volume estimation is
# per distinct prompt text, so duplicates are de-duplicated here). Reused the
# prompt_ids already assigned to these exact prompts in the reference run, so
# baseline rows line up 1:1 with the grounded rows.
TEST_PROMPTS: list[tuple[str, str]] = [
    ("prm_be14abe03efe", "Any AI security solution that detects malicious AI agents effectively?"),
    ("prm_45813564eea6", "Are there AI security platforms that focus on workload security for cloud AI?"),
    ("prm_dc5bfc0f6f20", "Best AI security platform for enterprise cloud teams?"),
    ("prm_42dac7ef71ba", "Best AI security solution for model guardrails?"),
    ("prm_daeff2caf2f1", "Can Wiz detect malicious activity from AI agents?"),
    ("prm_bcc9143b2914", "Can Wiz help prevent data exposure in AI applications?"),
]


def _auth_header(login: str, password: str) -> str:
    creds = f"{login}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(creds).decode("utf-8")


_WORD_RE = re.compile(r"[a-z0-9]+")


def _content_tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in NGRAM_STOPWORDS and len(w) > 1}


def _stem_match(word: str, tokens: set[str]) -> bool:
    if word in tokens:
        return True
    for t in tokens:
        if len(word) >= 4 and len(t) >= 4 and (t.startswith(word) or word.startswith(t)):
            return True
    return False


def is_grounded_in_prompt(keyword: str, prompt: str) -> bool:
    """Every content word in `keyword` must trace back to the prompt itself.

    The cross-encoder relevance score alone catches phrases that are
    *topically* similar but not *entity*-consistent — DataForSEO's
    keyword_suggestions for a generic seed like "enterprise cloud platform"
    happily returns "hitachi enterprise cloud platform" or
    "tcs enterprise cloud platform", which score well on surface similarity
    but introduce a vendor the prompt never mentioned. This gate rejects any
    grounded candidate that brings in a noun/entity absent from the prompt,
    mirroring the same "grounded only in the prompt" rule the LLM keyword
    extraction system prompt already enforces.
    """
    prompt_tokens = _content_tokens(prompt)
    kw_tokens = [w for w in _WORD_RE.findall(keyword.lower()) if w not in NGRAM_STOPWORDS and len(w) > 1]
    if not kw_tokens:
        return False
    return all(_stem_match(w, prompt_tokens) for w in kw_tokens)


def _build_hp_for_intent(cal: dict, intent_id: str, beta: float) -> tuple[Case2Hyperparameters, dict]:
    """Mirror cli.py's _default_hp + _hp_for_intent, without importing cli.py."""
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


async def ground_seed_keyword(
    client: httpx.AsyncClient,
    auth_header: str,
    base_url: str,
    seed: str,
    *,
    limit: int = SUGGESTIONS_PER_SEED,
) -> list[dict]:
    """NEW STEP: real queries containing `seed`, via DataForSEO Labs keyword_suggestions."""
    url = f"{base_url}/dataforseo_labs/google/keyword_suggestions/live"
    body = [{
        "keyword": seed,
        "location_code": LOCATION_CODE,
        "language_code": LANGUAGE_CODE,
        "limit": limit,
        "exact_match": False,
        "include_seed_keyword": False,
    }]
    try:
        resp = await client.post(
            url,
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            json=body,
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    [warn] keyword_suggestions failed for seed {seed!r}: {e}")
        return []

    out: list[dict] = []
    for task in data.get("tasks") or []:
        if task.get("status_code") != 20000:
            print(f"    [warn] keyword_suggestions status for {seed!r}: {task.get('status_message')}")
            continue
        for result in task.get("result") or []:
            for item in result.get("items") or []:
                kw = (item.get("keyword") or "").strip()
                if not kw:
                    continue
                info = item.get("keyword_info") or {}
                out.append({
                    "keyword": kw,
                    "seed_ngram": seed,
                    "suggested_sv": info.get("search_volume"),
                    "cpc": info.get("cpc"),
                    "competition": info.get("competition"),
                })
    return out


async def compute_grounded_estimate(
    *,
    prompt_id: str,
    prompt: str,
    http_client: httpx.AsyncClient,
    auth_header: str,
    base_url: str,
    sv_client: DataForSEOSVClient,
    asv_client: DataForSEOASVClient,
    hp: Case2Hyperparameters,
    rho_by_keyword: dict[str, float],
    cross_encoder_model: str,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Ground ngram candidates in real queries, then run the UNCHANGED Case2 fusion."""

    # Step 1 (unchanged): ngram candidate extraction — same function/params as prod pipeline.
    candidates = extract_keywords_with_importance(prompt, max_keywords=20, model_name=cross_encoder_model)
    seeds = [c.keyword for c in sorted(candidates, key=lambda c: c.importance_score, reverse=True)[:TOP_N_SEEDS]]

    # Step 2 (NEW): ground each ngram candidate in DataForSEO's real query suggestions.
    grounding_log: list[dict] = []
    pooled: dict[str, dict] = {}
    for seed in seeds:
        suggestions = await ground_seed_keyword(http_client, auth_header, base_url, seed)
        seed_importance = next((c.importance_score for c in candidates if c.keyword == seed), None)
        grounding_log.append({
            "prompt_id": prompt_id,
            "prompt": prompt,
            "seed_ngram": seed,
            "seed_importance": seed_importance,
            "num_suggestions_returned": len(suggestions),
        })
        for s in suggestions:
            pooled.setdefault(s["keyword"].lower(), s)

    # Step 3 (NEW): hard gate — reject any pooled suggestion that introduces a
    # word/entity absent from the prompt (this is what was letting "hitachi",
    # "tcs", "gartner", "google", "wiz lighting" leak through before).
    grounded_pool: dict[str, dict] = {}
    rejected_rows: list[dict] = []
    for key, s in pooled.items():
        if is_grounded_in_prompt(s["keyword"], prompt):
            grounded_pool[key] = s
        else:
            rejected_rows.append({
                "prompt_id": prompt_id,
                "prompt": prompt,
                "rejected_keyword": s["keyword"],
                "seed_ngram": s["seed_ngram"],
                "reason": "introduces word(s) not present in the prompt",
            })

    # Step 4 (unchanged): score the surviving, prompt-grounded queries for
    # relevance, reusing the same cross-encoder the pipeline already uses.
    grounded_texts = [v["keyword"] for v in grounded_pool.values()]
    scored = score_keywords_with_importance(prompt, grounded_texts, model_name=cross_encoder_model) if grounded_texts else []
    scored_sorted = sorted(scored, key=lambda s: s.importance_score, reverse=True)

    kept = [s for s in scored_sorted if s.importance_score >= RELEVANCE_THRESHOLD][:MAX_GROUNDED_KEYWORDS]
    if not kept and scored_sorted:
        # Nothing cleared the relevance bar, but at least one grounded (on-topic)
        # candidate exists — keep the best one instead of dropping to zero.
        kept = scored_sorted[:1]

    seed_for_keyword: dict[str, str] = {k.keyword: grounded_pool.get(k.keyword, {}).get("seed_ngram", "") for k in kept}

    if not kept:
        # No real-query suggestion survived grounding for ANY seed of this
        # prompt (rare/very narrow seeds return nothing groundable). Fall back
        # to the prompt's own top ngram candidate(s) — never to an ungrounded
        # suggestion — since ngram candidates are built only from prompt words
        # and are grounded by construction.
        fallback = sorted(candidates, key=lambda c: c.importance_score, reverse=True)[:2]
        kept = fallback
        for c in fallback:
            seed_for_keyword[c.keyword] = "(fallback: ngram candidate, no grounded match)"

    grounded_keywords = [k.keyword for k in kept]
    similarities = [k.importance_score for k in kept]

    for entry in grounding_log:
        entry["num_pooled_unique"] = len(pooled)
        entry["num_rejected_off_topic"] = len(rejected_rows)
        entry["num_grounded_on_topic"] = len(grounded_pool)
        entry["num_kept_after_relevance_filter"] = len(kept)

    # Step 4 (unchanged): SV + ASV lookup via the same DataForSEO clients the pipeline uses.
    sv_results = await sv_client.get_volume(grounded_keywords, location_code=LOCATION_CODE, language_code=LANGUAGE_CODE)
    asv_results = await asv_client.get_volume(grounded_keywords, location_code=LOCATION_CODE, language_code=LANGUAGE_CODE)
    sv_map = {r.keyword: (r.search_volume if r.search_volume is not None else 1) for r in sv_results}
    asv_map = {r.keyword: (r.search_volume if r.search_volume is not None else 1) for r in asv_results}
    cpc_map = {r.keyword: r.cpc for r in sv_results}
    comp_map = {r.keyword: r.competition for r in sv_results}
    sv_values = [sv_map.get(kw, 1) for kw in grounded_keywords]
    asv_values = [asv_map.get(kw, 1) for kw in grounded_keywords]

    # Step 5 (unchanged): the exact same Case2 SV+ASV Bayesian fusion the pipeline runs today.
    estimator = Case2Estimator(hp)
    Y_median, Y_mean, Y_std, interval, kw_estimates, weights = estimator.estimate_demand(
        prompt=prompt,
        keywords=grounded_keywords,
        similarities=similarities,
        sv_values=sv_values,
        asv_values=asv_values,
        rho_by_keyword=rho_by_keyword,
    )

    linear_median = sum(ke.A_median for ke in kw_estimates)
    linear_mean = sum(ke.A_mean for ke in kw_estimates)

    rows: list[dict] = []
    for ke in kw_estimates:
        rows.append({
            "intent_cluster_name": INTENT_NAME,
            "intent_cluster_id": INTENT_ID,
            "prompt_id": prompt_id,
            "prompt": prompt,
            "prompt_ai_demand_median": round(Y_median, 2),
            "prompt_ai_demand_mean": round(Y_mean, 2),
            "prompt_ai_demand_linear_median": round(linear_median, 2),
            "prompt_ai_demand_linear_mean": round(linear_mean, 2),
            "keyword": ke.keyword,
            "seed_ngram": seed_for_keyword.get(ke.keyword, ""),
            "importance_score": 0.0,  # filled in below from the relevance scorer
            "fusion_weight": round(float(weights.get(ke.keyword, 0.0)), 6),
            "sv": round(float(sv_map.get(ke.keyword, 0.0)), 2),
            "asv": round(float(asv_map.get(ke.keyword, 0.0)), 2),
            "keyword_ai_demand_median": round(ke.A_median, 2),
            "keyword_ai_demand_mean": round(ke.A_mean, 2),
            "keyword_ai_demand_std": round(ke.variance ** 0.5, 4) if ke.variance is not None else "",
            "keyword_interval_90_low": round(ke.interval_90[0], 2) if ke.interval_90 else "",
            "keyword_interval_90_high": round(ke.interval_90[1], 2) if ke.interval_90 else "",
            "cpc": cpc_map.get(ke.keyword) if cpc_map.get(ke.keyword) is not None else "",
            "competition": comp_map.get(ke.keyword) if comp_map.get(ke.keyword) is not None else "",
        })

    # importance_score should be the cross-encoder relevance score, not derived from weight.
    importance_lookup = {k.keyword: k.importance_score for k in kept}
    for r in rows:
        r["importance_score"] = round(float(importance_lookup.get(r["keyword"], 0.0)), 4)

    return rows, grounding_log, rejected_rows


def load_baseline_rows(prompt_ids: set[str]) -> pd.DataFrame:
    if not REFERENCE_CSV.exists():
        raise FileNotFoundError(f"Reference CSV not found: {REFERENCE_CSV}")
    df = pd.read_csv(REFERENCE_CSV)
    return df[df["prompt_id"].isin(prompt_ids)].copy()


def build_summary(baseline_df: pd.DataFrame, grounded_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for prompt_id, prompt in TEST_PROMPTS:
        b = baseline_df[baseline_df["prompt_id"] == prompt_id]
        g = grounded_df[grounded_df["prompt_id"] == prompt_id]

        b_y = float(b["prompt_ai_demand_median"].iloc[0]) if len(b) else None
        g_y = float(g["prompt_ai_demand_median"].iloc[0]) if len(g) else None

        b_top = b_top_share = None
        if len(b):
            b_contrib = b["fusion_weight"] * b["keyword_ai_demand_median"]
            top_idx = b_contrib.idxmax()
            b_top = b.loc[top_idx, "keyword"]
            b_top_share = round(100 * b_contrib[top_idx] / b_y, 1) if b_y else None

        g_top = g_top_share = None
        if len(g):
            g_contrib = g["fusion_weight"] * g["keyword_ai_demand_median"]
            top_idx = g_contrib.idxmax()
            g_top = g.loc[top_idx, "keyword"]
            g_top_share = round(100 * g_contrib[top_idx] / g_y, 1) if g_y else None

        rows.append({
            "prompt_id": prompt_id,
            "prompt": prompt,
            "baseline_y_median": b_y,
            "baseline_keyword_count": len(b),
            "baseline_top_keyword": b_top,
            "baseline_top_keyword_share_pct": b_top_share,
            "grounded_y_median": g_y,
            "grounded_keyword_count": len(g),
            "grounded_top_keyword": g_top,
            "grounded_top_keyword_share_pct": g_top_share,
            "ratio_grounded_over_baseline": round(g_y / b_y, 3) if (b_y and g_y is not None) else None,
        })
    return pd.DataFrame(rows)


async def main() -> None:
    settings = Settings()
    login = settings.DATAFORSEO_LOGIN or ""
    password = settings.DATAFORSEO_PASSWORD or ""
    base_url = settings.DATAFORSEO_BASE_URL or "https://api.dataforseo.com/v3"
    if not login or not password:
        print("ERROR: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD not set (check .env)", file=sys.stderr)
        sys.exit(1)

    if not REFERENCE_CALIBRATION.exists():
        print(f"ERROR: reference calibration not found: {REFERENCE_CALIBRATION}", file=sys.stderr)
        sys.exit(1)

    cal = load_calibration(REFERENCE_CALIBRATION)
    apply_rho_eta_floors_to_calibration_dict(cal)
    beta = settings.CASE2_BETA if settings.CASE2_BETA is not None else 60.0
    hp, rho_by_keyword = _build_hp_for_intent(cal, INTENT_ID, beta)
    cross_encoder_model = settings.CASE2_CROSS_ENCODER_MODEL

    sv_client = DataForSEOSVClient(
        login=login, password=password, base_url=base_url, sv_source=settings.CASE2_SV_SOURCE,
    )
    asv_client = DataForSEOASVClient(login=login, password=password, base_url=base_url)
    auth_header = _auth_header(login, password)

    all_grounded_rows: list[dict] = []
    all_grounding_log: list[dict] = []
    all_rejected_rows: list[dict] = []

    async with httpx.AsyncClient() as http_client:
        for prompt_id, prompt in TEST_PROMPTS:
            print(f"[grounding] {prompt_id}: {prompt}")
            rows, log, rejected = await compute_grounded_estimate(
                prompt_id=prompt_id,
                prompt=prompt,
                http_client=http_client,
                auth_header=auth_header,
                base_url=base_url,
                sv_client=sv_client,
                asv_client=asv_client,
                hp=hp,
                rho_by_keyword=rho_by_keyword,
                cross_encoder_model=cross_encoder_model,
            )
            all_grounded_rows.extend(rows)
            all_grounding_log.extend(log)
            all_rejected_rows.extend(rejected)
            y_median = rows[0]["prompt_ai_demand_median"] if rows else None
            print(f"    -> grounded Y_median = {y_median}, keywords kept = {len(rows)}, off-topic rejected = {len(rejected)}")

    grounded_df = pd.DataFrame(all_grounded_rows)
    grounding_log_df = pd.DataFrame(all_grounding_log)
    rejected_df = pd.DataFrame(all_rejected_rows)
    baseline_df = load_baseline_rows({pid for pid, _ in TEST_PROMPTS})
    summary_df = build_summary(baseline_df, grounded_df)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "keyword_grounding_test.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        baseline_df.to_excel(writer, sheet_name="baseline_ngram", index=False)
        grounded_df.to_excel(writer, sheet_name="grounded", index=False)
        rejected_df.to_excel(writer, sheet_name="rejected_off_topic", index=False)
        grounding_log_df.to_excel(writer, sheet_name="grounding_log", index=False)

    print(f"\nSaved comparison workbook -> {out_path}")
    print("\nSummary:")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    asyncio.run(main())
