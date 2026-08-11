"""Topic volume: highest prompt as anchor + discounted incremental non-overlapping keywords."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from case2_demand.intent_keyword_union import _get_sentence_model
from case2_demand.overlap_discount import overlap_discount_from_similarity
from case2_demand.schemas import IntentClusterDemandEstimate, PromptDemandEstimate


def _keywords_from_prompt(pe: PromptDemandEstimate) -> list[str]:
    if pe.weights:
        return list(pe.weights.keys())
    return [str(e.get("keyword", "")) for e in (pe.keyword_estimates or []) if e.get("keyword")]


def _keyword_lookup(pe: PromptDemandEstimate) -> dict[str, dict[str, Any]]:
    return {str(e["keyword"]): e for e in (pe.keyword_estimates or []) if e.get("keyword")}


def _marginal_volume(pe: PromptDemandEstimate, keywords: list[str], *, use_mean: bool) -> float:
    weights = pe.weights or {}
    lookup = _keyword_lookup(pe)
    field = "A_mean" if use_mean else "A_median"
    total = 0.0
    for kw in keywords:
        w = float(weights.get(kw, 0.0))
        est = lookup.get(kw)
        if est is None:
            continue
        total += w * float(est.get(field, 0.0) or 0.0)
    return total


def _marginal_variance(pe: PromptDemandEstimate, keywords: list[str], discount: float = 1.0) -> float:
    weights = pe.weights or {}
    lookup = _keyword_lookup(pe)
    var = 0.0
    for kw in keywords:
        w = float(weights.get(kw, 0.0))
        est = lookup.get(kw)
        if est is None:
            continue
        var += (w * discount) ** 2 * float(est.get("variance", 0.0) or 0.0)
    return var


def _embed_keywords(keywords: list[str], *, model_name: str) -> np.ndarray:
    if not keywords:
        return np.zeros((0, 0))
    model = _get_sentence_model(model_name)
    embeddings = model.encode(keywords, normalize_embeddings=True, show_progress_bar=False)
    if not isinstance(embeddings, np.ndarray):
        embeddings = np.asarray(embeddings)
    return embeddings


def _max_similarity_to_accumulated(
    embedding: np.ndarray,
    accumulated_embeddings: np.ndarray,
) -> float:
    if accumulated_embeddings.size == 0:
        return 0.0
    sims = embedding @ accumulated_embeddings.T
    return float(np.max(sims)) if sims.size else 0.0


def estimate_intent_cluster_representative_incremental(
    *,
    cluster_id: str,
    intent_name: str,
    prompt_estimates: list[PromptDemandEstimate],
    model_name: str,
    sim_threshold: float,
    alpha: float,
) -> IntentClusterDemandEstimate:
    """
    Topic volume = representative prompt Y_median
    + Σ (marginal volume from non-overlapping keywords on other prompts × overlap discount).

    Overlap is semantic (cosine sim > threshold vs accumulated keyword set).
    """
    if not prompt_estimates:
        raise ValueError("prompt_estimates must not be empty")

    ordered = sorted(
        prompt_estimates,
        key=lambda p: (-float(p.Y_median or 0.0), str(p.prompt_id)),
    )
    representative = ordered[0]
    rep_keywords = _keywords_from_prompt(representative)
    accumulated_keywords = list(rep_keywords)
    accumulated_embeddings = _embed_keywords(accumulated_keywords, model_name=model_name)

    rep_volume = float(representative.Y_median or 0.0)
    rep_mean = float(representative.Y_mean or rep_volume)
    topic_var = float(representative.Y_std or 0.0) ** 2
    incremental_volume = 0.0
    incremental_details: list[dict[str, Any]] = []

    for pe in ordered[1:]:
        prompt_keywords = _keywords_from_prompt(pe)
        if not prompt_keywords:
            continue

        prompt_embeddings = _embed_keywords(prompt_keywords, model_name=model_name)
        non_overlapping: list[str] = []
        sims_to_accumulated: list[float] = []

        for kw, emb in zip(prompt_keywords, prompt_embeddings):
            max_sim = _max_similarity_to_accumulated(emb, accumulated_embeddings)
            if max_sim > sim_threshold:
                continue
            non_overlapping.append(kw)
            sims_to_accumulated.append(max_sim)

        if not non_overlapping:
            incremental_details.append(
                {
                    "prompt_id": pe.prompt_id,
                    "added_volume": 0.0,
                    "non_overlapping_keywords": [],
                }
            )
            continue

        raw_incremental = _marginal_volume(pe, non_overlapping, use_mean=False)
        avg_sim = float(np.mean(sims_to_accumulated)) if sims_to_accumulated else 0.0
        discount = overlap_discount_from_similarity(avg_sim, alpha)
        added = raw_incremental * discount

        incremental_volume += added
        topic_var += _marginal_variance(pe, non_overlapping, discount=discount)

        new_embeddings = _embed_keywords(non_overlapping, model_name=model_name)
        if accumulated_embeddings.size == 0:
            accumulated_embeddings = new_embeddings
        else:
            accumulated_embeddings = np.vstack([accumulated_embeddings, new_embeddings])
        accumulated_keywords.extend(non_overlapping)

        incremental_details.append(
            {
                "prompt_id": pe.prompt_id,
                "added_volume": added,
                "raw_incremental": raw_incremental,
                "overlap_discount": discount,
                "average_keyword_similarity": avg_sim,
                "non_overlapping_keywords": non_overlapping,
            }
        )

    topic_volume = rep_volume + incremental_volume
    topic_mean = rep_mean + sum(d.get("added_volume", 0.0) for d in incremental_details)
    y_std = math.sqrt(max(topic_var, 0.0))
    z_90 = 1.645
    interval = (
        max(0.0, topic_volume - z_90 * y_std),
        topic_volume + z_90 * y_std,
    )

    return IntentClusterDemandEstimate(
        intent_cluster_id=cluster_id,
        intent_cluster_name=str(intent_name),
        num_prompts=len(prompt_estimates),
        Y_median=topic_volume,
        Y_mean=topic_mean,
        Y_std=y_std,
        interval_90=interval,
        volume_method="representative_incremental",
        representative_prompt_id=str(representative.prompt_id),
        representative_volume=rep_volume,
        incremental_volume=incremental_volume,
        prompts_with_incremental=sum(1 for d in incremental_details if d.get("added_volume", 0) > 0),
        incremental_prompt_details=incremental_details,
    )
