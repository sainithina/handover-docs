"""Importance scoring via BGE reranker v2 M3 (cross-encoder)."""

from __future__ import annotations

import math
from typing import List, Optional, Set

from case2_demand.keyword_extraction.keyword_validation import is_generic_phrase
from case2_demand.schemas import KeywordWithImportance

_BGE_RERANKER = None
_BGE_RERANKER_MODEL: Optional[str] = None
_DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-20, min(20, x))))


def _get_bge_reranker(model_name: str = _DEFAULT_MODEL):
    global _BGE_RERANKER, _BGE_RERANKER_MODEL
    if _BGE_RERANKER is None or _BGE_RERANKER_MODEL != model_name:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as e:
            raise ImportError(
                "BGE reranker importance scoring requires 'sentence-transformers'. "
                "Install with: pip install sentence-transformers"
            ) from e
        _BGE_RERANKER = CrossEncoder(model_name)
        _BGE_RERANKER_MODEL = model_name
    return _BGE_RERANKER


def score_keywords_with_bge_reranker_importance(
    prompt: str,
    keywords: List[str],
    *,
    max_keywords: Optional[int] = None,
    model_name: str = _DEFAULT_MODEL,
) -> List[KeywordWithImportance]:
    """Score keyword relevance to a prompt using BAAI/bge-reranker-v2-m3."""
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

    pairs = [(prompt.strip(), kw) for kw in unique]
    encoder = _get_bge_reranker(model_name)
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
