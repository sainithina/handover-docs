# Simplifying Prompt Generation for Scorecards

**For:** Building a lite gravton-console + gravton-frontend workflow  
**Context:** [`scorecard-feasibility.md`](./scorecard-feasibility.md)  
**Date:** July 2026

---

## TL;DR

The full product runs a **5-stage LLM pipeline per product vertical** (`synthetic_prompt_dag`). For an **automated** scorecard workflow, don't copy all 5 stages — preserve **one insight**:

> **Generate prompts from buyer DECISIONS, not from brand/category descriptions.**
> Use a two-step pipeline: extract decision signals first, then phrase them as AI-search questions.

That intermediate step is the **SIGNAL_BANK** — the quality layer everything else in the full pipeline exists to feed.

**Automated lite path (2 LLM calls):**

```
Brand + competitors + seed topics/keywords
  → Call 1: keyword_grounding  (decisions + funnel layer)
  → Call 2: generate_pre_purchase  (open vs branded probes)
  → persist SyntheticPrompt rows
  → prompt_volume_dag → responses_dag
```

Skip: web extraction (1b/1c), vertical profiler, post-purchase, mandatory template types.

| Report type | Prompt count | Automated approach |
|---|---|---|
| **Approach 1 — Company** | 25 | 2-call lite DAG from brand URL + competitors |
| **Approach 2 — Industry** | 100 | Same 2-call pattern; seed from industry topic list |

---

## The one insight worth keeping

### What naive automation gets wrong

A single-shot prompt like *"generate 25 AI search prompts for NorthPeak, a project management tool"* produces **SEO-shaped keyword strings**:

- "best project management software"
- "NorthPeak CRM features"
- "project management tools comparison"

These read like Google Ads, not like what someone types into ChatGPT. Downstream metrics (visibility, SOV, win/share) end up measuring the wrong demand.

### What the full pipeline actually does differently

The V4 pipeline never asks the LLM to jump straight from brand context → prompt text. It inserts an intermediate representation — the **SIGNAL_BANK** — where each entry is a **buyer decision**, not a topic or keyword:

```json
{
  "axis": "which project tool fits a remote startup team",
  "intent_layer": "evaluation",
  "intent": "comparison",
  "grounded_phrase": "asana vs monday for startups",
  "lifecycle": "pre_purchase"
}
```

Only **after** decisions are extracted does stage 3a turn each signal into a natural buyer question, with strict rules:

| Rule | Why it matters |
|---|---|
| **Three-layer coverage** (discovery → evaluation → selection) | Maps directly to Top/Mid/Bottom funnel — no lopsided prompt sets |
| **Open vs branded split** | Most prompts name no vendor (tests unprompted visibility); branded only from real comparison signals |
| **Grounding** | Every prompt traces to a `grounded_phrase` — no invented concerns |
| **One decision per prompt** | 5–20 words, first-person voice — matches real ChatGPT typing |

The keyword grounding stage (`KEYWORD_GROUNDING_SYSTEM_PROMPT`) describes itself as *"the BACKBONE the generator leans on to guarantee all three intent layers."* Web extraction (1b/1c) adds richer buyer language from Reddit/forums — nice-to-have, not the core quality mechanism.

### The insight in one sentence

**Quality comes from separating "what decision is the buyer making?" from "how would they ask it in ChatGPT?"** — not from web search, vertical modules, or post-purchase stages.

### Automated lite DAG (preserves the insight, drops the rest)

```
INPUT
  domain_id, brand profile (lite: 1-page LLM synopsis), competitors, seed keywords/topics
  module_id: hardcode "catch_all" (skip vertical_profiler_dag)

CALL 1 — Decision extraction (reuse KEYWORD_GROUNDING_SYSTEM_PROMPT)
  keywords/topics → SIGNAL_BANK with layer_coverage per topic
  Output: decision axes tagged discovery | evaluation | selection

CALL 2 — Prompt phrasing (reuse PRE_PURCHASE_PROMPT_GENERATOR_SYSTEM_PROMPT)
  SIGNAL_BANK → buyer-facing prompts
  Enforces: open probes (majority), brand-vs-competitor probes (from comparison signals only),
            funnel layer on each prompt, grounded_in trace

CODE — assign_funnel + cap at 25/100 + persist SyntheticPrompt
  discovery  → Top
  evaluation → Mid
  selection  → Bottom

SKIP
  source_extraction (1b), buyer_extraction (1c)  — web language enrichment
  generate_post_purchase (3b)                     — not needed for scorecards
  vertical_profiler_dag                           — use catch_all module
  mandatory_prompt_types / template_generated     — scorecard doesn't need coverage guarantees
  keyword_dag full run                            — lite seed: LLM topic list from brand URL

DOWNSTREAM (unchanged)
  prompt_volume_dag → responses_dag → insights_dag
```

**Cost:** ~$1–5 per report (2 LLM calls vs 5+ with web search)  
**Quality:** ~80% of full pipeline — you lose real forum language but keep decision framing, funnel mix, and open/branded discipline

### Where seed keywords come from (without full keyword_dag)

For automation you still need *something* to ground Call 1. Lite options, in order of preference:

1. **LLM topic seed** — one cheap call: given brand URL + competitors, emit 5–8 demand topics with 3–5 keywords each (replaces `keyword_dag` clustering)
2. **GSC export** — if the prospect shares Search Console data, use real keywords
3. **DataForSEO/domain keywords** — paid but fast

The 2-call core (grounding → generation) stays the same regardless of seed source.

---

## What the full product does today

### Architecture

Prompt generation lives almost entirely in **gravton-console**. The frontend does not construct prompts — it triggers DAGs, polls workflow state, and lets users review/edit results.

```
Upstream prerequisites (must complete before synthetic_prompt_dag)
  keyword_dag          → IntentCluster + KeywordLibrary
  vertical_profiler_dag → ProductVertical.raw_profile (module_id, buyer archetype)
  competitor_vertical_mapping_dag

Per product vertical (5 LLM calls + code steps)
  1a keyword_grounding     (no web)  keywords → SIGNAL_BANK
  1b source_extraction     (+ web)   discover buyer venues
  1c buyer_extraction      (+ web)   mine buyer language
  2  normalize             (code)    merge banks, dedup, pre/post split
  3a generate_pre_purchase (no web)  pre-purchase prompts
  3b generate_post_purchase  (no web)  post-purchase prompts
  → assign_funnel (code)
  → persist SyntheticPrompt rows
  → branded segregation
  → prompt_volume_dag (auto-chained)
  → responses_dag (user-triggered after review)
```

### Key files

| Layer | File | Role |
|---|---|---|
| DAG | `airflow/dags/synthetic_prompt_dag.py` | Orchestrator — 5 LLM stages, persistence, gates |
| LLM prompts | `airflow/dags/llm/prompts/system_prompts.py` | ~2,400 lines of stage-specific system prompts |
| Vertical rules | `airflow/dags/llm/prompts/vertical_modules.py` | 4 modules × 5 stage slices (`ecommerce`, `saas`, `hospitality`, `catch_all`) |
| Merge logic | `airflow/dags/app/synteticprompt/banks.py` | Signal bank normalization, dedup, provenance |
| Model | `backend_src/apps/intent_core/models.py` | `SyntheticPrompt`, `IntentCluster` |
| API | `backend_src/apps/intent_core/views.py` | CRUD at `/core/api/v1/brandkit/synthetic-prompts/` |
| Trigger | `backend_src/apps/workflow/views.py` | `POST /workflow/trigger/synthetic-prompts/` |
| Frontend | `gravton-frontend/src/features/onboarding/` | Trigger → poll → review → responses (no generation logic) |

### What each prompt row needs

Downstream DAGs (`prompt_volume_dag`, `responses_dag`, `insights_dag`) only require persisted `SyntheticPrompt` rows attached to an `IntentCluster`:

```python
SyntheticPrompt(
    cluster_id=...,           # required FK to IntentCluster
    text="best CRM for startups",  # the buyer prompt
    funnel="Top",             # Top | Mid | Bottom | Post-Purchase
    source="user_added",      # user_added for curated imports
    is_branded=False,       # optional; can run branded segregation later
)
```

You do **not** need `grounded_in`, `persona`, or full vertical profiling for scorecard metrics to compute.

---

## Why the full pipeline is overkill for scorecards

| Full pipeline requirement | Scorecard actually needs |
|---|---|
| Keyword clustering from GSC/k_dag | A fixed list of 25–100 prompts |
| Vertical profiler (4 module types) | Generic buyer language is fine |
| Web source + buyer extraction (2 GPT calls with web search) | Not needed for credible reports |
| Pre + post purchase generators | Pre-purchase only (Top/Mid/Bottom) |
| 3-layer funnel coverage guarantees | Rough funnel mix is enough |
| Mandatory template prompts per vertical | Skip entirely |
| Branded segregation at generation time | Can classify at review or skip |
| Onboarding review UI + full workflow state machine | CLI or minimal admin page |

**Cost impact:** Full pipeline ≈ 5 LLM calls × N verticals + web search. Lite path ≈ 0–2 LLM calls total.

---

## Three simplification options (ranked)

### Option A — Human/LLM curation + API import ⭐ Recommended for v1

**Best for:** Approach 1 (25 prompts), fastest time-to-first-report.

**How it works:**

1. Sales/CS (or a one-shot ChatGPT/Claude session) produces a JSON prompt list
2. Orchestrator creates a minimal domain + one catch-all `IntentCluster`
3. Prompts are POSTed to the existing API
4. Trigger `prompt_volume_dag` → `responses_dag` as normal

**Skip entirely:** `synthetic_prompt_dag`, `keyword_dag`, `vertical_profiler_dag`, competitor mapping gates.

#### Prompt curation template (Approach 1 — 25 prompts)

```json
{
  "domain": "northpeak.com",
  "focal_brand": "NorthPeak",
  "competitors": ["Competitor A", "Competitor B", "Competitor C", "Competitor D", "Competitor E"],
  "geo": "US",
  "prompts": [
    { "text": "best project management tools for remote teams", "funnel": "Top", "is_branded": false },
    { "text": "NorthPeak vs Asana for startups", "funnel": "Mid", "is_branded": true },
    { "text": "is NorthPeak worth it for small teams", "funnel": "Bottom", "is_branded": true }
  ]
}
```

**Funnel mix guideline (25 prompts):**

| Funnel | Count | Branded mix |
|---|---|---|
| Top (discovery) | ~10 | Mostly non-branded |
| Mid (evaluation) | ~8 | Mix of "X vs Y" and category |
| Bottom (selection) | ~7 | Mix of branded and "best X for Y" |

#### Prompt curation template (Approach 2 — 100 prompts)

```json
{
  "industry": "Beauty & Skincare",
  "geo": "US",
  "tracked_brands": ["Brand A", "Brand B", "..."],
  "prompts": [
    { "text": "best vitamin C serum for sensitive skin", "funnel": "Top", "pool": "Anti-aging", "is_branded": false },
    { "text": "retinol vs niacinamide for fine lines", "funnel": "Mid", "pool": "Anti-aging", "is_branded": false }
  ]
}
```

**Industry reports:** curate **once per vertical**, reuse across all company reports in that industry. Amortizes volume + response cost.

#### Import script sketch

```python
# scorecard orchestrator — prompt import step
def import_prompts(domain_id: int, prompts: list[dict]) -> list[int]:
    cluster, _ = IntentCluster.objects.get_or_create(
        domain_id=domain_id,
        label="Scorecard",
        defaults={"source": "scorecard"},
    )
    created_ids = []
    for p in prompts:
        row, _ = SyntheticPrompt.objects.get_or_create(
            cluster=cluster,
            text=p["text"],
            defaults={
                "funnel": p.get("funnel", "Top"),
                "source": "user_added",
                "is_branded": p.get("is_branded", False),
            },
        )
        created_ids.append(row.id)
    return created_ids
```

Or use the existing REST API:

```
POST /core/api/v1/brandkit/synthetic-prompts/
{ "cluster": <cluster_id>, "text": "...", "funnel": "Top", "source": "user_added" }
```

**Effort:** ~0.5 day (validation + import helper)  
**Cost per report:** ~$0 for prompt step  
**Turnaround:** 30–60 min human curation (or 5 min with LLM assist)

---

### Option B — Keyword-only lite DAG

**Best for:** When you want some automation but can't rely on manual curation every time.

**How it works:** Add a new `synthetic_prompt_lite` DAG (or scorecard conf on the existing DAG) that runs only:

```
INPUT: domain_id + cluster_ids (or inline keyword list)
  → keyword_grounding (1a only — no web)
  → generate_pre_purchase (3a only — catch_all module)
  → assign_funnel (code)
  → persist
  → prompt_volume_dag
SKIP: vertical_profiler gate, source_extraction, buyer_extraction, post_purchase, branded segregation
```

#### Stage toggles already supported

The existing trigger API accepts per-run overrides:

```
POST /core/api/v1/workflow/trigger/synthetic-prompts/
{
  "domain_id": 123,
  "enable_pre_purchase": true,
  "enable_post_purchase": false
}
```

But this **does not** skip web extraction (1b/1c) or upstream gates. A dedicated lite DAG is cleaner.

#### Lite DAG config

| Setting | Value |
|---|---|
| `module_id` | Hardcode `catch_all` (skip `vertical_profiler_dag`) |
| Stages | 1a + 3a only |
| Post-purchase | `enable_post_purchase: false` |
| Prompt cap | 25 (company) or 100 (industry) — add in post-processing |
| Upstream gates | Remove waits for profiler + competitor mapping |
| Keywords | Pass inline list OR require minimal `keyword_dag` run |

**Effort:** ~2–3 days (new DAG variant + prompt cap logic)  
**Cost per report:** ~$1–5 (1–2 LLM calls)  
**Quality:** Good for drafts; human review still recommended

---

### Option C — One-shot LLM prompt draft (no DAG at all)

**Best for:** Sales self-serve draft before import.

Use a single Claude/GPT call with a structured output schema — no Airflow, no signal banks:

```
SYSTEM: You are a buyer-intent researcher. Given a company URL and competitors,
generate 25 realistic AI search prompts a buyer would ask ChatGPT/Gemini.
Output JSON array: [{ text, funnel, is_branded }]

USER:
Company: NorthPeak (northpeak.com) — project management for remote teams
Competitors: Asana, Monday, ClickUp, Notion, Trello
Geo: US
Mix: 10 Top, 8 Mid, 7 Bottom. ~30% branded.
```

Then feed the JSON into Option A's import step.

**Effort:** ~2 hours (prompt template + validation)  
**Cost:** ~$0 via team subscription, or ~$0.10–0.50 via API  
**Quality:** Surprisingly good for v1; pair with human review checklist

---

## Recommended decision matrix

| Scenario | Use |
|---|---|
| Automated company scorecard (default) | **2-call lite DAG** (grounding → generation) |
| Need real forum/reddit buyer language | Add web extraction (1b+1c) — 5 calls, higher cost |
| Industry vertical, repeat runs | Same 2-call DAG + shared seed topic library |
| Sales needs instant draft before spend | Optional human review gate after Call 2 |
| Cheapest MVP | 2-call DAG + 15 prompt cap + 1 model downstream |

---

## What to simplify in gravton-console

### Reuse as-is

| Component | Why |
|---|---|
| `SyntheticPrompt` model + API | Downstream DAGs expect these rows |
| `prompt_volume_dag` | Volume numbers for scorecard tables |
| `responses_dag` → `citation_dag` → `insights_dag` | Core metrics pipeline |
| Read APIs (`/metric/visibility`, `/demand-universe/`, `/citation/`) | Scorecard JSON aggregation |
| Branded classification (`intent_core/services/branding.py`) | Optional post-import pass |

### Build new (thin layer)

| Component | Effort |
|---|---|
| `scorecard_run` management command | 2 days — input → import prompts → trigger DAGs → poll → export JSON |
| Prompt JSON validator (funnel mix, count, branded ratio) | 0.5 day |
| Bulk import helper (cluster auto-create + dedup) | 0.5 day |
| Industry prompt library storage (JSON per vertical) | 0.5 day |

### Do not build for v1

- `synthetic_prompt_dag` modifications (unless Option B)
- `keyword_dag`, `vertical_profiler_dag`, competitor mapping
- Full onboarding workflow state machine
- L3 opportunity re-runs
- Post-purchase prompt generation

---

## What to simplify in gravton-frontend

The frontend currently has **no prompt generation logic** — only trigger/poll/review. For scorecards, strip further:

### Full onboarding flow (don't need)

```
Brand Snapshot → trigger synthetic-prompts → poll 5+ stages
  → OnboardingGeneratingPromptsView → OnboardingPromptsReviewView
  → trigger responses → demand map streaming
```

Files involved:
- `src/features/onboarding/components/onboarding-page-controller.tsx`
- `src/features/onboarding/components/onboarding-generating-prompts-view.tsx`
- `src/features/onboarding/components/onboarding-prompts-review-view.tsx`

### Minimal scorecard UI (if any UI at all)

For v1, **skip the frontend entirely** — run via CLI/admin script per the feasibility doc.

If you need a minimal internal page later:

| Screen | Purpose |
|---|---|
| Scorecard run form | URL, competitors, geo, approach (1 or 2) |
| Prompt preview | Show imported/curated prompt list before spend |
| Run status | Poll volume → responses → done |
| Export | Download scorecard JSON or open rendered HTML |

That's 3–4 components, not the full onboarding controller.

---

## End-to-end lite workflow (prompt step only)

```
INPUT
  company URL + competitors + geo          (Approach 1)
  OR industry name + brand list + geo      (Approach 2)

STEP 1 — DOMAIN SETUP (lite)
  Create Domain row + Competitor rows
  Create one IntentCluster ("Scorecard" or industry name)
  Skip: brandkit_dag deep crawl, product verticals, keyword_dag

STEP 2 — PROMPT IDENTIFICATION (pick one)
  A) Paste/ upload curated JSON → bulk import via API     ← recommended
  B) One-shot LLM draft → human review → import
  C) Trigger synthetic_prompt_lite DAG with keyword list

STEP 3 — VALIDATE
  Count: 25 (company) or 100 (industry)
  Funnel mix: Top/Mid/Bottom present
  Branded ratio: ~20–40% for company reports; ~0% for industry
  Dedup: no duplicate text within cluster

STEP 4 — VOLUME
  POST /workflow/trigger/prompt-volume/  (or existing volume trigger)
  Poll until complete

STEP 5 — RESPONSES
  POST /workflow/trigger/responses/  with 2 models (ChatGPT + Gemini)
  Auto-chains: citation_dag → insights_dag

STEP 6+ — AGGREGATE → NARRATIVE → RENDER
  (see scorecard-feasibility.md)
```

---

## LLM assist for curation (Option C detail)

Use this as a sales-facing checklist prompt. Save as `prompts/scorecard-curation.md` or embed in the orchestrator.

### Company report (25 prompts)

```
Given:
- Company: {name} ({url})
- Category: {one-line description}
- Competitors: {list}
- Geo: {market}

Generate exactly 25 prompts a real buyer would type into ChatGPT or Gemini.

Rules:
1. Funnel mix: 10 Top (category discovery), 8 Mid (comparison/evaluation), 7 Bottom (purchase decision)
2. Branded: ~8 prompts should mention {name} or a competitor by name
3. Non-branded Top prompts should reflect how someone discovers the category
4. Mid prompts should include "X vs Y" and "best X for Y" patterns
5. Bottom prompts should include pricing, worth-it, and recommendation asks
6. Use natural conversational language — not SEO keyword strings
7. All prompts must be relevant to {geo} market unless explicitly global

Output JSON only:
[{ "text": "...", "funnel": "Top|Mid|Bottom", "is_branded": true|false }]
```

### Industry report (100 prompts)

```
Given:
- Industry: {name}
- Example brands (do NOT name in prompts): {list}
- Geo: {market}

Generate exactly 100 NON-BRANDED category prompts.

Rules:
1. No brand names in any prompt
2. Group into 5–8 theme pools (e.g. Anti-aging, Acne, Sun care)
3. Funnel mix: ~40 Top, ~35 Mid, ~25 Bottom
4. Cover discovery, comparison, ingredient, routine, and purchase-intent angles
5. Prompts should reflect real AI search behavior in {geo}

Output JSON only:
[{ "text": "...", "funnel": "Top|Mid|Bottom", "pool": "..." }]
```

---

## Complexity comparison

| Dimension | Full product | Scorecard lite |
|---|---|---|
| LLM calls (prompt step) | 5 × N verticals | 0–2 total |
| Upstream DAGs required | 3+ (keyword, profiler, mapping) | 0 |
| Time to prompts | 1–4 hours (automated) | 30–60 min (manual) or 10 min (LLM draft) |
| Prompt step cost | $5–20 | $0–5 |
| Frontend screens | 5+ onboarding states | 0 (CLI) or 3 minimal |
| Code to maintain | ~3,000 lines (DAG + prompts) | ~200 lines (import + validator) |
| Quality control | Automated coverage rules | Human review checklist |

---

## Open questions (from feasibility doc, prompt-specific)

1. **Who curates?** Sales drafts with LLM assist → CS/engineer reviews before import is the fastest v1 loop.
2. **Industry reuse?** One shared 100-prompt library per vertical is strongly recommended — store as JSON in repo or S3.
3. **Branded classification?** Run `classify_text()` on import, or defer to responses/metrics time. For scorecards, manual `is_branded` flag in JSON is enough.
4. **Intent clusters?** One catch-all cluster per scorecard run is fine. Downstream metrics aggregate at domain level.
5. **When to build Option B?** Only if manual curation becomes a bottleneck after ~10 reports.

---

## Bottom line

**Automate with the SIGNAL_BANK two-step, not a single-shot prompt generator.**

The full pipeline's quality secret is not web search or vertical modules — it's the **decision-first decomposition**:

1. **Extract** what decisions buyers are making (discovery / evaluation / selection)
2. **Phrase** each decision as a natural ChatGPT question (open vs branded)

For scorecards, implement this as a **2-call lite DAG** reusing `KEYWORD_GROUNDING_SYSTEM_PROMPT` + `PRE_PURCHASE_PROMPT_GENERATOR_SYSTEM_PROMPT`, with `catch_all` module and no web/post-purchase stages. Everything downstream (volume, responses, metrics) stays unchanged.

| | Full pipeline | Automated lite |
|---|---|---|
| LLM calls | 5+ with web search | 2 (+ optional seed call) |
| Quality driver | SIGNAL_BANK | **Same SIGNAL_BANK** |
| What you lose | Real forum buyer language | ~20% phrasing richness |
| What you keep | Decision framing, funnel mix, open/branded split | All of it |

---

*Related: [`scorecard-feasibility.md`](./scorecard-feasibility.md) · Reference HTML: `Approach 1 - Client Specific.html`, `Approach 2 - Industry.html`*
