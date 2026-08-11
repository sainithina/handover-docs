# AI Demand Scorecards — Feasibility & Implementation Plan

**For:** Tarun, Raoul, Sales  
**Author:** Sainithin  
**Date:** July 2026  
**Reference designs:** `Approach 1 - Client Specific.html` (company-specific) · `Approach 2 - Industry.html` (industry benchmark)

---

## Summary

Both scorecards can be generated **outside the product** using a **minimal backend workflow** that cherry-picks existing Gravton logic. We do **not** run full onboarding. We reuse site scan, prompt identification, volume estimation, response generation, and metric/citation read APIs — trimmed to the minimum needed for a credible report.

**Fastest path:** orchestrator script → lite DAG runs → aggregate JSON → fill HTML template → optional LLM narrative. **No PDF in v1.**

| | Approach 1 — Company-specific | Approach 2 — Industry benchmark |
|---|---|---|
| **Build time (v1 workflow)** | **~1.5–2 weeks** | **~2.5–3 weeks** (can share ~60% of infra with Approach 1) |
| **Data cost per report** | **~$15–40** | **~$50–120** |
| **Turnaround per report** | **4–8 hours** (mostly automated; prompt curation is manual) | **1–2 days** (more prompts + brands) |
| **Narrative (GPT/Claude)** | **~$0.50–2** | **~$1–3** |
| **PDF (later, optional)** | **~1–2 eng days** + design sign-off | Same |

---

## What each report needs (from sample HTML)

### Approach 1 — Company-specific (`NorthPeak` sample)

| Section | Data required | Existing Gravton source |
|---|---|---|
| **Overview** — AI Consideration Score, rank, discovery/evaluation win rates, presence, SOV, sentiment, won/shared/lost demand | Prompt-level metrics aggregated for 1 focal brand + 5 competitors | `insight_metrics` (visibility, SOV, position, sentiment), `demand_map`, `demand_universe` |
| **Prompt results** — 25 prompts with win/share/miss state + monthly volume | Curated prompt set + volume + response outcomes | Manual/LLM prompt list → `prompt_volume_dag` → `responses_dag` |
| **Sources & competitors** — leaderboard, top citation domains | Citation aggregation per brand | `citations/services.py`, citation performance APIs |
| **AI Readiness** — score for home / about / product pages | Lightweight site scan on 3 URLs | `technical_seo` (`seo_scan_dag`) — **optional slice, 3 pages only** |
| **Financial impact** — modeled $ from demand × conversion × AOV | Derived from volume totals + editable assumptions | Computed in scorecard layer (not in product today) |

**Default lite config:** 25 prompts · 2 models (ChatGPT + Gemini) · 6 brands · US geo.

---

### Approach 2 — Industry benchmark (`Beauty & Skincare` sample)

| Section | Data required | Existing Gravton source |
|---|---|---|
| **Industry overview** — category demand, claimed/unclaimed %, concentration, demand ownership stack | Aggregate across 100 non-branded prompts | `demand_universe`, `demand_map` distribution APIs |
| **Opportunity pools** — themed clusters, unclaimed %, leader per pool | Intent clusters + per-pool brand heatmap | `demand_universe` topics + custom pool aggregation |
| **Competitor benchmark** — 8-brand leaderboard, discovery/evaluation split, SOV, rank | Multi-brand metrics | `metrics_queries.py`, brand metrics APIs |
| **Sources** — top domains + source mix (UGC, retail, editorial) | Citation domain typing | `citations` enrichment + domain type classifier |
| **Commercial pool** — $ estimate with assumptions | Same formula as Approach 1, category-level | Scorecard layer |

**Default lite config:** 100 non-branded prompts · 2 models · 8 tracked brands · US geo.

---

## Recommended workflow (both approaches)

This runs **outside the product UI**. One engineer triggers it via CLI or internal admin script.

```
INPUT: company URL or industry name + competitor list + geo
  │
  ├─ 1. DOMAIN SETUP (lite)
  │     Create Domain row + 3–5 competitors
  │     Reuse: brandkit_dag OR manual competitor entry
  │     Skip: full crawl, product verticals, social ingestion
  │
  ├─ 2. PROMPT IDENTIFICATION (lite)
  │     Option A (fastest): human + ChatGPT/Claude curates prompt JSON
  │     Option B: shortened synthetic_prompt_dag (subset of intents)
  │     Output: 25 prompts (company) or 100 prompts (industry)
  │
  ├─ 3. VOLUME ESTIMATION
  │     Reuse: prompt_volume_dag OR Case2 CLI script
  │     Cost driver: DataForSEO keyword lookups
  │
  ├─ 4. AI RESPONSES (lite)
  │     Reuse: responses_dag — cap prompts, 2 models only
  │     Auto-triggers: citation_dag → insights_dag
  │     Skip: query_fanout, opportunity/L2-L3, social DAGs
  │
  ├─ 5. AGGREGATE SCORECARD JSON
  │     Reuse read layer — no new scoring math:
  │       • /metric/visibility, /metric/sov, /metric/sentiment
  │       • /demand-universe/summary, /demand-universe/topics
  │       • /citation/performance, /citation/share
  │     Add thin scorecard serializer (maps API shapes → HTML fields)
  │
  ├─ 6. AI READINESS (Approach 1 only)
  │     Reuse: seo_scan_dag limited to 3 pages
  │
  ├─ 7. NARRATIVE (optional, cheap)
  │     Pass scorecard JSON → ChatGPT or Claude
  │     Generate: industry conclusion, readiness issues summary
  │     Team subscriptions cover this — no API cost if manual paste
  │
  └─ 8. RENDER
        Fill Approach 1 or Approach 2 HTML template from JSON
        Deliver: static HTML file or guest share link
```

---

## What we reuse vs simplify vs build new

| Component | Reuse as-is | Simplify | Build new |
|---|---|---|---|
| Site / brand context | `brandkit_dag`, competitor model | Skip deep crawl; 1-page brand summary via LLM | — |
| Prompt identification | `SyntheticPrompt` model, intent APIs | Manual/LLM curation instead of full `synthetic_prompt_dag` | Prompt curation checklist for sales |
| Volume | `prompt_volume_dag`, Case2 bridge | Single geo, no calibration in v1 | — |
| AI visibility metrics | `metrics_queries.py`, demand APIs | Cap prompts + models | — |
| Citations / sources | `citations/services.py` | Top-5 domains only | Source-mix bucketing (UGC/retail/editorial) |
| AI Readiness | `technical_seo` | 3 pages only, not full site | Map SEO findings → readiness narrative |
| Delivery | Guest share JWT pattern | — | Scorecard orchestrator + HTML renderer |
| Financial modeling | — | — | Simple formula layer with exposed assumptions |

**Key principle (per Tarun):** reuse core logic, but never run the full pipeline.

---

## Time estimate — initial workflow build

Assumes 1 backend engineer, existing Airflow + API stack running.

### Shared foundation (do once) — ~1 week

| Task | Effort |
|---|---|
| `scorecard_run` management command (input → trigger DAGs → poll → export JSON) | 2 days |
| Scorecard JSON schema + aggregation from existing read APIs | 2 days |
| HTML template renderer (Jinja or simple string fill from JSON) | 1–2 days |

### Approach 1 add-on — ~3–5 days

| Task | Effort |
|---|---|
| Company prompt curation template + validation | 0.5 day |
| Competitor setup helper | 0.5 day |
| AI Readiness slice (3-page SEO scan hook) | 1–2 days |
| Financial impact calculator with assumption overrides | 1 day |
| End-to-end test on 1 sample company | 1 day |

### Approach 2 add-on — ~5–7 days

| Task | Effort |
|---|---|
| Industry prompt set workflow (100 non-branded) | 1 day |
| Opportunity pool clustering / grouping | 2 days |
| Brand × pool heatmap aggregation | 1–2 days |
| Category-level commercial pool rollup | 1 day |
| End-to-end test on 1 sample industry | 1 day |

**Total if building both:** ~3 weeks calendar (with overlap).  
**Total if Approach 1 only first:** ~2 weeks.

---

## Cost estimate — data generation per report

Rough order-of-magnitude for sales planning. Actuals depend on prompt count, model choice, and DataForSEO tier.

### Approach 1 — Company-specific (~25 prompts, 6 brands, 2 models)

| Step | Units | Est. cost |
|---|---|---|
| Domain / brand context (lite crawl or LLM) | 1 domain | $1–5 |
| Volume estimation (DataForSEO) | ~25–75 keyword lookups | $5–15 |
| LLM responses | 25 prompts × 2 models × 1 run | $3–10 |
| Citation extraction | Included in responses pipeline | $0 marginal |
| Insights / metrics compute | Internal | ~$0 |
| AI Readiness (3 pages) | 1 SEO scan | $2–5 |
| **Subtotal — data** | | **~$15–35** |
| Narrative (Claude/GPT from JSON) | 1 pass | $0–2 (or $0 via team subscription) |

### Approach 2 — Industry benchmark (~100 prompts, 8 brands, 2 models)

| Step | Units | Est. cost |
|---|---|---|
| Industry prompt curation | 100 prompts | $0–5 (mostly human/LLM assist) |
| Volume estimation | ~100–300 keyword lookups | $20–50 |
| LLM responses | 100 × 2 models | $12–35 |
| Citation + metrics | Internal | ~$0 |
| Pool / heatmap aggregation | Internal | ~$0 |
| **Subtotal — data** | | **~$50–90** |
| Narrative | 1 pass | $1–3 |

### Cost reduction levers (if too expensive)

1. **Fewer prompts** — 15 instead of 25 (company) cuts response cost ~40%
2. **Single model** — Gemini or ChatGPT only → halve LLM cost
3. **Skip AI Readiness** — saves $2–5 and ~2 hours (Approach 1)
4. **Reuse prompt sets within an industry** — amortize volume + response cost across multiple company reports in the same vertical
5. **Dry-run volume in dev** — `dry_run: true` for internal drafts (no DataForSEO spend)

---

## Narrative generation — assumption check

**Tarun's assumption is correct:** once structured data exists, narrative is inexpensive.

| Method | Cost | Speed | Quality |
|---|---|---|---|
| Paste JSON into ChatGPT / Claude (team subscription) | **$0 marginal** | 10–15 min | Good for v1 |
| API call (Claude Sonnet / GPT-4o) with scorecard JSON | **~$0.50–2** | Automated | Good; easy to template |
| Fully manual write-up from JSON | $0 | 30–60 min | Highest touch for key accounts |

**Recommendation:** template 2–3 narrative prompts (overview conclusion, readiness summary, industry takeaway). Run automatically via API in the orchestrator, with human review before sending to customer.

---

## PDF conversion (optional — not v1)

| Option | Effort | Cost per PDF | Notes |
|---|---|---|---|
| **Browser print-to-PDF** (Playwright on rendered HTML) | 1–2 eng days | ~$0 | Good enough for sales; no design tool needed |
| **Designed PDF** (Figma → export, or InDesign) | Design + 2–3 eng days | Design time | Requires Shaan sign-off |
| **Productized in-app export** | Later | — | Only if company scorecard proves useful |

**Recommendation:** ship HTML first (matches attached samples). Add Playwright PDF only after design sign-off and if sales needs a attachable file format.

---

## Fastest practical implementation path

**Phase 1 — Prove economics (2 weeks)**

1. Build shared orchestrator + JSON schema + HTML renderer
2. Ship **Approach 1** end-to-end for one real prospect
3. Document actual cost and turnaround from that run
4. Sales uses static HTML + optional manual narrative

**Phase 2 — Industry benchmark ( +1 week)**

5. Add Approach 2 aggregation (pools, heatmap, 8-brand leaderboard)
6. Run one industry vertical as proof

**Phase 3 — Optional polish**

7. LLM narrative automation
8. Guest share link delivery (reuse existing share JWT)
9. PDF export after design sign-off
10. Productize company scorecard on website if sales traction is strong

---

## Open questions for Gaurav / Utkarsh / Tathagat

1. **Prompt curation:** who owns the 25 / 100 prompt lists — sales, CS, or automated LLM draft + human review?
2. **Competitor list:** manual input per deal, or infer from `brandkit_dag`?
3. **Industry reports:** one shared prompt set per vertical (recommended) vs bespoke each time?
4. **AI Readiness:** is 3-page SEO scan sufficient for v1, or do we need a separate LLM page-review prompt?
5. **Financial assumptions:** sales-editable (conversion, AOV) or fixed defaults with disclaimer?

---

## Bottom line for sales

| Question | Answer |
|---|---|
| **Can we do this without the product?** | Yes — backend workflow + HTML output |
| **Do we reuse Gravton logic?** | Yes — metrics, citations, volume, responses; not full onboarding |
| **How long to first report?** | ~2 weeks to build workflow; then **4–8 hrs** per company report |
| **Cost per company report?** | **~$15–40** data + ~$0–2 narrative |
| **Cost per industry report?** | **~$50–120** data + ~$1–3 narrative |
| **PDF needed now?** | No — HTML samples are the v1 deliverable |
| **Cheapest MVP?** | Approach 1 with 15 prompts, 1 model, no AI Readiness → **~$10–20/report** |

---

*Working reference files: `Approach 1 - Client Specific.html`, `Approach 2 - Industry.html` (Downloads folder)*
