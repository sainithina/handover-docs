#!/usr/bin/env python3
"""Seed run: Duroflex / mattress intent prompts (130 rows, 13 clusters)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TOPICS = [
    "Sleep-Health Connection",
    "Back Pain & Spinal Problems",
    "Mattress Types & Materials",
    "Orthopedic Mattress Selection",
    "Pricing & Value Assessment",
    "Smart & Adjustable Sleep Technology",
    "Duroflex vs D2C Challengers",
    "Duroflex vs Legacy Brands",
    "Purchase De-risking & Warranty",
    "Institutional & Bulk Procurement",
    "Mattress Care & Maintenance",
    "Quality Issues & Warranty Claims",
    "Upgrade & Add-On Purchases",
]

PROMPTS = [
    "How does poor sleep quality affect long-term physical health and productivity at work?",
    "Why do I wake up with body aches even after sleeping eight hours every night?",
    "What are the proven health risks of sleeping on an old or unsupportive mattress?",
    "How much does sleep quality affect recovery time after exercise or injury?",
    "Can the surface I sleep on cause or worsen lower back pain over time?",
    "What does scientific research say about the connection between mattress quality and sleep depth?",
    "How do I know if my current mattress is causing my sleep problems or if it is something else?",
    "What happens to my spine when I sleep on a surface that is too soft or too hard?",
    "Are there specific sleep postures that reduce back strain during the night?",
    "My partner and I have different firmness preferences—how does that affect our sleep quality?",
    "What type of sleeping surface is recommended for people with chronic lower back pain?",
    "Can a new mattress actually reduce back pain, and what evidence supports that?",
    "I have a herniated disc—what firmness level should I look for in a mattress?",
    "What do orthopedic doctors recommend for people who sit at a desk all day and have back pain?",
    "Is a hard mattress or a firm orthopedic mattress better for spine alignment?",
    "How does mattress material—foam, latex, or spring—affect back pain differently?",
    "What is an orthopedic mattress and how is it different from a regular mattress?",
    "I wake up with stiff shoulders and neck pain every morning—could my mattress be the cause?",
    "Which mattress materials are medically validated for spinal support in India?",
    "Does sleeping on a mattress that is too old cause permanent damage to your back posture?",
    "What is the difference between memory foam, latex, coir, and pocket spring mattresses?",
    "Which mattress material lasts the longest and provides the best value over ten years?",
    "Is a latex mattress worth the higher price compared to memory foam in India?",
    "How do I choose between a coir mattress and a foam mattress for the Indian climate?",
    "What are the advantages and disadvantages of pocket spring mattresses for couples?",
    "Are natural latex mattresses better for people with allergies or sensitive skin?",
    "What is a hybrid mattress and is it better than pure memory foam for daily use?",
    "How does mattress thickness affect sleep quality, and what thickness is right for my weight?",
    "What is the difference between high-density foam and memory foam, and which is more durable?",
    "Which mattress type is most suitable for hot and humid conditions in South India?",
    "What makes Duroflex Duropedic mattresses different from generic orthopedic mattresses?",
    "Is the Duroflex Posture Perfect mattress actually recommended by orthopedic doctors?",
    "What certifications or medical endorsements should I look for when buying an orthopedic mattress in India?",
    "How do I evaluate whether an orthopedic mattress claim is backed by clinical evidence?",
    "What is the difference between the Duroflex Balance and the Duroflex Strength mattress for back support?",
    "What firmness level is recommended for side sleepers with lower back pain?",
    "Does Duroflex offer customizable firmness options for couples with different sleep preferences?",
    "What is the National Health Academy endorsement in mattresses and which Indian brands have it?",
    "How does Duroflex's orthopedic range compare in terms of support layers versus standard foam?",
    "What mattress features specifically help with lumbar support for people who sleep on their back?",
    "What is the right budget for a good quality mattress in India for a queen-size bed?",
    "Is a mattress costing above Rs 20,000 significantly better than one in the Rs 10,000 to 15,000 range?",
    "What is the price range of Duroflex mattresses and what does each tier offer differently?",
    "What trial period and return policies should I expect when buying a mattress online in India?",
    "Are mattress EMI schemes worth it or is it better to pay the full price upfront?",
    "How long should a good quality mattress last and what is the effective cost per year of sleep?",
    "What warranty terms matter most when comparing mattress brands in India?",
    "Does Duroflex offer a 100-night trial and what are the conditions to return the mattress?",
    "Why is there such a wide price range in mattresses in India and what drives the cost difference?",
    "What should I prioritize if I have a budget of Rs 30,000 for a mattress: brand, technology, or material?",
    "What is an adjustable firmness mattress and how does it work mechanically?",
    "How does the Duroflex Airboost adjustable firmness mattress work and who is it designed for?",
    "What is the difference between the Duroflex Neuma and the Airboost range in terms of adjustability?",
    "Are smart adjustable beds in India worth the premium over a standard mattress and bed frame?",
    "What does the Duroflex Wave Plus adjustable bed offer in terms of positions and smart features?",
    "How does an electrically adjustable bed help people with acid reflux, snoring, or back pain?",
    "Can an adjustable mattress replace a traditional orthopaedic mattress for someone with a spinal condition?",
    "What is the price range for adjustable bed systems in India and which brands make them?",
    "Does Duroflex's smart bed system integrate with any health tracking apps or devices?",
    "What should I check before buying an adjustable bed to ensure it fits my existing bed frame?",
    "Wakefit vs The Sleep Company vs Sleepyhead: which is the best value mattress brand for an urban Indian buyer?",
    "How does Wakefit's Orthopedic Memory Foam mattress compare to SmartGRID from The Sleep Company?",
    "Is Sleepyhead a good alternative to Wakefit for someone on a budget looking for a foam mattress?",
    "How does Duroflex justify its premium pricing compared to Wakefit which offers similar specs at lower cost?",
    "Does The Sleep Company SmartGRID technology outperform traditional memory foam for hot sleepers?",
    "Duroflex Livein Duropedic vs Wakefit Orthopedic Memory Foam: which has better back support for under Rs 15,000?",
    "Which D2C mattress brand in India has the best after-sales service and warranty claim process?",
    "Duroflex vs Wakefit: which has better long-term durability and which one is better for heavy users?",
    "What do real users say about The Sleep Company vs Sleepyhead after 12 to 24 months of use?",
    "Why would someone choose Duroflex over newer D2C brands that offer aggressive pricing and trials?",
    "Sleepwell vs Kurlon: which is the more trusted legacy brand for orthopedic support in India?",
    "How does Duroflex compare against Sleepwell for long-term durability in the Rs 15,000 to 30,000 range?",
    "Is Kurlon still worth buying or have newer brands caught up in quality for spring mattresses?",
    "Duroflex vs Sleepwell: which brand has better availability of experience stores across India?",
    "How does Sleepwell's Ortho IQ technology compare to Duroflex's National Health Academy endorsed range?",
    "What are the practical differences between Duroflex and Sleepwell for someone replacing a 10-year-old coir mattress?",
    "Kurlon vs Sleepwell for a double bed under Rs 20,000: which offers better value for money?",
    "Does Duroflex or Sleepwell have a stronger product range for senior citizens with joint pain?",
    "Which brand—Sleepwell, Kurlon, or Duroflex—is better for a first mattress purchase in a tier-2 city?",
    "What advantages does Duroflex hold over Sleepwell in the premium mattress segment above Rs 40,000?",
    "What are the exact terms of Duroflex's 100-night mattress trial and how do I initiate a return?",
    "How long does Duroflex take to deliver a mattress and what does the setup process involve?",
    "What mattress warranty terms should I insist on before making a final purchase decision?",
    "Does Duroflex provide white-glove delivery and old mattress removal service across all cities?",
    "What does Duroflex's 10-year warranty cover and what reasons for defects are excluded?",
    "What are the red flags to watch for in online mattress return policies before I commit to a purchase?",
    "Does Duroflex offer bulk order discounts and custom size mattresses for home renovation projects?",
    "Can I test a Duroflex mattress in a physical store before ordering online in Pune or Mumbai?",
    "What financing or no-cost EMI options are available for buying a premium mattress above Rs 30,000?",
    "If I order a Duroflex mattress online, how is it packaged and will it fit through a standard apartment door?",
    "Does Duroflex supply mattresses to hotels and hospitals and what is the institutional pricing process?",
    "What specifications should a procurement manager look for when buying mattresses for a 100-room hotel?",
    "Can Duroflex provide custom size mattresses for non-standard bed frames in a boutique hotel project?",
    "What certifications and quality standards should hospital-grade mattresses meet in India?",
    "What is the minimum order quantity for Duroflex's institutional mattress supply program?",
    "Which mattress brands in India have dedicated B2B procurement teams and volume pricing for corporates?",
    "Does Duroflex offer after-installation service contracts for institutional clients?",
    "How long does bulk mattress procurement typically take from order to delivery in India?",
    "What fireproofing or antimicrobial certifications does Duroflex offer for hospitality-grade mattresses?",
    "How should a facilities manager evaluate total cost of ownership when buying mattresses for corporate housing?",
    "How often should I rotate or flip my Duroflex mattress to prevent sagging?",
    "What is the best way to clean a spill from a Duroflex memory foam mattress without damaging it?",
    "Does my Duroflex mattress need a mattress protector and which ones are compatible?",
    "My Duroflex mattress has a slight chemical smell after unboxing—is this normal and how long does it last?",
    "Can I use an electric blanket on my Duroflex foam mattress safely?",
    "How do I store my Duroflex roll-pack mattress if I need to move homes without damaging it?",
    "What bed frame or foundation does Duroflex recommend to maintain the warranty on my mattress?",
    "Is it normal for a new Duroflex mattress to feel firmer in the first few weeks than the store sample?",
    "How do I use the Duroflex app or website to track my warranty registration for my mattress?",
    "My Duroflex mattress feels warmer than expected—what can I do to improve airflow and cooling?",
    "My Duroflex mattress is sagging in the middle after 18 months—is this covered under warranty?",
    "How do I file a warranty claim with Duroflex and how long does the replacement process take?",
    "My Duroflex mattress has a persistent odor even after 3 months—what should I do?",
    "The firmness of my Duroflex Airboost mattress has changed—is that a defect or normal wear?",
    "Duroflex customer care is not responding to my warranty complaint—what are my options?",
    "My Duroflex delivery arrived damaged—what is the process to report this and get a replacement?",
    "The cover fabric on my Duroflex mattress is tearing after one year of use—is this a warranty defect?",
    "I returned my Duroflex mattress within the trial period but have not received my refund—what should I do?",
    "My Duroflex pocket spring mattress is making a squeaking noise—is this repairable or is it a defect?",
    "The Duroflex adjustable bed remote is not working—is this covered under the smart bed warranty?",
    "I have a Duroflex mattress and want to upgrade to an adjustable bed—which Duroflex beds are compatible?",
    "What Duroflex pillows are recommended to complement a Duropedic orthopedic mattress?",
    "My Duroflex mattress is 7 years old—should I upgrade or replace it with the same model?",
    "Does Duroflex offer trade-in or upgrade discounts for existing customers buying a new mattress?",
    "I bought a Duroflex mattress last year—which Duroflex recliners pair well with the ergonomic support it provides?",
    "What is the difference between the Duroflex Livein series I own and the current Duropedic line—is it worth upgrading?",
    "Does Duroflex have a loyalty program or repeat-customer discount for buying a second mattress for another room?",
    "My Duroflex mattress is still good but I want to add a mattress topper—which ones does Duroflex recommend?",
    "I am furnishing a new flat and already own a Duroflex mattress—what sofa or bed frame does Duroflex suggest?",
    "Is the Duroflex Sleepyhead brand a lower-cost alternative if I want to buy a second mattress for a guest room?",
]


def slug(topic: str) -> str:
    s = topic.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")[:80]


def main() -> None:
    assert len(TOPICS) == 13 and len(PROMPTS) == 130, (len(TOPICS), len(PROMPTS))

    run_id = "duroflex_mattress_batch_20260329"
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    profile = {
        "company_name": "Duroflex",
        "aliases": ["Duroflex India", "Duroflex mattresses"],
        "description": "Indian mattress and sleep solutions brand: Duropedic orthopedic range, memory foam, latex, adjustable Airboost/Neuma/Wave Plus, D2C and retail presence, institutional supply.",
        "industry": "Consumer durables",
        "sub_industry": "Mattresses & sleep products",
        "products_services": [
            {
                "name": "Mattresses",
                "description": "Orthopedic Duropedic, Livein, pocket spring, latex, adjustable smart beds.",
                "key_features": ["Duropedic", "Airboost", "National Health Academy endorsement", "100-night trial"],
                "target_users": ["Urban Indian households", "Hotels", "Institutions"],
                "pricing_notes": None,
            }
        ],
        "customer_personas": [
            {
                "name": "Home buyer",
                "role": "Consumer",
                "seniority": None,
                "goals": ["Back support", "Value", "Warranty clarity"],
                "pains": ["Too many brands", "Online vs store"],
                "typical_workflow": None,
                "constraints": [],
            }
        ],
        "primary_geos": ["India"],
        "primary_languages": ["en"],
        "competitors": [
            {"name": "Wakefit", "aliases": [], "notes": None},
            {"name": "Sleepwell", "aliases": [], "notes": None},
            {"name": "Kurlon", "aliases": [], "notes": None},
            {"name": "The Sleep Company", "aliases": [], "notes": None},
            {"name": "Sleepyhead", "aliases": [], "notes": None},
        ],
        "differentiators": [],
        "common_misconceptions": [],
        "regulated_or_sensitive_topics": [],
        "seed_queries": [],
        "must_include_terms": [],
        "must_avoid_terms": [],
        "explicit_keywords": [],
    }
    (run_dir / "company_profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")

    lines = []
    for i, prompt in enumerate(PROMPTS):
        topic = TOPICS[i // 10]
        lines.append(
            json.dumps(
                {
                    "prompt_id": f"prm_duroflex_{i:03d}",
                    "prompt": prompt,
                    "intent_cluster_id": slug(topic),
                    "intent_cluster_name": topic,
                },
                ensure_ascii=False,
            )
        )
    (run_dir / "synthetic_prompts.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} prompts -> {run_dir / 'synthetic_prompts.jsonl'}")
    print(f"Run ID: {run_id}")


if __name__ == "__main__":
    main()
