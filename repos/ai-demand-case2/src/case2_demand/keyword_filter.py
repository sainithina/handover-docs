"""Per-prompt keyword filtering by cross-encoder importance_score before fusion."""

from __future__ import annotations

from typing import Literal

KeywordFilterMethod = Literal["none", "top_n", "median", "binary_search"]


def filter_keywords_top_n(
    items: list[tuple[str, float]],
    n: int,
) -> tuple[list[tuple[str, float]], float]:
    """Keep the top ``n`` keywords by importance (stable tie-break on keyword text)."""
    if not items:
        return [], 0.0
    sorted_items = sorted(items, key=lambda x: (-x[1], x[0]))
    kept = sorted_items[: max(1, n)]
    cutoff = kept[-1][1]
    return kept, cutoff


def filter_keywords_median(
    items: list[tuple[str, float]],
) -> tuple[list[tuple[str, float]], float]:
    """Keep keywords with importance_score >= per-prompt median."""
    if not items:
        return [], 0.0
    cutoff = _median_cutoff_via_binary_search(items, levels=1)
    kept = sorted(
        [(kw, score) for kw, score in items if score >= cutoff - 1e-12],
        key=lambda x: (-x[1], x[0]),
    )
    if not kept:
        kept, cutoff = filter_keywords_top_n(items, 1)
    return kept, cutoff


def _median_cutoff_via_binary_search(
    items: list[tuple[str, float]],
) -> float:
    """
    Binary-search the largest cutoff τ such that at least ⌈n/2⌉ keywords remain.

    Equivalent to a median importance cutoff on the current keyword set.
    """
    n = len(items)
    if n == 0:
        return 0.0
    if n == 1:
        return items[0][1]

    target = (n + 1) // 2
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        count = sum(1 for _, score in items if score >= mid - 1e-12)
        if count > target:
            lo = mid
        elif count < target:
            hi = mid
        else:
            return mid
    return hi


def filter_keywords_median_binary_search(
    items: list[tuple[str, float]],
    levels: int = 1,
) -> tuple[list[tuple[str, float]], float]:
    """
    Iterative median importance cutoff using binary search at each level.

    ``levels=1``: one median cutoff pass on all keywords.
    ``levels=2``: apply median cutoff, then recompute median on survivors and filter again.
    """
    if not items:
        return [], 0.0
    if levels < 1:
        raise ValueError("levels must be >= 1")

    kept = list(items)
    cutoff = 0.0
    for _ in range(levels):
        if len(kept) <= 1:
            break
        cutoff = _median_cutoff_via_binary_search(kept)
        next_kept = sorted(
            [(kw, score) for kw, score in kept if score >= cutoff - 1e-12],
            key=lambda x: (-x[1], x[0]),
        )
        if not next_kept:
            break
        kept = next_kept
    return kept, round(cutoff, 6)


def apply_keyword_filter(
    items: list[tuple[str, float]],
    *,
    method: str,
    levels: int = 1,
    top_n: int = 2,
) -> tuple[list[tuple[str, float]], float | None]:
    """Apply configured filter; returns (kept pairs, final cutoff or None)."""
    normalized = (method or "none").strip().lower()
    if normalized in ("none", ""):
        return items, None
    if normalized == "top_n":
        kept, cutoff = filter_keywords_top_n(items, top_n)
    elif normalized == "median":
        kept, cutoff = filter_keywords_median(items)
    elif normalized == "binary_search":
        kept, cutoff = filter_keywords_median_binary_search(items, levels=levels)
    else:
        raise ValueError(f"Unknown keyword filter method: {method!r}")
    return kept, cutoff
