#!/usr/bin/env python3
"""Reorder run outputs to match a reference prompt list (one prompt per line)."""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u2014", "-").replace("\u2013", "-")
    return re.sub(r"\s+", " ", s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("order_file", type=Path, help="One prompt per line, in desired order")
    args = ap.parse_args()
    run = args.run_dir
    ref_order = [ln.strip() for ln in args.order_file.read_text(encoding="utf-8").splitlines() if ln.strip()]

    rows = list(csv.DictReader((run / "prompt_estimates.csv").open(encoding="utf-8")))
    prompt_rows = [r for r in rows if (r.get("prompt_id") or "").strip()]
    by_prompt = {norm(r["prompt"]): r for r in prompt_rows}

    fields = [
        "order", "intent_cluster_name", "intent_cluster_id", "prompt_id", "prompt",
        "ai_demand_median", "ai_demand_mean", "ai_demand_std",
        "interval_90_low", "interval_90_high",
    ]
    out_rows = []
    missing = []
    for i, prompt in enumerate(ref_order, 1):
        r = by_prompt.get(norm(prompt))
        if not r:
            missing.append((i, prompt))
            continue
        out_rows.append({
            "order": i,
            "intent_cluster_name": r.get("intent_cluster_name", ""),
            "intent_cluster_id": r.get("intent_cluster_id", ""),
            "prompt_id": r.get("prompt_id", ""),
            "prompt": r.get("prompt", prompt),
            "ai_demand_median": r.get("ai_demand_median", ""),
            "ai_demand_mean": r.get("ai_demand_mean", ""),
            "ai_demand_std": r.get("ai_demand_std", ""),
            "interval_90_low": r.get("interval_90_low", ""),
            "interval_90_high": r.get("interval_90_high", ""),
        })

    ref_keys = {norm(p) for p in ref_order}
    extras = [r for r in prompt_rows if norm(r["prompt"]) not in ref_keys]
    ord_extra = len(ref_order) + 1
    for r in extras:
        out_rows.append({
            "order": ord_extra,
            "intent_cluster_name": r.get("intent_cluster_name", ""),
            "intent_cluster_id": r.get("intent_cluster_id", ""),
            "prompt_id": r.get("prompt_id", ""),
            "prompt": r.get("prompt", ""),
            "ai_demand_median": r.get("ai_demand_median", ""),
            "ai_demand_mean": r.get("ai_demand_mean", ""),
            "ai_demand_std": r.get("ai_demand_std", ""),
            "interval_90_low": r.get("interval_90_low", ""),
            "interval_90_high": r.get("interval_90_high", ""),
        })
        ord_extra += 1

    for name in ("prompt_estimates.csv", "prompt_estimates_ordered.csv"):
        with (run / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(out_rows)

    if (run / "prompt_estimates.jsonl").exists():
        records = [json.loads(l) for l in (run / "prompt_estimates.jsonl").open() if l.strip()]
        by_j = {norm(r["prompt"]): r for r in records}
        j_out = [by_j[norm(p)] for p in ref_order if norm(p) in by_j]
        j_idx = {norm(x["prompt"]): i for i, x in enumerate(records)}
        j_extras = [r for r in records if norm(r["prompt"]) not in ref_keys]
        j_extras.sort(key=lambda r: j_idx[norm(r["prompt"])])
        with (run / "prompt_estimates.jsonl").open("w", encoding="utf-8") as f:
            for r in j_out + j_extras:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    pkv = run / "prompt_keyword_volumes.csv"
    if pkv.exists():
        kw_all = list(csv.DictReader(pkv.open(encoding="utf-8")))
        kw_by = {}
        for r in kw_all:
            kw_by.setdefault(norm(r["prompt"]), []).append(r)
        kw_out = []
        for i, prompt in enumerate(ref_order, 1):
            for row in kw_by.get(norm(prompt), []):
                nr = dict(row)
                nr["order"] = i
                kw_out.append(nr)
        ord_extra = len(ref_order) + 1
        for r in extras:
            k = norm(r["prompt"])
            for row in kw_by.get(k, []):
                nr = dict(row)
                nr["order"] = ord_extra
                kw_out.append(nr)
            ord_extra += 1
        base = [c for c in (kw_out[0].keys() if kw_out else []) if c != "order"]
        kw_fields = ["order"] + base
        for name in ("prompt_keyword_volumes.csv", "prompt_keyword_volumes_ordered.csv"):
            with (run / name).open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=kw_fields, extrasaction="ignore")
                w.writeheader()
                w.writerows(kw_out)

    print(f"reference: {len(ref_order)} lines -> {len(out_rows)} rows")
    print(f"missing: {len(missing)}, extras appended: {len(extras)}")
    if missing:
        for i, p in missing[:15]:
            print(f"  [{i}] {p[:75]}")


if __name__ == "__main__":
    main()
