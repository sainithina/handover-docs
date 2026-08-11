"""Reject ultra-generic prompt fragments and pipeline metadata as search keywords."""

from __future__ import annotations

import re
from typing import Iterable, TypeVar

T = TypeVar("T")

# Exact phrases (normalized lowercase) that are prompt scaffolding, not search queries.
GENERIC_PHRASE_DENYLIST: frozenset[str] = frozenset(
    {
        # Comparison / question frames (high ASV, no intent signal)
        "difference between",
        "difference between a",
        "difference between the",
        "difference between bank",
        "difference between software",
        "difference between stored",
        "what's difference",
        "what's difference between",
        "whats difference",
        "whats difference between",
        "what is the",
        "what is the difference",
        "what's the difference",
        "between stored",
        "between bank funeral",
        "between software modernization",
        "compared to",
        "compared with",
        "better than",
        "types of",
        "meaning of",
        "definition of",
        "advantages of",
        "disadvantages of",
        "pros and cons",
        # Pronoun / function-word n-gram shards
        "if my",
        "if i",
        "if you",
        "if the",
        "if your",
        "if my golf",
        "claim if",
        "claim if my",
        "stolen my",
        "stolen my car",
        "my car",
        "my golf",
        "my golf clubs",
        "clubs stolen",
        "clubs stolen my",
        "services plain",
        "plain staff",
        "plain staff augmentation",
        "plan life insurance",
        "bank funeral",
        "company funeral cover",
        "cover kenya",
        "funeral cover kenya",
        "stored digital",
        "staged digital",
        # Question starters copied as keywords
        "how do i",
        "how do you",
        "how can i",
        "how can you",
        "how to",
        "how does",
        "how is",
        "can i",
        "can you",
        "should i",
        "do i",
        "does the",
        "is the",
        "is a",
        "is it",
        "are the",
        "will the",
        # Corrupted prompt / pipeline metadata
        "prompt claim",
        "prompt claim if",
        "prompt difference",
        "prompt difference between",
        "prompt what's",
        "prompt what's difference",
        "prompt_id",
        "cluster_id",
        "prompt_id cluster_id",
        "car prompt_id",
        "my car prompt_id",
        "kenya prompt_id",
        "kenya prompt_id cluster_id",
        "cover kenya prompt_id",
        "wallet prompt_id",
        "wallet prompt_id cluster_id",
        "augmentation prompt_id",
        "augmentation prompt_id cluster_id",
    }
)

_METADATA_TOKENS: frozenset[str] = frozenset(
    {"prompt_id", "cluster_id", "intent_cluster_id"}
)


def normalize_keyword(keyword: str) -> str:
    return re.sub(r"\s+", " ", (keyword or "").strip().lower())


def is_metadata_keyword(keyword: str) -> bool:
    k = normalize_keyword(keyword)
    return any(tok in k for tok in _METADATA_TOKENS)


def is_generic_phrase(keyword: str) -> bool:
    """True when keyword is a denylisted fragment or pipeline metadata."""
    k = normalize_keyword(keyword)
    if not k:
        return True
    if k in GENERIC_PHRASE_DENYLIST:
        return True
    if is_metadata_keyword(k):
        return True
    if re.fullmatch(r"difference between(?:\s+(?:a|an|the|my|your))?", k):
        return True
    if re.fullmatch(r"if (?:my|i|you|the|your|a|an)(?:\s+\w+)?", k):
        return True
    if k.startswith("prompt ") and len(k.split()) <= 4:
        return True
    return False


def filter_generic_phrases(keywords: Iterable[str]) -> list[str]:
    return [kw for kw in keywords if not is_generic_phrase(kw)]
