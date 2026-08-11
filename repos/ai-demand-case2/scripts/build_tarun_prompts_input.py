#!/usr/bin/env python3
"""Build intents JSON from Tarun TSV (Prompt, Comment, Group)."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import OrderedDict
from pathlib import Path

GROUP_TO_INTENT = {
    "Personal Accident Insurance": ("personal_accident_insurance", "Personal Accident Insurance"),
    "General Health Insurance & Policies": (
        "general_health_insurance_policies",
        "General Health Insurance & Policies",
    ),
    "Family & Senior Coverage": ("family_and_senior_coverage", "Family & Senior Coverage"),
    "Group / Employer Health Insurance": (
        "group_employer_health_insurance",
        "Group / Employer Health Insurance",
    ),
    "Top-Up Plans": ("top_up_plans", "Top-Up Plans"),
    "Online Purchasing & Quotes": (
        "online_purchasing_and_quotes",
        "Online Purchasing & Quotes",
    ),
    "Portability & Transfer": ("portability_and_transfer", "Portability & Transfer"),
    "OPD Coverage": ("opd_coverage", "OPD Coverage"),
}


def norm(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u2014", "-").replace("\u2013", "-")
    return re.sub(r"\s+", " ", s)


def load_tsv(path: Path) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader, None)
        for row in reader:
            if not row or not any(c.strip() for c in row):
                continue
            if len(row) >= 3:
                prompt, comment, group = row[0].strip(), row[1].strip(), row[2].strip()
            elif len(row) == 2:
                prompt, group = row[0].strip(), row[1].strip()
                comment = ""
            else:
                continue
            if not prompt or prompt.lower() == "prompt":
                continue
            if not group:
                continue
            rows.append((prompt, comment, group))
    return rows


def build_json(rows: list[tuple[str, str, str]]) -> dict:
    groups: OrderedDict[str, list[str]] = OrderedDict()
    tarun_check: dict[str, str] = {}
    seen_prompts: set[str] = set()
    dupes = 0

    for prompt, comment, group in rows:
        key = norm(prompt).lower()
        if key in seen_prompts:
            dupes += 1
            continue
        seen_prompts.add(key)
        if group not in groups:
            groups[group] = []
        groups[group].append(prompt)
        if comment and comment.lower() not in ("", "no"):
            tarun_check[prompt] = comment

    intents = []
    for group_name, prompts in groups.items():
        if group_name not in GROUP_TO_INTENT:
            raise ValueError(f"Unknown group: {group_name!r}")
        intent_id, intent_name = GROUP_TO_INTENT[group_name]
        intents.append(
            {
                "intent_name": intent_name,
                "intent_id": intent_id,
                "prompts": prompts,
            }
        )

    return {
        "company_name": "Digit Insurance",
        "description": "Tarun full prompt batch for Case 2 demand",
        "tarun_comment_by_prompt": tarun_check,
        "intents": intents,
        "_stats": {
            "prompts": sum(len(i["prompts"]) for i in intents),
            "intents": len(intents),
            "duplicates_skipped": dupes,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    args = ap.parse_args()
    rows = load_tsv(args.tsv)
    data = build_json(rows)
    stats = data.pop("_stats")
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}: {stats['prompts']} prompts, {stats['intents']} intents")
    if stats["duplicates_skipped"]:
        print(f"Skipped {stats['duplicates_skipped']} duplicate prompts")


if __name__ == "__main__":
    main()
