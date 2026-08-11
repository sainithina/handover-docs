# AI Demand Estimation (Case 2) — Customer Guide

**Estimate how much AI-driven search demand exists for your prompts** — by combining classic Google search volume with AI search volume, calibrated to your market and intent groups.

This tool answers: *“If users ask this question in ChatGPT, Perplexity, or AI Overviews, how much monthly demand does it represent?”* — at the level of individual prompts, keywords, and intent themes.

---

## What you provide

| Input | Description |
|--------|-------------|
| **Prompts** | Natural-language questions your audience asks (e.g. “how to add dependents in Digit group mediclaim policy”). |
| **Intent groups** | Business themes (Family coverage, Top-up plans, OPD, etc.) so estimates can be rolled up by product line. |
| **Company profile** | Optional context (brand, market, explicit keywords). |
| **Market** | Location and language for volume data (e.g. India, English). |

Prompts can be supplied as JSON, CSV, or generated from a company profile using an LLM.

---

## What you receive

Each run produces a timestamped folder under `runs/<run_id>/` with:

| Output | What it tells you |
|--------|-------------------|
| **`prompt_estimates.csv`** | One row per prompt: **fused AI demand** (median/mean), uncertainty interval, intent group. |
| **`prompt_keyword_volumes.csv`** | Drill-down: keywords per prompt, classic **SV**, **ASV**, fusion weights, keyword-level demand. |
| **`prompt_ai_demand_linear_*` columns** | Unweighted sum of keyword volumes — useful when you want total addressable signal across all extracted terms. |
| **`insights.md`** | Executive summary: total demand and **per intent cluster** with 90% confidence ranges. |
| **`keyword_volumes.csv`** | Master keyword list with SV/ASV from DataForSEO. |
| **`calibrated.json`** | Calibration parameters (AI-share, uplift, noise) learned from your keyword set. |

Deliverables can be reordered or merged with your own spreadsheets (Group, Funnel, Type) for reporting.

---

## How estimation works (in plain terms)

1. **Keywords** — For each prompt, the system extracts relevant search phrases (LLM or semantic n-grams) and scores how well each phrase matches the prompt.

2. **Two volume sources** — For every keyword it fetches:
   - **SV** — traditional monthly search volume.
   - **ASV** — AI search volume (AI assistants / AI-mode search).

3. **Calibration** — Using historical SV/ASV pairs, CPC, and competition, the model learns how much classic search “converts” to AI demand for your category (per intent where possible).

4. **Bayesian fusion** — Each keyword gets a posterior **AI demand** estimate that blends SV and ASV instead of trusting either source alone.

5. **Prompt-level total** — Keyword estimates are combined with **fusion weights** (higher weight on phrases that best match the prompt). The reported **fused** prompt volume is this weighted blend; **linear** columns sum keyword volumes without that weighting.

6. **Intent rollup** — Keywords across all prompts in an intent are unioned, de-duplicated semantically, and estimated once to avoid double-counting near-duplicate phrases at portfolio level.

---

## Interpreting the numbers

- **Units** — Estimates are expressed as **AI demand units per month** (comparable scale within a run, anchored to search data).

- **Fused vs linear** — **Fused** demand focuses on the keywords most representative of the prompt (controlled by fusion sharpness β). **Linear** demand is higher when many keywords carry volume but only weakly match the prompt — use it as an upper-bound style view.

- **Intent totals in `insights.md`** — These are **deduplicated portfolio estimates**, not the sum of every prompt row. Per-prompt files can be summed for different analyses; intent totals are designed for cluster-level planning.

- **Low prompt volumes** — Long-tail or highly specific prompts often have little ASV/SV on extracted phrases; fused estimates stay conservative by design.

---

## Typical workflow

```bash
# Install
pip install -e .

# Configure .env: DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD, OPENROUTER_API_KEY (for LLM keywords)

# Run on your intent + prompt file (India example)
PYTHONPATH=src python scripts/run_from_intents_prompts.py \
  inputs/your_prompts.json \
  --company-profile company_profiles/digit_insurance.json \
  --keyword-extraction llm \
  --with-calibration \
  --location 2356 \
  --language en
```

**Re-run fusion only** (same keywords and volumes, new weighting β):

```bash
PYTHONPATH=src python scripts/refusion_beta_for_run.py runs/<run_id> --beta 20
```

**Dry-run** (no API, illustrative numbers):

```bash
case2 dry-run
```

---

## Key settings (for operators)

| Setting | Role |
|---------|------|
| `CASE2_BETA` | Fusion sharpness — lower spreads weight across more keywords; higher concentrates on the best-matching phrase. |
| `CASE2_KEYWORD_EXTRACTION` | `llm` (recommended) or `ngram`. |
| `--with-calibration` | Learn ρ (AI-share) and η (uplift) from your keyword universe. |
| `--location` / `--language` | DataForSEO market (e.g. `2356` = India). |

Calibration applies floors so estimates stay stable when data is sparse (minimum AI-share, uplift, and ASV noise).

---

## Data & privacy

- Volume data is retrieved via **DataForSEO** (SV and ASV APIs).
- Optional **OpenRouter** LLM calls are used for keyword extraction and prompt generation only when enabled.
- Run artifacts are stored locally under `runs/`; no cloud dashboard is required.

---

## Support & extensions

- Merge run outputs with customer taxonomy (Group, Funnel, Depth/Breadth) from Excel or CSV.
- Compare runs by refusion with different β or by refreshing ASV on an existing run.
- For technical specification (equations, sensors, aggregation), see the main [README.md](README.md) and `src/case2_demand/estimation/bayesian_sv_asv.py`.

**Questions?** Share your `run_id`, market, and whether you need prompt-level or intent-level totals — we can align reporting to your funnel and planning process.
