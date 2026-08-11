"""Cluster topic volume via overlap discount on sum of per-prompt Case2 volumes."""

from __future__ import annotations

from typing import Any

import numpy as np

from case2_demand.intent_keyword_union import (
    _get_sentence_model,
    max_importance_scores_for_intent,
)
from case2_demand.schemas import IntentClusterDemandEstimate, PromptDemandEstimate


def mean_pairwise_cosine_similarity(embeddings: np.ndarray) -> float:
    n = len(embeddings)
    if n < 2:
        return 0.0
    sims: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            sims.append(float(np.dot(embeddings[i], embeddings[j])))
    return float(np.mean(sims)) if sims else 0.0


def overlap_discount_from_similarity(avg_sim: float, alpha: float) -> float:
    return 1.0 / (1.0 + alpha * max(avg_sim, 0.0))


def cluster_keyword_overlap_stats(
    keywords: list[str],
    *,
    model_name: str,
    alpha: float,
) -> dict[str, float]:
    if not keywords:
        return {"average_similarity": 0.0, "overlap_discount": 1.0, "keyword_count": 0.0}
    if len(keywords) == 1:
        return {"average_similarity": 0.0, "overlap_discount": 1.0, "keyword_count": 1.0}

    model = _get_sentence_model(model_name)
    embeddings = model.encode(keywords, normalize_embeddings=True, show_progress_bar=False)
    if not isinstance(embeddings, np.ndarray):
        embeddings = np.asarray(embeddings)

    avg_sim = mean_pairwise_cosine_similarity(embeddings)
    return {
        "average_similarity": float(avg_sim),
        "overlap_discount": float(overlap_discount_from_similarity(avg_sim, alpha)),
        "keyword_count": float(len(keywords)),
    }


def estimate_intent_cluster_overlap_discount(
    *,
    cluster_id: str,
    intent_name: str,
    extractions: list[dict[str, Any]],
    prompt_estimates_by_id: dict[str, PromptDemandEstimate],
    model_name: str,
    alpha: float,
) -> IntentClusterDemandEstimate:
    """
    Topic volume = sum(prompt Y_mean) × overlap_discount,
    where overlap_discount = 1 / (1 + α × mean_pairwise_keyword_similarity)
    on the union of all prompt keywords in the cluster.
    """
    union_scores = max_importance_scores_for_intent(extractions)
    keywords = sorted(union_scores.keys())
    stats = cluster_keyword_overlap_stats(keywords, model_name=model_name, alpha=alpha)
    discount = stats["overlap_discount"]

    sum_prompt_y_mean = 0.0
    sum_prompt_var = 0.0
    matched = 0
    for ext in extractions:
        pid = str(ext.get("prompt_id") or "")
        pe = prompt_estimates_by_id.get(pid)
        if pe is None:
            continue
        matched += 1
        sum_prompt_y_mean += float(pe.Y_mean or 0.0)
        sum_prompt_var += float(pe.Y_std or 0.0) ** 2

    overlap_volume = sum_prompt_y_mean * discount
    y_std = float(np.sqrt(sum_prompt_var) * discount) if sum_prompt_var > 0 else 0.0
    z_90 = 1.645
    interval = (
        max(0.0, overlap_volume - z_90 * y_std),
        overlap_volume + z_90 * y_std,
    )

    return IntentClusterDemandEstimate(
        intent_cluster_id=cluster_id,
        intent_cluster_name=str(intent_name),
        num_prompts=len(extractions),
        Y_median=overlap_volume,
        Y_mean=sum_prompt_y_mean,
        Y_std=y_std,
        interval_90=interval,
        volume_method="overlap_discount",
        overlap_discount=discount,
        average_keyword_similarity=stats["average_similarity"],
        union_keyword_count=int(stats["keyword_count"]),
        overlap_discount_volume=overlap_volume,
        sum_prompt_y_mean=sum_prompt_y_mean,
        prompts_matched=matched,
    )
