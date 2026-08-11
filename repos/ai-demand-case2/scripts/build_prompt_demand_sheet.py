#!/usr/bin/env python3
"""Build a prompt demand sheet (custom order) from prompt_estimates_ordered.csv."""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


def norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u2014", "-").replace("\u2013", "-")
    return re.sub(r"\s+", " ", s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("order_file", type=Path, help="One prompt per line")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output CSV (default: run_dir/prompt_demand_sheet.csv)",
    )
    args = ap.parse_args()

    run_dir = args.run_dir.resolve()
    order_file = args.order_file.resolve()
    out_path = args.out or (run_dir / "prompt_demand_sheet.csv")

    ref_order = [ln.strip() for ln in order_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if ref_order and ref_order[0].lower() == "prompt":
        ref_order = ref_order[1:]

    est_path = run_dir / "prompt_estimates_ordered.csv"
    if not est_path.exists():
        est_path = run_dir / "prompt_estimates.csv"
    rows = list(csv.DictReader(est_path.open(encoding="utf-8")))
    by_norm = {norm(r["prompt"]): r for r in rows if (r.get("prompt") or "").strip()}

    fields = [
        "order",
        "prompt",
        "ai_demand_median",
        "ai_demand_mean",
        "ai_demand_linear_median",
        "ai_demand_linear_mean",
    ]
    out_rows: list[dict] = []
    missing: list[tuple[int, str]] = []

    for i, prompt in enumerate(ref_order, 1):
        r = by_norm.get(norm(prompt))
        if not r:
            missing.append((i, prompt))
            out_rows.append({
                "order": i,
                "prompt": prompt,
                "ai_demand_median": "",
                "ai_demand_mean": "",
                "ai_demand_linear_median": "",
                "ai_demand_linear_mean": "",
            })
            continue
        out_rows.append({
            "order": i,
            "prompt": r.get("prompt", prompt),
            "ai_demand_median": r.get("ai_demand_median", ""),
            "ai_demand_mean": r.get("ai_demand_mean", ""),
            "ai_demand_linear_median": r.get("ai_demand_linear_median", ""),
            "ai_demand_linear_mean": r.get("ai_demand_linear_mean", ""),
        })

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)

    print(f"order lines: {len(ref_order)}")
    print(f"wrote: {out_path} ({len(out_rows)} rows)")
    print(f"matched: {len(out_rows) - len(missing)}, missing: {len(missing)}")
    if missing:
        print("first missing:")
        for m in missing[:10]:
            print(f"  {m[0]}: {m[1][:80]}...")


if __name__ == "__main__":
    main()
