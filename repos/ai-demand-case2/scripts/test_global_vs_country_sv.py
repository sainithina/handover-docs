#!/usr/bin/env python3
"""
Compare DataForSEO clickstream search volume: worldwide vs country-specific.

Calls:
  1. POST /v3/keywords_data/clickstream_data/global_search_volume/live
     → worldwide search_volume + country_distribution[] per keyword
  2. POST /v3/keywords_data/clickstream_data/bulk_search_volume/live
     → country search_volume for the same keywords + location_code
  3. (optional reference) POST /v3/keywords_data/google/search_volume/live
     → Google Ads SV used by case2 DataForSEOSVClient

The main check: for each keyword, does
  global.country_distribution[COUNTRY_ISO].search_volume
match
  bulk_search_volume(location_code=COUNTRY).search_volume
within MATCH_TOLERANCE_PCT?

Credentials: DATAFORSEO_LOGIN + DATAFORSEO_PASSWORD in .env (project root).

Run from project root:
  python scripts/test_global_vs_country_sv.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
load_dotenv(project_root / ".env")

from case2_demand.config import Settings
from case2_demand.util.countries import enrich_country_distribution, iso_to_country_name

# --- Subsample from test_sv_api.py keyword list (161 total) ---
KEYWORDS = [
    "ai brand visibility",
    "ai content optimization platform",
    "ai search visibility",
    "ai visibility platform",
    "ai visibility measurement",
    "ai visibility gap analysis",
    "brand visibility in ai platforms",
    "content optimization for ai search",
    "content optimization software",
    "customer journey analytics",
    "enterprise buyer journey analytics",
    "opportunity engine for marketing",
]

# Country to compare (ISO from global API country_distribution)
COUNTRY_ISO = "US"
LOCATION_CODE = 2840  # United States (DataForSEO)
LANGUAGE_CODE = "en"

# Treat volumes as matching if within this % of the larger value
MATCH_TOLERANCE_PCT = 5.0

TAG = "gravton-sv-compare-test"
BASE_URL = "https://api.dataforseo.com/v3"

GLOBAL_URL = f"{BASE_URL}/keywords_data/clickstream_data/global_search_volume/live"
BULK_COUNTRY_URL = f"{BASE_URL}/keywords_data/clickstream_data/bulk_search_volume/live"
GOOGLE_SV_URL = f"{BASE_URL}/keywords_data/google/search_volume/live"


@dataclass
class KeywordComparison:
    keyword: str
    global_worldwide: int | None
    sum_country_volumes: int | None
    country_count: int
    delta_ww_vs_sum: int | None
    ww_sum_diff_pct: float | None
    ww_sum_matches: bool | None
    global_country_slice: int | None
    global_country_pct: float | None
    bulk_country: int | None
    google_ads_country: int | None
    delta_global_vs_bulk: int | None
    bulk_global_diff_pct: float | None
    bulk_global_matches: bool | None
    delta_bulk_vs_google: int | None
    bulk_google_diff_pct: float | None
    bulk_google_matches: bool | None
    notes: str = ""


def _auth_header(login: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def _task_ok(data: dict[str, Any]) -> dict[str, Any]:
    tasks = data.get("tasks") or []
    if not tasks:
        raise RuntimeError(f"No tasks in response: {json.dumps(data)[:500]}")
    task = tasks[0]
    if task.get("status_code") != 20000:
        raise RuntimeError(
            f"Task failed: status_code={task.get('status_code')} "
            f"message={task.get('status_message')}"
        )
    return task


def _parse_global_items(task: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """keyword_lower -> {worldwide, country_distribution map by ISO, enriched rows}."""
    out: dict[str, dict[str, Any]] = {}
    for block in task.get("result") or []:
        for item in block.get("items") or []:
            kw = str(item.get("keyword") or "").strip().lower()
            if not kw:
                continue
            raw_distribution = list(item.get("country_distribution") or [])
            distribution = enrich_country_distribution(raw_distribution)
            by_iso: dict[str, int] = {}
            for row in distribution:
                iso = str(row.get("country_iso_code") or "").strip().upper()
                if not iso:
                    continue
                vol = row.get("search_volume")
                if vol is not None:
                    by_iso[iso] = int(vol)
            out[kw] = {
                "worldwide": int(item["search_volume"]) if item.get("search_volume") is not None else None,
                "by_iso": by_iso,
                "country_pct": {
                    str(row.get("country_iso_code") or "").strip().upper(): float(row.get("percentage") or 0)
                    for row in distribution
                    if row.get("country_iso_code")
                },
                "country_distribution": distribution,
            }
    return out


def _parse_bulk_country_items(task: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for block in task.get("result") or []:
        for item in block.get("items") or []:
            kw = str(item.get("keyword") or "").strip().lower()
            if not kw:
                continue
            vol = item.get("search_volume")
            if vol is not None:
                out[kw] = int(vol)
    return out


def _parse_google_sv_items(task: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in task.get("result") or []:
        kw = str(row.get("keyword") or "").strip().lower()
        if not kw:
            continue
        vol = row.get("search_volume")
        if vol is not None:
            out[kw] = int(vol)
    return out


def _pct_diff(a: int | None, b: int | None) -> float | None:
    if a is None or b is None:
        return None
    denom = max(abs(a), abs(b), 1)
    return 100.0 * abs(a - b) / denom


def _within_tolerance(a: int | None, b: int | None, tolerance_pct: float) -> bool | None:
    if a is None or b is None:
        return None
    diff = _pct_diff(a, b)
    return diff is not None and diff <= tolerance_pct


async def fetch_global(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    keywords: list[str],
) -> dict[str, dict[str, Any]]:
    payload = [{"tag": TAG, "keywords": keywords}]
    resp = await client.post(GLOBAL_URL, headers=headers, json=payload)
    resp.raise_for_status()
    task = _task_ok(resp.json())
    return _parse_global_items(task)


async def fetch_bulk_country(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    keywords: list[str],
    location_code: int,
) -> dict[str, int]:
    payload = [{"tag": TAG, "location_code": location_code, "keywords": keywords}]
    resp = await client.post(BULK_COUNTRY_URL, headers=headers, json=payload)
    resp.raise_for_status()
    task = _task_ok(resp.json())
    return _parse_bulk_country_items(task)


async def fetch_google_sv_country(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    keywords: list[str],
    location_code: int,
    language_code: str,
) -> dict[str, int]:
    payload = [
        {
            "keywords": keywords,
            "location_code": location_code,
            "language_code": language_code,
            "search_partners": True,
        }
    ]
    resp = await client.post(GOOGLE_SV_URL, headers=headers, json=payload)
    resp.raise_for_status()
    task = _task_ok(resp.json())
    return _parse_google_sv_items(task)


def build_comparisons(
    *,
    keywords: list[str],
    global_data: dict[str, dict[str, Any]],
    bulk_country: dict[str, int],
    google_country: dict[str, int],
    country_iso: str,
    tolerance_pct: float,
) -> list[KeywordComparison]:
    iso = country_iso.upper()
    rows: list[KeywordComparison] = []
    for kw in keywords:
        key = kw.strip().lower()
        g = global_data.get(key, {})
        worldwide = g.get("worldwide")
        by_iso = g.get("by_iso") or {}
        country_pct_map = g.get("country_pct") or {}
        sum_countries = sum(by_iso.values()) if by_iso else None
        global_slice = by_iso.get(iso)
        bulk = bulk_country.get(key)
        google = google_country.get(key)

        delta_ww = None
        if worldwide is not None and sum_countries is not None:
            delta_ww = sum_countries - worldwide
        ww_sum_diff_pct = _pct_diff(worldwide, sum_countries)
        ww_sum_matches = _within_tolerance(worldwide, sum_countries, tolerance_pct)

        delta_bulk_global = None
        if global_slice is not None and bulk is not None:
            delta_bulk_global = bulk - global_slice
        bulk_global_diff_pct = _pct_diff(global_slice, bulk)
        bulk_global_matches = _within_tolerance(global_slice, bulk, tolerance_pct)

        delta_bulk_google = None
        if bulk is not None and google is not None:
            delta_bulk_google = bulk - google
        bulk_google_diff_pct = _pct_diff(bulk, google)
        bulk_google_matches = _within_tolerance(bulk, google, tolerance_pct)

        notes = []
        if global_slice is None:
            notes.append(f"missing {iso} in global country_distribution")
        if bulk is None:
            notes.append("missing bulk country volume")
        if google is None:
            notes.append("missing Google Ads volume")
        if worldwide is not None and global_slice is not None and worldwide < global_slice:
            notes.append("country slice > worldwide (unexpected)")

        rows.append(
            KeywordComparison(
                keyword=kw,
                global_worldwide=worldwide,
                sum_country_volumes=sum_countries,
                country_count=len(by_iso),
                delta_ww_vs_sum=delta_ww,
                ww_sum_diff_pct=ww_sum_diff_pct,
                ww_sum_matches=ww_sum_matches,
                global_country_slice=global_slice,
                global_country_pct=country_pct_map.get(iso),
                bulk_country=bulk,
                google_ads_country=google,
                delta_global_vs_bulk=delta_bulk_global,
                bulk_global_diff_pct=bulk_global_diff_pct,
                bulk_global_matches=bulk_global_matches,
                delta_bulk_vs_google=delta_bulk_google,
                bulk_google_diff_pct=bulk_google_diff_pct,
                bulk_google_matches=bulk_google_matches,
                notes="; ".join(notes),
            )
        )
    return rows


def _fmt(v: int | float | None) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return f"{v:,}"


def _match_label(flag: bool | None) -> str:
    if flag is True:
        return "YES"
    if flag is False:
        return "NO"
    return "N/A"


def print_country_distribution_table(
    *,
    keyword: str,
    worldwide: int | None,
    distribution: list[dict[str, Any]],
    top_n: int = 15,
) -> None:
    """Print country_distribution with country_name and percentage_pct columns."""
    print(f"\nCountry breakdown for keyword: {keyword!r}")
    if worldwide is not None:
        print(f"Worldwide search_volume: {worldwide:,}")
    if not distribution:
        print("  (no country_distribution rows)")
        return
    sorted_rows = sorted(
        distribution,
        key=lambda r: float(r.get("percentage") or 0),
        reverse=True,
    )[:top_n]
    header = (
        f"{'ISO':<6} {'Country':<22} {'Search volume':>16} {'% raw':>10} "
        f"{'% display':>10} {'Share label':<32}"
    )
    print(header)
    print("-" * len(header))
    for row in sorted_rows:
        iso = str(row.get("country_iso_code") or "").upper()
        print(
            f"{iso:<6} {row.get('country_name', iso_to_country_name(iso)):<22} "
            f"{_fmt(row.get('search_volume')):>16} "
            f"{float(row.get('percentage') or 0):>10.5f} "
            f"{row.get('percentage_pct', ''):>10} "
            f"{row.get('country_share', ''):<32}"
        )


def print_report(
    *,
    country_iso: str,
    location_code: int,
    tolerance_pct: float,
    rows: list[KeywordComparison],
    dump_raw: dict[str, Any] | None = None,
) -> None:
    print("=" * 130)
    print("DataForSEO: Global clickstream vs country clickstream vs Google Ads")
    print(f"Country: {country_iso} (location_code={location_code})")
    print(f"Match tolerance: {tolerance_pct}%")
    print(f"Keywords ({len(KEYWORDS)} subsampled from test_sv_api.py): {KEYWORDS}")
    print("=" * 130)

    print("\n[1] Does linear sum of country_distribution volumes equal Global WW?")
    h1 = (
        f"{'Keyword':<42} {'Global WW':>12} {'Sum countries':>14} {'#Ctry':>6} "
        f"{'Delta':>12} {'Diff %':>8} {'Match':>6}"
    )
    print(h1)
    print("-" * len(h1))
    ww_all_match = True
    for row in rows:
        if row.ww_sum_matches is False:
            ww_all_match = False
        print(
            f"{row.keyword:<42} {_fmt(row.global_worldwide):>12} {_fmt(row.sum_country_volumes):>14} "
            f"{row.country_count:>6} {_fmt(row.delta_ww_vs_sum):>12} "
            f"{_fmt(row.ww_sum_diff_pct):>8} {_match_label(row.ww_sum_matches):>6}"
        )
    print("-" * len(h1))
    if ww_all_match and all(r.ww_sum_matches is not None for r in rows):
        print(f"RESULT [WW vs sum]: All keywords — sum(countries) ≈ Global WW within {tolerance_pct}%.")
    else:
        print("RESULT [WW vs sum]: At least one keyword — sum(countries) does NOT match Global WW.")

    print(f"\n[2] Does Global {country_iso} slice match Bulk country clickstream?")
    h2 = (
        f"{'Keyword':<42} {f'Global {country_iso}':>14} {'Bulk country':>14} "
        f"{'Delta':>12} {'Diff %':>8} {'Match':>6}"
    )
    print(h2)
    print("-" * len(h2))
    bulk_global_all_match = True
    for row in rows:
        if row.bulk_global_matches is False:
            bulk_global_all_match = False
        print(
            f"{row.keyword:<42} {_fmt(row.global_country_slice):>14} {_fmt(row.bulk_country):>14} "
            f"{_fmt(row.delta_global_vs_bulk):>12} {_fmt(row.bulk_global_diff_pct):>8} "
            f"{_match_label(row.bulk_global_matches):>6}"
        )
    print("-" * len(h2))
    if bulk_global_all_match and all(r.bulk_global_matches is not None for r in rows):
        print(f"RESULT [Global {country_iso} vs Bulk]: All keywords match within {tolerance_pct}%.")
    else:
        print(f"RESULT [Global {country_iso} vs Bulk]: At least one keyword did not match.")

    print(f"\n[3] Does Bulk country clickstream match Google Ads ({country_iso})?")
    h3 = (
        f"{'Keyword':<42} {'Bulk country':>14} {'Google Ads':>12} "
        f"{'Delta':>12} {'Diff %':>8} {'Match':>6}"
    )
    print(h3)
    print("-" * len(h3))
    bulk_google_all_match = True
    for row in rows:
        if row.bulk_google_matches is False:
            bulk_google_all_match = False
        print(
            f"{row.keyword:<42} {_fmt(row.bulk_country):>14} {_fmt(row.google_ads_country):>12} "
            f"{_fmt(row.delta_bulk_vs_google):>12} {_fmt(row.bulk_google_diff_pct):>8} "
            f"{_match_label(row.bulk_google_matches):>6}"
        )
        if row.notes:
            print(f"  note: {row.notes}")
    print("-" * len(h3))
    if bulk_google_all_match and all(r.bulk_google_matches is not None for r in rows):
        print(f"RESULT [Bulk vs Google Ads]: All keywords match within {tolerance_pct}%.")
    else:
        print("RESULT [Bulk vs Google Ads]: Numbers differ — expected (different data sources / grouping).")

    print(
        "\nInterpretation:\n"
        "  • Global WW       = worldwide clickstream volume\n"
        "  • Sum countries   = linear sum of all country_distribution[].search_volume\n"
        f"  • Global {country_iso}   = US slice from global API country_distribution\n"
        "  • Bulk country    = US clickstream via bulk_search_volume API\n"
        "  • Google Ads      = Keyword Planner volume (groups synonyms; different product)"
    )

    if dump_raw:
        print("\n--- Raw API payloads (truncated) ---")
        print(json.dumps(dump_raw, indent=2, default=str)[:12000])


async def main() -> None:
    settings = Settings()
    login = (settings.DATAFORSEO_LOGIN or "").strip()
    password = (settings.DATAFORSEO_PASSWORD or "").strip()
    if not login or not password:
        print("Error: set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env")
        sys.exit(1)

    headers = _auth_header(login, password)
    raw_dump: dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        print("Fetching global clickstream volumes...")
        global_data = await fetch_global(client, headers, KEYWORDS)

        print(f"Fetching bulk clickstream volumes for location_code={LOCATION_CODE}...")
        bulk_country = await fetch_bulk_country(client, headers, KEYWORDS, LOCATION_CODE)

        print("Fetching Google Ads SV (reference)...")
        try:
            google_country = await fetch_google_sv_country(
                client, headers, KEYWORDS, LOCATION_CODE, LANGUAGE_CODE
            )
        except Exception as exc:
            print(f"  (Google Ads SV skipped: {exc})")
            google_country = {}

        if "--dump-raw" in sys.argv:
            # Re-fetch for dump only when requested (avoid doubling cost in normal runs)
            for name, url, payload in (
                ("global", GLOBAL_URL, [{"tag": TAG, "keywords": KEYWORDS}]),
                (
                    "bulk_country",
                    BULK_COUNTRY_URL,
                    [{"tag": TAG, "location_code": LOCATION_CODE, "keywords": KEYWORDS}],
                ),
            ):
                r = await client.post(url, headers=headers, json=payload)
                raw_dump[name] = r.json()

    rows = build_comparisons(
        keywords=KEYWORDS,
        global_data=global_data,
        bulk_country=bulk_country,
        google_country=google_country,
        country_iso=COUNTRY_ISO,
        tolerance_pct=MATCH_TOLERANCE_PCT,
    )

    print_report(
        country_iso=COUNTRY_ISO,
        location_code=LOCATION_CODE,
        tolerance_pct=MATCH_TOLERANCE_PCT,
        rows=rows,
        dump_raw=raw_dump if raw_dump else None,
    )

    # Show enriched country_distribution for the first keyword (with data)
    for kw in KEYWORDS:
        g = global_data.get(kw.strip().lower(), {})
        dist = g.get("country_distribution") or []
        if dist:
            print_country_distribution_table(
                keyword=kw,
                worldwide=g.get("worldwide"),
                distribution=dist,
            )
            break


if __name__ == "__main__":
    asyncio.run(main())
