#!/usr/bin/env python3
"""Build runs/tina_davies_100/ — Tina Davies brand, 100 prompts / 10 intent topics."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "tina_davies_100"
RUN_DIR = ROOT / "runs" / RUN_ID

PROMPTS_BY_TOPIC: dict[str, list[str]] = {
    "Aftercare & Post-Procedure Support": [
        "After using Tina Davies PIXL needles for brow PMU, what aftercare should clients follow?",
        "How long should I wait before applying makeup after a Tina Davies lip blushing procedure?",
        "Is aftercare guidance included in The Collective+ for Tina Davies PMU procedures?",
        "My client experienced excessive swelling after Tina Davies lip blushing, what aftercare steps?",
        "What are the aftercare steps for Tina Davies brow procedures?",
        "What's the best aftercare for microblading with Tina Davies pigments?",
        "What's the difference between Tina Davies' lip blushing and brow aftercare protocols?",
        "Where can I buy Tina Davies PMU aftercare products in the US?",
        "Why is my client's Tina Davies brow pigment not retaining color after aftercare?",
        "how 2 handle dry healing with tina davies lip blushing?",
    ],
    "Application Techniques & Best Practices": [
        "any tricks to make tina davies pigments heal brighter?",
        "Best Tina Davies pigment for clients with dry skin",
        "Does The Collective+ cover advanced PMU correction?",
        "How to avoid pigment blowout with lip blushing?",
        "How to create natural hair strokes with PIXL needle cartridges?",
        "Layering Tina Davies lip pigments for ombré effect",
        "Optimal dipping depth for Tina Davies brow pigments",
        "Tina Davies aftercare protocol for new clients",
        "Tina Davies brow pigment retention tips",
        "What needle cartridge is best for soft powder brows using Tina Davies pigments?",
    ],
    "Brand & Product Comparison": [
        "Best pigment for microblading: Tina Davies or Phi Beauty?",
        "How do Tina Davies brow pigments compare to Everlasting Brows?",
        "Is Tina Davies or Magic Pigment better for nano brow healing results?",
        "TDPMU vs Microbeau machines",
        "Tina Davies Collective+ membership worth it compared to other brands' courses?",
        "Tina Davies pigment cost per ml vs competitors",
        "Tina Davies PIXL needles versus standard cartridges for ombré brows",
        "Tina Davies vs Perma Blend for lip pigments",
        "tinadavies vs permablnd for lip blushing",
        "Which lasts longer, Tina Davies or Perma Blend pigments?",
    ],
    "Education & Training Services": [
        "Any free tutorials on lip blushing from Tina Davies?",
        "As a beginner PMU artist, what courses does Tina Davies offer for learning microblading and brow techniques?",
        "Best Tina Davies course for ombre powder brows",
        "Can I get certified in permanent makeup through Tina Davies' online courses for brow and lip techniques?",
        "Does The Collective+ include live Q&A sessions on brow techniques?",
        "how 2 join Tina Davies Collective+ for PMU",
        "How much is The Collective+ membership for PMU artists in the US?",
        "PMU lip neutralization workshop schedule",
        "Tina Davies brow courses",
        "Tina Davies online learning platform certification for permanent makeup",
    ],
    "Equipment & Tool Evaluation": [
        "Are Tina Davies tools compatible with all PMU pigment brands?",
        "Can you compare the precision and longevity of Tina Davies PIXL needle cartridges versus standard needles for permanent makeup applications?",
        "Do Tina Davies machines come with warranty for PMU studios?",
        "how 2 choose tina davies needle size for brows",
        "How do I determine the best Tina Davies needle cartridge configuration for different permanent makeup techniques?",
        "How durable are Tina Davies microblades for daily PMU work?",
        "PIXL vs regular needles for microblading",
        "Tina Davies 16 Curved Nano lip blushing",
        "Tina Davies PIXL needles microblading",
        "What is the difference between Tina Davies PIXL-ated performance needles and their standard microblades for brow work?",
    ],
    "Industry Awareness & Career Exploration": [
        "how 2 become PMU artist",
        "How long does permanent makeup last?",
        "How long is the healing process for lip blushing?",
        "How to start a PMU career in the United States?",
        "Is microblading safer than machine brows?",
        "PMU safety standards",
        "What are common side effects of PMU?",
        "What are the key factors that affect the longevity of PMU pigments on different skin types?",
        "What is lip blushing and what to expect?",
        "What is PMU?",
    ],
    "Membership Value & Community Access": [
        "Can I access all permanent makeup courses with Tina Davies Collective+ membership, including microblading?",
        "collective+ membership benefits for pmu artists",
        "Collective+ vs buying courses separately for PMU education",
        "Does The Collective+ offer discounts on machines and pigments?",
        "How does Collective+ community support lip blushing training?",
        "How often does Tina Davies update The Collective+ content with new pigment techniques and aftercare guides?",
        "Is Collective+ worth it for PMU?",
        "PMU artist Collective+ review",
        "Tina Davies membership value",
        "What's included in The Collective+ for brow artists?",
    ],
    "Pigment Selection & Color Matching": [
        "Got a client with red undertones, what brow pigment to use?",
        "How to select the right Tina Davies pigment for a client with warm skin tones and dark hair?",
        "Is FADE or Perma Blend pigment better for neutral brows?",
        "Olive skin brow pigment",
        "Pigments for microblading on mature skin",
        "PMU artist seeking pigment for lip blushing on pale skin",
        "Tina Davies I INK pigment for dark skin tones?",
        "tinadavies pigment for cool brow tones",
        "What are the best permanent makeup pigments from Tina Davies for clients with golden undertones and freckles?",
        "What lip blushing pigment for cool undertones?",
    ],
    "Pricing & Budget Considerations": [
        "Are Tina Davies pigments affordable for new PMU artists?",
        "As a PMU studio owner, how much should I allocate in my budget for Tina Davies pigments, machines, and membership fees each year?",
        "how much do tinadavies pigments cost",
        "How much is The Collective+ membership for PMU artists?",
        "Tina Davies pigment cost",
        "Tina Davies Pigments USD price list for permanent makeup",
        "Tina Davies PMU supplies pricing",
        "Tina Davies pricing in US dollars for brow pigments",
        "What are the prices for Tina Davies brow pigments and lip blushing pigments including any discounts for bulk orders?",
        "What's the budget for a full Tina Davies pigment set?",
    ],
    "Product Quality, Safety & Compliance": [
        "Are Tina Davies pigments safe for sensitive skin?",
        "Are Tina Davies PMU pigments FDA approved?",
        "Can Tina Davies demonstrate that their lip blushing pigments are free from allergens and comply with all regulatory requirements for cosmetic tattooing?",
        "Do Tina Davies brow pigments comply with international safety guidelines?",
        "FDA approval for Tina Davies PMU pigments",
        "How does Tina Davies test ingredients in lip blushing pigments?",
        "Ingredient list for Tina Davies microblading pigments",
        "Tina Davies organic pigments",
        "What certifications does Tina Davies have for brow pigments?",
        "What specific steps does Tina Davies take in their quality control process to ensure that every batch of pigments meets the highest safety and consistency standards for permanent makeup artists?",
    ],
}


def slug_topic(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")[:96] or "cluster"


def main() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    company = {
        "company_name": "Tina Davies",
        "aliases": ["Tina Davies PMU", "TDPMU", "Tina Davies Professional"],
        "description": "Tina Davies is a professional permanent makeup brand offering pigments, PIXL needles, machines, education (including The Collective+), and supplies for brow, lip, and cosmetic tattoo artists.",
        "industry": "Beauty & Cosmetics",
        "sub_industry": "Permanent Makeup (PMU) & Professional Supplies",
        "products_services": [
            {
                "name": "PMU pigments & education",
                "description": "Brow and lip pigments, I INK and collections; online training and Collective+ membership.",
                "key_features": ["PIXL needles", "The Collective+"],
                "target_users": ["PMU artists", "studios"],
                "pricing_notes": None,
            }
        ],
        "customer_personas": [
            {
                "name": "PMU professional",
                "role": "Permanent makeup artist",
                "seniority": None,
                "goals": ["quality results", "client safety", "ongoing education"],
                "pains": ["product selection", "aftercare compliance"],
                "typical_workflow": "Consultation, procedure, aftercare",
                "constraints": [],
            }
        ],
        "primary_geos": ["United States", "Global"],
        "primary_languages": ["en"],
        "competitors": [
            {"name": "Perma Blend", "aliases": [], "notes": None},
            {"name": "Microbeau", "aliases": [], "notes": None},
        ],
        "differentiators": ["PIXL needles", "The Collective+", "brand education"],
        "common_misconceptions": [],
        "regulated_or_sensitive_topics": ["tattoo", "PMU", "FDA", "cosmetic regulations"],
        "seed_queries": [],
        "must_include_terms": [],
        "must_avoid_terms": [],
        "explicit_keywords": [
            "Tina Davies",
            "Tina Davies PMU",
            "PIXL",
            "The Collective+",
            "TDPMU",
        ],
    }
    (RUN_DIR / "company_profile.json").write_text(
        json.dumps(company, indent=2), encoding="utf-8"
    )

    cluster_slugs = {name: slug_topic(name) for name in PROMPTS_BY_TOPIC}
    clusters = []
    for name in PROMPTS_BY_TOPIC:
        cid = cluster_slugs[name]
        first_p = PROMPTS_BY_TOPIC[name][0]
        clusters.append(
            {
                "cluster_id": cid,
                "name": name,
                "user_mindset": f"Researching {name.lower()} for Tina Davies PMU.",
                "example_prompt": first_p,
                "description": None,
            }
        )
    plan = {
        "rationale": "Manual intent clusters for Tina Davies 100-prompt list.",
        "clusters": clusters,
    }
    (RUN_DIR / "intent_cluster_plan.json").write_text(
        json.dumps(plan, indent=2), encoding="utf-8"
    )

    lines_out: list[str] = []
    idx = 0
    for topic, prompts in PROMPTS_BY_TOPIC.items():
        cid = cluster_slugs[topic]
        for p in prompts:
            rec = {
                "prompt_id": f"prm_td_{idx:04d}",
                "prompt": p,
                "intent_cluster_id": cid,
                "intent_cluster_name": topic,
                "weight": 1.0,
            }
            lines_out.append(json.dumps(rec, ensure_ascii=False))
            idx += 1

    (RUN_DIR / "synthetic_prompts.jsonl").write_text(
        "\n".join(lines_out) + "\n", encoding="utf-8"
    )

    print(f"Wrote {RUN_DIR}/company_profile.json")
    print(f"Wrote {RUN_DIR}/intent_cluster_plan.json ({len(clusters)} clusters)")
    print(f"Wrote {RUN_DIR}/synthetic_prompts.jsonl ({len(lines_out)} prompts)")
    print()
    print(
        f"cd {ROOT} && PYTHONPATH=src python -m case2_demand.cli run-all "
        f"--from-run {RUN_ID} --location 2356 --language en --with-calibration"
    )


if __name__ == "__main__":
    main()
