"""Extract keywords from prompts with importance scores.

Supports two methods:
- llm: Gemini (or CASE2_LLM_MODEL) via OpenRouter — default
- ngram: Cross-encoder similarity over n-gram candidates (opt-in only)
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import List, Optional, Set

from case2_demand.keyword_extraction.keyword_validation import is_generic_phrase
from case2_demand.schemas import KeywordWithImportance

_CROSS_ENCODER = None
_CROSS_ENCODER_MODEL: Optional[str] = None
_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _get_cross_encoder(model_name: str = _DEFAULT_MODEL):
    global _CROSS_ENCODER, _CROSS_ENCODER_MODEL
    if _CROSS_ENCODER is None or _CROSS_ENCODER_MODEL != model_name:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as e:
            raise ImportError(
                "The 'ngram' keyword extraction method requires the 'sentence-transformers' package. "
                "Install it in your environment, e.g.: pip install sentence-transformers\n"
                "Alternatively, use LLM-based extraction: --keyword-extraction llm "
                "(requires OPENROUTER_API_KEY and network access)."
            ) from e
        _CROSS_ENCODER = CrossEncoder(model_name)
        _CROSS_ENCODER_MODEL = model_name
    return _CROSS_ENCODER


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-20, min(20, x))))


STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "as", "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "do", "does", "did", "will", "would", "should", "could", "may", "might", "must",
    "can", "this", "that", "these", "those", "i", "you", "he", "she", "it", "we", "they",
    "what", "which", "who", "whom", "whose", "where", "when", "why", "how", "about",
    "into", "through", "during", "before", "after", "above", "below", "up", "down",
    "out", "off", "over", "under", "again", "further", "then", "once", "here", "there",
    "all", "both", "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just", "now",
    # pronouns and conjunctions commonly missing from base sets
    "if", "my", "me", "your", "our", "their", "its", "his", "her",
    "any", "every", "whether", "while", "although", "since", "unless",
    "am", "get", "got", "getting", "let", "make", "made", "put", "set",
    "also", "even", "still", "already", "yet", "either", "neither",
    "much", "many", "well", "really", "actually", "quite", "rather",
}


def _has_min_content_words(phrase: str, min_content: int = 2) -> bool:
    """Return True if the phrase contains at least min_content non-stopword tokens."""
    tokens = phrase.lower().split()
    return sum(1 for t in tokens if t not in STOPWORDS and not t.isdigit()) >= min_content


def _generate_candidate_keywords(prompt: str, min_length: int = 2) -> List[str]:
    words = re.split(r"[\s\.,;:!?()\[\]{}\'\"\-]+", prompt.lower())
    meaningful = [
        w.strip() for w in words
        if w and len(w) >= min_length and w not in STOPWORDS and not w.isdigit()
    ]
    if len(meaningful) < 2:
        return []
    candidates: List[str] = []
    seen: Set[str] = set()
    for n in [3, 2]:
        for i in range(len(meaningful) - n + 1):
            phrase = " ".join(meaningful[i : i + n])
            # Require at least 2 content words so pure function-word n-grams are excluded
            if phrase not in seen and _has_min_content_words(phrase, min_content=2):
                seen.add(phrase)
                candidates.append(phrase)
    return candidates


def extract_keywords_with_importance(
    prompt: str,
    min_length: int = 2,
    max_keywords: int = 8,
    top_k: Optional[int] = None,
    model_name: str = _DEFAULT_MODEL,
) -> List[KeywordWithImportance]:
    k = top_k if top_k is not None else max_keywords
    if not prompt:
        return []
    candidates = [
        c for c in _generate_candidate_keywords(prompt, min_length=min_length)
        if not is_generic_phrase(c)
    ]
    if not candidates:
        return [KeywordWithImportance(keyword=prompt[:50] or "general", importance_score=0.8)]
    pairs = [(prompt, kw) for kw in candidates]
    encoder = _get_cross_encoder(model_name)
    raw_scores = encoder.predict(pairs)
    scored = [(candidates[i], _sigmoid(float(raw_scores[i]))) for i in range(len(candidates))]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [(kw, score) for kw, score in scored[: k * 2] if not is_generic_phrase(kw)][:k]
    keywords = [KeywordWithImportance(keyword=kw, importance_score=round(score, 4)) for kw, score in top]
    return keywords if keywords else [KeywordWithImportance(keyword=prompt[:50], importance_score=0.7)]


def score_keywords_with_importance(
    prompt: str,
    keywords: List[str],
    *,
    max_keywords: Optional[int] = None,
    model_name: str = _DEFAULT_MODEL,
) -> List[KeywordWithImportance]:
    """Score fixed keyword phrases with the same cross-encoder used for ngram extraction."""
    if not prompt or not prompt.strip():
        return []
    seen: Set[str] = set()
    unique: List[str] = []
    for raw in keywords:
        k = (raw or "").strip().lower()
        if not k or k in seen or is_generic_phrase(k):
            continue
        seen.add(k)
        unique.append(k)
    if not unique:
        return []

    pairs = [(prompt, kw) for kw in unique]
    encoder = _get_cross_encoder(model_name)
    raw_scores = encoder.predict(pairs)
    scored = [
        KeywordWithImportance(
            keyword=unique[i],
            importance_score=round(_sigmoid(float(raw_scores[i])), 4),
        )
        for i in range(len(unique))
    ]
    scored.sort(key=lambda x: x.importance_score, reverse=True)
    if max_keywords is not None:
        scored = scored[:max_keywords]
    return scored


def _finalize_llm_keyword_strings(
    prompt: str,
    keyword_strings: List[str],
    *,
    max_keywords: int,
    model_name: str,
) -> List[KeywordWithImportance]:
    """Cross-encoder score LLM phrases, then drop invalid copies of the prompt."""
    from case2_demand.llm.openai_client import _filter_valid_keywords

    scored = score_keywords_with_importance(
        prompt,
        keyword_strings,
        max_keywords=max_keywords * 2,
        model_name=model_name,
    )
    return _filter_valid_keywords(scored, prompt, max_keywords=max_keywords)


def extract_keywords_with_importance_llm(
    prompt: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt_path: Path,
    max_keywords: int = 3,
    timeout_sec: float = 180.0,
    cross_encoder_model: str = _DEFAULT_MODEL,
) -> List[KeywordWithImportance]:
    """LLM proposes keyword phrases; cross-encoder assigns importance (same as ngram)."""
    from case2_demand.llm.openai_client import OpenAIClient

    client = OpenAIClient(api_key=api_key, base_url=base_url, timeout_sec=timeout_sec)
    strings = client.extract_keyword_strings_for_prompt(
        model=model,
        prompt=prompt,
        system_prompt_path=system_prompt_path,
        max_keywords=max_keywords,
    )
    return _finalize_llm_keyword_strings(
        prompt,
        strings,
        max_keywords=max_keywords,
        model_name=cross_encoder_model,
    )


def extract_keywords_with_importance_llm_batch(
    prompts: List[str],
    *,
    api_key: str,
    base_url: str,
    model: str,
    system_prompt_path: Path,
    max_keywords: int = 3,
    max_prompts_per_call: int = 10,
    request_delay_sec: float = 8.0,
    timeout_sec: float = 180.0,
    cross_encoder_model: str = _DEFAULT_MODEL,
) -> List[List[KeywordWithImportance]]:
    """LLM proposes keyword phrases per prompt; cross-encoder scores each (same as ngram)."""
    from case2_demand.llm.openai_client import OpenAIClient

    client = OpenAIClient(api_key=api_key, base_url=base_url, timeout_sec=timeout_sec)
    string_lists = client.extract_keyword_strings_for_prompts_batch(
        model=model,
        prompts=prompts,
        system_prompt_path=system_prompt_path,
        max_keywords=max_keywords,
        max_prompts_per_call=max_prompts_per_call,
        request_delay_sec=request_delay_sec,
    )
    return [
        _finalize_llm_keyword_strings(
            prompt,
            kws,
            max_keywords=max_keywords,
            model_name=cross_encoder_model,
        )
        for prompt, kws in zip(prompts, string_lists)
    ]
