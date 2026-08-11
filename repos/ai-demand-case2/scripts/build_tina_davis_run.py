#!/usr/bin/env python3
"""Build runs/tina_davis_pmu/ with company_profile + synthetic_prompts.jsonl for case2 run-all --from-run."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "tina_davis_pmu"
RUN_DIR = ROOT / "runs" / RUN_ID

# intent_cluster_name -> stable cluster id (slug)
CLUSTER_SLUG = {
    "Machine Brands": "machine_brands",
    "Mapping Tools": "mapping_tools",
    "PMU Cartridges": "pmu_cartridges",
    "PMU Machines": "pmu_machines",
    "PMU Numbing": "pmu_numbing",
    "PMU Pigment Brands": "pmu_pigment_brands",
    "PMU Pigments": "pmu_pigments",
    "PMU Tools": "pmu_tools",
    "Pigment Brands": "pigment_brands",
    "Pigment Selection": "pigment_selection",
    "Pigment Sets": "pigment_sets",
    "Pigment Types": "pigment_types",
    "Professional PMU Tools": "professional_pmu_tools",
    "Training Kits": "training_kits",
    "Wholesale PMU Supplies": "wholesale_pmu_supplies",
}

ROWS: list[tuple[str, str]] = [
    ("Machine Brands", "Microbeau Xion S alternatives"),
    ("Mapping Tools", "brow mapping string and tools"),
    ("PMU Cartridges", "membrane pmu cartridges"),
    ("PMU Machines", "pmu machine for ombre powder brows"),
    ("PMU Machines", "wireless pmu machine for lip blush"),
    ("PMU Numbing", "Zensa numbing cream alternatives for tattooing"),
    ("PMU Numbing", "anesthetic gel for lip blush and eyeliner"),
    ("PMU Numbing", "lidocaine numbing spray for permanent makeup"),
    ("PMU Numbing", "maximum strength pmu topical anesthetic"),
    ("PMU Numbing", "professional pmu numbing cream"),
    ("PMU Numbing", "secondary numbing for broken skin microblading"),
    ("PMU Pigment Brands", "EU REACH compliant pmu pigments"),
    ("PMU Pigment Brands", "Perma Blend vs Brow Daddy pigments"),
    ("PMU Pigment Brands", "best pmu pigments for ombre brows"),
    ("PMU Pigment Brands", "hybrid permanent makeup pigment brands"),
    ("PMU Pigment Brands", "medical grade permanent makeup ink"),
    ("PMU Pigment Brands", "professional permanent makeup ink manufacturers"),
    ("PMU Pigments", "Brow Daddy Gold Collection alternatives"),
    ("PMU Pigments", "Perma Blend vs Girlz Ink"),
    ("PMU Pigments", "high retention microblading pigments"),
    ("PMU Pigments", "permanent makeup ink for dark skin"),
    ("PMU Pigments", "permanent makeup ink for eyeliner"),
    ("PMU Pigments", "pigment color correction chart for pmu"),
    ("PMU Pigments", "pigment diluent for permanent makeup"),
    ("PMU Tools", "disposable microblading pens bulk"),
    ("Pigment Brands", "Girlz Ink vs Li Pigments"),
    ("Pigment Brands", "Nouveau Contour vs Perma Blend"),
    ("Pigment Brands", "Perma Blend vs Li Pigments"),
    ("Pigment Brands", "best cosmetic tattoo ink brands"),
    ("Pigment Selection", "best permanent makeup pigments"),
    ("Pigment Selection", "eyebrow tattoo ink sets"),
    ("Pigment Selection", "perma blend alternatives"),
    ("Pigment Sets", "lip blush pigment sets for professionals"),
    ("Pigment Types", "organic vs inorganic pmu pigments"),
    ("Professional PMU Tools", "microblading supplies for professionals"),
    ("Professional PMU Tools", "pmu cartridge needles"),
    ("Training Kits", "lip blush training kits for beginners"),
    ("Training Kits", "microblading tool kits for students"),
    ("Wholesale PMU Supplies", "microblading practice skins wholesale"),
    ("Wholesale PMU Supplies", "permanent makeup supplies wholesale"),
]

COMPANY_PROFILE = {
    "company_name": "Tina Davis",
    "aliases": ["Tina Davis PMU", "Tina Davis Professional"],
    "description": "Tina Davis is a professional permanent makeup (PMU) brand focused on pigments, machines, cartridges, numbing, training, and wholesale supplies for cosmetic tattoo artists.",
    "industry": "Beauty & Cosmetics",
    "sub_industry": "Permanent Makeup (PMU) & Cosmetic Tattoo Supplies",
    "products_services": [
        {
            "name": "PMU pigments & inks",
            "description": "Professional permanent makeup pigments, color correctors, and diluents.",
            "key_features": ["EU REACH options", "ombre brows", "lip blush", "eyeliner"],
            "target_users": ["PMU artists", "studios"],
            "pricing_notes": None,
        },
        {
            "name": "PMU machines & cartridges",
            "description": "Wireless and corded PMU devices, membrane cartridges, needles.",
            "key_features": ["lip blush", "ombre powder brows"],
            "target_users": ["PMU professionals"],
            "pricing_notes": None,
        },
    ],
    "customer_personas": [
        {
            "name": "PMU artist",
            "role": "Cosmetic tattoo professional",
            "seniority": None,
            "goals": ["quality pigments", "reliable machines", "client comfort"],
            "pains": ["product selection", "regulatory compliance"],
            "typical_workflow": "Consultation, procedure, aftercare",
            "constraints": [],
        }
    ],
    "primary_geos": ["United States", "Global"],
    "primary_languages": ["en"],
    "competitors": [
        {"name": "Perma Blend", "aliases": [], "notes": None},
        {"name": "Brow Daddy", "aliases": [], "notes": None},
        {"name": "Girlz Ink", "aliases": [], "notes": None},
    ],
    "differentiators": ["Professional-grade PMU focus", "Training and wholesale"],
    "common_misconceptions": [],
    "regulated_or_sensitive_topics": ["tattoo", "permanent makeup", "topical anesthetics"],
    "seed_queries": [],
    "must_include_terms": [],
    "must_avoid_terms": [],
    "explicit_keywords": [
        "Tina Davis",
        "Tina Davis PMU",
        "permanent makeup",
        "pmu pigments",
        "pmu machine",
    ],
}


def slug(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")[:80] or "cluster"


def main() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "company_profile.json").write_text(
        json.dumps(COMPANY_PROFILE, indent=2), encoding="utf-8"
    )

    clusters_out = []
    seen = set()
    for name in CLUSTER_SLUG:
        cid = CLUSTER_SLUG[name]
        if cid in seen:
            continue
        seen.add(cid)
        clusters_out.append(
            {
                "cluster_id": cid,
                "name": name,
                "user_mindset": f"Researching {name.lower()} for professional PMU.",
                "example_prompt": next(
                    (p for n, p in ROWS if n == name), ROWS[0][1]
                ),
                "description": None,
            }
        )

    plan = {
        "rationale": "Manual intent clusters for Tina Davis PMU prompt list.",
        "clusters": clusters_out,
    }
    (RUN_DIR / "intent_cluster_plan.json").write_text(
        json.dumps(plan, indent=2), encoding="utf-8"
    )

    lines = []
    for i, (intent_name, prompt_text) in enumerate(ROWS):
        cid = CLUSTER_SLUG[intent_name]
        rec = {
            "prompt_id": f"prm_tina_{i:04d}",
            "prompt": prompt_text,
            "intent_cluster_id": cid,
            "intent_cluster_name": intent_name,
            "weight": 1.0,
        }
        lines.append(json.dumps(rec, ensure_ascii=False))

    (RUN_DIR / "synthetic_prompts.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(f"Wrote {RUN_DIR}/company_profile.json")
    print(f"Wrote {RUN_DIR}/intent_cluster_plan.json ({len(clusters_out)} clusters)")
    print(f"Wrote {RUN_DIR}/synthetic_prompts.jsonl ({len(lines)} prompts)")
    print(f"\nRun: cd {ROOT} && PYTHONPATH=src python -m case2_demand.cli run-all --from-run {RUN_ID} --location 2356 --language en --with-calibration")


if __name__ == "__main__":
    main()
