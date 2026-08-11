# Research Plan: Sector Source Mapping

## Source row (as given)

| Theme | Question to answer | Suggested methods | Note |
|---|---|---|---|
| Sector | Where does each engine pull its sector data from, meaning which domains and page types | Qualitative mapping | You find this by reading citations, not by modeling. Output is a per-sector source list you can hand a client. |

## Objective

Produce a clean, client-handoff **source list** per sector: which specific domains and page types (not signal *weighting*, just *presence*) each of the 3 engines actually draws citations from. This is a mapping exercise, not a modeling exercise — no counting/statistics required, just careful reading and cataloging.

This is a narrower, purely-qualitative companion to `sector_signal_teardown_plan.md` (that plan asks *what matters most and how much*; this one just asks *where does the data even come from*). No Phase 2 quantitative step here — the note is explicit that this is found "by reading citations, not by modeling."

## Scope

**Engines:** ChatGPT, Perplexity, Google AI Overviews (same as the signal-teardown plan, for consistency).

**Brands (same reused assets, one per sector — treat as a single-brand proxy per sector, see limitation below):**

| Sector | Brand | Existing asset |
|---|---|---|
| Hospitality | Wylie Hotel Atlanta (Hilton) | `https://www.hilton.com/en/hotels/atlylup-wylie-hotel-atlanta/`, prompt set in `runs/keyword_grounding_test/` |
| SaaS | Wiz (cloud security) | `company_profiles/wiz.json` |
| E-commerce | PMU Professional Supplies | `company_profiles/pmu_professional.json` |

## Method — qualitative mapping only

1. **Pick prompts that span intent categories**, not just one type — the source mix changes a lot by intent. Use at least one prompt per category per brand:
   - Discovery / "best X" comparison
   - Specific feature or spec question
   - Pricing question
   - Reputation / reviews / "is X good" question
   - Troubleshooting / support / how-to question
   - (Hospitality-specific) location/logistics question; (SaaS-specific) integration/API question; (e-commerce-specific) product-specific / ingredient-material question
2. **Run each prompt once per engine** (3 engines × ~6 intent categories × 3 brands ≈ 54 queries — small and fast on purpose, this is a mapping pass not a statistical one).
3. **For every citation that appears, open the actual page** and record:
   - Domain
   - Full URL (or at least URL pattern, e.g. `/reviews/`, `/pricing/`, `/blog/best-x-2026/`)
   - Page type — classify into a fixed vocabulary so the output is comparable across sectors:
     - `official_site` (brand's own site: home/product/pricing/docs page)
     - `review_aggregator` (G2, Capterra, TripAdvisor, Trustpilot, Yelp, etc.)
     - `forum_ugc` (Reddit, Quora, brand community forums)
     - `comparison_content` ("best X" / "X vs Y" blog or listicle, third-party)
     - `news_press` (news articles, press releases)
     - `reference` (Wikipedia, directories like Justdial-style listings)
     - `video` (YouTube reviews/demos)
     - `other` (anything not fitting above — name it)
   - Which engine cited it
   - Which prompt/intent category it came from
4. **Don't infer or guess a page's type from its domain name alone** — a G2 domain can also host a "best of" blog post, not just structured reviews; a brand's own domain can host a comparison ("us vs competitor") page. Classify based on what you actually read on the page.
5. Repeat until new prompts stop surfacing new domains for a given sector × engine pair — that's the signal to stop for that cell (this is the "read citations" version of a saturation stopping rule, not a fixed query count).

## Deliverable — the client-handable source list

One table per sector, e.g.:

### Hospitality — source map

| Domain | Page type | Cited by (engine) | Intent category | Example URL/pattern |
|---|---|---|---|---|
| *(fill in during execution)* | | | | |

### SaaS — source map

| Domain | Page type | Cited by (engine) | Intent category | Example URL/pattern |
|---|---|---|---|---|
| *(fill in during execution)* | | | | |

### E-commerce — source map

| Domain | Page type | Cited by (engine) | Intent category | Example URL/pattern |
|---|---|---|---|---|
| *(fill in during execution)* | | | | |

Optionally add a 4th rollup table: **page type by sector** (just the `page_type` column collapsed across domains) so a client can see at a glance "hospitality leans on review aggregators + official site; SaaS leans on comparison content + official docs; e-commerce leans on official product pages + video" (illustrative — replace with what's actually observed).

## Where to save results

- `docs/research/sector_source_map.md` — the filled-in client-deliverable tables above.
- `runs/sector_source_mapping/` — raw per-query citation logs (one row per citation, same fields as the table columns) backing the rollup, in case a client asks "show me the actual answer that cited this."

## Limitations to flag to the client

- One brand per sector is a **proxy**, not a sector-representative sample — a single hotel's citation pattern may not generalize to all hospitality brands (e.g. an independent boutique hotel vs. a Hilton-flagged property likely differ). If the client needs higher confidence, add 1–2 more brands per sector before finalizing the source list.
- Citations are a snapshot in time — engines change retrieval behavior frequently (model updates, index refreshes), so the map should note the date it was captured and be treated as perishable, not permanent.

## Explicitly out of scope for now

- No quantitative counting/statistics (that belongs to `sector_signal_teardown_plan.md`'s Phase 2, if pursued).
- No production/`gravton-console` changes, no Case2/volume estimation work — this is pure citation-source cataloging.
