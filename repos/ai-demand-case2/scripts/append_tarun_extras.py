#!/usr/bin/env python3
"""Append prompts from raw Tarun paste file that are not yet in the TSV."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
TSV = PROJECT / "inputs" / "digit_tarun_user_paste.tsv"
RAW = PROJECT / "inputs" / "digit_tarun_raw_paste.txt"
ALL_GROUPS = PROJECT / "inputs" / "digit_all_groups_prompts.json"


def norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u2014", "-").replace("\u2013", "-")
    return re.sub(r"\s+", " ", s)


def load_existing(tsv: Path) -> set[str]:
    seen = set()
    with tsv.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader, None)
        for row in reader:
            if row:
                seen.add(norm(row[0]))
    return seen


def parse_raw(raw: Path) -> list[tuple[str, str, str]]:
    rows = []
    for line in raw.read_text(encoding="utf-8").splitlines():
        line = line.rstrip("\n")
        if not line.strip() or line.lower().startswith("prompt\t"):
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            prompt, comment, group = parts[0].strip(), parts[1].strip(), parts[2].strip()
        elif len(parts) == 2:
            prompt, group = parts[0].strip(), parts[1].strip()
            comment = ""
        else:
            continue
        if prompt and group:
            rows.append((prompt, comment, group))
    return rows


def main() -> None:
    if not RAW.exists():
        print(f"Missing {RAW} — save full Tarun paste (Prompt\\tComment\\tGroup) there first.")
        return
    seen = load_existing(TSV)
    new_rows = []
    for prompt, comment, group in parse_raw(RAW):
        if norm(prompt) not in seen:
            seen.add(norm(prompt))
            new_rows.append((prompt, comment, group))
    if not new_rows:
        print("No new rows to append.")
        return
    with TSV.open("a", encoding="utf-8", newline="") as f:
        for prompt, comment, group in new_rows:
            f.write(f"{prompt}\t{comment}\t{group}\n")
    print(f"Appended {len(new_rows)} prompts to {TSV}")


if __name__ == "__main__":
    main()
