#!/usr/bin/env python3
"""
Direct keyword-volume lookup for a flat list of Nike product titles.

Unlike the prompt-volume pipeline scripts (test_wylie_hotel_all_methods.py etc.),
there is no "prompt" here to extract keywords from — each product title IS the
keyword. So this script:

  1. Fetches raw SV (classic search volume) and ASV (AI search volume) from
     DataForSEO for every title, treated as a standalone keyword/query.
  2. Also runs each title through the same Case2Estimator Bayesian fusion used
     everywhere else in this project (treating the title as both its own
     "prompt" and its own sole "keyword", similarity=1.0), to get a fused
     Y_median volume estimate consistent with how prompt volume is computed
     elsewhere in this repo.

No calibration entry exists for this ad-hoc Nike product list, so hyperparameters
fall back to the shared defaults (same _global-less fallback pattern used in
test_wylie_hotel_all_methods.py for brand-new domains).

Market: United States (location_code=2840), language=en.

Usage:
    PYTHONPATH=src python scripts/get_nike_product_title_volumes.py
"""

from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from case2_demand.calibration import (  # noqa: E402
    apply_rho_eta_floors_to_calibration_dict,
    floor_sigma_a_c,
    load_calibration,
)
from case2_demand.config import Settings  # noqa: E402
from case2_demand.estimation.bayesian_sv_asv import (  # noqa: E402
    Case2Estimator,
    Case2Hyperparameters,
)
from case2_demand.keyword_volume.dataforseo import (  # noqa: E402
    DataForSEOASVClient,
    DataForSEOSVClient,
)

REFERENCE_CALIBRATION = REPO_ROOT / "runs" / "20260617T170025Z" / "calibrated.json"
LOCATION_CODE = 2840  # USA
LANGUAGE_CODE = "en"
OUTPUT_DIR = REPO_ROOT / "runs" / "nike_product_title_volumes"
OUTPUT_PATH = OUTPUT_DIR / "nike_product_title_volumes.xlsx"
INTENT_ID = "nike_product_titles_adhoc"

TITLES = [
    "Dri-FIT Park Derby IV Football Jersey",
    "India Cricket Dri-FIT Stadium Jersey",
    "Dri-FIT Energy Polo Jersey - England",
    "France Dri-FIT Stadium Home Jersey",
    "England Stadium Home Dri-FIT Jersey 2026",
    "Brazil 2026 Stadium Home Dri-FIT Football Replica Shirt",
    "Jordan T-Shirt (NBA Brooklyn Nets)",
    "Los Angeles Lakers 2025/26 Icon Edition Jersey",
    "Los Angeles Lakers 2025/26 Statement Edition Jersey",
    "Jordan Sport Dri-FIT Woven Jacket",
    "Dri-FIT Academy Drill Top",
    "Windrunner Jacket",
    "Sportswear Club Fleece Crew",
    "X Nike 560 Fleece Crew (VNV Exclusive)",
    "Jordan Sport Crossover Fleece Hoodie",
    "Sportswear Club Fleece Pullover Hoodie",
    "X Nike 560 Fleece Full-Zip Hoodie (VNV Exclusive)",
    "X Nike 560 Fleece Hoodie (VNV Exclusive)",
    "Sportswear Studio Fleece Hoodie",
    "Sportswear Club Fleece Hoodie",
    "Dri-FIT Tempo Shorts",
    "One Dri-FIT Shorts",
    "Dri-FIT Run Division Challenger Shorts",
    "Jordan Sport Fleece Shorts",
    "X Nike 560 Fleece Short (VNV Exclusive)",
    "Flow Woven Short FTBL LATAM",
    "Dri-FIT Academy Shorts",
    "Epic Knit Pants",
    "Phenom Dri-FIT Knit Joggers",
    "Jordan Sport Fleece Pant",
    "Dri-FIT Academy Football Pants",
    "X Nike 560 Fleece Pant (VNV Exclusive)",
    "Women Sportswear Trackpant",
    "Club Pant",
    "Indy Plunge Sports Bra",
    "Dri-FIT Swoosh Sports Bra",
    "Dri-FIT One Racerback Sports Bra",
    "Dri-FIT Rise 365 Running Tank",
    "Jordan Sport Tan Top",
    "Sportswear Essential Slim Crop T-Shirt",
    "Dri-FIT One Slim-Fit T-Shirt",
    "Dri-FIT Disrupt Short Sleeve Tee",
    "X Lego Graphic Tee",
    "X Nike Tee (VNV Exclusive)",
    "X NOCTA Tee",
    "M J Reissue Oversized SS Crew T-Shirt",
    "Jordan T-Shirt",
    "Sportswear Classic Boyfriend Oversized Graphic Tee",
    "Sportswear Club T-Shirt",
    "Dri-FIT Legend T-Shirt",
    "Dri-FIT Training T-Shirt",
    "Air Jordan 3 Retro",
    "React Hyperset",
    "Infinity RN 4",
    "Nike Killshot 2",
    "Air Zoom Speed",
    "React Miler 3",
    "Air Zoom Alphafly 2",
    "Waffle Debut",
    "Waffle One",
    "Air Zoom Terra Kiger 9",
    "React Terra Kiger 9",
    "Pegasus Trail 5",
    "ZoomX Streakfly",
    "Giannis Freak 6",
    "LeBron 22",
    "KD 17",
    "Air Zoom GT Cut 3",
    "Jordan One Take 5",
    "Jordan Max Aura 6",
    "Air Max Intrlk Lite",
    "Air Max Excee",
    "Air Max SYSTM",
    "Air Max SC",
    "Star Runner 4",
    "Flex Runner 3",
    "Air Monarch IV",
    "React Escape Run 2",
    "Invincible 3",
    "Air Zoom Structure 25",
    "Nike Tanjun EasyOn",
    "Nike Tanjun",
    "Blazer Low '77",
    "Blazer Mid '77",
    "Air Huarache",
    "Jordan Stadium 90",
    "Jordan Flight Flex Trainer",
    "City Response Sneakers",
    "C1Ty Premium Cordura Sneakers",
    "C1TY Surplus Sneakers",
    "SB Dunk Low",
    "SB Zoom Blazer Mid Sneakers",
    "Dunk High Sneakers",
    "Dunk Low Sneakers",
    "Court Vision Mid",
    "Court Vision Low",
    "Free Metcon 6",
    "Metcon 9",
    "Alphafly 3",
    "ZoomX Vaporfly Next% 4",
    "Winflo 11",
    "Run Defy",
    "Revolution 7",
    "Revolution 8",
    "Downshifter 14",
    "ReactX Infinity Run 4",
    "Air Zoom Pegasus 41",
    "Air Zoom Pegasus 42",
    "Vomero 18 Sneakers",
    "Zoom Vomero 5 Running Shoes",
    "Air Max 2013",
    "Air Max 97",
    "Air Max 270",
    "Air Max Cirro Slides",
    "Air Max Moto 2K Sneakers",
    "Air Max Dn Sneakers",
    "Air Max LTD 3 Sneakers",
    "Air Max Plus NSW Running",
    "Air Max 90 NSW",
    "Air Max 90 NSW Running Shoes",
    "Air Max 90 Premium Sneakers",
    "Air Max 90 Sneakers",
    "Jordan Flight Court Sneakers",
    "Air Jordan 1 Retro High OG Sneakers",
    "Air Jordan 1 Retro Low OG Banned Sneakers",
    "Air Jordan 1 Low Sneakers",
    "Air Jordan 1 Mid Sneakers",
    "Air Force 1 Sneakers",
    "Air Force 1 Shadow Sneakers",
    "Air Force 1 '07 Next Nature Sneakers",
    "Air Force 1 '07 NSW Basketball",
    "Air Force 1 '07 Sneakers",
]


def _build_hp(cal: dict, beta: float) -> tuple[Case2Hyperparameters, dict]:
    """Mirrors cli.py's _default_hp + _hp_for_intent fallback for a domain with
    no calibration entry (no _global key in this reference calibration)."""
    defaults = dict(
        nu_c=math.log(50_000), omega_c=3.0, b_S=0.0, sigma_S_c=0.20,
        b_A=0.0, sigma_A_c=0.20, delta_c=0.20, sigma_delta=0.50,
        rho=0.25, mu_eta=0.262364, sigma_eta=0.25,
    )
    sv_params_by_intent = cal.get("sv_params_by_intent") or {}
    asv_params_by_intent = cal.get("asv_params_by_intent") or {}
    svp = sv_params_by_intent.get(INTENT_ID) or sv_params_by_intent.get("_global")
    avp = asv_params_by_intent.get(INTENT_ID) or asv_params_by_intent.get("_global")

    hp = Case2Hyperparameters(
        nu_c=svp["nu_c"] if svp else defaults["nu_c"],
        omega_c=svp["omega_c"] if svp else defaults["omega_c"],
        b_S=svp["b_S"] if svp else defaults["b_S"],
        sigma_S_c=svp["sigma_S_c"] if svp else defaults["sigma_S_c"],
        b_A=avp["b_A"] if avp else defaults["b_A"],
        sigma_A_c=floor_sigma_a_c(avp["sigma_A_c"] if avp else defaults["sigma_A_c"]),
        delta_c=defaults["delta_c"],
        sigma_delta=defaults["sigma_delta"],
        beta=beta,
        rho=defaults["rho"],
        mu_eta=cal.get("mu_eta", defaults["mu_eta"]),
        sigma_eta=cal.get("sigma_eta", defaults["sigma_eta"]),
    )
    rho_by_keyword = cal.get("rho_by_keyword") or {}
    return hp, rho_by_keyword


async def main() -> None:
    settings = Settings()
    login = settings.DATAFORSEO_LOGIN or ""
    password = settings.DATAFORSEO_PASSWORD or ""
    base_url = settings.DATAFORSEO_BASE_URL or "https://api.dataforseo.com/v3"
    if not login or not password:
        print("ERROR: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD not set (check .env)", file=sys.stderr)
        sys.exit(1)
    if not REFERENCE_CALIBRATION.exists():
        print(f"ERROR: reference calibration not found: {REFERENCE_CALIBRATION}", file=sys.stderr)
        sys.exit(1)

    titles = sorted(set(TITLES), key=TITLES.index)  # dedupe, keep first-seen order
    print(f"[setup] {len(titles)} unique product titles (from {len(TITLES)} input rows)")

    cal = load_calibration(REFERENCE_CALIBRATION)
    apply_rho_eta_floors_to_calibration_dict(cal)
    beta = settings.CASE2_BETA if settings.CASE2_BETA is not None else 60.0
    hp, rho_by_keyword = _build_hp(cal, beta)

    sv_client = DataForSEOSVClient(login=login, password=password, base_url=base_url, sv_source=settings.CASE2_SV_SOURCE)
    asv_client = DataForSEOASVClient(login=login, password=password, base_url=base_url)

    print(f"[sv/asv] fetching SV + ASV for {len(titles)} titles (location={LOCATION_CODE}, lang={LANGUAGE_CODE}) ...")
    sv_results = await sv_client.get_volume(titles, location_code=LOCATION_CODE, language_code=LANGUAGE_CODE)
    asv_results = await asv_client.get_volume(titles, location_code=LOCATION_CODE, language_code=LANGUAGE_CODE)
    sv_map = {r.keyword: (r.search_volume if r.search_volume is not None else 0) for r in sv_results}
    asv_map = {r.keyword: (r.search_volume if r.search_volume is not None else 0) for r in asv_results}
    cpc_map = {r.keyword: r.cpc for r in sv_results}
    comp_map = {r.keyword: r.competition for r in sv_results}

    print("[estimate] running Case2Estimator (each title = its own prompt + sole keyword) ...")
    estimator = Case2Estimator(hp)
    rows = []
    for title in titles:
        sv = sv_map.get(title, 0) or 1  # estimator takes log(max(sv,1)) internally; keep raw sv for display separately
        asv = asv_map.get(title, 0) or 1
        Y_median, Y_mean, Y_std, interval, kw_estimates, weights = estimator.estimate_demand(
            prompt=title,
            keywords=[title],
            similarities=[1.0],
            sv_values=[sv],
            asv_values=[asv],
            rho_by_keyword=rho_by_keyword,
        )
        ke = kw_estimates[0]
        rows.append({
            "title": title,
            "sv": round(float(sv_map.get(title, 0.0)), 2),
            "asv": round(float(asv_map.get(title, 0.0)), 2),
            "cpc": cpc_map.get(title) if cpc_map.get(title) is not None else "",
            "competition": comp_map.get(title) if comp_map.get(title) is not None else "",
            "volume_y_median": round(Y_median, 2),
            "volume_y_mean": round(Y_mean, 2),
            "volume_y_std": round(Y_std, 4) if Y_std is not None else "",
            "volume_interval_90_low": round(interval[0], 2) if interval else "",
            "volume_interval_90_high": round(interval[1], 2) if interval else "",
            "keyword_a_median": round(ke.A_median, 2),
            "keyword_a_mean": round(ke.A_mean, 2),
        })

    df = pd.DataFrame(rows).sort_values("volume_y_median", ascending=False).reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="volumes", index=False)

    print(f"\nSaved -> {OUTPUT_PATH}")
    print(f"\nTop 15 by volume_y_median:")
    print(df.head(15).to_string(index=False))
    print(f"\nZero-SV count: {(df['sv'] == 0).sum()} / {len(df)}   Zero-ASV count: {(df['asv'] == 0).sum()} / {len(df)}")


if __name__ == "__main__":
    asyncio.run(main())
