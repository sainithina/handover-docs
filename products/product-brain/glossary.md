# Glossary — metrics & taxonomy as the code computes them

> status: draft
> source: code — `insight_metrics` + upstream DAGs (grounded 2026-07-28)
> owner: engineering team
> confirmed: — (awaiting human correction pass)

Definitions here are **what the code actually computes**, not the marketing phrasing.
Where a PRD term and the code term differ, the code term wins for engineering.

**Owning subsystem (see `module-map.md`):** these metrics live in the `insight_metrics`
app (`services/metrics_queries.py`), which dashboards read. The *raw* per-generation scores
are produced upstream in the **scoring/insights DAG segment** (`sentiment_dag` → `insights`,
which writes `PromptMetric`) and the vendored Case2 / `MetricsAggregator`. `insight_metrics`
only aggregates, renormalizes, and org-scopes them.

## Core metrics

### visibility
- **Plain:** a brand's *appearance rate* across prompts, 0–100. An absolute presence
  measure — **not** renormalized across brands.
- **Compute:** raw per-generation `visibility_score` (presence signal) summed per
  (prompt, brand) ÷ the prompt's model-variant count → per-prompt ×100; brand-level =
  `sum(per-prompt visibility) / prompt_count`.
- **Where:** `metrics_queries.py:1745` (`get_visibility_metric`), per-prompt `:518`,
  `:1783`. Raw score originates upstream: `airflow/dags/insights.py:96` (`presence × w_p ×
  alpha_m`, w_p = demand weight, alpha_m = 1/|models|).

### share of voice (SoV)
- **Plain:** visibility *renormalized* as a share of total visibility mass across all
  brands — sums to ~100%.
- **Compute:** `sov = brand_visibility / total_visibility * 100`.
- **Where:** `metrics_queries.py:1801` (`get_sov_metric`), `:1841-1847`.
- **Gotcha:** visibility and SoV answer different questions — absolute presence vs. relative
  share. Don't use them interchangeably.

### sentiment
- **Plain:** how favorably an answer frames a brand — LLM-assigned 0–10 (5 = neutral),
  equal-weight mean across models.
- **Compute:** raw `sentiment_score` produced by an **LLM scorer**, not code
  (`system_prompts.py:831`, `:2978`); no signal → 5/neutral (`sentiment_dag.py:1024`).
  `get_sentiment_metric` takes the latest run's per-brand value.
- **Buckets** (`metrics_queries.py:3112`): <3 negative · <5 mixed · <7 neutral · <9 positive
  · else strong.
- **Where:** `metrics_queries.py:1930`; per-prompt `adoption_metrics.py:757`.

### citations / citation share
- **Plain:** the source URLs a model grounded on, weighted by domain authority; citation
  share = a brand's citation mass as % of total, averaged over all executions.
- **Compute:** `citation_mass_weight = base_weight × damping` where base = official 1.2 /
  unknown 0.8 / aggregator 0.5 / social 0.4, and `damping = 1/(1+ln(n))` for n pages per
  domain. Brand share = `brand_mass / total_mass * 100`, simple-averaged over ALL executions
  (uncited count as 0).
- **Where:** `airflow/dags/utils/citation_weighting.py:219`; `metrics_queries.py:812`, `:853`.
- **Gotcha:** citation-only evidence does **not** count a brand as "mentioned" — only
  visibility/SoV presence does (`metrics_queries.py:638`).

### attribution categories
Owned / community / earned, normalized to three buckets (`adoption_metrics.py:34-47`):
`OWNED` (brand-owned pages), `COMMUNITY` (platform/community), `EARNED_MEDIA`. "Owned page
share" (post-purchase) = `focal_owned_citation_mass / total_citation_mass * 100`.

### position_score (adjacent)
Mean of per-mention rank score (lower rank = better) — `metrics_queries.py:1872`, `:1180`.

## Taxonomy

### funnel stages
- **Plain:** each prompt's buyer-journey stage, derived **in code** from the generator's
  `intent_layer` (no LLM classifier).
- **Values gotcha:** enum member names ≠ DB values — `UPPER="Top"`, `MID="Mid"`,
  `LOWER="Bottom"`, `POST_PURCHASE="Post-Purchase"` (`intent_core/models.py:104-108`).
  Map (`synthetic_prompt_dag.py:356`): discovery→Top, evaluation→Mid, selection→Bottom;
  post-purchase stamped directly. Adoption-Health metrics filter to `Post-Purchase`
  (`adoption_metrics.py:32`).

### PRD term ↔ code term (vocabulary gap — read this before greping)
The Shopping PRD's names do **not** exist in code. Mapping:
| PRD says | Code actually has |
|---|---|
| "offering taxonomy" | `ProductVertical` (`brandkit/models.py:332`) — per-domain offering grouping with competitors + `raw_profile` (buyer_archetype/segments/use_case_values) |
| "attribute taxonomy" | *no direct equivalent* — nearest is prompt classification: `IntentCluster → SyntheticPrompt` with `intent_layer`, `category`, `industry`, `PromptType` (Breadth/Depth) |

## Ground-truth caveat
Raw `visibility_score` / `sov` / `position_score` / `sentiment_score` are produced upstream
(insights + sentiment DAGs); `insight_metrics` only aggregates/renormalizes. The authoritative
visibility/SoV formula lives in the vendored `MetricsAggregator` (`insights.py:113`), which
CLAUDE.md marks **do-not-explore** — treat its output as a contract, not something to re-derive.

## Open questions for the correction pass
1. Are "offering taxonomy" / "attribute taxonomy" real product concepts we should build
   toward (and the code just hasn't caught up), or PRD-only language we should retire?
2. Is the visibility-vs-SoV distinction well understood on the team, or a frequent mix-up
   worth calling out louder?
3. Should the vendored `MetricsAggregator` formula be documented here as a contract, or
   deliberately left opaque per the do-not-explore rule?
