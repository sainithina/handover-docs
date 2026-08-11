#!/usr/bin/env python3
"""
Standalone TEST for a second candidate fix: derive keywords directly from the
prompt's grammar via spaCy noun-phrase chunking + verb-object phrases + named
entities — instead of ngram fragments, LLM free text, or DataForSEO grounding.

This is a SEPARATE test from scripts/test_keyword_grounding.py. It does NOT
modify that script, and does NOT modify the production pipeline. It only
*imports* the existing, unmodified pipeline modules:
    - keyword_extraction.extractor          (cross-encoder importance scoring)
    - keyword_extraction.keyword_validation (denylist, used only as a sanity
      check here — noun-phrase chunking should rarely trigger it, since
      scaffolding words like "if my" / "is the" / "difference between" are
      not grammatical noun phrases in the first place)
    - keyword_volume.dataforseo              (SV + ASV clients)
    - estimation.bayesian_sv_asv             (Case2Estimator fusion — untouched)

The only NEW code is the extraction step itself (`extract_ner_noun_chunk_candidates`),
which uses spaCy's dependency parser instead of ngrams/LLM/grounding.

Baseline numbers are NOT recomputed — read verbatim from the same reference
production run used by the grounding test (runs/20260617T170025Z), for the
same prompts, so all three methods (baseline ngram, DataForSEO grounding,
NER/noun-chunking) are directly comparable.

Output: runs/keyword_ner_chunking_test/keyword_ner_chunking_test.xlsx
    - summary            one row per prompt: baseline vs NER-chunked Y_median
    - baseline_ngram      baseline rows (verbatim from the reference run's CSV)
    - ner_chunked         new method rows, same column shape + extraction_type
    - extraction_log      raw candidates found per prompt before dedupe/scoring (audit trail)

Usage:
    PYTHONPATH=src python scripts/test_keyword_ner_chunking.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

import spacy  # noqa: E402

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
    score_keywords_with_importance,
)
from case2_demand.keyword_extraction.keyword_validation import is_generic_phrase  # noqa: E402
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
OUTPUT_DIR = REPO_ROOT / "runs" / "keyword_ner_chunking_test"

LOCATION_CODE = 2840
LANGUAGE_CODE = "en"
SPACY_MODEL = "en_core_web_sm"

MAX_KEYWORDS = 8  # cap fused keywords per prompt (parity with the other two methods)

# Same de-duplicated test prompts / prompt_ids as the grounding test, so all
# three methods (baseline, grounding, NER-chunking) line up on the same rows.
TEST_PROMPTS: list[tuple[str, str]] = [
    ("prm_be14abe03efe", "Any AI security solution that detects malicious AI agents effectively?"),
    ("prm_45813564eea6", "Are there AI security platforms that focus on workload security for cloud AI?"),
    ("prm_dc5bfc0f6f20", "Best AI security platform for enterprise cloud teams?"),
    ("prm_42dac7ef71ba", "Best AI security solution for model guardrails?"),
    ("prm_daeff2caf2f1", "Can Wiz detect malicious activity from AI agents?"),
    ("prm_bcc9143b2914", "Can Wiz help prevent data exposure in AI applications?"),
]

_LEADING_STRIP = {
    "a", "an", "the", "any", "some", "such", "this", "that", "these", "those",
    "other", "another", "each", "every", "no",
}
_NON_ENTITY_LABELS = {"CARDINAL", "ORDINAL", "DATE", "TIME", "PERCENT", "MONEY", "QUANTITY"}
_OBJECT_DEPS = {"dobj", "pobj", "attr", "acomp", "oprd"}

_NLP = None


def _get_nlp():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load(SPACY_MODEL)
    return _NLP


def _clean_chunk_text(text: str) -> str:
    words = [w for w in text.strip().split() if w]
    while words and words[0].lower().strip(".,!?") in _LEADING_STRIP:
        words = words[1:]
    cleaned = " ".join(words).strip().lower()
    cleaned = cleaned.strip(".,!?\"'")
    return cleaned


def _is_redundant(a: str, b: str) -> bool:
    """True if two keyword phrases overlap too much to keep both (keep the longer/more specific one)."""
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    wa, wb = set(a.split()), set(b.split())
    if not wa or not wb:
        return False
    if wa <= wb or wb <= wa:
        return True
    inter = len(wa & wb)
    union = len(wa | wb)
    return union > 0 and inter / union >= 0.75


def extract_ner_noun_chunk_candidates(prompt: str) -> list[dict]:
    """NEW extraction method: derive keywords from the prompt's own grammar
    (noun phrases, verb-object phrases, named entities) instead of ngram
    fragments, LLM-generated text, or a DataForSEO-grounded search query.

    Because every candidate is a syntactic constituent of the prompt itself,
    connector/question scaffolding ("if my", "is the", "difference between")
    structurally cannot appear — those are not noun phrases or verb objects,
    so there is no separate "generic phrase" gate needed the way the
    grounding method required one.
    """
    nlp = _get_nlp()
    doc = nlp(prompt)
    raw: list[dict] = []

    # Noun phrases: the core entities/concepts the prompt is actually about.
    for nc in doc.noun_chunks:
        cleaned = _clean_chunk_text(nc.text)
        if cleaned and len(cleaned.split()) >= 1:
            raw.append({"keyword": cleaned, "extraction_type": "noun_chunk", "spacy_label": ""})

    # Verb + object phrases: captures action-intent (e.g. "detect malicious
    # activity", "prevent data exposure") without keeping a bare verb or a
    # bare pronoun subject.
    for tok in doc:
        if tok.pos_ != "VERB":
            continue
        for child in tok.children:
            if child.dep_ not in _OBJECT_DEPS:
                continue
            span_tokens = sorted(child.subtree, key=lambda t: t.i)
            phrase = " ".join(t.text for t in span_tokens)
            cleaned = _clean_chunk_text(f"{tok.lemma_} {phrase}")
            if cleaned:
                raw.append({"keyword": cleaned, "extraction_type": "verb_object", "spacy_label": ""})

    # Named entities (brand/product names spaCy's small model does catch).
    for ent in doc.ents:
        if ent.label_ in _NON_ENTITY_LABELS:
            continue
        cleaned = _clean_chunk_text(ent.text)
        if cleaned:
            raw.append({"keyword": cleaned, "extraction_type": "entity", "spacy_label": ent.label_})

    return raw


def _dedupe_candidates(raw: list[dict]) -> list[dict]:
    """Keep the longer/more specific phrase when two candidates overlap heavily."""
    ordered = sorted(raw, key=lambda r: len(r["keyword"]), reverse=True)
    kept: list[dict] = []
    seen_text: set[str] = set()
    for cand in ordered:
        text = cand["keyword"]
        if text in seen_text:
            continue
        if any(_is_redundant(text, k["keyword"]) for k in kept):
            continue
        seen_text.add(text)
        kept.append(cand)
    return kept


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


async def compute_ner_chunked_estimate(
    *,
    prompt_id: str,
    prompt: str,
    sv_client: DataForSEOSVClient,
    asv_client: DataForSEOASVClient,
    hp: Case2Hyperparameters,
    rho_by_keyword: dict[str, float],
    cross_encoder_model: str,
) -> tuple[list[dict], list[dict]]:
    """Extract keywords via spaCy noun-chunking, then run the UNCHANGED Case2 fusion."""

    # Step 1 (NEW): grammar-based candidate extraction.
    raw_candidates = extract_ner_noun_chunk_candidates(prompt)

    extraction_log = [
        {
            "prompt_id": prompt_id,
            "prompt": prompt,
            "keyword": c["keyword"],
            "extraction_type": c["extraction_type"],
            "spacy_label": c["spacy_label"],
        }
        for c in raw_candidates
    ]

    # Step 2 (NEW): dedupe overlapping phrases (e.g. "ai security solution" vs
    # "security solution" -> keep the longer one), then defensively run the
    # existing denylist (should rarely trigger anything here).
    deduped = _dedupe_candidates(raw_candidates)
    denylist_hits = [c for c in deduped if is_generic_phrase(c["keyword"])]
    filtered = [c for c in deduped if not is_generic_phrase(c["keyword"])]

    for entry in extraction_log:
        entry["num_raw_candidates"] = len(raw_candidates)
        entry["num_after_dedupe"] = len(deduped)
        entry["num_denylist_hits"] = len(denylist_hits)

    if not filtered:
        # Extremely short/unparseable prompt with no noun phrases at all —
        # fall back to the whole prompt text, same fallback shape used
        # elsewhere in the pipeline for empty candidate lists.
        filtered = [{"keyword": prompt[:50].strip().lower(), "extraction_type": "fallback_prompt", "spacy_label": ""}]

    # Step 3 (unchanged): score candidates for importance with the SAME
    # cross-encoder the pipeline already uses for ngram importance.
    candidate_texts = [c["keyword"] for c in filtered]
    scored = score_keywords_with_importance(prompt, candidate_texts, model_name=cross_encoder_model, max_keywords=MAX_KEYWORDS)
    type_lookup = {c["keyword"]: c["extraction_type"] for c in filtered}
    label_lookup = {c["keyword"]: c["spacy_label"] for c in filtered}

    if not scored:
        scored = [type("K", (), {"keyword": candidate_texts[0], "importance_score": 0.5})()]

    keywords = [s.keyword for s in scored]
    similarities = [s.importance_score for s in scored]

    # Step 4 (unchanged): SV + ASV lookup via the same DataForSEO clients the pipeline uses.
    sv_results = await sv_client.get_volume(keywords, location_code=LOCATION_CODE, language_code=LANGUAGE_CODE)
    asv_results = await asv_client.get_volume(keywords, location_code=LOCATION_CODE, language_code=LANGUAGE_CODE)
    sv_map = {r.keyword: (r.search_volume if r.search_volume is not None else 1) for r in sv_results}
    asv_map = {r.keyword: (r.search_volume if r.search_volume is not None else 1) for r in asv_results}
    cpc_map = {r.keyword: r.cpc for r in sv_results}
    comp_map = {r.keyword: r.competition for r in sv_results}
    sv_values = [sv_map.get(kw, 1) for kw in keywords]
    asv_values = [asv_map.get(kw, 1) for kw in keywords]

    # Step 5 (unchanged): the exact same Case2 SV+ASV Bayesian fusion the pipeline runs today.
    estimator = Case2Estimator(hp)
    Y_median, Y_mean, Y_std, interval, kw_estimates, weights = estimator.estimate_demand(
        prompt=prompt,
        keywords=keywords,
        similarities=similarities,
        sv_values=sv_values,
        asv_values=asv_values,
        rho_by_keyword=rho_by_keyword,
    )

    linear_median = sum(ke.A_median for ke in kw_estimates)
    linear_mean = sum(ke.A_mean for ke in kw_estimates)

    rows: list[dict] = []
    importance_lookup = {s.keyword: s.importance_score for s in scored}
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
            "extraction_type": type_lookup.get(ke.keyword, ""),
            "spacy_label": label_lookup.get(ke.keyword, ""),
            "importance_score": round(float(importance_lookup.get(ke.keyword, 0.0)), 4),
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

    return rows, extraction_log


def load_baseline_rows(prompt_ids: set[str]) -> pd.DataFrame:
    if not REFERENCE_CSV.exists():
        raise FileNotFoundError(f"Reference CSV not found: {REFERENCE_CSV}")
    df = pd.read_csv(REFERENCE_CSV)
    return df[df["prompt_id"].isin(prompt_ids)].copy()


def build_summary(baseline_df: pd.DataFrame, ner_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for prompt_id, prompt in TEST_PROMPTS:
        b = baseline_df[baseline_df["prompt_id"] == prompt_id]
        n = ner_df[ner_df["prompt_id"] == prompt_id]

        b_y = float(b["prompt_ai_demand_median"].iloc[0]) if len(b) else None
        n_y = float(n["prompt_ai_demand_median"].iloc[0]) if len(n) else None

        b_top = b_top_share = None
        if len(b):
            b_contrib = b["fusion_weight"] * b["keyword_ai_demand_median"]
            top_idx = b_contrib.idxmax()
            b_top = b.loc[top_idx, "keyword"]
            b_top_share = round(100 * b_contrib[top_idx] / b_y, 1) if b_y else None

        n_top = n_top_share = None
        if len(n):
            n_contrib = n["fusion_weight"] * n["keyword_ai_demand_median"]
            top_idx = n_contrib.idxmax()
            n_top = n.loc[top_idx, "keyword"]
            n_top_share = round(100 * n_contrib[top_idx] / n_y, 1) if n_y else None

        rows.append({
            "prompt_id": prompt_id,
            "prompt": prompt,
            "baseline_y_median": b_y,
            "baseline_keyword_count": len(b),
            "baseline_top_keyword": b_top,
            "baseline_top_keyword_share_pct": b_top_share,
            "ner_chunked_y_median": n_y,
            "ner_chunked_keyword_count": len(n),
            "ner_chunked_top_keyword": n_top,
            "ner_chunked_top_keyword_share_pct": n_top_share,
            "ratio_ner_over_baseline": round(n_y / b_y, 3) if (b_y and n_y is not None) else None,
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

    print(f"[setup] loading spaCy model {SPACY_MODEL!r} ...")
    _get_nlp()  # fail fast if the model isn't installed

    cal = load_calibration(REFERENCE_CALIBRATION)
    apply_rho_eta_floors_to_calibration_dict(cal)
    beta = settings.CASE2_BETA if settings.CASE2_BETA is not None else 60.0
    hp, rho_by_keyword = _build_hp_for_intent(cal, INTENT_ID, beta)
    cross_encoder_model = settings.CASE2_CROSS_ENCODER_MODEL

    sv_client = DataForSEOSVClient(
        login=login, password=password, base_url=base_url, sv_source=settings.CASE2_SV_SOURCE,
    )
    asv_client = DataForSEOASVClient(login=login, password=password, base_url=base_url)

    all_ner_rows: list[dict] = []
    all_extraction_log: list[dict] = []

    for prompt_id, prompt in TEST_PROMPTS:
        print(f"[ner-chunking] {prompt_id}: {prompt}")
        rows, log = await compute_ner_chunked_estimate(
            prompt_id=prompt_id,
            prompt=prompt,
            sv_client=sv_client,
            asv_client=asv_client,
            hp=hp,
            rho_by_keyword=rho_by_keyword,
            cross_encoder_model=cross_encoder_model,
        )
        all_ner_rows.extend(rows)
        all_extraction_log.extend(log)
        y_median = rows[0]["prompt_ai_demand_median"] if rows else None
        print(f"    -> NER-chunked Y_median = {y_median}, keywords kept = {len(rows)}")

    ner_df = pd.DataFrame(all_ner_rows)
    extraction_log_df = pd.DataFrame(all_extraction_log)
    baseline_df = load_baseline_rows({pid for pid, _ in TEST_PROMPTS})
    summary_df = build_summary(baseline_df, ner_df)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "keyword_ner_chunking_test.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        baseline_df.to_excel(writer, sheet_name="baseline_ngram", index=False)
        ner_df.to_excel(writer, sheet_name="ner_chunked", index=False)
        extraction_log_df.to_excel(writer, sheet_name="extraction_log", index=False)

    print(f"\nSaved comparison workbook -> {out_path}")
    print("\nSummary:")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    asyncio.run(main())
