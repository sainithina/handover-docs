# Module Map — the whole system

> status: draft
> source: code + `architecture.md`, `CLAUDE.md`, `docs/onboarding-flow.md`, `docs/onboarding-dag-io.md` (grounded 2026-07-28)
> owner: engineering team
> confirmed: — (awaiting human correction pass)

The spine of the product brain: what subsystems exist and how they relate, so any
feature can be located. Not to be confused with the prompt-generation **vertical
archetypes** (ecommerce/saas/hospitality/…) — those are one leaf, in the appendix.

## System topology (1 paragraph)

Monorepo (uv workspace): a **Django 5.2 REST API** (`backend_src/`) owns business
entities, auth, tenancy, and the metrics engine, and acts as the control plane that
**triggers Airflow** and receives its callbacks. **Airflow 3.1.8** (`airflow/dags/`) does
the heavy crawl + AI enrichment + demand/opportunity compute. They meet over two channels
(`architecture.md`): control plane Django → Airflow REST (`POST /api/v2/dags/{id}/dagRuns`),
and callback plane Airflow → Django (`POST /core/api/v1/workflow/airflow-callback/` for
status, `/persist-brandkit/` for artifacts). The **frontend is a separate repo**
(gravton-frontend), sharing only the prod box + compose file.

## 1. Top-level components (uv workspace members)

| Dir | Responsibility |
|---|---|
| `backend_src/` | Django REST API — entities, auth, tenancy, metrics engine, the Airflow bridge. 26 apps (below); config in `core/`. |
| `airflow/dags/` | ~30 single-file `*_dag.py` DAGs (all `schedule=None`). Support libs beside them: `app/`, `llm/`, `utils/`, `net/`, `dataio/`, `schemas/`, `crawlerkit/`, `repos/`. |
| `airflow/dags/crawlerkit/` | Crawl primitives lib — canonicalization, Apify render, robots/sitemap policy, resilience, snapshots. |
| `airflow/dags/repos/ai-demand-case2` | Vendored "Case2" demand engine (Bayesian SV/ASV fusion). **do-not-explore** (CLAUDE.md). |
| `agentkit/` | Zero-runtime-dependency agent SDK — the one agent runtime Django/Airflow/CLI build on. Zero-dep gate CI-enforced. |
| `observability/` (`obskit`) | OpenTelemetry facade — emit OTLP once, collector fans out to Sentry/Langfuse/CloudWatch/Grafana. |
| `cli/` (`gravton-cli`) | Ops + build-time CLI. Heavy build-only stack (dspy/optuna/litellm) for **prompt-optimization/evals**; ops commands over Postgres + CloudWatch. |
| `docs/` | Authoritative flow/architecture docs (`onboarding-flow.md`, `onboarding-dag-io.md`, `agent-boundaries.md`). |
| `dag-analysis/` | Output artifacts from the `dag-onboarding-review` skill (not runtime). |
| `product-brain/` | This — durable product truth. |

> Note: `cli/` already ships a prompt-optimization/eval stack (dspy/optuna) — relevant if
> the eval-harness problem comes back on the roadmap.

## 2. Django backend apps (`backend_src/apps/` — 26 per CLAUDE.md, grouped)

| Group | Apps | Role |
|---|---|---|
| **Foundations** | `base`, `user`, `client`, `feature_flags` | base models/OTel; JWT auth (`user`); orgs & tenancy — **every queryset scopes to `client.Organization`**; DB-backed flags. |
| **Bridge** | `workflow` | Django↔Airflow bridge: triggers DAG runs, holds the `Workflow` lifecycle row, receives callbacks + brandkit persistence. |
| **Brand & taxonomy** | `brandkit`, `intent_core` | domains/competitors/brandkit/product-verticals + fires crawl/product_vertical/brandkit on domain add; intent clusters (`intent_core`) are the taxonomy prompt-gen builds on. |
| **Data-source ingest/persist** | `crawl`, `gsc`, `keywords`, `technical_seo`, `citations`, `reddit`, `quora`, `youtube` | crawled pages; Google Search Console OAuth+data; keyword library (`k_lib`, SV/ASV/ai_demand); SEO Health Score; citation pipeline; per-source community intelligence. |
| **Metrics** | `insight_metrics` | Core metrics engine — `PromptMetric` + the heavy `services/metrics_queries.py` dashboards read. |
| **Opportunities** | `opportunity`, `l2_opportunity`, `l3_opportunity` | L1 checkpoints/stages/ranking; L2 social-grounded sessions; L3 NEW/EXISTING topic decisions + doc-upload extraction. |
| **In-product LLM agents** | `agent_hub`, `metric_agent`, `technical_seo_agent` | route-based multi-agent chat; metric-explainer; SEO-audit Q&A. **These are in-product agents (`docs/agent-boundaries.md`), unrelated to Claude Code subagents.** |
| **Supporting** | `content_engine`, `share` | content generation sub-apps; Share Mode / guest-token read access (`guest_access.py` do-not-touch). |

## 3. Airflow pipeline

**Key correction:** it is **not one auto-chained graph**. It's **five user-gated segments**
stitched by Django REST triggers; `TriggerDagRunOperator` edges exist only *inside* a
segment. `dag_id` ≠ filename in places (`keyword_dag.py`→`k_dag`, `opportunity_dag.py`→
`opportunity`).

**Functional groups:**
- **Ingestion / crawl** — `crawl_dag` (Apify crawl+enrich→S3), `gsc_dag` (only if GSC connected), `seo_scan_dag` (technical-SEO scan over `app/seo/`).
- **Brand setup / verticals** — `product_vertical_dag` (owns the onboarding stage in UI), `brandkit_dag` (intents+brandkit→persist to Django), `vertical_profiler_dag` (fire-and-forget; **no Workflow row, no callback**), `competitor_vertical_mapping_dag`.
- **Demand / keyword** — `k_dag`→`keyword_volume` (DataForSEO SV+ASV → Case2 `ai_demand`), `demand_universe` (per-prompt demand + untapped topics), `prompt_volume` (Case2 volume over existing intents, no LLM regen), `query_fanout_dag`.
- **Prompt generation** — `synthetic_prompt` (V4 module-routed synthetic prompts per product vertical; see appendix).
- **Response collection** — `responses_dag` (collects LLM answers; fan-out hub), `citation_dag` (Gemini-grounded citation attribution).
- **Community sources** — `reddit_dag`/`quora_dag`/`youtube_dag` (discover→scrape→score authority→extract mentions→sentiment). Triggered via `l2_flow_opp` social ingestion, **not** the onboarding spine.
- **Scoring / insights** — `sentiment_dag`→`insights` (writes `PromptMetric`, folds in community signals) → demand + opportunity.
- **Opportunities** — L1 `opportunity`→`opportunity_stages`; L2 `l2_flow_opp`→`l2_opportunity`; L3 `opportunity_l3`.

**Verified in-DAG trigger edges** (`trigger_dag_id` grep): `brandkit`→`competitor_vertical_mapping` (`brandkit_dag.py:904`); `responses`→`{prompt_volume, citation, sentiment, query_fanout}` (`responses_dag.py:1600/1630/1641/1650`); `sentiment`→`insights` (`sentiment_dag.py:1745`); `insights`→`{demand_universe(branch-gated), opportunity}` (`insights.py:936/947`); `opportunity`→`opportunity_stages` (`opportunity_dag.py:245`); `synthetic_prompt`→`prompt_volume` only, deliberately **not** responses (`synthetic_prompt_dag.py:2368`); `k_dag`→`keyword_volume` (`keyword_dag.py:1299`).

**The onboarding spine (⏸ = a user click gates the next segment):**
```
add domain ──> crawl_dag  +  product_vertical_dag
⏸ verticals ──> brandkit_dag ══> competitor_vertical_mapping_dag  (+ vertical_profiler fire-and-forget)
⏸ connect data ──> gsc_dag(opt) + k_dag ══> keyword_volume
⏸ build demand map ──> synthetic_prompt ══> prompt_volume
⏸ prompts review ──> responses_dag ══> {prompt_volume, citation, sentiment══>insights══>{demand_universe, opportunity══>opportunity_stages}, query_fanout}
```
Everything before `responses_dag` is a click; everything after is automatic.

## 4. How Django and Airflow relate

- **Trigger:** `trigger_airflow_workflow` (`workflow/services.py:1155-1265`) assigns `run_id`,
  builds `dag_run.conf` (`domain_id, domain_url, organization_id, workflow_id, run_id,
  correlation_id, config, organization_region, location`), preflights the DAG, POSTs the run.
  Each hop is 10s-timeout/zero-retry → a transient blip marks the `Workflow` row FAILED
  (single point of failure; outbox mitigation unimplemented).
- **Status convergence:** push callback + a 60s Celery-Beat pull reconciler + a 600s stall
  detector (`services.py:129-147`).
- **Django-in-DAG:** Airflow mounts `./backend_src`; several DAGs (`keyword_volume`,
  `demand_universe`, `vertical_profiler`) read/write Django models directly, *in addition*
  to the REST callback path.

## 5. Cross-cutting
- **LLM routing:** all model calls go through OpenRouter / agentkit adapters; per-stage
  model + token knobs are **env vars** (`.env.example`); prompt text lives in
  `airflow/dags/llm/prompts/`.

---

## Appendix — prompt-generation vertical archetypes (a leaf, not "the modules")

Inside `synthetic_prompt_dag` only, prompts are steered by **buyer archetypes** registered
at `airflow/dags/llm/prompts/vertical_modules.py:745-757`: `ecommerce`, `saas`,
`hospitality`, `automobile` (**disabled**, commented at `:755`), + `catch_all` fallback.

- **Assignment (once/brand):** `vertical_profiler_dag` LLM-classifies the brand
  (`system_prompts.py:1096-1120`) → `ProductVertical.raw_profile.module_id`.
- **Routing (every run):** `synthetic_prompt_dag` reads `module_id` (unknown → forced
  `catch_all`, `:1234-1242`); each stage gets only its allowed slice (`_STAGE_MODULE_KEYS`,
  `vertical_modules.py:778-798`).
- **Divergence axes** (the "does this need testing across archetypes?" checklist):
  mandatory prompt types · voice · use-case meaning · geography sensitivity · post-purchase
  intents · industry tag — all in `vertical_modules.py:134-690`.

## Open questions for the correction pass
1. Is the five-segment / user-gated framing how the team actually thinks about onboarding,
   or do they mentally treat it as one pipeline?
2. `content_engine` "re-exports sub-apps under one label" — what are those sub-apps, and is
   this a real product area or scaffolding?
3. Are the in-product agents (`agent_hub`/`metric_agent`/`technical_seo_agent`) an active
   product surface or experimental? (Affects how much brain they deserve.)
4. Is `automobile` disabled intentionally, and does one-archetype-per-brand mis-slice
   multi-vertical brands?
