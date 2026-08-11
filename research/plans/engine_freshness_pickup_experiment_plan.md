# Research Plan: Fresh-Content Pickup Experiment

## Source row (as given)

| Theme | Question to answer | Suggested methods | Note |
|---|---|---|---|
| Engine | Can we get engines to pick up fresh content we publish, and how fast | Experimental | The one question you cannot answer by watching. You publish something, then see if and when it gets pulled in. Only a test shows cause and timing. |

## Why this plan looks different from the other four

All four prior plans (`sector_signal_teardown_plan.md`, `sector_source_mapping_plan.md`, `engine_differences_plan.md`, `engine_live_search_vs_memory_plan.md`) are **observational** — they query engines about things that already exist and infer patterns from the responses. This question is explicitly **causal and longitudinal**: you have to publish something new, control exactly when and where it went live, and then track *if/when* it shows up — a one-shot query can't answer this, only a monitored experiment over time can. So this plan has a fundamentally different shape: a publish event, a monitoring cadence, and a latency measurement, not a single batch of prompts.

## Critical design decision: use synthetic canary content, not the real sector brands

The other four plans reuse Wylie Hilton / Wiz / PMU Professional because those are safe to *query about*. This plan is different — it requires *publishing* something, and we don't control those companies' actual websites. Two tracks:

**Track A — Canary content (primary, do this first):**
Publish deliberately **fictitious, unique, harmless facts** that exist nowhere else on the internet, so any engine surfacing them is unambiguous proof of pickup (not memory, not coincidence, not hallucination-that-happens-to-be-right). E.g. invent a small fictitious product with a made-up name and a made-up spec value (e.g. "the Corvexa T4 mounting bracket has a rated load of 214 kg") on a page clearly labeled as a research test page. Do **not** attach invented facts to the real brand names used elsewhere in this research track — publishing fabricated claims about real companies (Wiz, Hilton, PMU Professional) risks looking like misinformation about them, even if intended only as an internal test. Keep canary content clearly self-contained and labeled as a test artifact.

**Track B — Real content (optional, only if available):**
If the client has a real piece of content they're about to publish anyway (a real blog post, a real press release, a real product page update), that can be monitored the same way as a secondary, higher-stakes data point — but it's opportunistic, not something to fabricate content for.

This plan below is written for Track A; Track B reuses the identical monitoring methodology whenever real content becomes available.

## Method

### 1. Prepare the publish event

- Create 1 canary fact **per distribution channel** being tested, so channel is a controlled variable (a real question a client will ask: "does it matter *where* I publish?"). Suggested channels to compare:
  - Own low-authority domain/blog (whatever the team already controls)
  - A higher-authority third-party platform (e.g. a syndication platform, LinkedIn post, or similar) — if available
  - (Optional) a forum/UGC post (e.g. Reddit) — since some engines weight UGC differently, per `sector_source_mapping_plan.md`'s `forum_ugc` category
- Each canary page needs: a unique invented fact/entity, a visible publish timestamp, and — critically — must actually be crawlable (no `robots.txt`/`noindex` block, submitted to a sitemap).
- **Immediately after publishing**, actively request indexing rather than waiting for organic crawl discovery (e.g. Google Search Console URL inspection/submit, IndexNow ping if the platform supports it, Bing Webmaster Tools submit). This matters because otherwise you're measuring "how long until a crawler happens to visit," which conflates *crawl* latency with *engine pickup* latency — submitting for indexing isolates the engine-side latency more cleanly, and the difference between "submitted" and "not submitted" is itself worth recording as a variable.

### 2. Design the probe prompt per canary fact

- Write a prompt that can *only* be answered correctly using the canary fact (since it's invented, there's no other source that could produce the right answer by chance).
- Prepare **two prompt framings** per canary fact, connecting this plan to `engine_live_search_vs_memory_plan.md`:
  - A neutral/default framing (does the engine spontaneously decide to search for something it doesn't know?)
  - An explicit freshness-cued framing ("search the web for the latest spec on the Corvexa T4 bracket") — isolates whether forcing search mode changes pickup speed for engines that support it.

### 3. Monitoring cadence

Query all 5 engines (ChatGPT, Perplexity, Gemini, Google AI Overviews, Claude) with both prompt framings at fixed checkpoints after publish:

`t+1hr, t+6hr, t+24hr, t+3d, t+7d, t+14d, t+30d`

Stop early for a given engine once it has successfully surfaced the fact (record that checkpoint as the pickup latency) — no need to keep querying an engine that already picked it up, just re-confirm once more a checkpoint later to make sure it's stable, not a one-off fluke.

### 4. What to record per check

- Did the answer include the canary fact correctly, incorrectly (mutated/garbled — worth noting as a distinct failure mode from "not picked up at all"), or not at all?
- Was the canary URL cited directly? (Direct citation is strong proof; correct-but-uncited is weaker but still meaningful for engines that don't always show citations.)
- Which prompt framing (neutral vs freshness-cued) succeeded first, if they differ.
- Cross-check indexing status directly (e.g. `site:` search or Search Console) at the same checkpoints, so you can tell "engine hasn't picked it up because it's not indexed yet at all" apart from "it's indexed but this specific engine hasn't surfaced it."

## Deliverable

- `docs/research/engine_freshness_pickup_results.md` — per-channel, per-engine **pickup latency table**: first checkpoint at which each engine surfaced each canary fact, whether via direct citation, and whether the neutral or freshness-cued framing triggered it. Include a plain-language summary a client can act on, e.g. "content published on [higher-authority channel] was picked up by Perplexity within 24h but ChatGPT never surfaced it even by day 30 without an explicit freshness cue in the prompt."
- `runs/engine_freshness_pickup/` — raw per-checkpoint logs (canary fact, channel, engine, framing, checkpoint, result, cited y/n, indexing status cross-check).

## Explicitly out of scope for now

- No fabricated claims about the real sector brands (Wiz/Hilton/PMU Professional) used elsewhere in this research track — canary content must be self-contained and clearly a test artifact.
- No production/`gravton-console` changes, no Case2/volume estimation work.
- Track B (real content) is opportunistic only — don't manufacture a fake "real" publish just to run this test; wait for genuine content if that track is wanted.
