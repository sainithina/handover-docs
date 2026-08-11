# Volume Prediction Algorithm — Handover (P0)

**This is the most important item in the departure pack.**

Product name in docs: **AI Demand Estimation (Case 2)** — Bayesian fusion of classic search volume (**SV**) and AI search volume (**ASV**) into monthly AI-demand estimates per prompt / intent.

Copied narrative docs in this folder:

- [FLOW.md](./FLOW.md) — full end-to-end explanation  
- [CASE2_README.md](./CASE2_README.md) — developer README  
- [README_CUSTOMER.md](./README_CUSTOMER.md) — customer-facing guide  

---

## What question it answers

> If buyers ask this prompt in AI tools (ChatGPT, Perplexity, AI Overviews, …), how large is that monthly demand opportunity?

Output units: **AI-demand units / month**, with a 90% interval when fusion succeeds.

---

## Where the code lives

| Role | Absolute path |
|---|---|
| **Research / richest source of truth (zip this)** | `/Users/sainithinartham/Downloads/ai-demand-case2` |
| **Production engine (vendored in Airflow)** | `/Users/sainithinartham/Downloads/gravton-console/airflow/dags/repos/ai-demand-case2` |
| **Prod orchestration** | `prompt_volume_dag.py`, `keyword_volume_dag.py` |
| **Prod bridge** | `airflow/dags/utils/case2_gravton_bridge.py` (+ `prompt_volume_gravton_bridge.py`) |
| **Django read path** | `backend_src/apps/intent_core/services/prompt_volume.py` → `Case2DemandRun` |
| Experiment: overlap discount fork | `Downloads/ai-demand-case2_overlap_discount` |
| Experiment: Intent Match Score aggregation | `Downloads/ai-demand-case2_Intent_Match_Score` |
| Offline analysis notebooks/scripts | `Downloads/Analysis` |

### Production vs research gap (know this)

| Topic | Research tree (`Downloads/ai-demand-case2`) | Vendored prod (`dags/repos/ai-demand-case2`) |
|---|---|---|
| Default intent/topic rollup | `representative_incremental` | `overlap_discount` |
| Extra scorers (BGE, etc.) | Present | Often absent / older |
| Hospitality metrics package | Present | Not required for volume |
| Who generates prompts | Optional LLM in Case2 | **Gravton** (synthetic prompt / scorecard lite) — Case2 only volumes |

---

## Pipeline (12 steps)

1. **Inputs:** prompts + intent clusters (+ optional company profile, market/location).  
2. **Keyword extraction** per prompt (default **LLM**; fallbacks: n-gram, ngram+LLM filter).  
3. **Importance scores** (cross-encoder / semantic ranker) — how well each phrase matches the prompt.  
4. **Fetch SV + ASV** from **DataForSEO** for unique keywords in the market (also CPC / competition).  
5. **Optional calibration** from monthly history → learn ρ (AI share), η (uplift), per-intent SV/ASV priors.  
6. **Stability floors:** ρ ≥ 0.25, η ≥ 1.3, σ_A ≥ 0.5 (when calibrated).  
7. **Per keyword Bayesian fusion:** SV posterior → coupling prior (ρ, η, δ) → fuse with ASV → keyword AI demand A*.  
8. **Per prompt aggregation:** softmax fusion weights from importance (sharpness **β**) → Y(p) + CI.  
9. **Linear totals** also computed (unweighted sum) as upper-bound style view.  
10. **Intent / topic rollup** without double-counting: overlap-discount **or** representative-incremental **or** legacy union+dedupe+fusion.  
11. Write `runs/<run_id>/` artifacts (`prompt_estimates.*`, `calibrated.json`, `insights.md`, …).  
12. **Prod:** Airflow persists slim payload to `Case2DemandRun`; UI/API read via `prompt_volume_map()`.

Mathematical sketch (from README):

1. SV posterior: `si | yi ~ N(μ_s_post, σ²_s_post)` with `yi = log(SV)`  
2. Coupling prior: `ai | si, ρ, η ~ N(si + log ρ + log η + δc, σ²δ)`  
3. ASV likelihood: `xi | ai ~ N(ai + bA, σ²A,c)` with `xi = log(ASV)`  
4. Fuse prior + likelihood → posterior for `ai`  
5. Aggregate: `Y(p) = Σ wi · A*(ki)` with softmax weights from similarity / importance  

Dry-run worked example: prompt “best running shoes for flat feet” → **Y(p) ≈ 18.6k** AI-units/month, 90% CI [14.0k, 23.9k].

---

## Core files (absolute paths)

| File | Role |
|---|---|
| `…/ai-demand-case2/src/case2_demand/estimation/bayesian_sv_asv.py` | Core Bayesian fusion + softmax aggregation |
| `…/ai-demand-case2/src/case2_demand/calibration.py` | ρ, η, priors, floors |
| `…/ai-demand-case2/src/case2_demand/cli.py` | `case2` CLI / orchestration |
| `…/ai-demand-case2/src/case2_demand/config.py` | `CASE2_*` settings |
| `…/ai-demand-case2/src/case2_demand/keyword_extraction/extractor.py` | Keyword extraction |
| `…/ai-demand-case2/src/case2_demand/keyword_volume/dataforseo.py` | DataForSEO client |
| `…/ai-demand-case2/src/case2_demand/overlap_discount.py` | Overlap-discount topic volumes |
| `…/ai-demand-case2/src/case2_demand/topic_volume_representative.py` | Representative-incremental rollup (research) |
| `…/ai-demand-case2/src/case2_demand/intent_keyword_union.py` | Legacy intent union + semantic dedupe |
| `…/ai-demand-case2/scripts/run_from_intents_prompts.py` | Gravton-shaped JSON → Case2 volumes |
| `…/gravton-console/airflow/dags/prompt_volume_dag.py` | Prod prompt volume DAG |
| `…/gravton-console/airflow/dags/keyword_volume_dag.py` | Prod keyword library volume DAG |
| `…/gravton-console/airflow/dags/utils/case2_gravton_bridge.py` | Bridge into vendored Case2 |
| `…/gravton-console/backend_src/apps/intent_core/services/prompt_volume.py` | API/UI volume map |

---

## How to run

### Local research engine

```bash
cd /Users/sainithinartham/Downloads/ai-demand-case2
pip install -e .

# No API — sanity check
case2 dry-run

# Real volumes (needs DataForSEO + optionally OpenRouter in .env)
case2 run "best running shoes for flat feet" --with-calibration

# Gravton-shaped intents/prompts JSON (mirrors Airflow)
PYTHONPATH=src python scripts/run_from_intents_prompts.py \
  inputs/your_prompts.json \
  --with-calibration
```

### Production (Airflow)

- Trigger DAG **`prompt_volume`** with `domain_id` (optional: `with_calibration`, `dry_run`, `location`).  
- Trigger DAG **`keyword_volume`** for `KeywordLibrary` SV/ASV/`ai_demand`.  
- Case2 home resolution order: `AI_DEMAND_CASE2_HOME` → `dags/repos/ai-demand-case2` → legacy `/opt/airflow/ai-demand-case2`.

Consumers of volumes: Demand Map, opportunity / insights, scorecards lite pipeline, brandkit fallbacks.

---

## Hyperparameters (watch drift)

| Param | Meaning | Typical / floor | Where |
|---|---|---|---|
| ρ | AI share of classic demand | default/floor **0.25** | `CASE2_RHO`, calibration |
| η | Global AI uplift | floor **1.3** | `CASE2_MU_ETA`, calibration |
| β | Softmax fusion sharpness | README 60; config often **5**; keyword utils often **6** | `CASE2_BETA` — **surfaces disagree; confirm before changing** |
| σ_A | ASV noise | floor **0.5** when calibrated | `calibration.py` |
| δc, σδ | Coupling offset / noise | 0.20 / 0.50 | env defaults |
| `CASE2_KEYWORD_EXTRACTION` | `llm` / `ngram` / … | `llm` | env |
| `CASE2_INTENT_VOLUME_METHOD` | rollup method | research vs prod differ | env |
| `CASE2_OVERLAP_DISCOUNT_ALPHA` | overlap discount strength | 0.7 | env |
| `CASE2_SV_SOURCE` | `clickstream` or `google_ads` | clickstream | env |

Defaults table also in [CASE2_README.md](./CASE2_README.md).

---

## Credentials required for volume

See [../credentials/CREDENTIALS_CHECKLIST.md](../credentials/CREDENTIALS_CHECKLIST.md). Minimum for a live Case2 run:

- `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD`  
- `OPENROUTER_API_KEY` (LLM keyword extraction / intent gen)  
- In Airflow: Variables `ai_demand_case2_dataforseo_*`, `ai_demand_case2_openrouter_api_key` (and env mirrors)

**Do not put values in email.**

---

## Known operational issues / context

- Prompt-volume “not populating” on Self Starter plan — investigated (mail/PDF artifacts in Downloads; not copied here).  
- Outlier / confidence work: `Prompt_Volume_Confidence_Plan_Sai.docx` in `research/papers-and-decks/`.  
- Client calibration sensitivity: sparse history → floors dominate; long-tail prompts stay conservative.  
- Prod does **not** use Case2 `run-all` for intent/prompt generation — Gravton owns that upstream.

---

## Related but NOT volume fusion

`ai-demand-case2/hospitality_metrics/` — **Shortlist Rate** + **Routing Interception Rate** for hotels (visibility research). Methodology under `research/plans/`. Do not confuse with SV/ASV fusion.
