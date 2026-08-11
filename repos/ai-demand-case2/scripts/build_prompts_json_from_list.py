#!/usr/bin/env python3
"""Build intents JSON from a plain prompt list + cluster lookup from digit_all_groups."""
from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
LOOKUP_GLOB = "digit*.json"
INTENT_NAMES = {
    "personal_accident_insurance": "Personal Accident Insurance",
    "general_health_insurance_policies": "General Health Insurance & Policies",
    "family_and_senior_coverage": "Family & Senior Coverage",
    "group_employer_health_insurance": "Group / Employer Health Insurance",
    "top_up_plans": "Top-Up Plans",
    "online_purchasing_and_quotes": "Online Purchasing & Quotes",
    "portability_and_transfer": "Portability & Transfer",
    "opd_coverage": "OPD Coverage",
}
DEFAULT_FALLBACK = (
    "general_health_insurance_policies",
    "General Health Insurance & Policies",
)


def norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u2014", "-").replace("\u2013", "-")
    return re.sub(r"\s+", " ", s)


def classify(prompt: str) -> tuple[str, str]:
    p = norm(prompt)
    if any(k in p for k in ("personal accident", "accidental insurance", "accidental insurance")):
        return "personal_accident_insurance", INTENT_NAMES["personal_accident_insurance"]
    if any(k in p for k in ("opd", "doctor visit", "outpatient", "consultation and medicines")):
        return "opd_coverage", INTENT_NAMES["opd_coverage"]
    if any(k in p for k in ("super top-up", "super top up", "top-up", "top up")) or (
        "deductible" in p and "super" in p
    ):
        return "top_up_plans", INTENT_NAMES["top_up_plans"]
    if any(
        k in p
        for k in (
            "group health",
            "group medical",
            "group mediclaim",
            "employer health",
            "corporate health",
            "employee",
            "employers",
        )
    ):
        return "group_employer_health_insurance", INTENT_NAMES["group_employer_health_insurance"]
    if any(k in p for k in ("port", "portability", "porting", "migrate", "migration")):
        return "portability_and_transfer", INTENT_NAMES["portability_and_transfer"]
    if any(
        k in p
        for k in (
            "senior citizen",
            "parents",
            "parent",
            "family floater",
            "family mediclaim",
            "mediclaim for family",
            "newborn",
        )
    ):
        return "family_and_senior_coverage", INTENT_NAMES["family_and_senior_coverage"]
    if any(k in p for k in ("online", "quote", "premium calculator", "checkout", "buy online")):
        return "online_purchasing_and_quotes", INTENT_NAMES["online_purchasing_and_quotes"]
    return DEFAULT_FALLBACK


def load_lookup(inputs_dir: Path) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for path in sorted(inputs_dir.glob(LOOKUP_GLOB)):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for intent in data.get("intents", []):
            iid = intent["intent_id"]
            iname = intent["intent_name"]
            for p in intent.get("prompts", []):
                out[norm(p)] = (iid, iname)
    return out


def build(prompts_path: Path, output: Path, inputs_dir: Path) -> None:
    lookup = load_lookup(inputs_dir)
    groups: OrderedDict[str, dict] = OrderedDict()
    seen: set[str] = set()
    missing: list[str] = []
    dupes = 0
    all_lines = prompts_path.read_text(encoding="utf-8").splitlines()
    raw_lines = sum(1 for ln in all_lines if ln.strip())

    for line in all_lines:
        prompt = line.strip()
        if not prompt:
            continue
        key = norm(prompt)
        if key in seen:
            dupes += 1
            continue
        seen.add(key)

        meta = lookup.get(key) or classify(prompt)
        if key not in lookup:
            missing.append(prompt)
        iid, iname = meta
        if iid not in groups:
            groups[iid] = {"intent_name": iname, "intent_id": iid, "prompts": []}
        groups[iid]["prompts"].append(prompt)

    intents = list(groups.values())
    out = {
        "company_name": "Digit Insurance",
        "description": (
            f"User batch: {sum(len(i['prompts']) for i in intents)} unique prompts "
            f"({raw_lines} lines in source list)"
        ),
        "intents": intents,
    }
    output.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(len(i["prompts"]) for i in intents)
    print(f"Wrote {output}: {total} prompts, {len(intents)} intents")
    if dupes:
        print(f"  Skipped {dupes} duplicate line(s)")
    if missing:
        print(f"  {len(missing)} prompt(s) not in lookup → {DEFAULT_FALLBACK[1]}")
        for p in missing[:5]:
            print(f"    - {p[:80]}...")
        if len(missing) > 5:
            print(f"    ... and {len(missing) - 5} more")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("prompts_txt", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--inputs-dir", type=Path, default=PROJECT / "inputs")
    args = ap.parse_args()
    build(args.prompts_txt, args.output, args.inputs_dir)


if __name__ == "__main__":
    main()
