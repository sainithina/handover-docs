"""Importance scoring via BGE-M3 dense embeddings (cosine similarity)."""

from __future__ import annotations

from typing import List, Optional, Set

import numpy as np

from case2_demand.keyword_extraction.keyword_validation import is_generic_phrase
from case2_demand.schemas import KeywordWithImportance

_BGE_M3_MODEL = None
_DEFAULT_MODEL = "BAAI/bge-m3"
# BGE-M3 retrieval instruction for the prompt side (query).
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _get_bge_m3(model_name: str = _DEFAULT_MODEL):
    global _BGE_M3_MODEL
    if _BGE_M3_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "BGE-M3 importance scoring requires 'sentence-transformers'. "
                "Install with: pip install sentence-transformers"
            ) from e
        _BGE_M3_MODEL = SentenceTransformer(model_name)
    return _BGE_M3_MODEL


def score_keywords_with_bge_m3_importance(
    prompt: str,
    keywords: List[str],
    *,
    max_keywords: Optional[int] = None,
    model_name: str = _DEFAULT_MODEL,
) -> List[KeywordWithImportance]:
    """Score keyword relevance to a prompt using BGE-M3 dense cosine similarity."""
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

    model = _get_bge_m3(model_name)
    query_text = _QUERY_PREFIX + prompt.strip()
    query_emb = model.encode([query_text], normalize_embeddings=True)[0]
    kw_embs = model.encode(unique, normalize_embeddings=True)

    scored: List[KeywordWithImportance] = []
    for kw, emb in zip(unique, kw_embs):
        # L2-normalized vectors → dot product equals cosine similarity in [-1, 1].
        cosine = float(np.dot(query_emb, emb))
        # Map to (0, 1) for compatibility with cross-encoder importance_score scale.
        importance = round(float((cosine + 1.0) / 2.0), 4)
        scored.append(KeywordWithImportance(keyword=kw, importance_score=importance))

    scored.sort(key=lambda x: x.importance_score, reverse=True)
    if max_keywords is not None:
        scored = scored[:max_keywords]
    return scored
