# Metric Definitions + Extraction Methodology: Shortlist Rate & Routing Interception Rate

## Source rows (as given)

| Metric | Definition | Framing note |
|---|---|---|
| Shortlist Rate | Are we in the first five properties named? | There is no page two in an AI answer. |
| Routing Interception Rate | When we are named, does the engine send the guest to us or to an OTA? Can we get a breakup of which all merchants selling this specific hotel came up | — |

Both are computed from the **same underlying response corpus** — they're not separate query campaigns, they're two different things you read off of every response you already collect. This doc reuses the brand/engine setup from the other `docs/research/*.md` plans (Wylie Hotel Atlanta as the hospitality proxy; ChatGPT, Perplexity, Gemini, Google AI Overviews, Claude as the engines).

## Metric 1 — Shortlist Rate

### Precise definition

Of all **discovery/comparison-style** prompts (prompts that elicit a list of multiple named properties, not a single-entity factual question), what fraction of the time does our target brand appear **among the first 5 properties actually named**, in the order they appear in the rendered answer?

"First five" means the *rendered, visible* list a real user sees — not some hypothetical longer internal ranking. If the engine only surfaces 3 named properties total and we're not one of them, that's a miss, not "N/A."

### Step 1 — filter to the right prompts

Shortlist Rate only makes sense for prompts that produce a **list of competing options**, e.g. "best boutique hotels in Atlanta," "where should I stay near Ponce City Market," "recommend a hotel in Old Fourth Ward." Exclude single-entity prompts (e.g. "what are the Wylie Hotel's amenities") — there's no list to rank in, so they don't belong in this metric's denominator. Tag each prompt at design time as `discovery` vs `single_entity` (this is the same `discovery/comparison` category already used in `sector_signal_teardown_plan.md`'s Phase 1 probes — reuse those prompts rather than writing new ones).

### Step 2 — resolve brand identity in the response text

Build an alias list for the target brand the same way `company_profiles/*.json` already does (`company_name` + `aliases`), e.g. for Wylie Hotel: `"Wylie Hotel"`, `"The Wylie"`, `"Wylie Hotel Atlanta"`, `"Wylie, Tapestry Collection by Hilton"`. Any of these mentioned in the response counts as "named."

### Step 3 — extract the ordered list of named properties

This is the part that needs a consistent rule, since engines don't always format answers as numbered lists:

1. If the answer uses an explicit numbered/bulleted list of properties → use that order directly.
2. If the answer is prose without explicit numbering (e.g. "You might consider the Ritz-Carlton, the Wylie Hotel, or the St. Regis...") → use **order of first mention** in the text as the position. This is a deliberate simplification, not a claim that prose order is a "true ranking" — it's the best available proxy for "what a skimming user would see first."
3. Do not de-duplicate re-mentions — only the position of the *first* mention of each property counts.
4. If the same engine response groups properties without clearly separating them (e.g. a comparison table), read row order top-to-bottom as position order.

### Step 4 — score

- Position of target brand = 1-indexed rank in the extracted list (or `not_named` if absent entirely).
- `shortlisted = 1` if `position <= 5`, else `0` (including `not_named`).
- **Shortlist Rate** (per engine, per prompt, or rolled up overall) = `sum(shortlisted) / count(discovery prompts run)`.

### Repeated sampling requirement

Per `engine_differences_plan.md`'s core finding (answers vary run-to-run), **do not compute Shortlist Rate from a single run per prompt**. Run each discovery prompt N=5 times per engine (same baseline N used in that plan) and report Shortlist Rate as a proportion across those repeats, not a binary yes/no from one query. A prompt where we're shortlisted 4/5 times is meaningfully different from 1/5, even though a single run of either could show "yes."

### Reporting

Per engine: `Shortlist Rate = X%` (with the N behind it, e.g. "18/40 discovery-prompt runs across all engines"), broken out by:
- Engine (does Perplexity shortlist us more/less than ChatGPT?)
- Prompt sub-type (generic "best hotel in Atlanta" vs. specific "boutique hotel near Ponce City Market" — specificity almost certainly changes this a lot)
- Position distribution when shortlisted (1st vs. 5th is a very different outcome even though both count as "shortlisted" — report the position histogram, not just the binary rate)

## Metric 2 — Routing Interception Rate

### Precise definition

**Conditional on the brand being named**, what fraction of those responses route the user (via hyperlink, citation, or an explicit "book on X" style card) to a channel **we control** (our own site, or — for a chain-flagged property like a Hilton property — the chain's own direct-booking domain, e.g. hilton.com) versus to a **third-party OTA/merchant** (Booking.com, Expedia, Hotels.com, Agoda, Trip.com, Priceline) or a **metasearch/aggregator** (Google Hotels, TripAdvisor, Kayak, Skyscanner)?

This metric is explicitly about **monetization capture**, not visibility — a brand can have a great Shortlist Rate and still lose the booking to an OTA if every citation routes there instead of to the direct channel.

### Step 1 — filter to responses where we're named

Only responses where the brand was actually mentioned (from Metric 1's extraction) are eligible — if we're not named, there's no routing to measure.

### Step 2 — find the actual outbound destination tied to that specific mention

- If the engine hyperlinks the brand name/mention directly → follow that link, record the destination domain.
- If the engine shows a separate citation/source list (Perplexity-style footnotes) → match the citation number/marker attached to the sentence that named the brand, not just any citation in the whole response.
- If the engine shows a structured "book now" / hotel card UI element → record whichever domain that card's action points to.
- If the brand is named with **no** associated link/citation at all in that response → tag as `no_link` (distinct from OTA routing — this is "named but didn't route anywhere," worth tracking separately since it's neither a win nor a loss to an OTA).

### Step 3 — classify the destination domain

Use a fixed vocabulary (extend as needed once you see real examples):
- `direct_official` — the property's own site, or the parent chain's direct-booking domain (e.g. `hilton.com` booking page for a Hilton-flagged property counts as "us," since that's the chain-direct channel, not a third party)
- `ota` — Booking.com, Expedia, Hotels.com, Agoda, Trip.com, Priceline, and similar
- `metasearch` — Google Hotels, TripAdvisor, Kayak, Skyscanner (these aggregate multiple sellers rather than being a single merchant)
- `other` — anything not fitting above (name it when it comes up)

### Step 4 — score

- **Routing Interception Rate** = `count(destination == direct_official) / count(responses where brand named AND some link/citation exists)`.
  (Decide up front whether `no_link` responses count in the denominator as a "miss" or are excluded — recommend reporting **both** ways: interception rate among all named mentions, and interception rate among only the mentions that actually linked somewhere, since they answer slightly different questions.)
- **Merchant breakdown** (the specific ask: "which all merchants selling this specific hotel came up") — a straightforward frequency table of every distinct destination domain seen across all named-and-linked responses, e.g.:

| Destination domain | Category | Count | Share |
|---|---|---|---|
| hilton.com | direct_official | 12 | 40% |
| booking.com | ota | 9 | 30% |
| expedia.com | ota | 5 | 17% |
| tripadvisor.com | metasearch | 4 | 13% |

Break this table out per engine too — it's very plausible one engine (e.g. Google AI Overviews, which is tightly search-index-coupled) leaks disproportionately to OTAs/metasearch compared to a more citation-disciplined engine like Perplexity.

## Shared response-annotation schema (compute both metrics from one pass)

Per individual query response, record:

| Field | Values |
|---|---|
| `prompt_id`, `engine`, `repeat_index` | — |
| `prompt_type` | `discovery` \| `single_entity` |
| `brand_named` | yes/no |
| `brand_position` | integer or `not_named` (discovery prompts only) |
| `shortlisted` | derived: `brand_position <= 5` |
| `link_destination_domain` | domain string or `no_link` (only when `brand_named = yes`) |
| `link_category` | `direct_official` \| `ota` \| `metasearch` \| `other` \| `no_link` |

This single schema feeds both metrics plus the merchant breakdown table, and it's a superset-compatible extension of the citation-logging schema already defined in `sector_source_mapping_plan.md` (same idea, applied specifically to "the citation tied to our brand's mention" rather than every citation in the response).

## Deliverable

- `docs/research/hospitality_shortlist_routing_results.md` — Shortlist Rate and Routing Interception Rate per engine, position histogram, and the merchant breakdown table.
- `runs/hospitality_shortlist_routing/` — raw per-response annotation rows (the schema above), so any summary number is traceable back to the specific response it came from.

## Explicitly out of scope for now

- No production/`gravton-console` changes, no Case2/volume estimation work.
- This doc defines methodology only — running the actual repeated queries across 5 engines is the same operational lift as `engine_differences_plan.md` and should be scheduled/budgeted the same way (start at N=5 repeats, escalate only for ambiguous cells).
