#!/usr/bin/env python3
"""
Export prompt × keyword volumes from a Case 2 run directory.

Joins prompt_estimates.jsonl (fused keyword AI demand) with keyword_volumes.csv (SV/ASV)
and keyword_extractions.jsonl (importance scores).

Includes prompt_ai_demand_linear_* columns: sum of keyword AI demand per prompt
without fusion_weight (compare to prompt_ai_demand_* which uses weighted fusion).

Usage:
    python scripts/export_prompt_keyword_volumes.py runs/20260520T061905Z
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
src_dir = project_root / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

from case2_demand.util.io import (
    export_prompt_keyword_volumes_to_csv,
    importance_by_prompt_keyword_from_extractions,
    iter_jsonl,
)


def _load_keyword_volumes(path: Path) -> tuple[dict[str, float], dict[str, float]]:
    sv: dict[str, float] = {}
    asv: dict[str, float] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            kw = row.get("keyword", "").strip()
            if not kw:
                continue
            sv[kw] = float(row.get("sv") or 0)
            asv[kw] = float(row.get("asv") or 0)
    return sv, asv


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export prompt × keyword volume CSV from a Case 2 run",
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help="Run directory (e.g. runs/20260520T061905Z)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output CSV (default: <run_dir>/prompt_keyword_volumes.csv)",
    )
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    jsonl_path = run_dir / "prompt_estimates.jsonl"
    volumes_path = run_dir / "keyword_volumes.csv"
    extractions_path = run_dir / "keyword_extractions.jsonl"
    out_path = args.output or (run_dir / "prompt_keyword_volumes.csv")

    if not jsonl_path.exists():
        raise SystemExit(f"Missing {jsonl_path}")
    if not volumes_path.exists():
        raise SystemExit(f"Missing {volumes_path}")

    prompt_rows = list(iter_jsonl(jsonl_path))
    if not prompt_rows:
        raise SystemExit(f"No rows in {jsonl_path}")

    keyword_to_sv, keyword_to_asv = _load_keyword_volumes(volumes_path)
    importance = (
        importance_by_prompt_keyword_from_extractions(iter_jsonl(extractions_path))
        if extractions_path.exists()
        else None
    )

    n = export_prompt_keyword_volumes_to_csv(
        prompt_rows,
        keyword_to_sv=keyword_to_sv,
        keyword_to_asv=keyword_to_asv,
        importance_by_prompt_keyword=importance,
        out_path=out_path,
    )
    print(f"Exported {n} prompt×keyword rows to {out_path}")


if __name__ == "__main__":
    main()
