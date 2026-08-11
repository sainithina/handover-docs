"""N-gram candidate generation + LLM relevance/dedup filter + cross-encoder scoring."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from case2_demand.keyword_extraction.extractor import (
    _generate_candidate_keywords,
    score_keywords_with_importance,
)
from case2_demand.keyword_extraction.keyword_validation import is_generic_phrase
from case2_demand.llm.openai_client import OpenAIClient, _filter_valid_keywords
from case2_demand.schemas import KeywordWithImportance

_DEFAULT_FILTER_PROMPT = (
    Path(__file__).resolve().parents[1] / "prompts" / "keyword_filter_ngram_system.txt"
)


def generate_ngram_candidates(prompt: str) -> List[str]:
    return [
        c for c in _generate_candidate_keywords(prompt)
        if not is_generic_phrase(c)
    ]


def _enforce_candidate_subset(selected: List[str], candidates: List[str]) -> List[str]:
    cand_set = {c.lower().strip() for c in candidates}
    out: List[str] = []
    seen: set[str] = set()
    for raw in selected:
        k = (raw or "").strip().lower()
        if k in cand_set and k not in seen:
            out.append(k)
            seen.add(k)
    return out


def filter_ngram_keywords_with_llm(
    prompt: str,
    candidates: List[str],
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt_path: Path = _DEFAULT_FILTER_PROMPT,
    max_keywords: int = 6,
    timeout_sec: float = 180.0,
) -> Tuple[List[str], List[str]]:
    """Return (kept_keywords, dropped_keywords) after LLM filter."""
    if not candidates:
        return [], []

    client = OpenAIClient(api_key=api_key, base_url=base_url, timeout_sec=timeout_sec)
    selected = client.filter_ngram_candidates_for_prompt(
        model=model,
        prompt=prompt,
        candidates=candidates,
        system_prompt_path=system_prompt_path,
        max_keywords=max_keywords,
    )
    kept = _enforce_candidate_subset(selected, candidates)
    dropped = [c for c in candidates if c not in set(kept)]
    return kept, dropped


def extract_ngram_llm_filtered_keywords(
    prompt: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt_path: Path = _DEFAULT_FILTER_PROMPT,
    max_keywords: int = 6,
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    timeout_sec: float = 180.0,
) -> Tuple[List[KeywordWithImportance], dict]:
    """N-gram candidates → LLM filter → cross-encoder importance on survivors."""
    candidates = generate_ngram_candidates(prompt)
    meta = {
        "num_ngram_candidates": len(candidates),
        "ngram_candidates": list(candidates),
        "llm_kept": [],
        "llm_dropped": [],
        "used_fallback": False,
    }
    if not candidates:
        fallback = prompt[:50].strip().lower() or "general"
        meta["used_fallback"] = True
        return [KeywordWithImportance(keyword=fallback, importance_score=0.8)], meta

    scored_all = score_keywords_with_importance(
        prompt, candidates, model_name=cross_encoder_model, max_keywords=len(candidates),
    )
    score_by_kw = {k.keyword: k.importance_score for k in scored_all}

    kept, dropped = filter_ngram_keywords_with_llm(
        prompt,
        candidates,
        api_key=api_key,
        base_url=base_url,
        model=model,
        system_prompt_path=system_prompt_path,
        max_keywords=max_keywords,
        timeout_sec=timeout_sec,
    )
    meta["llm_kept"] = kept
    meta["llm_dropped"] = dropped

    if not kept:
        meta["used_fallback"] = True
        fallback_scored = _filter_valid_keywords(scored_all, prompt, max_keywords=max_keywords)
        if fallback_scored:
            return fallback_scored, meta
        top = scored_all[0]
        return [KeywordWithImportance(keyword=top.keyword, importance_score=top.importance_score)], meta

    kept_scored = [
        KeywordWithImportance(keyword=kw, importance_score=score_by_kw.get(kw, 0.5))
        for kw in kept
    ]
    kept_scored.sort(key=lambda x: x.importance_score, reverse=True)
    final = _filter_valid_keywords(kept_scored, prompt, max_keywords=max_keywords)
    return final or kept_scored[:max_keywords], meta


def extract_ngram_llm_filtered_keywords_batch(
    prompts: List[str],
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt_path: Path = _DEFAULT_FILTER_PROMPT,
    max_keywords: int = 6,
    max_items_per_call: int = 10,
    request_delay_sec: float = 8.0,
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    timeout_sec: float = 180.0,
) -> Tuple[List[List[KeywordWithImportance]], List[dict]]:
    """Batch n-gram → LLM filter → cross-encoder importance."""
    from case2_demand.llm.openai_client import OpenAIClient

    all_candidates = [generate_ngram_candidates(p) for p in prompts]
    client = OpenAIClient(api_key=api_key, base_url=base_url, timeout_sec=timeout_sec)
    items = [{"prompt": p, "candidates": cands} for p, cands in zip(prompts, all_candidates)]
    selected_lists = client.filter_ngram_candidates_batch(
        model=model,
        items=items,
        system_prompt_path=system_prompt_path,
        max_keywords=max_keywords,
        max_items_per_call=max_items_per_call,
        request_delay_sec=request_delay_sec,
    )

    # Retry individually when batch parsing returns empty for a prompt with candidates.
    for i, (item, selected) in enumerate(zip(items, selected_lists)):
        if item["candidates"] and not selected:
            print(f"  retry single-prompt LLM filter ({i + 1}/{len(items)}) ...", flush=True)
            selected_lists[i] = client.filter_ngram_candidates_for_prompt(
                model=model,
                prompt=item["prompt"],
                candidates=item["candidates"],
                system_prompt_path=system_prompt_path,
                max_keywords=max_keywords,
            )

    results: List[List[KeywordWithImportance]] = []
    logs: List[dict] = []
    for prompt, candidates, selected in zip(prompts, all_candidates, selected_lists):
        meta = {
            "prompt": prompt,
            "num_ngram_candidates": len(candidates),
            "ngram_candidates": list(candidates),
            "llm_selected_raw": list(selected),
            "llm_kept": [],
            "llm_dropped": [],
            "used_fallback": False,
        }
        if not candidates:
            fallback = prompt[:50].strip().lower() or "general"
            meta["used_fallback"] = True
            results.append([KeywordWithImportance(keyword=fallback, importance_score=0.8)])
            logs.append(meta)
            continue

        scored_all = score_keywords_with_importance(
            prompt, candidates, model_name=cross_encoder_model, max_keywords=len(candidates),
        )
        score_by_kw = {k.keyword: k.importance_score for k in scored_all}
        kept = _enforce_candidate_subset(selected, candidates)
        meta["llm_kept"] = kept
        meta["llm_dropped"] = [c for c in candidates if c not in set(kept)]

        if not kept:
            meta["used_fallback"] = True
            fallback_scored = _filter_valid_keywords(scored_all, prompt, max_keywords=max_keywords)
            results.append(fallback_scored or [scored_all[0]])
            logs.append(meta)
            continue

        kept_scored = [
            KeywordWithImportance(keyword=kw, importance_score=score_by_kw.get(kw, 0.5))
            for kw in kept
        ]
        kept_scored.sort(key=lambda x: x.importance_score, reverse=True)
        final = _filter_valid_keywords(kept_scored, prompt, max_keywords=max_keywords)
        results.append(final or kept_scored[:max_keywords])
        logs.append(meta)

    return results, logs
