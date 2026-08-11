# AI Demand Scorecards — Design & Process

**Audience:** Managers, sales, CS  
**Date:** August 2026  
**Samples:** *Approach 1 — Client Specific* · *Approach 2 — Industry* · [Feasibility & cost detail](./scorecard-feasibility.md)

---

## What this is

Standalone HTML reports that show how buyers discover and evaluate brands via AI assistants (ChatGPT, Gemini). Runs on a **lite pipeline** — not full product onboarding.

| | Approach 1 — Company | Approach 2 — Industry |
|---|---|---|
| **Question** | How visible is **this company** vs competitors? | How is **category demand** split — and what’s unclaimed? |
| **Brands** | 1 focal + ~5 competitors | 5–10 peers, no focal |
| **Prompts** | 25 (5 discovery / 15 evaluation / 5 decision) | 100 non-branded (30 / 70 discovery–evaluation) |
| **Unique sections** | AI Readiness, focal financial impact | Opportunity pools, claimed/unclaimed, heatmap |

---

**Pilot measured (Aug 2026 — Beauty & Skincare, US, 5 peers, 20-prompt cap, single pass):**

| Step | Time |
|---|---|
| Brand/topic bootstrap | ~10 sec |
| Prompt generation | ~3.5 min |
| Volume estimation | ~30 sec |
| AI responses (20 prompts × 2 models) | ~11 min |
| Report assembly | ~instant |
| **Automated total** | **~15 min** |

---

## Process (both approaches)

```
Inputs confirmed → Brand/topic setup → Prompts → Volume + AI responses → HTML report → QA → Send
```

| Stage | What happens | Owner |
|---|---|---|
| **1. Inputs** | Geo, brand URL *or* industry + peer list, AOV | Sales |
| **2. Setup** | Research context, competitors/themes, seed keywords | System (~1 min) |
| **3. Prompts** | Generate buyer questions with funnel mix | System (~3–4 min) |
| **4. Measure** | Volume lookup; ChatGPT + Gemini responses; score mentions & citations | System (scales with prompt count) |
| **5. Deliver** | Aggregate metrics, render HTML, human review | Ops + reviewer |

**Skipped vs full product:** deep crawl, social, opportunity/L2–L3 workflows, open-ended fan-out.

**Delivery:** HTML report; ops views via admin on **app.gravton.ai**.

---

## Approach 1 — Company scorecard

**Story:** “Your brand vs rivals in AI search.”

**Tabs:** Overview · Prompt results · Sources & competitors · AI Readiness & financial impact

**Hero metrics:** AI Consideration Score · rank · discovery/evaluation win rates · presence · share of voice · won/shared/lost demand · modeled $ gap

**Inputs:** Company name + URL · market · ~5 competitors · AOV / conversion (optional)

---

## Approach 2 — Industry scorecard

**Story:** “Category demand map — who owns it, what’s open.”

**Tabs:** Industry overview · Opportunity pools · Competitor benchmark

**Hero metrics:** Category demand · claimed vs unclaimed % · concentration · opportunity pools + heatmap · peer leaderboard · commercial pool ($)

**Inputs:** Industry name · 5–10 peer brands (name + domain) · market · category AOV

**Pilot output (Beauty & Skincare, 20-cap):** claimed **1.5%** / unclaimed **98.5%**; 5 opportunity pools; 5-brand leaderboard.

**Tip:** Run Approach 2 once per vertical, then Approach 1 reports in that vertical to reuse themes.

---

## QA before send

- [ ] Competitor/peer list approved  
- [ ] Prompt count and funnel mix look right  
- [ ] Financial section shows assumptions  
- [ ] Narrative framed as **modeled opportunity**, not guaranteed revenue  

---

## When to use which

| Situation | Use |
|---|---|
| Active deal, named prospect | **Approach 1** |
| Category entry, investor deck, vertical GTM | **Approach 2** |
| Tight budget / first proof | **Approach 2 at 20 prompts** (~$8–12, ~1–1.5 hrs) |

---

## Glossary

| Term | Meaning |
|---|---|
| **Prompt** | Realistic buyer question typed into an AI assistant |
| **Discovery / Evaluation / Decision** | Top / mid / bottom funnel |
| **Claimed demand** | Prompts where at least one tracked brand appears in AI answers |
| **Unclaimed demand** | Prompts where no tracked brand appears |
| **Opportunity pool** | Themed demand cluster in an industry report |

---

*Reference layouts: `Approach 1 - Client Specific.html`, `Approach 2 - Industry.html`*
