#!/usr/bin/env python3
"""
Four-way keyword-extraction comparison for a brand-new brand/domain: The Wylie
Hotel Atlanta, Tapestry Collection by Hilton (551 Ponce De Leon Ave NE,
Atlanta, GA 30308). Unlike test_keyword_grounding.py / test_keyword_ner_chunking.py
(which reuse an existing reference run for the baseline), this script computes
ALL FOUR methods fresh, for 100 new synthetic prompts across 10 topics:

    1. ngram        (production default fallback — extractor.extract_keywords_with_importance)
    2. llm          (production default — extractor.extract_keywords_with_importance_llm_batch)
    3. grounded     (experimental — ngram seeds grounded in DataForSEO keyword_suggestions)
    4. ner_chunked  (experimental — spaCy noun-chunk / verb-object / entity extraction)

It only *imports* existing, unmodified pipeline modules (extractor, keyword_volume,
estimation) — no production code is changed. The grounding + NER extraction helpers
are copied verbatim from test_keyword_grounding.py / test_keyword_ner_chunking.py
(those scripts are standalone entry points, not importable modules).

All four methods share the same Case2Estimator hyperparameters (there is no
calibration entry for this brand-new domain, so the shared defaults + the
_global-less fallback already built into `_build_hp_for_intent` apply equally
to all four methods — the comparison is about the *keyword extraction step*,
not about domain-specific calibration).

SV/ASV lookups are pooled: every keyword produced by any of the 4 methods for
any of the 100 prompts is deduped into one list, then fetched with a single
SV call + a single ASV call (the DataForSEO clients already batch internally),
instead of one call per prompt per method.

Output (overwrites the existing grounding-only workbook, now with all 4 methods):
    runs/keyword_grounding_test/keyword_grounding_test.xlsx
        - summary          one row per prompt: Y_median for all 4 methods side by side
        - ngram            production ngram method, full keyword-level rows
        - llm              production LLM method, full keyword-level rows
        - grounded         experimental grounding method, full keyword-level rows
        - ner_chunked      experimental NER/noun-chunk method, full keyword-level rows
        - grounding_log    per-seed grounding detail (audit trail, grounded method)
        - rejected_off_topic  suggestions rejected by the prompt-grounding gate
        - extraction_log   raw candidates before dedupe/scoring (audit trail, NER method)
        - prompts          the 100 generated prompts with their topic

Usage:
    PYTHONPATH=src python scripts/test_wylie_hotel_all_methods.py
"""

from __future__ import annotations

import asyncio
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
    STOPWORDS as NGRAM_STOPWORDS,
    extract_keywords_with_importance,
    extract_keywords_with_importance_llm_batch,
    score_keywords_with_importance,
)
from case2_demand.keyword_extraction.keyword_validation import is_generic_phrase  # noqa: E402
from case2_demand.keyword_volume.dataforseo import (  # noqa: E402
    DataForSEOASVClient,
    DataForSEOSVClient,
)

# ---------------------------------------------------------------------------
# Brand + config for this test
# ---------------------------------------------------------------------------

BRAND_NAME = "The Wylie Hotel Atlanta, Tapestry Collection by Hilton"
BRAND_URL = "https://www.hilton.com/en/hotels/atlylup-wylie-hotel-atlanta/"
REFERENCE_CALIBRATION = REPO_ROOT / "runs" / "20260617T170025Z" / "calibrated.json"
INTENT_ID = "hospitality_wylie_hotel_atlanta"
INTENT_NAME = "Wylie Hotel Atlanta (Tapestry Collection by Hilton)"
OUTPUT_DIR = REPO_ROOT / "runs" / "keyword_grounding_test"
OUTPUT_PATH = OUTPUT_DIR / "keyword_grounding_test.xlsx"

LOCATION_CODE = 2840  # USA
LANGUAGE_CODE = "en"
SPACY_MODEL = "en_core_web_sm"

TOP_N_SEEDS = 4               # ngram seeds grounded per prompt
SUGGESTIONS_PER_SEED = 20     # DataForSEO keyword_suggestions `limit` per seed
RELEVANCE_THRESHOLD = 0.35    # min cross-encoder score to keep a grounded suggestion
GROUNDING_CONCURRENCY = 8     # concurrent keyword_suggestions requests

# ---------------------------------------------------------------------------
# 100 prompts / 10 topics — grounded in this hotel's real facts (address,
# neighborhood, restaurant name, amenities) so keyword extraction has real
# entities/details to work with, same as any real user prompt would.
# ---------------------------------------------------------------------------

TOPICS: dict[str, list[str]] = {
    "booking_rates": [
        "What is the average nightly rate at The Wylie Hotel Atlanta?",
        "Can I book a room at Wylie Hotel Atlanta with free cancellation?",
        "What is the best time to book Wylie Hotel Atlanta for lower rates?",
        "Does Wylie Hotel Atlanta offer discounts for extended stays?",
        "Is there a minimum stay requirement at The Wylie Hotel Atlanta?",
        "What is the cancellation policy for The Wylie Hotel Atlanta?",
        "How much does a weekend stay cost at Wylie Hotel Atlanta?",
        "Does Wylie Hotel Atlanta price match other booking sites?",
        "What taxes and fees are added to the room rate at Wylie Hotel Atlanta?",
        "Can I get a corporate rate at The Wylie Hotel Atlanta?",
    ],
    "rooms_suites": [
        "What is included in the King Suite at The Wylie Hotel Atlanta?",
        "Do the rooms at Wylie Hotel Atlanta have a mini fridge?",
        "How big are the standard rooms at The Wylie Hotel Atlanta?",
        "Does The Wylie Hotel Atlanta have ADA compliant rooms?",
        "What size are the TVs in Wylie Hotel Atlanta rooms?",
        "Is there a wet bar in the Wylie Hotel Atlanta suites?",
        "Do Wylie Hotel Atlanta rooms have blackout curtains?",
        "Does Wylie Hotel Atlanta offer connecting rooms for families?",
        "What amenities come with the King Suite at Wylie Hotel Atlanta?",
        "Are the rooms at The Wylie Hotel Atlanta non smoking?",
    ],
    "amenities_fitness": [
        "Does The Wylie Hotel Atlanta have a 24 hour fitness center?",
        "Is there a pool at Wylie Hotel Atlanta?",
        "What fitness equipment is available at The Wylie Hotel Atlanta gym?",
        "Does Wylie Hotel Atlanta have a business center?",
        "Is Wi-Fi free at The Wylie Hotel Atlanta?",
        "Does The Wylie Hotel Atlanta have a spa?",
        "Is there a rooftop bar at Wylie Hotel Atlanta?",
        "Does Wylie Hotel Atlanta provide laundry service?",
        "Is there an in room safe at Wylie Hotel Atlanta?",
        "Does The Wylie Hotel Atlanta have digital key access?",
    ],
    "dining": [
        "What restaurant is inside The Wylie Hotel Atlanta?",
        "Does Mrs P's Bar and Kitchen at Wylie Hotel Atlanta serve breakfast?",
        "What type of cuisine does Wylie Hotel Atlanta's restaurant serve?",
        "Is room service available at The Wylie Hotel Atlanta?",
        "Does Wylie Hotel Atlanta have a hotel bar?",
        "What are the dinner hours at Mrs P's Bar and Kitchen?",
        "Does Wylie Hotel Atlanta offer brunch on weekends?",
        "Is coffee available in the lobby at The Wylie Hotel Atlanta?",
        "Does Wylie Hotel Atlanta cater to dietary restrictions at its restaurant?",
        "What is the best dish at Mrs P's Bar and Kitchen?",
    ],
    "location_attractions": [
        "How far is The Wylie Hotel Atlanta from Ponce City Market?",
        "Is Wylie Hotel Atlanta near the Atlanta BeltLine?",
        "How close is Piedmont Park to The Wylie Hotel Atlanta?",
        "What neighborhood is Wylie Hotel Atlanta located in?",
        "Is The Wylie Hotel Atlanta walkable to Midtown Atlanta?",
        "How far is Georgia Tech from Wylie Hotel Atlanta?",
        "Is Fox Theatre near The Wylie Hotel Atlanta?",
        "How far is The Wylie Hotel Atlanta from the Atlanta airport?",
        "What is there to do near Wylie Hotel Atlanta in Old Fourth Ward?",
        "Is The Wylie Hotel Atlanta close to downtown Atlanta?",
    ],
    "parking_transportation": [
        "Does The Wylie Hotel Atlanta offer valet parking?",
        "How much does parking cost at Wylie Hotel Atlanta?",
        "Is there self parking available at The Wylie Hotel Atlanta?",
        "Does Wylie Hotel Atlanta have EV charging stations?",
        "Is there a shuttle from Wylie Hotel Atlanta to the airport?",
        "Can I get a rideshare easily from The Wylie Hotel Atlanta?",
        "Is street parking available near Wylie Hotel Atlanta?",
        "Does The Wylie Hotel Atlanta have accessible parking?",
        "How do I get from the airport to Wylie Hotel Atlanta?",
        "Is public transit near The Wylie Hotel Atlanta?",
    ],
    "pet_policy": [
        "Is The Wylie Hotel Atlanta pet friendly?",
        "What is the pet fee at Wylie Hotel Atlanta?",
        "Are dogs allowed in the rooms at The Wylie Hotel Atlanta?",
        "Is there a weight limit for pets at Wylie Hotel Atlanta?",
        "Does The Wylie Hotel Atlanta provide pet beds?",
        "Can I bring two dogs to Wylie Hotel Atlanta?",
        "Are cats allowed at The Wylie Hotel Atlanta?",
        "Is there a dog park near Wylie Hotel Atlanta?",
        "Does The Wylie Hotel Atlanta charge a cleaning fee for pets?",
        "What pet amenities does Wylie Hotel Atlanta offer?",
    ],
    "events_meetings": [
        "Can I host a wedding at The Wylie Hotel Atlanta?",
        "Does Wylie Hotel Atlanta have a meeting room?",
        "What is the capacity of the event space at The Wylie Hotel Atlanta?",
        "Does The Wylie Hotel Atlanta offer AV equipment for meetings?",
        "Can I book a small conference at Wylie Hotel Atlanta?",
        "Does Wylie Hotel Atlanta host corporate events?",
        "Is catering available for events at The Wylie Hotel Atlanta?",
        "Can I have a rehearsal dinner at Wylie Hotel Atlanta?",
        "Does The Wylie Hotel Atlanta offer group room blocks for weddings?",
        "What is the rental cost for the event space at Wylie Hotel Atlanta?",
    ],
    "hilton_honors_loyalty": [
        "Can I earn Hilton Honors points at The Wylie Hotel Atlanta?",
        "Does Wylie Hotel Atlanta accept Hilton Honors redemption?",
        "What Hilton Honors tier benefits apply at The Wylie Hotel Atlanta?",
        "Can I get a room upgrade with Hilton Honors at Wylie Hotel Atlanta?",
        "Is late checkout included for Hilton Honors members at Wylie Hotel Atlanta?",
        "Does The Wylie Hotel Atlanta offer free breakfast for Hilton Diamond members?",
        "How many points does a stay at Wylie Hotel Atlanta earn?",
        "Can I use a free night certificate at The Wylie Hotel Atlanta?",
        "Is Wylie Hotel Atlanta part of the Tapestry Collection by Hilton?",
        "Does Wylie Hotel Atlanta honor Hilton Honors Gold status perks?",
    ],
    "reviews_service": [
        "Is The Wylie Hotel Atlanta good for a business trip?",
        "How is the customer service at Wylie Hotel Atlanta?",
        "Is The Wylie Hotel Atlanta family friendly?",
        "What do guests say about Wylie Hotel Atlanta in reviews?",
        "Is The Wylie Hotel Atlanta good for a romantic getaway?",
        "How clean are the rooms at Wylie Hotel Atlanta according to reviews?",
        "Is Wylie Hotel Atlanta noisy at night?",
        "Is The Wylie Hotel Atlanta safe for solo travelers?",
        "How responsive is the front desk at Wylie Hotel Atlanta?",
        "Would you recommend The Wylie Hotel Atlanta for a first visit to Atlanta?",
    ],
}


def build_prompts() -> list[dict]:
    prompts = []
    counter = 1
    for topic, texts in TOPICS.items():
        for text in texts:
            prompts.append({
                "prompt_id": f"wylie_{counter:04d}",
                "topic": topic,
                "prompt": text,
            })
            counter += 1
    # Optional smoke-test limit (e.g. WYLIE_TEST_LIMIT=6), for quickly validating the
    # pipeline end-to-end before spending the full API budget on all 100 prompts.
    import os
    limit = os.environ.get("WYLIE_TEST_LIMIT")
    if limit:
        prompts = prompts[: int(limit)]
    return prompts


# ---------------------------------------------------------------------------
# Grounding-method helpers (copied from scripts/test_keyword_grounding.py —
# that script is a standalone entry point, not an importable module).
# ---------------------------------------------------------------------------

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
    """Every content word in `keyword` must trace back to the prompt itself."""
    prompt_tokens = _content_tokens(prompt)
    kw_tokens = [w for w in _WORD_RE.findall(keyword.lower()) if w not in NGRAM_STOPWORDS and len(w) > 1]
    if not kw_tokens:
        return False
    return all(_stem_match(w, prompt_tokens) for w in kw_tokens)


async def ground_seed_keyword(
    client: httpx.AsyncClient,
    auth_header: str,
    base_url: str,
    seed: str,
    *,
    limit: int = SUGGESTIONS_PER_SEED,
) -> list[dict]:
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


# ---------------------------------------------------------------------------
# NER/noun-chunking helpers (copied from scripts/test_keyword_ner_chunking.py)
# ---------------------------------------------------------------------------

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
    nlp = _get_nlp()
    doc = nlp(prompt)
    raw: list[dict] = []

    for nc in doc.noun_chunks:
        cleaned = _clean_chunk_text(nc.text)
        if not cleaned:
            continue
        # Skip bare wh-pronouns/pronouns picked up as their own one-word "noun
        # chunk" in question-initial position (e.g. "What is the rate?" ->
        # spaCy chunks "What" as a noun_chunk headed by an interrogative
        # pronoun). These aren't search keywords, but DataForSEO happily
        # returns a huge SV/ASV for "what" itself, which silently dominates
        # the whole prompt's volume estimate if not filtered here.
        if len(cleaned.split()) == 1 and (nc.root.pos_ in ("PRON", "DET") or nc.root.is_stop):
            continue
        raw.append({"keyword": cleaned, "extraction_type": "noun_chunk", "spacy_label": ""})

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

    for ent in doc.ents:
        if ent.label_ in _NON_ENTITY_LABELS:
            continue
        cleaned = _clean_chunk_text(ent.text)
        if cleaned:
            raw.append({"keyword": cleaned, "extraction_type": "entity", "spacy_label": ent.label_})

    return raw


def _dedupe_candidates(raw: list[dict]) -> list[dict]:
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


# ---------------------------------------------------------------------------
# Shared Case2 hyperparameters (mirrors cli.py's _default_hp + _hp_for_intent)
# ---------------------------------------------------------------------------

def _build_hp_for_intent(cal: dict, intent_id: str, beta: float) -> tuple[Case2Hyperparameters, dict]:
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


# ---------------------------------------------------------------------------
# Per-method candidate generation (returns {prompt_id: [(keyword, score), ...]}
# plus any audit-log rows)
# ---------------------------------------------------------------------------

def run_ngram_method(prompts: list[dict], *, max_keywords: int, cross_encoder_model: str) -> dict[str, list[tuple[str, float]]]:
    out: dict[str, list[tuple[str, float]]] = {}
    for p in prompts:
        kws = extract_keywords_with_importance(p["prompt"], max_keywords=max_keywords, model_name=cross_encoder_model)
        out[p["prompt_id"]] = [(k.keyword, k.importance_score) for k in kws]
    return out


def run_llm_method(
    prompts: list[dict],
    *,
    settings: Settings,
    max_keywords: int,
    cross_encoder_model: str,
) -> dict[str, list[tuple[str, float]]]:
    system_prompt_path = SRC_DIR / "case2_demand" / "prompts" / "keyword_extraction_system.txt"
    prompt_texts = [p["prompt"] for p in prompts]
    results = extract_keywords_with_importance_llm_batch(
        prompt_texts,
        api_key=settings.OPENROUTER_API_KEY or "",
        base_url=settings.OPENROUTER_BASE_URL,
        model=settings.CASE2_LLM_MODEL,
        system_prompt_path=system_prompt_path,
        max_keywords=max_keywords,
        max_prompts_per_call=settings.CASE2_LLM_MAX_PROMPTS_PER_CALL,
        request_delay_sec=settings.CASE2_LLM_REQUEST_DELAY_SEC,
        timeout_sec=settings.CASE2_LLM_REQUEST_TIMEOUT_SEC,
        cross_encoder_model=cross_encoder_model,
    )
    out: dict[str, list[tuple[str, float]]] = {}
    for p, kws in zip(prompts, results):
        out[p["prompt_id"]] = [(k.keyword, k.importance_score) for k in kws]
    return out


async def run_grounding_method(
    prompts: list[dict],
    ngram_results: dict[str, list[tuple[str, float]]],
    *,
    http_client: httpx.AsyncClient,
    auth_header: str,
    base_url: str,
    max_keywords: int,
    cross_encoder_model: str,
) -> tuple[dict[str, list[tuple[str, float, str]]], list[dict], list[dict]]:
    """Returns {prompt_id: [(keyword, score, seed_ngram), ...]}, grounding_log, rejected_rows."""
    sem = asyncio.Semaphore(GROUNDING_CONCURRENCY)

    async def _grounded_call(seed: str) -> list[dict]:
        async with sem:
            return await ground_seed_keyword(http_client, auth_header, base_url, seed)

    # Build (prompt_id, seed) worklist from each prompt's top ngram candidates.
    seeds_by_prompt: dict[str, list[str]] = {}
    for p in prompts:
        cands = ngram_results.get(p["prompt_id"], [])
        seeds_by_prompt[p["prompt_id"]] = [kw for kw, _ in cands[:TOP_N_SEEDS]]

    worklist = [(pid, seed) for pid, seeds in seeds_by_prompt.items() for seed in seeds]
    print(f"[grounding] {len(worklist)} seed lookups across {len(prompts)} prompts (concurrency={GROUNDING_CONCURRENCY}) ...")
    tasks = [_grounded_call(seed) for _, seed in worklist]
    all_suggestions = await asyncio.gather(*tasks)

    suggestions_by_prompt: dict[str, list[dict]] = {p["prompt_id"]: [] for p in prompts}
    for (pid, seed), suggestions in zip(worklist, all_suggestions):
        suggestions_by_prompt[pid].extend(suggestions)

    out: dict[str, list[tuple[str, float, str]]] = {}
    grounding_log: list[dict] = []
    rejected_rows: list[dict] = []
    prompt_by_id = {p["prompt_id"]: p["prompt"] for p in prompts}

    for p in prompts:
        pid, prompt = p["prompt_id"], p["prompt"]
        candidates = ngram_results.get(pid, [])
        seeds = seeds_by_prompt[pid]
        suggestions = suggestions_by_prompt[pid]

        pooled: dict[str, dict] = {}
        for s in suggestions:
            pooled.setdefault(s["keyword"].lower(), s)

        for seed in seeds:
            seed_suggestions = [s for s in suggestions if s["seed_ngram"] == seed]
            seed_score = next((score for kw, score in candidates if kw == seed), None)
            grounding_log.append({
                "prompt_id": pid,
                "prompt": prompt,
                "seed_ngram": seed,
                "seed_importance": seed_score,
                "num_suggestions_returned": len(seed_suggestions),
            })

        grounded_pool: dict[str, dict] = {}
        for key, s in pooled.items():
            if is_grounded_in_prompt(s["keyword"], prompt):
                grounded_pool[key] = s
            else:
                rejected_rows.append({
                    "prompt_id": pid,
                    "prompt": prompt,
                    "rejected_keyword": s["keyword"],
                    "seed_ngram": s["seed_ngram"],
                    "reason": "introduces word(s) not present in the prompt",
                })

        grounded_texts = [v["keyword"] for v in grounded_pool.values()]
        scored = score_keywords_with_importance(prompt, grounded_texts, model_name=cross_encoder_model) if grounded_texts else []
        scored_sorted = sorted(scored, key=lambda s: s.importance_score, reverse=True)

        kept = [s for s in scored_sorted if s.importance_score >= RELEVANCE_THRESHOLD][:max_keywords]
        if not kept and scored_sorted:
            kept = scored_sorted[:1]

        seed_for_keyword = {k.keyword: grounded_pool.get(k.keyword, {}).get("seed_ngram", "") for k in kept}

        if not kept:
            fallback = candidates[:2]
            out[pid] = [(kw, score, "(fallback: ngram candidate, no grounded match)") for kw, score in fallback]
        else:
            out[pid] = [(k.keyword, k.importance_score, seed_for_keyword.get(k.keyword, "")) for k in kept]

        for entry in grounding_log[-len(seeds):]:
            entry["num_pooled_unique"] = len(pooled)
            entry["num_rejected_off_topic"] = len([r for r in rejected_rows if r["prompt_id"] == pid])
            entry["num_grounded_on_topic"] = len(grounded_pool)
            entry["num_kept_after_relevance_filter"] = len(kept)

    return out, grounding_log, rejected_rows


def run_ner_method(
    prompts: list[dict],
    *,
    max_keywords: int,
    cross_encoder_model: str,
) -> tuple[dict[str, list[tuple[str, float, str, str]]], list[dict]]:
    """Returns {prompt_id: [(keyword, score, extraction_type, spacy_label), ...]}, extraction_log."""
    out: dict[str, list[tuple[str, float, str, str]]] = {}
    extraction_log: list[dict] = []

    for p in prompts:
        pid, prompt = p["prompt_id"], p["prompt"]
        raw_candidates = extract_ner_noun_chunk_candidates(prompt)
        for c in raw_candidates:
            extraction_log.append({
                "prompt_id": pid,
                "prompt": prompt,
                "keyword": c["keyword"],
                "extraction_type": c["extraction_type"],
                "spacy_label": c["spacy_label"],
            })

        deduped = _dedupe_candidates(raw_candidates)
        filtered = [c for c in deduped if not is_generic_phrase(c["keyword"])]
        if not filtered:
            filtered = [{"keyword": prompt[:50].strip().lower(), "extraction_type": "fallback_prompt", "spacy_label": ""}]

        candidate_texts = [c["keyword"] for c in filtered]
        scored = score_keywords_with_importance(prompt, candidate_texts, model_name=cross_encoder_model, max_keywords=max_keywords)
        type_lookup = {c["keyword"]: c["extraction_type"] for c in filtered}
        label_lookup = {c["keyword"]: c["spacy_label"] for c in filtered}

        if not scored:
            out[pid] = [(candidate_texts[0], 0.5, type_lookup.get(candidate_texts[0], ""), label_lookup.get(candidate_texts[0], ""))]
        else:
            out[pid] = [
                (s.keyword, s.importance_score, type_lookup.get(s.keyword, ""), label_lookup.get(s.keyword, ""))
                for s in scored
            ]

    return out, extraction_log


# ---------------------------------------------------------------------------
# Case2 estimation + row-building (shared across all 4 methods)
# ---------------------------------------------------------------------------

def estimate_and_build_rows(
    prompts: list[dict],
    per_prompt_keywords: dict[str, list],  # list of tuples, first 2 elements are (keyword, score)
    *,
    hp: Case2Hyperparameters,
    rho_by_keyword: dict,
    sv_map: dict[str, float],
    asv_map: dict[str, float],
    cpc_map: dict,
    comp_map: dict,
    extra_cols_fn=None,  # (pid, keyword, extra_tuple_fields) -> dict of extra columns
) -> list[dict]:
    rows: list[dict] = []
    estimator = Case2Estimator(hp)
    for p in prompts:
        pid, prompt, topic = p["prompt_id"], p["prompt"], p["topic"]
        entries = per_prompt_keywords.get(pid, [])
        if not entries:
            continue
        keywords = [e[0] for e in entries]
        similarities = [e[1] for e in entries]
        sv_values = [sv_map.get(kw, 1) for kw in keywords]
        asv_values = [asv_map.get(kw, 1) for kw in keywords]

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
        importance_lookup = {kw: sim for kw, sim in zip(keywords, similarities)}
        extra_by_kw = {e[0]: e[2:] for e in entries}

        for ke in kw_estimates:
            row = {
                "intent_cluster_name": INTENT_NAME,
                "intent_cluster_id": INTENT_ID,
                "topic": topic,
                "prompt_id": pid,
                "prompt": prompt,
                "prompt_ai_demand_median": round(Y_median, 2),
                "prompt_ai_demand_mean": round(Y_mean, 2),
                "prompt_ai_demand_linear_median": round(linear_median, 2),
                "prompt_ai_demand_linear_mean": round(linear_mean, 2),
                "keyword": ke.keyword,
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
            }
            if extra_cols_fn is not None:
                row.update(extra_cols_fn(ke.keyword, extra_by_kw.get(ke.keyword, ())))
            rows.append(row)
    return rows


def build_summary(prompts: list[dict], rows_by_method: dict[str, list[dict]]) -> pd.DataFrame:
    method_names = list(rows_by_method.keys())
    dfs = {m: pd.DataFrame(rows) for m, rows in rows_by_method.items()}
    out_rows = []
    for p in prompts:
        pid = p["prompt_id"]
        row = {"prompt_id": pid, "topic": p["topic"], "prompt": p["prompt"]}
        for m in method_names:
            df = dfs[m]
            sub = df[df["prompt_id"] == pid] if len(df) else df
            y = float(sub["prompt_ai_demand_median"].iloc[0]) if len(sub) else None
            row[f"{m}_y_median"] = y
            row[f"{m}_keyword_count"] = len(sub)
            if len(sub):
                contrib = sub["fusion_weight"] * sub["keyword_ai_demand_median"]
                top_idx = contrib.idxmax()
                row[f"{m}_top_keyword"] = sub.loc[top_idx, "keyword"]
            else:
                row[f"{m}_top_keyword"] = None
        out_rows.append(row)
    return pd.DataFrame(out_rows)


async def main() -> None:
    settings = Settings()
    login = settings.DATAFORSEO_LOGIN or ""
    password = settings.DATAFORSEO_PASSWORD or ""
    base_url = settings.DATAFORSEO_BASE_URL or "https://api.dataforseo.com/v3"
    if not login or not password:
        print("ERROR: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD not set (check .env)", file=sys.stderr)
        sys.exit(1)
    if not settings.OPENROUTER_API_KEY:
        print("ERROR: OPENROUTER_API_KEY not set (check .env)", file=sys.stderr)
        sys.exit(1)
    if not REFERENCE_CALIBRATION.exists():
        print(f"ERROR: reference calibration not found: {REFERENCE_CALIBRATION}", file=sys.stderr)
        sys.exit(1)

    print(f"[setup] brand: {BRAND_NAME}")
    print(f"[setup] loading spaCy model {SPACY_MODEL!r} ...")
    _get_nlp()

    cal = load_calibration(REFERENCE_CALIBRATION)
    apply_rho_eta_floors_to_calibration_dict(cal)
    beta = settings.CASE2_BETA if settings.CASE2_BETA is not None else 60.0
    hp, rho_by_keyword = _build_hp_for_intent(cal, INTENT_ID, beta)
    cross_encoder_model = settings.CASE2_CROSS_ENCODER_MODEL
    max_keywords = settings.CASE2_MAX_KEYWORDS

    prompts = build_prompts()
    print(f"[setup] {len(prompts)} prompts across {len(TOPICS)} topics")

    sv_client = DataForSEOSVClient(login=login, password=password, base_url=base_url, sv_source=settings.CASE2_SV_SOURCE)
    asv_client = DataForSEOASVClient(login=login, password=password, base_url=base_url)
    auth_header = f"Basic {__import__('base64').b64encode(f'{login}:{password}'.encode()).decode()}"

    # --- Method 1: ngram (production) ---
    print("\n[1/4] ngram extraction ...")
    ngram_results = run_ngram_method(prompts, max_keywords=max_keywords, cross_encoder_model=cross_encoder_model)

    # --- Method 2: LLM (production) ---
    print("[2/4] LLM extraction (OpenRouter) ...")
    llm_results = run_llm_method(prompts, settings=settings, max_keywords=max_keywords, cross_encoder_model=cross_encoder_model)

    # --- Method 3: grounding (experimental), seeded from ngram candidates ---
    print("[3/4] DataForSEO grounding ...")
    async with httpx.AsyncClient() as http_client:
        grounded_results, grounding_log, rejected_rows = await run_grounding_method(
            prompts, ngram_results,
            http_client=http_client, auth_header=auth_header, base_url=base_url,
            max_keywords=max_keywords, cross_encoder_model=cross_encoder_model,
        )

    # --- Method 4: NER + noun-phrase chunking (experimental) ---
    print("[4/4] NER + noun-phrase chunking ...")
    ner_results, extraction_log = run_ner_method(prompts, max_keywords=max_keywords, cross_encoder_model=cross_encoder_model)

    # --- Pool every keyword from every method into one SV + one ASV lookup ---
    all_keywords: set[str] = set()
    for d in (ngram_results, llm_results):
        for entries in d.values():
            all_keywords.update(kw for kw, _ in entries)
    for entries in grounded_results.values():
        all_keywords.update(kw for kw, _, _ in entries)
    for entries in ner_results.values():
        all_keywords.update(kw for kw, _, _, _ in entries)
    all_keywords_list = sorted(all_keywords)
    print(f"\n[sv/asv] {len(all_keywords_list)} unique keywords across all 4 methods — fetching SV + ASV ...")

    sv_results = await sv_client.get_volume(all_keywords_list, location_code=LOCATION_CODE, language_code=LANGUAGE_CODE)
    asv_results = await asv_client.get_volume(all_keywords_list, location_code=LOCATION_CODE, language_code=LANGUAGE_CODE)
    sv_map = {r.keyword: (r.search_volume if r.search_volume is not None else 1) for r in sv_results}
    asv_map = {r.keyword: (r.search_volume if r.search_volume is not None else 1) for r in asv_results}
    cpc_map = {r.keyword: r.cpc for r in sv_results}
    comp_map = {r.keyword: r.competition for r in sv_results}

    # --- Estimate + build rows per method ---
    print("[estimate] running Case2Estimator for all 4 methods ...")
    ngram_rows = estimate_and_build_rows(
        prompts, ngram_results, hp=hp, rho_by_keyword=rho_by_keyword,
        sv_map=sv_map, asv_map=asv_map, cpc_map=cpc_map, comp_map=comp_map,
    )
    llm_rows = estimate_and_build_rows(
        prompts, llm_results, hp=hp, rho_by_keyword=rho_by_keyword,
        sv_map=sv_map, asv_map=asv_map, cpc_map=cpc_map, comp_map=comp_map,
    )
    grounded_rows = estimate_and_build_rows(
        prompts, grounded_results, hp=hp, rho_by_keyword=rho_by_keyword,
        sv_map=sv_map, asv_map=asv_map, cpc_map=cpc_map, comp_map=comp_map,
        extra_cols_fn=lambda kw, extra: {"seed_ngram": extra[0] if extra else ""},
    )
    ner_rows = estimate_and_build_rows(
        prompts, ner_results, hp=hp, rho_by_keyword=rho_by_keyword,
        sv_map=sv_map, asv_map=asv_map, cpc_map=cpc_map, comp_map=comp_map,
        extra_cols_fn=lambda kw, extra: {
            "extraction_type": extra[0] if len(extra) > 0 else "",
            "spacy_label": extra[1] if len(extra) > 1 else "",
        },
    )

    rows_by_method = {"ngram": ngram_rows, "llm": llm_rows, "grounded": grounded_rows, "ner_chunked": ner_rows}
    summary_df = build_summary(prompts, rows_by_method)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="summary", index=False)
        pd.DataFrame(prompts).to_excel(writer, sheet_name="prompts", index=False)
        pd.DataFrame(ngram_rows).to_excel(writer, sheet_name="ngram", index=False)
        pd.DataFrame(llm_rows).to_excel(writer, sheet_name="llm", index=False)
        pd.DataFrame(grounded_rows).to_excel(writer, sheet_name="grounded", index=False)
        pd.DataFrame(ner_rows).to_excel(writer, sheet_name="ner_chunked", index=False)
        pd.DataFrame(grounding_log).to_excel(writer, sheet_name="grounding_log", index=False)
        pd.DataFrame(rejected_rows).to_excel(writer, sheet_name="rejected_off_topic", index=False)
        pd.DataFrame(extraction_log).to_excel(writer, sheet_name="extraction_log", index=False)

    print(f"\nSaved 4-method comparison workbook -> {OUTPUT_PATH}")
    print("\nSummary (first 15 rows):")
    print(summary_df.head(15).to_string(index=False))
    print("\nMean Y_median per method:")
    for m in rows_by_method:
        col = f"{m}_y_median"
        print(f"  {m}: {summary_df[col].mean():.2f}")


if __name__ == "__main__":
    asyncio.run(main())
