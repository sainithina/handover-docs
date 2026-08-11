"""Intent-level keyword union + semantic dedupe for Case2 fusion."""

from __future__ import annotations

from typing import Any

import numpy as np

# Lazy cache: model name -> SentenceTransformer instance
_ST_MODELS: dict[str, Any] = {}


def _get_sentence_model(model_name: str):
    if model_name not in _ST_MODELS:
        from sentence_transformers import SentenceTransformer

        _ST_MODELS[model_name] = SentenceTransformer(model_name)
    return _ST_MODELS[model_name]


def max_importance_scores_for_intent(extractions: list[dict[str, Any]]) -> dict[str, float]:
    """
    Union all keywords under one intent; per keyword keep max importance_score
    across prompts (same string after strip).
    """
    out: dict[str, float] = {}
    for ext in extractions:
        for kd in ext.get("keywords") or []:
            if not isinstance(kd, dict):
                continue
            kw = (kd.get("keyword") or "").strip()
            if not kw:
                continue
            try:
                score = float(kd.get("importance_score") if kd.get("importance_score") is not None else 0.7)
            except (TypeError, ValueError):
                score = 0.7
            prev = out.get(kw)
            if prev is None or score > prev:
                out[kw] = score
    return out


def dedupe_keywords_semantic(
    keyword_to_score: dict[str, float],
    *,
    model_name: str,
    sim_threshold: float,
) -> tuple[list[str], list[float]]:
    """
    Greedy dedupe: sort by descending score (then keyword for stability), embed with
    SentenceTransformer, drop any candidate with max cosine similarity to an already-kept
    keyword strictly greater than ``sim_threshold``.

    Returns parallel lists (keywords, importance_scores) for Case2Estimator.
    """
    if not keyword_to_score:
        return [], []

    if len(keyword_to_score) == 1:
        kw = next(iter(keyword_to_score))
        return [kw], [float(keyword_to_score[kw])]

    ordered = sorted(
        keyword_to_score.keys(),
        key=lambda k: (-keyword_to_score[k], k),
    )
    model = _get_sentence_model(model_name)
    embeddings = model.encode(ordered, normalize_embeddings=True, show_progress_bar=False)
    if not isinstance(embeddings, np.ndarray):
        embeddings = np.asarray(embeddings)

    kept_indices: list[int] = []
    for i, _kw in enumerate(ordered):
        if not kept_indices:
            kept_indices.append(i)
            continue
        sims = embeddings[i] @ embeddings[kept_indices].T
        max_sim = float(np.max(sims)) if sims.size else 0.0
        if max_sim <= sim_threshold:
            kept_indices.append(i)

    keywords = [ordered[i] for i in kept_indices]
    similarities = [float(keyword_to_score[k]) for k in keywords]
    return keywords, similarities


def fallback_keyword_from_extractions(extractions: list[dict[str, Any]]) -> dict[str, float]:
    """When no keywords were extracted for an intent, mirror per-prompt fallback (prompt slice)."""
    if not extractions:
        return {"general": 0.7}
    p = extractions[0].get("prompt") or "general"
    label = (str(p)[:50] if p else "general").strip() or "general"
    return {label: 0.7}
