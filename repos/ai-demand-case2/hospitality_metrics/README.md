# Hospitality Shortlist Rate & Routing Interception Rate

Standalone script (kept separate from `gravton-console`). Computes two
hospitality-specific AI-visibility metrics from a fresh sample of AI answers:

- **Shortlist Rate** — of discovery-style prompts ("best boutique hotels in
  Atlanta"), what fraction of the time is the target property named among the
  first 5 properties in the rendered answer? There's no page two in an AI
  answer, so "not named" or "named 6th+" both count as a miss.
- **Routing Interception Rate** — conditional on the property being named,
  does the answer route the guest to a channel the brand controls (its own
  site, or its parent chain's direct-booking domain) or to a third-party OTA /
  metasearch site? Includes a merchant breakdown: which specific OTAs/
  metasearch sites came up selling that property.

Full methodology this implements: `../docs/research/hospitality_shortlist_and_routing_metrics.md`.

## Setup

```bash
cd hospitality_metrics
pip install -r requirements.txt
```

Needs `OPENROUTER_API_KEY`. It auto-loads from a `.env` in this folder or
from `ai-demand-case2/.env` (which already has one), or pass `--api-key`.

## Run

Quick smoke test with the built-in Wylie Hotel Atlanta sample (2 repeats, 1 engine):

```bash
python hospitality_shortlist_routing.py --max-prompts 3 --repeats 1
```

Full sample run:

```bash
python hospitality_shortlist_routing.py --repeats 3 \
  --models openai/gpt-4o-mini google/gemini-2.5-flash-lite
```

Point it at a different brand:

```bash
python hospitality_shortlist_routing.py \
  --brand "Your Hotel Name" \
  --alias "Alias One" --alias "Alias Two" \
  --direct-domain yourhotel.com --direct-domain parentchain.com \  # e.g. wyliehotel.com hilton.com
  --location "Your City" \
  --repeats 3
```

Or supply your own prompt set (only `discovery`-type prompts count toward
Shortlist Rate's denominator; `single_entity` prompts — "what amenities does
X have" — are excluded since there's no list to rank in):

```json
[
  {"prompt": "best boutique hotels in Austin", "type": "discovery"},
  {"prompt": "what amenities does Your Hotel have", "type": "single_entity"}
]
```

```bash
python hospitality_shortlist_routing.py --prompts-file my_prompts.json
```

## How it works

Per `(engine, prompt, repeat)`:

1. Ask the model the prompt (OpenRouter, with the `:online` web-search
   plugin suffix by default — disable with `--no-web-search`).
2. A second JSON-mode extraction call pulls the ordered list of named
   properties from that answer (list order if the answer is a numbered/
   bulleted list, else order of first prose mention), flags which entry (if
   any) is the target brand, and captures whatever link/domain/platform text
   is tied to that specific mention.
3. That linked text is classified against a **hardcoded** domain list
   (`OTA_DOMAINS` in the script, plus your `--direct-domain` list) — no LLM
   judgment in this step, by design. Extend `OTA_DOMAINS` as you see new
   merchants show up.

Repeats matter: answers vary run to run, so Shortlist Rate and Routing
Interception Rate are reported as a proportion across repeats, not a
yes/no from a single call.

## Outputs

Each run writes to `runs/<run_id>/`:

- `raw/*.json` — one file per (engine, prompt, repeat): the raw answer,
  extracted properties, and scored row, so every summary number is traceable.
- `annotations.jsonl` — the flat per-response scoring schema (one row per
  response): `brand_named`, `brand_position`, `shortlisted`,
  `link_destination_raw`, `link_category`, etc.
- `metrics.json` — aggregated Shortlist Rate, position histogram, Routing
  Interception Rate (both denominators), merchant breakdown, and a per-engine
  breakdown.
- `report.md` — human-readable summary in the same shape as the deliverable
  described in the methodology doc.

## Customizing the OTA/metasearch list

Edit `OTA_DOMAINS` at the top of `hospitality_shortlist_routing.py`. Keys are
lowercase domain substrings (matched against whatever the extractor ties to a
mention — a URL, a bare domain, or a platform name like "Booking.com");
values are `"ota"` or `"metasearch"`. Anything matching `--direct-domain`
wins first and classifies as `"direct_official"`.
