#!/usr/bin/env python3
"""
Test DataForSEO Google Ads search volume API.

Fill in KEYWORDS below and ensure .env has DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD.
Run from project root: python scripts/test_sv_api.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Add project root for imports
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv

load_dotenv(project_root / ".env")

from case2_demand.config import Settings
from case2_demand.keyword_volume.dataforseo import DataForSEOSVClient

# --- Fill these manually ---
KEYWORDS = [
"ai brand visibility",
"ai buyer intent analysis",
"ai buyer intent tracking",
"ai buyer prompt analysis",
"ai buyer prompt tracking",
"ai buyer sentiment analysis",
"ai citation monitoring",
"ai citation monitoring tools",
"ai content brief creation",                                                    
"ai content compliance checking",
"ai content compliance checks",
"ai content drafting tools",
"ai content funnel intent",
"ai content optimization",
"ai content optimization platform",
"ai content optimization tools",
"ai content outline generation",
"ai content performance analytics",
"ai content production pipeline",           
"ai content quality control",
"ai content quality evaluation",
"ai content structural optimization",
"ai content structure optimization",
"ai discovery and revenue analytics",
"ai discovery and revenue optimization",
"ai discovery journey mapping",
"ai-driven content briefing",
"ai-driven content strategy",           
"ai driven customer journey mapping",
"ai driven customer journey os",
"ai-driven journey insights",
"ai influenced enterprise buying",
"ai journey analytics software",
"ai journey competitive positioning",
"ai journey sentiment analysis",
"ai-mediated buyer journey",
"ai mediated buyer journey insights",                                           
"ai mediated buyer prompts analysis",
"ai mediated discovery tools",
"ai-native content production",
"ai optimized content production",                                  
"ai platform brand tracking",
"ai platform buyer behavior analysis",
"ai platform buyer insights",
"ai platforms buyer behavior tracking",
"ai-powered content briefs",
"ai-powered journey analytics",
"ai prompt tracking analytics",         
"ai search competitive analysis",
"ai search content performance",        
"ai search demand universe",            
"ai search gap analysis",
"ai search optimization",
"ai search optimization platform",
"ai search optimization workflow",
"ai search visibility",
"ai search visibility measurement",
"ai search visibility platform",
"ai search visibility tools",
"ai visibility analytics",
"ai visibility and content strategy",
"ai visibility attribution gap",    
"ai visibility automation",
"ai visibility brand citation rates",
"ai visibility brand positioning",
"ai visibility brand tracking",
"ai visibility buyer journey",          
"ai visibility buyer journey mapping",
"ai visibility competitive analysis",
"ai visibility competitive positioning",
"ai visibility content optimization",
"ai visibility content strategy",
"ai visibility content studio",
"ai visibility customer journey",
"ai visibility customer journey os",
"ai visibility demand universe",
"ai visibility discovery evaluation",
"ai visibility discovery tools",
"ai visibility for b2b software",
"ai visibility for distributed sales",
"ai visibility for marketing teams",
"ai visibility for mid-market saas",
"ai visibility for saas",
"ai visibility gap analysis",
"ai visibility insights",
"ai visibility insights engine",
"ai visibility intelligence",
"ai visibility intelligence content",         
"ai visibility intelligence platform",          
"ai visibility marketing tools",
"ai visibility measurement",
"ai visibility measurement tools",
"ai visibility metrics",
"ai visibility monitoring",
"ai visibility opportunity engine",
"ai visibility optimization",        
"ai visibility pipeline connection",
"ai visibility platform",
"ai visibility platform monitoring",
"ai visibility positioning metrics",
"ai visibility prompt intelligence",
"ai visibility prompt tracking",
"ai visibility revenue impact",
"ai visibility sales intelligence",
"ai visibility sentiment analysis",
"ai visibility software",
"ai visibility tools",
"ai visibility tracking",
"b2b software ai visibility",
"brand-aligned content generation",
"brand visibility in ai platforms",
"brand voice content generation",
"brand voice content optimization",
"buyer journey mapping software",
"competitive positioning analytics",
"competitive positioning in ai search",
"content optimization and governance",
"content optimization competitive analysis",
"content optimization for ai search",
"content optimization for b2b",   
"content optimization for buyer journey",
"content optimization for funnel intent",
"content optimization for search visibility",
"content optimization for seo",
"content optimization for topic coverage",
"content optimization funnel intent",
"content optimization keyword suggestions",
"content optimization opportunity engine",
"content optimization software",
"content optimization strategy",
"content optimization tools",
"content optimization with competitive analysis",
"content optimization with entity coverage",
"content optimization with insights",
"content optimization with keyword suggestions",
"content optimization workflow",
"content outline drafting tool",
"content planning with ai",
"content planning with ai insights",            
"content production workflow automation",
"content refresh for ai ranking",
"content refresh optimization",
"content studio ai optimization",               
"content studio ai platform",
"content studio for ai optimization",
"content studio platform",
"content studio software",
"content workflow automation",
"customer journey analytics",
"customer journey mapping ai",          
"customer journey os",
"enterprise buyer journey analytics",
"enterprise buyer journey insights",        
"journey analytics for enterprises",
"journey analytics for marketing",
"journey analytics platform",
"multi-agent content drafting",
"multi-agent content generation",
"opportunity engine analytics",
"opportunity engine content ideas",
"opportunity engine for marketing"
]
LOCATION_CODE = 2840  # United States
# LOCATION_CODE = 2356  # India
LANGUAGE_CODE = "en"
# ---


def _parse_monthly(data: dict, vol_field: str, monthly_field: str) -> dict[str, list[dict]]:
    """Extract monthly history from a raw API response into {keyword_lower: [{year, month, volume}]}."""
    result: dict[str, list[dict]] = {}
    try:
        for task in data.get("tasks", []):
            for res in task.get("result", []) or []:
                for item in res.get("items", []) or []:
                    kw = (item.get("keyword") or "").strip().lower()
                    # SV: monthly data is under keyword_info.monthly_searches
                    # ASV: monthly data is directly under ai_monthly_searches
                    monthly_raw = (
                        (item.get("keyword_info") or {}).get(monthly_field)
                        or item.get(monthly_field)
                        or []
                    )
                    parsed = [
                        {"year": m.get("year"), "month": m.get("month"), "volume": m.get(vol_field) or 0}
                        for m in monthly_raw
                    ]
                    if kw and parsed:
                        result[kw] = parsed
    except Exception as e:
        print(f"  (Could not parse monthly data: {e})")
    return result


def _print_monthly_table(label: str, keywords: list[str], monthly_by_kw: dict[str, list[dict]]) -> None:
    print(f"\n--- {label}: monthly history (sum of all months) ---")
    print(f"  {'Keyword':<45}  {'# Months':>8}  {'Total':>10}  {'Avg/Month':>10}  {'Monthly breakdown'}")
    print(f"  {'-'*115}")
    for kw in keywords:
        monthly = monthly_by_kw.get(kw.strip().lower(), [])
        if not monthly:
            print(f"  {kw:<45}  {'N/A':>8}  {'N/A':>10}  {'N/A':>10}")
            continue
        monthly_sorted = sorted(monthly, key=lambda m: (m.get("year", 0), m.get("month", 0)))
        total = sum(m["volume"] for m in monthly_sorted)
        n = len(monthly_sorted)
        avg = total / n if n else 0
        breakdown = "  ".join(
            f"{m['year']}-{m['month']:02d}:{m['volume']:,}" for m in monthly_sorted
        )
        print(f"  {kw:<45}  {n:>8}  {total:>10,}  {avg:>10,.0f}  {breakdown}")


async def main() -> None:
    settings = Settings()
    login = settings.DATAFORSEO_LOGIN or ""
    password = settings.DATAFORSEO_PASSWORD or ""

    if not login or not password:
        print("Error: Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in .env")
        sys.exit(1)

    import base64
    import httpx

    auth = base64.b64encode(f"{login}:{password}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}

    print("Keywords:", KEYWORDS)
    print("Location:", LOCATION_CODE, "| Language:", LANGUAGE_CODE)
    print("-" * 60)

    payload = [{"keywords": KEYWORDS, "location_code": LOCATION_CODE, "language_code": LANGUAGE_CODE}]

    # ── SV: DataForSEO Labs historical search volume ──────────────────────────
    sv_url = "https://api.dataforseo.com/v3/dataforseo_labs/google/historical_search_volume/live"
    async with httpx.AsyncClient(timeout=60.0) as http:
        sv_resp = await http.post(sv_url, headers=headers, json=payload)
        sv_resp.raise_for_status()
        sv_data = sv_resp.json()

    print("\n--- Raw SV API response ---")
    print(json.dumps(sv_data, indent=2, default=str))

    sv_monthly = _parse_monthly(sv_data, vol_field="search_volume", monthly_field="monthly_searches")

    # Current SV per keyword (from keyword_info.search_volume in response)
    print("\n--- SV current values ---")
    print(f"  {'Keyword':<45}  {'Current SV':>12}")
    print(f"  {'-'*60}")
    try:
        sv_current: dict[str, int] = {}
        for task in sv_data.get("tasks", []):
            for res in task.get("result", []) or []:
                for item in res.get("items", []) or []:
                    kw = (item.get("keyword") or "").strip().lower()
                    sv = (item.get("keyword_info") or {}).get("search_volume") or 0
                    sv_current[kw] = sv
        for kw in KEYWORDS:
            sv = sv_current.get(kw.strip().lower(), 0)
            print(f"  {kw:<45}  {sv:>12,}")
    except Exception as e:
        print(f"  (Could not parse SV current: {e})")

    _print_monthly_table("SV", KEYWORDS, sv_monthly)

    # ── ASV: AI Search Volume ─────────────────────────────────────────────────
    asv_url = "https://api.dataforseo.com/v3/ai_optimization/ai_keyword_data/keywords_search_volume/live"
    async with httpx.AsyncClient(timeout=60.0) as http:
        asv_resp = await http.post(asv_url, headers=headers, json=payload)
        asv_resp.raise_for_status()
        asv_data = asv_resp.json()

    print("\n\n--- Raw ASV API response ---")
    print(json.dumps(asv_data, indent=2, default=str))

    asv_monthly = _parse_monthly(asv_data, vol_field="ai_search_volume", monthly_field="ai_monthly_searches")

    # Current ASV per keyword
    print("\n--- ASV current values ---")
    print(f"  {'Keyword':<45}  {'Current ASV':>12}")
    print(f"  {'-'*60}")
    try:
        asv_current: dict[str, int] = {}
        for task in asv_data.get("tasks", []):
            for res in task.get("result", []) or []:
                for item in res.get("items", []) or []:
                    kw = (item.get("keyword") or "").strip().lower()
                    asv = item.get("ai_search_volume") or 0
                    asv_current[kw] = asv
        for kw in KEYWORDS:
            asv = asv_current.get(kw.strip().lower(), 0)
            print(f"  {kw:<45}  {asv:>12,}")
    except Exception as e:
        print(f"  (Could not parse ASV current: {e})")

    _print_monthly_table("ASV", KEYWORDS, asv_monthly)

    # ── Combined summary ──────────────────────────────────────────────────────
    print("\n\n--- Combined SV vs ASV summary ---")
    print(f"  {'Keyword':<45}  {'SV(cur)':>10}  {'SV(total)':>10}  {'SV(avg)':>9}  {'ASV(cur)':>10}  {'ASV(total)':>11}  {'ASV(avg)':>9}")
    print(f"  {'-'*115}")
    for kw in KEYWORDS:
        key = kw.strip().lower()
        sv_c  = sv_current.get(key, 0)
        asv_c = asv_current.get(key, 0)
        sv_m  = sv_monthly.get(key, [])
        asv_m = asv_monthly.get(key, [])
        sv_tot  = sum(m["volume"] for m in sv_m)  if sv_m  else 0
        asv_tot = sum(m["volume"] for m in asv_m) if asv_m else 0
        sv_avg  = sv_tot  / len(sv_m)  if sv_m  else 0
        asv_avg = asv_tot / len(asv_m) if asv_m else 0
        print(f"  {kw:<45}  {sv_c:>10,}  {sv_tot:>10,}  {sv_avg:>9,.0f}  {asv_c:>10,}  {asv_tot:>11,}  {asv_avg:>9,.0f}")


if __name__ == "__main__":
    asyncio.run(main())
