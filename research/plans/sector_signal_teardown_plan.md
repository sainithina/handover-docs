# Research Plan: Sector-Level Signal Teardown

## Source row (as given)

| Theme | Question to answer | Suggested methods | Note |
|---|---|---|---|
| Sector | What matters most in e-commerce vs hospitality vs SaaS, and which signals each engine weights inside each sector | Qualitative teardown first, then quantitative to confirm | Read the actual cited pages. Patterns show up fast and cheap. Only count at scale once you see a pattern worth counting. Go deeper as needed. |

## Objective

Determine, per sector (e-commerce, hospitality, SaaS), what actually drives an AI answer engine to cite/recommend a brand — and whether the *same* signal (e.g. review volume, structured data, official-site authority, third-party comparison content, forum mentions) matters equally across sectors or whether each engine re-weights signals differently depending on sector.

Output should be actionable: a short list of per-sector, per-engine "what to fix first" levers, not just an academic writeup.

## Scope

**Engines:** ChatGPT, Perplexity, Google AI Overviews.
These three were picked because they differ structurally in how they source citations (ChatGPT = web-browsing tool calls + training-data priors, Perplexity = live retrieval-heavy with visible per-claim citations, Google AI Overviews = search-index-grounded, tightly coupled to classic SEO signals). That structural difference is exactly what should produce sector-dependent variation worth teardown.

**Brands (reusing existing assets already profiled in this repo, one per sector):**

| Sector | Brand | Why this one | Existing asset |
|---|---|---|---|
| Hospitality | Wylie Hotel Atlanta (Hilton) | Already has a full 100-prompt / 10-topic set and keyword-extraction comparison run in this repo (`runs/keyword_grounding_test/`) | `https://www.hilton.com/en/hotels/atlylup-wylie-hotel-atlanta/` |
| SaaS | Wiz (cloud security) | Existing company profile (`company_profiles/wiz.json`); already flagged earlier in this project as a case where generic keywords ("wiz", "cloud ai") created volume-inflation risk — useful to see if the same generic-vs-specific tension shows up in *citation* behavior, not just keyword volume | `company_profiles/wiz.json` |
| E-commerce | PMU Professional Supplies (permanent makeup / cosmetic tattoo supplies) | Existing company profile (`company_profiles/pmu_professional.json`); genuine product-catalog e-commerce/wholesale business, distinct enough from SaaS/hospitality to be a clean contrast | `company_profiles/pmu_professional.json` |

If any of these three isn't the right representative, swap it — the methodology below doesn't depend on the specific brand.

## Phase 1 — Qualitative teardown (fast, cheap, do this first)

**Goal:** spot candidate patterns before spending any effort counting them.

1. For each brand, take 8–10 prompts that a real prospective customer would plausibly type into an AI assistant (a mix of: comparison prompts, "best X for Y" prompts, feature/pricing questions, and troubleshooting/how-to prompts). Reuse existing prompt sets where available (e.g. the Wylie Hilton 100-prompt set — sample down to ~10) instead of writing new ones from scratch.
2. Run the same 8–10 prompts through each of the 3 engines (24–30 queries per brand, ~75–90 total across all three sectors).
3. For every response, record:
   - Was the brand mentioned/cited at all?
   - Which **domains** were cited as sources (official site, Reddit/forums, review aggregators like G2/Capterra/TripAdvisor, comparison/"best of" blog posts, news, Wikipedia, YouTube)?
   - What **content type** on the cited page did the answer actually draw from (a spec/feature table, a pricing page, a review snippet, a listicle ranking, structured FAQ/schema markup, a Reddit thread opinion)?
   - Did the engine paraphrase marketing copy verbatim, or synthesize/compare across multiple sources?
   - **Read the actual cited page**, not just the citation label — confirm what specific passage the engine pulled from and why that passage (structure, freshness, specificity, authority) probably made it citeable.
4. After ~10 prompts per brand, write a 5–10 bullet "first-pass pattern list" per sector, e.g.:
   - Hospitality: heavy reliance on TripAdvisor/Google review aggregates + official site amenities pages; less reliance on blog "best hotels in X" content unless the prompt is explicitly "best hotel for Y".
   - SaaS: heavy reliance on G2/Capterra comparison pages and the vendor's own docs/pricing pages; almost no reliance on Reddit unless prompt is troubleshooting-flavored ("X keeps crashing").
   - E-commerce: heavy reliance on the product page itself + review count/rating snippets; comparison content only surfaces for "best X" prompts, not for specific-product prompts.
   (These are illustrative hypotheses to test, not conclusions — replace with what you actually observe.)

**Stop condition for Phase 1:** once the same pattern shows up 3+ times independently within a sector, and looks meaningfully different from the other two sectors, it's a candidate worth quantifying. Don't try to quantify everything — only patterns that already look real from the teardown.

## Phase 2 — Quantitative confirmation (only for patterns worth counting)

**Goal:** turn "I think X matters more in SaaS than hospitality" into a number.

1. Scale up the prompt set for the sector(s)/pattern(s) worth confirming — e.g. reuse the full 100-prompt Wylie Hilton set, or generate an equivalent 50–100 prompt set for Wiz / PMU Professional following the same topic-clustering approach already used in `scripts/test_wylie_hotel_all_methods.py`.
2. For each response, tag structurally (not just eyeballing):
   - domain-of-citation category (official / review-aggregator / forum / comparison-blog / news / other)
   - whether the brand was mentioned at all (mention rate)
   - position/prominence within the answer (first-mentioned vs buried)
3. Aggregate per sector × per engine: citation-source-category distribution, mention rate, average prominence.
4. Compare distributions across sectors statistically (even simple proportion comparisons are enough at this sample size — don't over-engineer significance testing for an N of ~100 per cell).
5. Only go deeper (larger N, more brands per sector) if the first quantitative pass still doesn't clearly confirm or reject the Phase 1 hypothesis.

## Deliverables

- `docs/research/sector_signal_teardown_notes.md` — running log of Phase 1 qualitative observations, one section per sector, updated as teardown happens (citations + the specific passage read, not just domain names).
- `runs/sector_signal_teardown/` — Phase 2 quantitative outputs (raw query/response logs + a summary Excel/CSV per sector × engine, following the same multi-sheet workbook convention used in `runs/keyword_grounding_test/keyword_grounding_test.xlsx`).
- A final short synthesis (5–10 bullets) answering the original question directly: which signals matter most per sector, and where they diverge by engine.

## Explicitly out of scope for now

- No production/`gravton-console` changes — this is a standalone research exercise in `ai-demand-case2`, consistent with how prior experimental work in this repo has been kept separate from production until explicitly promoted.
- No new keyword-volume/Case2 estimation work — this research question is about *citation behavior*, not search/AI-search volume, so it doesn't need `Case2Estimator` or DataForSEO SV/ASV lookups.
