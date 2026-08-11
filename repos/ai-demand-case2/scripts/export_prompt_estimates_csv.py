#!/usr/bin/env python3
"""
Export prompt estimates from JSONL to CSV, grouped by intent cluster name.

Usage:
    python scripts/export_prompt_estimates_csv.py runs/20260317T121411Z
    python scripts/export_prompt_estimates_csv.py runs/20260317T121411Z -o estimates.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from case2_demand.util.io import export_prompt_estimates_to_csv


def load_prompt_estimates(jsonl_path: Path) -> list[dict]:
    """Load prompt estimates from JSONL file."""
    rows = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export prompt estimates from JSONL to CSV, grouped by intent cluster"
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help="Path to run directory (e.g. runs/20260317T121411Z) or directly to prompt_estimates.jsonl",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: <run_dir>/prompt_estimates.csv)",
    )
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    if run_dir.is_file():
        jsonl_path = run_dir
        out_path = args.output or (run_dir.parent / "prompt_estimates.csv")
    else:
        jsonl_path = run_dir / "prompt_estimates.jsonl"
        out_path = args.output or (run_dir / "prompt_estimates.csv")

    if not jsonl_path.exists():
        raise SystemExit(f"File not found: {jsonl_path}")

    rows = load_prompt_estimates(jsonl_path)
    if not rows:
        raise SystemExit(f"No rows in {jsonl_path}")

    export_prompt_estimates_to_csv(rows, out_path)
    print(f"Exported {len(rows)} prompts to {out_path}")


if __name__ == "__main__":
    main()
