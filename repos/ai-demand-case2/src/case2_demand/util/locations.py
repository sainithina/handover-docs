"""Multi-market location parsing and volume aggregation."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Sequence

MAX_LOCATION_CODES = 5
DEFAULT_LOCATION_CODE = 2840


def parse_location_codes(
    location: int | None = None,
    locations: str | None = None,
) -> list[int]:
    """
    Parse 1–5 DataForSEO location codes.

    ``locations`` wins over ``location`` when both are set (comma-separated).
    Default: US (2840).
    """
    if locations and str(locations).strip():
        raw = [part.strip() for part in str(locations).split(",") if part.strip()]
        if not raw:
            raise ValueError("--locations must include at least one location code")
        codes = [int(part) for part in raw]
    elif location is not None:
        codes = [int(location)]
    else:
        codes = [DEFAULT_LOCATION_CODE]

    seen: set[int] = set()
    ordered: list[int] = []
    for code in codes:
        if code in seen:
            continue
        seen.add(code)
        ordered.append(code)

    if len(ordered) > MAX_LOCATION_CODES:
        raise ValueError(
            f"At most {MAX_LOCATION_CODES} distinct location codes allowed, got {len(ordered)}"
        )
    if not ordered:
        ordered = [DEFAULT_LOCATION_CODE]
    return ordered


def location_subdir(run_dir: Path, location_code: int) -> Path:
    return run_dir / "by_location" / str(location_code)


def write_locations_manifest(
    run_dir: Path,
    location_codes: Sequence[int],
    *,
    language_code: str = "en",
    sv_source: str | None = None,
) -> Path:
    path = run_dir / "locations.json"
    payload: dict[str, Any] = {
        "location_codes": list(location_codes),
        "language_code": language_code,
        "aggregation": "sum_of_fused_volumes",
    }
    if sv_source:
        payload["sv_source"] = sv_source
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def aggregate_prompt_estimates(
    per_location: Sequence[Sequence[Any]],
) -> list[dict[str, Any]]:
    """
    Sum fused prompt volumes across markets (keyed by prompt_id).

    Each inner sequence holds PromptDemandEstimate or dict rows for one market.
    """
    by_id: dict[str, dict[str, Any]] = {}

    for loc_rows in per_location:
        for row in loc_rows:
            data = row.model_dump() if hasattr(row, "model_dump") else dict(row)
            pid = data["prompt_id"]
            if pid not in by_id:
                by_id[pid] = {
                    **data,
                    "Y_median": 0.0,
                    "Y_mean": 0.0,
                    "Y_std": 0.0,
                    "interval_90": [0.0, 0.0],
                    "keyword_estimates": [],
                    "weights": {},
                }
            agg = by_id[pid]
            agg["Y_median"] += float(data.get("Y_median", 0) or 0)
            agg["Y_mean"] += float(data.get("Y_mean", 0) or 0)
            var = float(data.get("Y_std", 0) or 0) ** 2
            agg["Y_std"] = float(agg["Y_std"]) ** 2 + var
            low, high = data.get("interval_90") or (0.0, 0.0)
            agg["interval_90"][0] += float(low)
            agg["interval_90"][1] += float(high)

    out: list[dict[str, Any]] = []
    for row in by_id.values():
        row["Y_std"] = math.sqrt(max(float(row["Y_std"]), 0.0))
        row["interval_90"] = tuple(row["interval_90"])
        out.append(row)
    out.sort(key=lambda r: (r.get("intent_cluster_name") or "", r.get("prompt") or ""))
    return out


def aggregate_intent_estimates(
    per_location: Sequence[Sequence[Any]],
) -> list[dict[str, Any]]:
    """Sum fused intent volumes across markets (keyed by intent_cluster_id)."""
    by_id: dict[str, dict[str, Any]] = {}

    for loc_rows in per_location:
        for row in loc_rows:
            data = row.model_dump() if hasattr(row, "model_dump") else dict(row)
            iid = data["intent_cluster_id"]
            if iid not in by_id:
                by_id[iid] = {
                    **data,
                    "Y_median": 0.0,
                    "Y_mean": 0.0,
                    "Y_std": 0.0,
                    "interval_90": [0.0, 0.0],
                }
            agg = by_id[iid]
            agg["Y_median"] += float(data.get("Y_median", 0) or 0)
            agg["Y_mean"] += float(data.get("Y_mean", 0) or 0)
            var = float(data.get("Y_std", 0) or 0) ** 2
            agg["Y_std"] = float(agg["Y_std"]) ** 2 + var
            low, high = data.get("interval_90") or (0.0, 0.0)
            agg["interval_90"][0] += float(low)
            agg["interval_90"][1] += float(high)

    out: list[dict[str, Any]] = []
    for row in by_id.values():
        row["Y_std"] = math.sqrt(max(float(row["Y_std"]), 0.0))
        row["interval_90"] = tuple(row["interval_90"])
        out.append(row)
    out.sort(key=lambda r: r.get("intent_cluster_name") or "")
    return out
