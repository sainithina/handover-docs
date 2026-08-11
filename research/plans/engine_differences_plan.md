# Research Plan: Engine Differences (Repeated-Sampling)

## Source row (as given)

| Theme | Question to answer | Suggested methods | Note |
|---|---|---|---|
| Engine | How do ChatGPT, Perplexity, Gemini, AI Overviews, and Claude differ in what they surface | Quantitative observation, supported by repeated quantitative sampling | Same prompts across engines, sampled many times. A difference is only real if it holds across repeated runs, since answers vary run to run. |

## Objective

Determine which differences between the 5 engines are **structural** (a real, reproducible property of how that engine sources/ranks answers) versus **noise** (just run-to-run stochastic variation any single engine would show on its own). The note is explicit that this requires repeated sampling — a single query per engine per prompt cannot distinguish a real engine effect from ordinary sampling variance.

This is a different axis from the two `sector_*` plans: those hold the engine fixed and vary sector/brand; this one holds the prompt fixed and varies engine, with repetition as the core methodological requirement.

## Scope

**Engines (5):** ChatGPT, Perplexity, Gemini, Google AI Overviews, Claude.

**Brands/prompts:** reuse the same 3 sector proxies already used in the other two plans, for cross-referencing:
- Hospitality → Wylie Hotel Atlanta (Hilton)
- SaaS → Wiz
- E-commerce → PMU Professional Supplies

Keep the **prompt set small and fixed** (this is the opposite tradeoff from the sector plans, which favor breadth of prompts/intents over repetition). Recommend **3 prompts per brand** (9 total), chosen to span a discovery/comparison prompt, a specific-fact prompt, and a reputation/review prompt — the same prompt text must be reused verbatim across all 5 engines and across all repeats, since the whole point is holding the prompt constant.

## Method — repeated sampling with a variance baseline

1. **Fix the prompt set** (9 prompts as above) and freeze the exact wording — no per-engine rephrasing.
2. **For each prompt × engine pair, run it N times** (start with **N = 5**; increase to 10 only for cells where the first 5 look borderline/ambiguous — no need to over-sample cells that are already obviously stable or obviously divergent). Total baseline budget: 9 prompts × 5 engines × 5 repeats = 225 queries.
3. **For each individual run, record the same structured fields** as the sector plans, so this data is comparable/joinable with them:
   - Was the target brand mentioned? (yes/no)
   - Cited domains + page type (`official_site`, `review_aggregator`, `forum_ugc`, `comparison_content`, `news_press`, `reference`, `video`, `other` — same vocabulary as `sector_source_mapping_plan.md`)
   - Position/prominence of the brand in the answer (first-mentioned, mid, buried, not mentioned)
   - Answer structure (prose paragraph, bullet list, comparison table, direct one-line answer)
4. **Compute within-engine run-to-run variance first**, before comparing across engines. For each engine × prompt cell, across its N repeats:
   - Mention rate (proportion of the N runs that mention the brand) with a simple confidence interval (Wilson interval is fine for N=5–10, don't overbuild this)
   - Set of distinct domains cited, and how consistent that set is run-to-run (e.g. Jaccard overlap between each pair of runs within the same engine)
5. **Only then compare across engines.** A cross-engine difference (e.g. "Perplexity cites review_aggregator pages 4x more than ChatGPT for this prompt") is only reportable as **real** if:
   - The engines' mention-rate/domain-type confidence intervals **don't overlap**, or
   - The cross-engine gap is clearly larger than the largest within-engine run-to-run spread observed in step 4.
   If a difference looks real but the CIs are wide (common at N=5), that's the trigger to bump that specific cell to N=10 rather than increasing sample size everywhere.
6. Repeat for all 9 prompts, then roll up per engine across all 3 sectors (does an engine's behavior look consistent across sectors, or does it also change by sector — connecting back to the `sector_*` plans).

## Deliverable

- `docs/research/engine_differences_results.md` — per-prompt tables showing, for each of the 5 engines: mention rate ± CI, dominant page-type(s) cited ± run-to-run consistency, typical answer structure. Explicitly marks each cross-engine comparison as **CONFIRMED DIFFERENT** (CIs don't overlap / gap exceeds within-engine noise) or **NOT DISTINGUISHABLE FROM NOISE** (CIs overlap) — don't report a difference without one of these two labels attached.
- `runs/engine_differences/` — raw per-run logs (one row per individual query execution: prompt, engine, repeat index, mentioned?, domains cited, page types, position, structure) so any summary number can be traced back to the underlying runs.

## Why N starts at 5, not higher

Repeated sampling across 5 engines is the most operationally expensive plan of the three in this research track (225 queries just for the baseline pass, before any follow-up). Starting at N=5 and only escalating specific ambiguous cells to N=10 keeps the initial pass cheap while still being enough to catch obviously-real differences (e.g. an engine that mentions the brand 5/5 times vs. one that mentions it 0/5 times is already a clear signal at N=5). Save the larger N for cells that are actually close calls.

## Explicitly out of scope for now

- No new brands beyond the 3 existing sector proxies — this plan is about engine behavior, not sector breadth (that's `sector_signal_teardown_plan.md`'s job).
- No production/`gravton-console` changes, no Case2/volume estimation work.
- No formal hypothesis-testing framework (p-values, power analysis) — confidence-interval-overlap is a deliberately lightweight bar appropriate for N=5–10 samples; if the client later needs statistical rigor beyond that, that's a scope expansion to flag, not something to build by default.
