#!/usr/bin/env python3
"""Build digit_subsample_55.json from stratified prompt list + Digit intent mapping."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DIGIT = PROJECT / "inputs" / "digit_all_groups_prompts.json"
OUT = PROJECT / "inputs" / "digit_subsample_55.json"

SUBSAMPLE: list[tuple[str, str]] = [
    # (funnel_segment, prompt)
    ("upper_funnel_depth", "How much personal accident cover should I buy if my family depends on my income?"),
    ("upper_funnel_depth", "Can I get tax benefits if I pay health insurance premiums for my parents, and how does that usually work?"),
    ("upper_funnel_depth", "How much health insurance cover is usually enough for a family with senior citizen parents in India?"),
    ("upper_funnel_depth", "What are the real benefits of having health insurance in India if I'm young and healthy?"),
    ("upper_funnel_depth", "how many employees do i need before i can buy group health insurance for my company"),
    ("upper_funnel_depth", "I am confused about deductibles in health insurance, how does a super top-up actually start paying?"),
    ("upper_funnel_depth", "How do waiting periods work in health insurance policies in India?"),
    ("upper_funnel_depth", "I'm buying health insurance for the first time in India—what should I understand before choosing a policy?"),
    ("upper_funnel_depth", "Why do people say health insurance is essential even if I already have savings?"),
    ("upper_funnel_depth", "How does a personal accident policy work in India if an accident causes disability instead of death?"),
    ("upper_funnel_breadth", "what is medical insurance"),
    ("upper_funnel_breadth", "what is not covered in health insurance"),
    ("upper_funnel_breadth", "how much health insurance cover is enough in india"),
    ("upper_funnel_breadth", "difference between top-up and super top-up health insurance"),
    ("upper_funnel_breadth", "what is the difference between health insurance and mediclaim"),
    ("upper_funnel_breadth", "benefits of health insurance"),
    ("upper_funnel_breadth", "what is deductible in health insurance"),
    ("upper_funnel_breadth", "what is a waiting period in health insurance"),
    ("mid_funnel_depth", "What's the best health insurance policy in India if I want fewer surprises at claim time?"),
    ("mid_funnel_depth", "what should I compare before buying a health insurance top-up plan"),
    ("mid_funnel_depth", "best health insurance in India if claim experience matters more than premium"),
    ("mid_funnel_depth", "Should I port my policy after a bad claims experience or just buy a new health insurance plan?"),
    ("mid_funnel_depth", "How to choose health insurance for parents with diabetes, BP, or heart history"),
    ("mid_funnel_depth", "best health insurance plans in India for pre-existing diseases after waiting period"),
    ("mid_funnel_depth", "How to choose between Digit, HDFC Ergo, and Niva Bupa for online health insurance"),
    ("mid_funnel_depth", "Best health insurance companies in India for portability and waiting period continuity"),
    ("mid_funnel_depth", "Digit vs Care Health insurance for online quotes and premium value"),
    ("mid_funnel_depth", "which group health insurance companies are better for cashless claims in india"),
    ("mid_funnel_breadth", "how to compare health insurance plans for senior citizens"),
    ("mid_funnel_breadth", "cost of group health insurance for employees in india"),
    ("mid_funnel_breadth", "best health insurance plans for senior citizens in india"),
    ("mid_funnel_breadth", "how to compare health insurance company when porting a policy"),
    ("mid_funnel_breadth", "top-up vs super top-up health insurance which is better"),
    ("mid_funnel_breadth", "best super top-up health insurance plans in india"),
    ("mid_funnel_breadth", "Digit vs HDFC Ergo health insurance for OPD cover"),
    ("mid_funnel_breadth", "super top-up health insurance premium comparison"),
    ("lower_funnel_depth", "How long does Digit take to issue a health insurance policy after online payment"),
    ("lower_funnel_depth", "Does Digit health insurance have co-pay for senior citizen parents"),
    ("lower_funnel_depth", "Does Digit health insurance cover parents with diabetes or hypertension at purchase"),
    ("lower_funnel_depth", "does Digit health insurance cover pre-existing diseases after waiting period"),
    ("lower_funnel_depth", "Does Digit health insurance give waiting period credit when I port from another insurer?"),
    ("lower_funnel_depth", "does Digit health insurance offer online policy issuance without agent follow-up"),
    ("lower_funnel_depth", "Can I port my existing policy to Digit if I have a pre-existing disease and previous claims?"),
    ("lower_funnel_breadth", "digit health insurance room rent limit"),
    ("lower_funnel_breadth", "Digit senior citizen health insurance waiting period"),
    ("lower_funnel_breadth", "digit health insurance pre existing disease waiting period"),
    ("lower_funnel_breadth", "digit health insurance claim settlement time"),
    ("lower_funnel_breadth", "digit health insurance pricing for family floater"),
    ("lower_funnel_breadth", "digit health insurance cashless claim process"),
    ("lower_funnel_breadth", "digit health insurance co payment"),
    ("post_purchase_depth", "My Digit health insurance app is not showing my policy correctly—what should I do?"),
    ("post_purchase_depth", "How do I renew my Digit health insurance policy without losing continuity benefits?"),
    ("post_purchase_depth", "I already have Digit health insurance — how do I claim OPD expenses for doctor consultation and medicines?"),
    ("post_purchase_depth", "Why was my Digit health insurance claim rejected and how can I appeal it?"),
    ("post_purchase_depth", "My parents are covered by Digit — how do I submit reimbursement if the hospital was not cashless?"),
]

# Prompts not in digit_all_groups (wording variants) → intent_id
MANUAL_INTENT: dict[str, str] = {
    "what is medical insurance": "general_health_insurance_policies",
    "what is not covered in health insurance": "general_health_insurance_policies",
    "how much health insurance cover is enough in india": "general_health_insurance_policies",
    "difference between top-up and super top-up health insurance": "top_up_plans",
    "what is the difference between health insurance and mediclaim": "general_health_insurance_policies",
    "benefits of health insurance": "general_health_insurance_policies",
    "what is deductible in health insurance": "top_up_plans",
    "what is a waiting period in health insurance": "general_health_insurance_policies",
    "how to compare health insurance plans for senior citizens": "family_and_senior_coverage",
    "cost of group health insurance for employees in india": "group_employer_health_insurance",
    "best health insurance plans for senior citizens in india": "family_and_senior_coverage",
    "how to compare health insurance company when porting a policy": "portability_and_transfer",
    "best super top-up health insurance plans in india": "top_up_plans",
    "digit vs hdfc ergo health insurance for opd cover": "opd_coverage",
    "super top-up health insurance premium comparison": "top_up_plans",
    "digit health insurance room rent limit": "general_health_insurance_policies",
    "digit senior citizen health insurance waiting period": "family_and_senior_coverage",
    "digit health insurance pre existing disease waiting period": "general_health_insurance_policies",
    "digit health insurance claim settlement time": "general_health_insurance_policies",
    "digit health insurance pricing for family floater": "family_and_senior_coverage",
    "digit health insurance cashless claim process": "general_health_insurance_policies",
    "digit health insurance co payment": "family_and_senior_coverage",
}


def norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def main() -> None:
    digit = json.loads(DIGIT.read_text(encoding="utf-8"))
    intent_meta = {i["intent_id"]: i for i in digit["intents"]}
    prompt_to_intent: dict[str, dict] = {}
    for intent in digit["intents"]:
        for p in intent["prompts"]:
            prompt_to_intent[norm(p)] = intent

    by_intent: dict[str, list[dict]] = {}
    funnel_map: dict[str, str] = {}

    for funnel, prompt in SUBSAMPLE:
        key = norm(prompt)
        intent = prompt_to_intent.get(key)
        if intent is None:
            iid = MANUAL_INTENT.get(key)
            if not iid:
                raise SystemExit(f"No intent mapping for: {prompt}")
            intent = intent_meta[iid]
        iid = intent["intent_id"]
        by_intent.setdefault(iid, []).append({"prompt": prompt.strip(), "funnel_segment": funnel})
        funnel_map[prompt.strip()] = funnel

    intents_out = []
    for iid in [
        "general_health_insurance_policies",
        "family_and_senior_coverage",
        "top_up_plans",
        "group_employer_health_insurance",
        "portability_and_transfer",
        "online_purchasing_and_quotes",
        "opd_coverage",
        "personal_accident_insurance",
    ]:
        items = by_intent.get(iid)
        if not items:
            continue
        meta = intent_meta[iid]
        intents_out.append({
            "intent_name": meta["intent_name"],
            "intent_id": iid,
            "prompts": [x["prompt"] for x in items],
        })

    payload = {
        "company_name": digit.get("company_name", "Digit Insurance"),
        "description": "Stratified subsample of 55 prompts (funnel × depth/breadth)",
        "intents": intents_out,
        "funnel_segment_by_prompt": funnel_map,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"Intents: {len(intents_out)}, prompts: {sum(len(i['prompts']) for i in intents_out)}")
    for i in intents_out:
        print(f"  {i['intent_id']}: {len(i['prompts'])}")


if __name__ == "__main__":
    main()
