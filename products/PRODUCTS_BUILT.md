# Products Built & Launched

Status is inferred from code, docs, and work history. **“Launched”** means shipped to customers or live in the product; mark uncertain items clearly.

---

## Flagship / high ownership

### 1. Prompt volume / AI Demand Estimation (Case2) — **P0**

| | |
|---|---|
| **Status** | **Production** — powers Airflow `prompt_volume` / `keyword_volume`; consumed by insights, demand map, scorecards |
| **Repos** | `ai-demand-case2` (research), vendored under `gravton-console/airflow/dags/repos/ai-demand-case2` |
| **Docs** | [../volume-prediction/ALGORITHM.md](../volume-prediction/ALGORITHM.md), FLOW.md, README_CUSTOMER.md |
| **What shipped** | Bayesian SV+ASV fusion, calibration, keyword extraction, intent rollups, Django `Case2DemandRun` persistence |

### 2. AI Demand Scorecards (Approach 1 company / Approach 2 industry)

| | |
|---|---|
| **Status** | **Ops / sales product** — HTML/PDF/Excel via lite pipeline; UI `/ops/scorecard/:token`; delivery via app admin |
| **Repos** | `gravton-console/backend_src/apps/scorecards/`, `airflow/.../lite_pipeline.py`, `gravton-frontend/src/features/scorecard-ops/` |
| **Docs in this pack** | [scorecards/scorecard-design.md](./scorecards/scorecard-design.md), [scorecard-feasibility.md](./scorecards/scorecard-feasibility.md) (author: Sainithin), [scorecard-prompt-generation-simplification.md](./scorecards/scorecard-prompt-generation-simplification.md) |
| **What shipped** | Bootstrap → lite prompts → volume + AI responses → HTML report; Beauty & Skincare pilot measured ~15 min / ~$8–12 at 20-prompt cap |

### 3. Demand Map

| | |
|---|---|
| **Status** | **In-product** (onboarding + dashboard) |
| **Repos** | BE `insight_metrics/services/demand_map.py`; FE `src/features/demand-map/` |
| **Depends on** | Case2 volumes + insight metrics pipeline |

### 4. Hospitality Shortlist + Routing Interception metrics

| | |
|---|---|
| **Status** | **Research tooling / experiment** (not full platform product) |
| **Repos** | `ai-demand-case2/hospitality_metrics/` |
| **Docs** | [../research/plans/hospitality_shortlist_and_routing_metrics.md](../research/plans/hospitality_shortlist_and_routing_metrics.md) |
| **What it does** | Shortlist Rate (top-5 property mentions) + Routing Interception Rate (direct vs OTA) across engines |

---

## Broader product surfaces Sai contributed to

| Product | Status (inferred) | Key paths |
|---|---|---|
| **Citations dashboard** | Shipped | FE `dashboard/citation/`; BE `citations/`, insight_metrics |
| **Metric Agent + Technical SEO Agent + Agent Hub** | In-product | BE `metric_agent/`, `technical_seo_agent/`, `agent_hub/`; FE `agents/`, `technical-seo/` |
| **L2 Opportunity / social ingestion** | Backend + FE handoff | BE `l2_opportunity/`, `l2_flow_opp_dag.py`; handoff [gravton-l2-social-frontend-handover.md](./gravton-l2-social-frontend-handover.md) |
| **Demand Lens** (Category / Contested / Owned) | **In progress** (`feat/demand-lens`, brainstorm 2026-08-04) | `intent_core/services/demand_lens.py`, console docs brainstorm |
| **Full onboarding spine** | Main Gravton product (team-owned) | crawl → brandkit → synthetic prompts → responses → insights; Sai pieces: volume, demand map, prompts/scorecard lite |

Product context maps: [product-brain/module-map.md](./product-brain/module-map.md), [product-brain/glossary.md](./product-brain/glossary.md)  
(Note: module-map draft may omit newer apps like `scorecards` / `ecommerce`.)

---

## Frontend features inventory

`gravton-frontend/src/features/`:

`agents`, `auth`, `dashboard`, `demand-map`, `export`, `gsc`, `onboarding`, `scorecard-ops`, `share`, `technical-seo`

## Backend apps inventory

`gravton-console/backend_src/apps/`:

`agent_hub`, `base`, `brandkit`, `citations`, `client`, `content_engine`, `crawl`, `ecommerce`, `feature_flags`, `gsc`, `insight_metrics`, `intent_core`, `keywords`, `l2_opportunity`, `l3_opportunity`, `metric_agent`, `opportunity`, `quora`, `reddit`, `scorecards`, `share`, `technical_seo`, `technical_seo_agent`, `user`, `workflow`, `youtube`

---

## Sample customer / pilot artifacts (on disk, not all in this pack)

- Scorecard PDFs: Gravton AI, Our Habitas, etc. under `Downloads/scorecard-*.pdf`  
- Approach 1 / Approach 2 HTML samples in Downloads  
- Company profiles in `ai-demand-case2/company_profiles/` (e.g. RIU, Digit, …)  
- Hospitality runs under `ai-demand-case2/hospitality_metrics/runs/` (exclude from email zip unless requested)

---

## Suggested ownership after departure

| Area | Suggested next owner focus |
|---|---|
| Case2 math + calibration | Whoever owns insights / demand map numbers |
| Airflow volume DAGs | Platform / Airflow on-call |
| Scorecards ops | Sales eng / CS eng using `scorecard_run` CLI |
| Hospitality metrics | Research — only if hospitality GTM continues |
| Demand Lens | Finish `feat/demand-lens` brainstorm → tech-spec path |
