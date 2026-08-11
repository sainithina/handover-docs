# Case 2: AI Demand Estimation (SV + ASV)

Bayesian fusion of **SV** (classic search volume) and **ASV** (AI search volume) sensors for AI-demand estimation.

> **Customer-facing overview:** see [README_CUSTOMER.md](README_CUSTOMER.md).

## Theory

We estimate AI-demand for a prompt using two sensors:

- **SV(k)**: Classic search volume (Family B) – anchors baseline demand scale
- **ASV(k)**: AI-demand sensor (Family A) – direct AI signals

The model fuses them via:

1. **SV posterior**: `si | yi ~ N(μ_s_post, σ²_s_post)` from observed `yi = log(SV(ki))`
2. **Coupling prior**: `ai | si, ρ, η ~ N(si + log ρ + log η + δc, σ²δ)` converts classic → AI demand
3. **ASV likelihood**: `xi | ai ~ N(ai + bA, σ²A,c)` with `xi = log(ASV(ki))`
4. **Fusion**: Posterior for `ai` combines coupling prior + ASV
5. **Aggregation**: `Y(p) = Σ wi · A*(ki)` with softmax weights from semantic similarity

## Dry-run (no API)

Fully worked example matching the spec:

```bash
pip install -e .
case2 dry-run
```

Uses fixed numbers: prompt "best running shoes for flat feet", keywords, SV=(90k, 40k), ASV=(22k, 9.5k). Output: **Y(p) ≈ 18.6k** AI-units/month, 90% CI [14.0k, 23.9k].

## Intent & prompt generation (DeepSeek R1)

Similar to Case 1, generate intent clusters and synthetic prompts from a company profile using **DeepSeek R1** via OpenRouter:

```bash
# Set OpenRouter API key in .env (get one at https://openrouter.ai)
OPENROUTER_API_KEY=your_key

# Step 1: Generate intent clusters
case2 generate-intents --company-profile path/to/company_profile.json

# Step 2: Generate prompts per intent
case2 generate-prompts --n-prompts-per-intent 10

# Or run full pipeline: company -> intents -> prompts -> SV+ASV -> estimate
case2 run-all --company-profile path/to/company_profile.json --n-prompts-per-intent 10
```

## Run pipeline (with DataForSEO)

```bash
# Set credentials in .env
DATAFORSEO_LOGIN=your_login
DATAFORSEO_PASSWORD=your_password

# Run on prompts (explicit or from generated)
case2 run "best running shoes for flat feet" "stability running shoes for overpronation"

# Dry-run mode (placeholder SV/ASV, no API)
case2 run "your prompt" --dry-run
```

## Outputs

- `runs/<run_id>/prompt_estimates.jsonl` – per-prompt AI demand estimates
- `runs/<run_id>/prompt_estimates.csv` – same, CSV
- `runs/<run_id>/prompt_keyword_volumes.csv` – per prompt × keyword (SV, ASV, fusion weights, AI demand)
- `runs/<run_id>/keyword_volumes.csv` – per-keyword SV/ASV
- `runs/<run_id>/metrics.json` – run summary

## Hyperparameters (env)

| Variable | Default | Description |
|----------|---------|-------------|
| CASE2_NU_C | log(50000) | νc (SV prior median) |
| CASE2_OMEGA_C | 3.0 | ωc |
| CASE2_SIGMA_S_C | 0.20 | σS,c (SV noise) |
| CASE2_SIGMA_A_C | 0.20 | σA,c (ASV noise) |
| CASE2_DELTA_C | 0.20 | δc (coupling offset) |
| CASE2_SIGMA_DELTA | 0.50 | σδ |
| CASE2_RHO | 0.25 | AI-share ρ (calibrated ρ floored at 0.25) |
| CASE2_MU_ETA | log(1.3) | log(η) prior mean (calibrated η floored at 1.3) |
| CASE2_SIGMA_A_C | 0.20 | ASV noise σ_A,c (floored at **0.5** when calibrated lower) |
| CASE2_BETA | 60.0 | Softmax sharpness (fusion weights) |

## Extracted from Case 1

- Keyword extraction (cross-encoder)
- DataForSEO client pattern
- I/O utilities
