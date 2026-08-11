# Research Plan: Live Web Search vs. Trained Memory

## Source row (as given)

| Theme | Question to answer | Suggested methods | Note |
|---|---|---|---|
| Engine | How does each engine use live web search vs trained memory | Quantitative observation, can be experimented further | *(none given)* |

## Objective

For each engine, determine **when it answers from live retrieval** (visible citations, a tool-call/"searching the web" indicator, content that reflects current reality) **vs. from trained/parametric memory** (no citation, generic phrasing, content that reflects stale/training-time state) — and build a per-engine "live-search propensity profile" by prompt type.

This complements `engine_differences_plan.md` (which asks *what* differs across engines) by asking a specific mechanism question: *why* it might differ — because one engine defaults to searching and another defaults to recalling.

## Scope

**Engines (5, same as `engine_differences_plan.md`):** ChatGPT, Perplexity, Gemini, Google AI Overviews, Claude.

**Brands:** same 3 sector proxies (Wylie Hilton, Wiz, PMU Professional) — reused specifically because we can independently verify ground truth for them (their live websites, `company_profiles/*.json`, and known recent changes), which this plan requires and the other plans didn't.

## Method — three probe categories (this is the core design choice)

The key methodological problem: you can't tell "search vs memory" from a single prompt type, because engines behave very differently depending on whether the prompt *needs* freshness. So use three deliberately different probe categories per brand:

1. **Freshness-required probes** — questions whose correct answer has demonstrably changed recently and is verifiable against the brand's live site or other current ground truth (e.g. current room rates/availability for Wylie Hilton, Wiz's current product lineup/latest feature announcement, PMU Professional's current catalog/pricing for a specific SKU). Pick facts you can confirm as of **today's date** before running the probe, and note that confirmed value so answers can be checked for accuracy, not just citation-presence.
2. **Evergreen/stable probes** — questions whose answer is unlikely to have changed in a long time (e.g. "what does Wiz do", "what city is the Wylie Hotel in", "what is PMU Professional's core product category"). These act as a baseline control — expect these to be answerable correctly from memory alone, with or without a search.
3. **Ambiguous/decision-boundary probes** — questions that don't obviously require freshness but plausibly could (e.g. "is Wiz still a good fit for a mid-size startup", "how's the Wylie Hotel's reputation these days", "are PMU Professional's PMU pigments still REACH-compliant"). These reveal each engine's *default disposition* — search-happy (searches even when not obviously required) vs memory-happy (answers from recall even when a quick search would improve accuracy).

Use ~3 prompts per category × 3 brands = ~27 prompts, run once per engine per prompt (no repeated-sampling requirement here unless a specific result looks borderline — this plan is about behavior classification, not run-to-run variance, so it can reuse `engine_differences_plan.md`'s repeated-sampling method only for cells that look ambiguous).

## What to record per response

- **Live-search evidence**: citations present? explicit "searched the web" / tool-call indicator visible in the UI? (Note: Perplexity and Google AI Overviews are close to always retrieval-grounded by design — the more interesting comparison is ChatGPT/Gemini/Claude, which can go either way.)
- **Accuracy vs. confirmed ground truth** (freshness-required probes only): does the answer match what you independently confirmed today, or does it reflect an older/stale state?
- **Hedging language**: does the engine say something like "as of my last update" or "I don't have real-time access" — this is a direct admission of memory-only mode, worth recording explicitly even without checking citations.
- **Verbosity/structure difference**: retrieval-grounded answers often look different structurally (more likely to quote a source, include a date, link out) than memory-only answers (more likely to be a flat, undated, generic paragraph) — record this as a secondary signal, not the primary one.

## Quantitative rollup

Per engine, compute:
- % of freshness-required probes that showed live-search evidence
- % of freshness-required probes that were actually accurate against confirmed ground truth (this can diverge from the above — an engine might search but still misreport, or might get it right from memory by luck)
- % of evergreen probes that showed live-search evidence anyway (a sign of a search-happy default even when unnecessary)
- % of ambiguous probes that showed live-search evidence (the real signal for "default disposition")

This gives a 2×2-ish profile per engine: **searches when needed / doesn't search when needed / searches when unnecessary / doesn't search when unnecessary** — which is more informative than a single "% uses search" number.

## "Can be experimented further" — follow-on experiment ideas

Once the baseline pass above is done, cheap follow-ups worth trying if the initial pattern is interesting enough to dig into:
- **Explicit freshness cues**: add words like "as of today", "latest", "currently", "right now" to the same ambiguous probes and see if that measurably increases live-search rate for a given engine.
- **Explicit no-search instruction** (for engines/interfaces that support it): compare forced-memory-only answers against the default, to isolate how much the default search decision actually changes the answer content (not just whether a citation appears).
- **Obscurity gradient**: repeat freshness-required probes with a well-known fact vs. a genuinely long-tail/niche fact (e.g. PMU Professional's default catalog vs. a specific niche pigment SKU) — hypothesis: engines search more readily when their own confidence in a memory-only answer would be low.
- **Cross-reference with `engine_differences_plan.md`**: for probes that show up in both plans, check whether "used live search" correlates with "cited a domain type the sector-mapping plan flagged as authoritative" — i.e. does searching actually produce *better* sourcing, or just *some* sourcing.

## Deliverable

- `docs/research/engine_live_search_vs_memory_results.md` — per-engine profile table (the 2×2 rollup above) + notable examples of stale/incorrect memory-only answers worth flagging to a client as a risk (e.g. "Engine X will confidently state outdated pricing for Wiz without searching").
- `runs/engine_live_search_vs_memory/` — raw per-probe logs: prompt, probe category, engine, live-search evidence (y/n + how detected), confirmed ground truth (for freshness probes), answer accuracy, hedging language present (y/n).

## Explicitly out of scope for now

- No new brands beyond the 3 existing sector proxies.
- No production/`gravton-console` changes, no Case2/volume estimation work.
- Repeated-sampling rigor (N=5+ per cell) is not required by default here — only escalate to repeated sampling, following `engine_differences_plan.md`'s method, for specific cells whose live-search-vs-memory classification looks inconsistent on a single run.
