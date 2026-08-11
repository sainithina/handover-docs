#!/usr/bin/env python3
"""
Shortlist Rate & Routing Interception Rate for hospitality brands in AI answers.

Standalone, single-file tool. Not wired into gravton-console.

Metric definitions (see docs/research/hospitality_shortlist_and_routing_metrics.md
in ai-demand-case2 for the full methodology this implements):

  Shortlist Rate
    Of all discovery-style prompts run (prompts that elicit a list of named
    properties), what fraction of the time does the target brand appear among
    the first 5 properties actually named, in the order they first appear in
    the rendered answer? "Not named at all" counts as a miss, not N/A.

  Routing Interception Rate
    Conditional on the brand being named, does the response point the guest to
    a channel the brand controls (its own site, or its parent chain's direct
    booking domain) or to a third-party OTA / metasearch site? Reported both
    among all named mentions and among only the mentions that pointed anywhere,
    plus a merchant breakdown table (which specific OTAs/metasearch sites came
    up selling this property).

Pipeline per (model, prompt, repeat):
  1. Ask the model the prompt (optionally with OpenRouter's web-search plugin
     via a ":online" model suffix) -> raw answer text.
  2. Ask a second, JSON-mode extraction call to pull out the ordered list of
     named lodging properties from that answer, flagging which one (if any) is
     the target brand, and what link/domain/platform text is tied to that
     specific mention.
  3. Classify the tied link/domain against a hardcoded OTA/metasearch/direct
     domain list (no LLM judgment in this step) and score the row.

Usage:
    python hospitality_shortlist_routing.py --repeats 2
    python hospitality_shortlist_routing.py \\
        --brand "Wylie Hotel" \\
        --alias "The Wylie" --alias "Wylie Hotel Atlanta" \\
        --direct-domain wylieatlanta.com --direct-domain hilton.com \\
        --location Atlanta --models openai/gpt-4o-mini --repeats 3

Requires OPENROUTER_API_KEY in the environment or a .env file next to this
script (or in ../.env, so it picks up ai-demand-case2/.env automatically).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ---------------------------------------------------------------------------
# Hardcoded destination classification (per product decision: list-only, no
# LLM judgment for OTA vs direct). Matched as case-insensitive substrings
# against whatever domain/platform text the extractor ties to a mention.
# ---------------------------------------------------------------------------
OTA_DOMAINS: dict[str, str] = {
    "booking.com": "ota",
    "expedia.com": "ota",
    "hotels.com": "ota",
    "agoda.com": "ota",
    "trip.com": "ota",
    "priceline.com": "ota",
    "orbitz.com": "ota",
    "travelocity.com": "ota",
    "hotwire.com": "ota",
    "makemytrip.com": "ota",
    "goibibo.com": "ota",
    "ebookers.com": "ota",
    "laterooms.com": "ota",
    "hostelworld.com": "ota",
    "reservations.com": "ota",
    "getaroom.com": "ota",
    "cheaptickets.com": "ota",
    "ctrip.com": "ota",
    "despegar.com": "ota",
    "wotif.com": "ota",
    "tripadvisor.com": "metasearch",
    "kayak.com": "metasearch",
    "skyscanner.": "metasearch",
    "trivago.com": "metasearch",
    "hotelscombined.com": "metasearch",
    "momondo.com": "metasearch",
    "google.com/travel": "metasearch",
    "google.com/hotels": "metasearch",
}

DISCOVERY = "discovery"
SINGLE_ENTITY = "single_entity"

DEFAULT_BRAND = "Wylie Hotel"
DEFAULT_ALIASES = ["The Wylie", "Wylie Hotel Atlanta", "Wylie, Tapestry Collection by Hilton"]
DEFAULT_DIRECT_DOMAINS = ["wyliehotel.com", "hilton.com"]
DEFAULT_LOCATION = "Atlanta"

DEFAULT_PROMPTS: list[dict[str, str]] = [
    {"prompt": "best boutique hotels in {location}", "type": DISCOVERY},
    {"prompt": "where should I stay near Ponce City Market in {location}", "type": DISCOVERY},
    {"prompt": "recommend a hotel in Old Fourth Ward, {location}", "type": DISCOVERY},
    {"prompt": "top rated hotels in downtown {location} for a weekend trip", "type": DISCOVERY},
    {"prompt": "unique places to stay in {location} instead of a big chain hotel", "type": DISCOVERY},
    {"prompt": "best hotels near the {location} Beltline", "type": DISCOVERY},
    {"prompt": "what amenities does the {brand} have", "type": SINGLE_ENTITY},
]

DEFAULT_GENERATION_MODELS = ["openai/gpt-4o-mini"]
DEFAULT_EXTRACTION_MODEL = "openai/gpt-4o-mini"


def _load_dotenv_files() -> None:
    for candidate in (SCRIPT_DIR / ".env", SCRIPT_DIR.parent / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


# ---------------------------------------------------------------------------
# OpenRouter calls
# ---------------------------------------------------------------------------


def _post_openrouter(api_key: str, body: dict[str, Any], timeout: int = 90) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://gravton.ai",
                    "X-Title": "hospitality-shortlist-routing-metrics",
                },
                json=body,
                timeout=timeout,
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"OpenRouter {resp.status_code}: {resp.text[:400]}")
            return resp.json()
        except Exception as exc:  # noqa: BLE001 - retry loop, re-raised below
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _assistant_text(raw: dict[str, Any]) -> str:
    choices = raw.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content if isinstance(c, dict)]
        return "\n".join(p for p in parts if p)
    return ""


def _citation_urls(raw: dict[str, Any]) -> list[str]:
    """Best-effort pull of any web citations OpenRouter's ':online' plugin attached."""
    urls: list[str] = []
    choices = raw.get("choices") or []
    if not choices:
        return urls
    message = choices[0].get("message") or {}
    for ann in message.get("annotations") or []:
        if isinstance(ann, dict):
            url = (ann.get("url_citation") or {}).get("url") or ann.get("url")
            if isinstance(url, str) and url:
                urls.append(url)
    return urls


def generate_response(*, model: str, prompt: str, api_key: str, web_search: bool) -> tuple[str, list[str]]:
    model_id = f"{model}:online" if web_search and not model.endswith(":online") else model
    body = {
        "model": model_id,
        "temperature": 0.7,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful travel assistant answering a real traveler's question. "
                    "Recommend specific, real named properties where relevant. Keep the answer "
                    "conversational, the way a chat assistant would."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    raw = _post_openrouter(api_key, body)
    return _assistant_text(raw), _citation_urls(raw)


EXTRACTION_SYSTEM_PROMPT = """You extract the ordered list of named lodging properties (hotels, inns, resorts, B&Bs) from a travel assistant's answer.

Rules:
1. Read text_blob. List every DISTINCT named property mentioned, in the order it is FIRST mentioned.
   - If the answer uses an explicit numbered or bulleted list of properties, use that list order.
   - Otherwise use order of first appearance in the prose.
   - A comparison table's row order (top to bottom) counts as list order.
2. Do not create duplicate entries for the same property mentioned more than once; only its first-mention position matters.
3. target_brand and target_brand_aliases identify the brand we care about. Mark is_target_brand true on the
   single entry that refers to it (matching the canonical name or any alias, case-insensitively). If it is not
   mentioned at all, do not fabricate an entry for it.
4. For EVERY property, look at the text immediately around that specific mention (same sentence, same list item,
   or an attached citation/link near it) for any of: a URL, a bare domain, or a named platform/site
   ("book on Booking.com", "see rates on Expedia", "check availability on the hotel's website", a citation
   number tied to a source list). Put the most specific such text you find into linked_text (verbatim,
   e.g. "booking.com", "hilton.com", "the hotel's own site", "Expedia"). If nothing is tied to that specific
   mention, set linked_text to null. Do not invent a link that is not actually near that mention.
5. Only extract entities that are actual lodging properties (a specific hotel/inn/resort by name), not
   neighborhoods, cities, streets, or landmarks.
6. Ground everything in text_blob. Never use outside knowledge to add a property that is not in the text.

Return JSON only, no markdown, no commentary:
{
  "properties": [
    {"name": string, "position": integer (1-indexed, first-mention order), "is_target_brand": boolean, "linked_text": string|null}
  ]
}
If no properties are named, return {"properties": []}.
"""


def _extract_json_text(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    match = re.search(r"\{[\s\S]*\}", text)
    return match.group(0) if match else text


def _repair_json(raw: str) -> dict[str, Any]:
    text = _extract_json_text(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    open_sq, close_sq = text.count("["), text.count("]")
    open_cu, close_cu = text.count("{"), text.count("}")
    repaired = text + ("]" * max(0, open_sq - close_sq)) + ("}" * max(0, open_cu - close_cu))
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    return json.loads(repaired)


def extract_properties(
    *,
    response_text: str,
    citations: list[str],
    brand_name: str,
    aliases: list[str],
    model: str,
    api_key: str,
) -> list[dict[str, Any]]:
    if not response_text.strip():
        return []
    user_payload = {
        "text_blob": response_text,
        "target_brand": brand_name,
        "target_brand_aliases": aliases,
        "citations_seen_in_response": citations,
    }
    body = {
        "model": model,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }
    try:
        raw = _post_openrouter(api_key, body)
        text = _assistant_text(raw)
        parsed = _repair_json(text)
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] extraction failed: {exc}", file=sys.stderr)
        return []
    properties = parsed.get("properties")
    return properties if isinstance(properties, list) else []


# ---------------------------------------------------------------------------
# Classification & scoring
# ---------------------------------------------------------------------------


def _normalize_domain_text(text: str) -> str:
    text = (text or "").strip().lower()
    if not text:
        return ""
    if "://" in text:
        text = urllib.parse.urlparse(text).netloc or text
    return text.removeprefix("www.")


def classify_destination(linked_text: str | None, direct_domains: list[str]) -> str:
    """Returns one of: direct_official | ota | metasearch | other | no_link."""
    if not linked_text or not str(linked_text).strip():
        return "no_link"
    normalized = _normalize_domain_text(str(linked_text))
    haystack = normalized or str(linked_text).strip().lower()
    for domain in direct_domains:
        d = _normalize_domain_text(domain)
        if d and d in haystack:
            return "direct_official"
    for domain, category in OTA_DOMAINS.items():
        if domain in haystack:
            return category
    return "other"


@dataclass
class ResponseRow:
    prompt_id: str
    prompt_text: str
    prompt_type: str
    engine: str
    repeat_index: int
    brand_named: bool
    brand_position: int | None
    shortlisted: bool
    link_destination_raw: str | None
    link_category: str
    named_properties_count: int
    properties: list[dict[str, Any]] = field(default_factory=list)
    response_excerpt: str = ""


def score_response(
    *,
    prompt_id: str,
    prompt_text: str,
    prompt_type: str,
    engine: str,
    repeat_index: int,
    response_text: str,
    properties: list[dict[str, Any]],
    direct_domains: list[str],
) -> ResponseRow:
    target_entry = next((p for p in properties if isinstance(p, dict) and p.get("is_target_brand")), None)
    brand_named = target_entry is not None
    brand_position = None
    link_destination_raw = None
    link_category = "no_link"
    if brand_named:
        try:
            brand_position = int(target_entry.get("position"))
        except (TypeError, ValueError):
            brand_position = None
        link_destination_raw = target_entry.get("linked_text")
        link_category = classify_destination(link_destination_raw, direct_domains)

    shortlisted = bool(brand_named and brand_position is not None and brand_position <= 5)

    return ResponseRow(
        prompt_id=prompt_id,
        prompt_text=prompt_text,
        prompt_type=prompt_type,
        engine=engine,
        repeat_index=repeat_index,
        brand_named=brand_named,
        brand_position=brand_position,
        shortlisted=shortlisted,
        link_destination_raw=link_destination_raw,
        link_category=link_category,
        named_properties_count=len(properties),
        properties=properties,
        response_excerpt=(response_text[:280] + "…") if len(response_text) > 280 else response_text,
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate(rows: list[ResponseRow]) -> dict[str, Any]:
    discovery_rows = [r for r in rows if r.prompt_type == DISCOVERY]
    named_rows = [r for r in discovery_rows if r.brand_named]
    linked_rows = [r for r in named_rows if r.link_category != "no_link"]
    direct_rows = [r for r in named_rows if r.link_category == "direct_official"]

    def rate(n: int, d: int) -> float | None:
        return round(100.0 * n / d, 1) if d else None

    position_histogram = Counter(r.brand_position for r in named_rows if r.brand_position is not None)

    merchant_counter: Counter[str] = Counter()
    merchant_category: dict[str, str] = {}
    for r in named_rows:
        label = (r.link_destination_raw or "no_link").strip() if r.link_category != "no_link" else "no_link"
        merchant_counter[label] += 1
        merchant_category[label] = r.link_category
    merchant_breakdown = [
        {
            "destination": dest,
            "category": merchant_category.get(dest, "other"),
            "count": count,
            "share_of_named_pct": rate(count, len(named_rows)),
        }
        for dest, count in merchant_counter.most_common()
    ]

    by_engine: dict[str, Any] = {}
    for engine in sorted({r.engine for r in discovery_rows}):
        e_discovery = [r for r in discovery_rows if r.engine == engine]
        e_named = [r for r in e_discovery if r.brand_named]
        e_linked = [r for r in e_named if r.link_category != "no_link"]
        e_direct = [r for r in e_named if r.link_category == "direct_official"]
        e_merchant_counter: Counter[str] = Counter()
        for r in e_named:
            label = (r.link_destination_raw or "no_link").strip() if r.link_category != "no_link" else "no_link"
            e_merchant_counter[label] += 1
        by_engine[engine] = {
            "discovery_prompt_runs": len(e_discovery),
            "shortlist_rate_pct": rate(sum(1 for r in e_discovery if r.shortlisted), len(e_discovery)),
            "named_count": len(e_named),
            "routing_interception_rate_among_named_pct": rate(len(e_direct), len(e_named)),
            "routing_interception_rate_among_linked_pct": rate(len(e_direct), len(e_linked)),
            "merchant_breakdown": [
                {"destination": d, "category": e_merchant_counter and merchant_category.get(d, "other"), "count": c}
                for d, c in e_merchant_counter.most_common()
            ],
        }

    return {
        "discovery_prompt_runs": len(discovery_rows),
        "shortlisted_runs": sum(1 for r in discovery_rows if r.shortlisted),
        "shortlist_rate_pct": rate(sum(1 for r in discovery_rows if r.shortlisted), len(discovery_rows)),
        "position_histogram": dict(sorted(position_histogram.items())),
        "named_count": len(named_rows),
        "linked_count": len(linked_rows),
        "direct_official_count": len(direct_rows),
        "routing_interception_rate_among_named_pct": rate(len(direct_rows), len(named_rows)),
        "routing_interception_rate_among_linked_pct": rate(len(direct_rows), len(linked_rows)),
        "merchant_breakdown": merchant_breakdown,
        "by_engine": by_engine,
        "single_entity_prompt_runs": len(rows) - len(discovery_rows),
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(metrics: dict[str, Any], *, brand: str) -> None:
    line = "=" * 72
    print(f"\n{line}\nShortlist Rate & Routing Interception Rate — {brand}\n{line}")
    print(f"\nDiscovery-prompt runs: {metrics['discovery_prompt_runs']}")
    print(f"Shortlist Rate: {metrics['shortlist_rate_pct']}%  "
          f"({metrics['shortlisted_runs']}/{metrics['discovery_prompt_runs']})")
    if metrics["position_histogram"]:
        hist = ", ".join(f"pos {p}: {c}" for p, c in metrics["position_histogram"].items())
        print(f"  Position histogram (when named): {hist}")

    print(f"\nNamed in {metrics['named_count']}/{metrics['discovery_prompt_runs']} discovery runs")
    print(f"Routing Interception Rate (of all named):   {metrics['routing_interception_rate_among_named_pct']}%")
    print(f"Routing Interception Rate (of named+linked): {metrics['routing_interception_rate_among_linked_pct']}%")

    if metrics["merchant_breakdown"]:
        print("\nMerchant breakdown (who came up selling this property):")
        print(f"  {'Destination':<28}{'Category':<16}{'Count':<8}{'Share of named'}")
        for row in metrics["merchant_breakdown"]:
            share = f"{row['share_of_named_pct']}%" if row["share_of_named_pct"] is not None else "—"
            print(f"  {row['destination']:<28}{row['category']:<16}{row['count']:<8}{share}")

    if metrics["by_engine"]:
        print("\nBy engine:")
        for engine, e in metrics["by_engine"].items():
            print(f"  {engine}: shortlist {e['shortlist_rate_pct']}%  "
                  f"routing(named) {e['routing_interception_rate_among_named_pct']}%  "
                  f"routing(linked) {e['routing_interception_rate_among_linked_pct']}%")
    print(f"\n{line}\n")


def write_markdown_report(path: Path, metrics: dict[str, Any], *, brand: str) -> None:
    lines = [
        f"# Shortlist Rate & Routing Interception Rate — {brand}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Shortlist Rate",
        "",
        f"**{metrics['shortlist_rate_pct']}%** "
        f"({metrics['shortlisted_runs']}/{metrics['discovery_prompt_runs']} discovery-prompt runs)",
        "",
    ]
    if metrics["position_histogram"]:
        lines.append("Position histogram (when named):")
        lines.append("")
        lines.append("| Position | Count |")
        lines.append("|---|---|")
        for pos, count in metrics["position_histogram"].items():
            lines.append(f"| {pos} | {count} |")
        lines.append("")

    lines += [
        "## Routing Interception Rate",
        "",
        f"- Among all named mentions: **{metrics['routing_interception_rate_among_named_pct']}%** "
        f"({metrics['direct_official_count']}/{metrics['named_count']})",
        f"- Among named-and-linked mentions only: **{metrics['routing_interception_rate_among_linked_pct']}%** "
        f"({metrics['direct_official_count']}/{metrics['linked_count']})",
        "",
        "### Merchant breakdown",
        "",
        "| Destination | Category | Count | Share of named |",
        "|---|---|---|---|",
    ]
    for row in metrics["merchant_breakdown"]:
        share = f"{row['share_of_named_pct']}%" if row["share_of_named_pct"] is not None else "—"
        lines.append(f"| {row['destination']} | {row['category']} | {row['count']} | {share} |")

    lines += ["", "## By engine", "", "| Engine | Discovery runs | Shortlist Rate | Routing (named) | Routing (linked) |",
              "|---|---|---|---|---|"]
    for engine, e in metrics["by_engine"].items():
        lines.append(
            f"| {engine} | {e['discovery_prompt_runs']} | {e['shortlist_rate_pct']}% | "
            f"{e['routing_interception_rate_among_named_pct']}% | {e['routing_interception_rate_among_linked_pct']}% |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI / main
# ---------------------------------------------------------------------------


def _load_prompts(path: str | None, *, brand: str, location: str) -> list[dict[str, str]]:
    if path:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("prompts", [])
    else:
        items = DEFAULT_PROMPTS
    prompts = []
    for item in items:
        text = str(item.get("prompt") or "").format(brand=brand, location=location)
        prompt_type = str(item.get("type") or DISCOVERY)
        prompts.append({"prompt": text, "type": prompt_type})
    return prompts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--brand", default=DEFAULT_BRAND)
    p.add_argument("--alias", dest="aliases", action="append", default=None,
                   help="Repeatable. Defaults to a built-in Wylie Hotel alias set if omitted.")
    p.add_argument("--direct-domain", dest="direct_domains", action="append", default=None,
                   help="Repeatable. Own domain and/or parent chain's direct-booking domain.")
    p.add_argument("--location", default=DEFAULT_LOCATION)
    p.add_argument("--prompts-file", default=None, help="JSON file: [{\"prompt\": \"...\", \"type\": \"discovery|single_entity\"}]")
    p.add_argument("--models", nargs="+", default=None, help="OpenRouter model slugs to treat as 'engines'.")
    p.add_argument("--extraction-model", default=DEFAULT_EXTRACTION_MODEL)
    p.add_argument("--repeats", type=int, default=2, help="Repeat samples per (engine, prompt) — answers vary run to run.")
    p.add_argument("--max-prompts", type=int, default=None, help="Cap prompt count for a quick smoke test.")
    p.add_argument("--no-web-search", action="store_true", help="Disable OpenRouter ':online' web-search suffix.")
    p.add_argument("--out-dir", default=str(SCRIPT_DIR / "runs"))
    p.add_argument("--api-key", default=None, help="Defaults to OPENROUTER_API_KEY env var.")
    p.add_argument("--concurrency", type=int, default=6,
                   help="Parallel (model, prompt, repeat) jobs in flight. Calls are I/O-bound; raise for large batches.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv_files()
    args = parse_args(argv)

    api_key = args.api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Missing OPENROUTER_API_KEY (env var, --api-key, or .env next to this script).", file=sys.stderr)
        return 1

    brand = args.brand
    aliases = args.aliases if args.aliases is not None else (
        DEFAULT_ALIASES if brand == DEFAULT_BRAND else []
    )
    direct_domains = args.direct_domains if args.direct_domains is not None else (
        DEFAULT_DIRECT_DOMAINS if brand == DEFAULT_BRAND else []
    )
    if not direct_domains:
        print("[warn] no --direct-domain given; every named mention will classify as ota/metasearch/other/no_link.",
              file=sys.stderr)

    prompts = _load_prompts(args.prompts_file, brand=brand, location=args.location)
    if args.max_prompts:
        prompts = prompts[: args.max_prompts]
    models = args.models or DEFAULT_GENERATION_MODELS
    web_search = not args.no_web_search

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(args.out_dir) / run_id
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[str, str, str, str, int]] = []
    for model in models:
        for idx, item in enumerate(prompts):
            prompt_id = f"p{idx + 1}"
            for repeat_index in range(1, args.repeats + 1):
                jobs.append((model, prompt_id, item["prompt"], item["type"], repeat_index))

    total = len(jobs)
    done_lock = threading.Lock()
    done = 0

    def run_job(job: tuple[str, str, str, str, int]) -> ResponseRow:
        nonlocal done
        model, prompt_id, prompt_text, prompt_type, repeat_index = job
        try:
            response_text, citations = generate_response(
                model=model, prompt=prompt_text, api_key=api_key, web_search=web_search
            )
            properties = extract_properties(
                response_text=response_text,
                citations=citations,
                brand_name=brand,
                aliases=aliases,
                model=args.extraction_model,
                api_key=api_key,
            )
        except Exception as exc:  # noqa: BLE001 - keep going across the sample
            print(f"  [error] {model} {prompt_id} r{repeat_index}: {exc}", file=sys.stderr)
            response_text, citations, properties = "", [], []

        row = score_response(
            prompt_id=prompt_id,
            prompt_text=prompt_text,
            prompt_type=prompt_type,
            engine=model,
            repeat_index=repeat_index,
            response_text=response_text,
            properties=properties,
            direct_domains=direct_domains,
        )

        safe_model = re.sub(r"[^a-z0-9]+", "_", model.lower())
        out_file = raw_dir / f"{safe_model}__{prompt_id}__r{repeat_index}.json"
        out_file.write_text(
            json.dumps(
                {
                    "model": model,
                    "prompt_id": prompt_id,
                    "prompt": prompt_text,
                    "prompt_type": prompt_type,
                    "repeat_index": repeat_index,
                    "response_text": response_text,
                    "citations": citations,
                    "properties": properties,
                    "scored": row.__dict__,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        with done_lock:
            done += 1
            print(f"[{done}/{total}] {model} | {prompt_id} ({prompt_type}) | run {repeat_index}: {prompt_text!r}")
        return row

    rows: list[ResponseRow] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        for row in pool.map(run_job, jobs):
            rows.append(row)

    annotations_path = run_dir / "annotations.jsonl"
    with annotations_path.open("w", encoding="utf-8") as fh:
        for r in rows:
            record = dict(r.__dict__)
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    metrics = aggregate(rows)
    (run_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(run_dir / "report.md", metrics, brand=brand)

    print_report(metrics, brand=brand)
    print(f"Outputs written to: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
