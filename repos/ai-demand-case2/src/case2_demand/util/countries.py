"""ISO 3166-1 alpha-2 country codes → English country names (DataForSEO global SV)."""

from __future__ import annotations

from typing import Any

# Common markets returned in clickstream global_search_volume country_distribution.
ISO_TO_COUNTRY_NAME: dict[str, str] = {
    "AD": "Andorra",
    "AE": "United Arab Emirates",
    "AF": "Afghanistan",
    "AG": "Antigua and Barbuda",
    "AI": "Anguilla",
    "AL": "Albania",
    "AM": "Armenia",
    "AO": "Angola",
    "AR": "Argentina",
    "AT": "Austria",
    "AU": "Australia",
    "AW": "Aruba",
    "AZ": "Azerbaijan",
    "BA": "Bosnia and Herzegovina",
    "BB": "Barbados",
    "BD": "Bangladesh",
    "BE": "Belgium",
    "BF": "Burkina Faso",
    "BG": "Bulgaria",
    "BH": "Bahrain",
    "BI": "Burundi",
    "BJ": "Benin",
    "BM": "Bermuda",
    "BN": "Brunei",
    "BO": "Bolivia",
    "BR": "Brazil",
    "BS": "Bahamas",
    "BT": "Bhutan",
    "BW": "Botswana",
    "BY": "Belarus",
    "BZ": "Belize",
    "CA": "Canada",
    "CD": "Democratic Republic of the Congo",
    "CF": "Central African Republic",
    "CG": "Republic of the Congo",
    "CH": "Switzerland",
    "CI": "Côte d'Ivoire",
    "CL": "Chile",
    "CM": "Cameroon",
    "CN": "China",
    "CO": "Colombia",
    "CR": "Costa Rica",
    "CU": "Cuba",
    "CV": "Cape Verde",
    "CY": "Cyprus",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "DJ": "Djibouti",
    "DK": "Denmark",
    "DM": "Dominica",
    "DO": "Dominican Republic",
    "DZ": "Algeria",
    "EC": "Ecuador",
    "EE": "Estonia",
    "EG": "Egypt",
    "ES": "Spain",
    "ET": "Ethiopia",
    "FI": "Finland",
    "FJ": "Fiji",
    "FR": "France",
    "GA": "Gabon",
    "GB": "United Kingdom",
    "GD": "Grenada",
    "GE": "Georgia",
    "GF": "French Guiana",
    "GH": "Ghana",
    "GI": "Gibraltar",
    "GL": "Greenland",
    "GM": "Gambia",
    "GN": "Guinea",
    "GP": "Guadeloupe",
    "GR": "Greece",
    "GT": "Guatemala",
    "GU": "Guam",
    "GY": "Guyana",
    "HK": "Hong Kong",
    "HN": "Honduras",
    "HR": "Croatia",
    "HT": "Haiti",
    "HU": "Hungary",
    "ID": "Indonesia",
    "IE": "Ireland",
    "IL": "Israel",
    "IN": "India",
    "IQ": "Iraq",
    "IR": "Iran",
    "IS": "Iceland",
    "IT": "Italy",
    "JM": "Jamaica",
    "JO": "Jordan",
    "JP": "Japan",
    "KE": "Kenya",
    "KG": "Kyrgyzstan",
    "KH": "Cambodia",
    "KR": "South Korea",
    "KW": "Kuwait",
    "KZ": "Kazakhstan",
    "LA": "Laos",
    "LB": "Lebanon",
    "LK": "Sri Lanka",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "LV": "Latvia",
    "LY": "Libya",
    "MA": "Morocco",
    "MC": "Monaco",
    "MD": "Moldova",
    "ME": "Montenegro",
    "MG": "Madagascar",
    "MK": "North Macedonia",
    "ML": "Mali",
    "MM": "Myanmar",
    "MN": "Mongolia",
    "MO": "Macau",
    "MQ": "Martinique",
    "MR": "Mauritania",
    "MT": "Malta",
    "MU": "Mauritius",
    "MV": "Maldives",
    "MW": "Malawi",
    "MX": "Mexico",
    "MY": "Malaysia",
    "MZ": "Mozambique",
    "NA": "Namibia",
    "NC": "New Caledonia",
    "NG": "Nigeria",
    "NI": "Nicaragua",
    "NL": "Netherlands",
    "NO": "Norway",
    "NP": "Nepal",
    "NZ": "New Zealand",
    "OM": "Oman",
    "PA": "Panama",
    "PE": "Peru",
    "PF": "French Polynesia",
    "PG": "Papua New Guinea",
    "PH": "Philippines",
    "PK": "Pakistan",
    "PL": "Poland",
    "PR": "Puerto Rico",
    "PT": "Portugal",
    "PY": "Paraguay",
    "QA": "Qatar",
    "RE": "Réunion",
    "RO": "Romania",
    "RS": "Serbia",
    "RU": "Russia",
    "RW": "Rwanda",
    "SA": "Saudi Arabia",
    "SE": "Sweden",
    "SG": "Singapore",
    "SI": "Slovenia",
    "SK": "Slovakia",
    "SN": "Senegal",
    "SV": "El Salvador",
    "TH": "Thailand",
    "TJ": "Tajikistan",
    "TN": "Tunisia",
    "TR": "Turkey",
    "TT": "Trinidad and Tobago",
    "TW": "Taiwan",
    "TZ": "Tanzania",
    "UA": "Ukraine",
    "UG": "Uganda",
    "US": "United States",
    "UY": "Uruguay",
    "UZ": "Uzbekistan",
    "VE": "Venezuela",
    "VN": "Vietnam",
    "YE": "Yemen",
    "ZA": "South Africa",
    "ZM": "Zambia",
    "ZW": "Zimbabwe",
}


def iso_to_country_name(iso_code: str | None) -> str:
    """Return English country name for ISO 3166-1 alpha-2 code; fallback to ISO if unknown."""
    iso = (iso_code or "").strip().upper()
    if not iso:
        return ""
    return ISO_TO_COUNTRY_NAME.get(iso, iso)


def enrich_country_distribution(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Add display columns to DataForSEO country_distribution rows.

    Input keys: country_iso_code, search_volume, percentage
    Added keys:
      - country_name: e.g. "United States"
      - percentage_pct: e.g. "14.93%"
      - country_share: e.g. "United States (14.93%)"
    """
    enriched: list[dict[str, Any]] = []
    for row in rows:
        iso = str(row.get("country_iso_code") or "").strip().upper()
        name = iso_to_country_name(iso)
        pct_raw = row.get("percentage")
        pct_val = float(pct_raw) if pct_raw is not None else 0.0
        pct_str = f"{pct_val:.2f}%"
        enriched.append(
            {
                **row,
                "country_name": name,
                "percentage_pct": pct_str,
                "country_share": f"{name} ({pct_str})",
            }
        )
    return enriched


def select_countries_for_coverage(
    rows: list[dict[str, Any]],
    target_pct: float = 85.0,
) -> tuple[list[dict[str, Any]], float]:
    """
    Return countries (sorted by percentage desc) until cumulative share >= target_pct.

    Returns (selected_rows, cumulative_percentage).
    Each row is enriched with country_name / percentage_pct if not already present.
    """
    enriched = enrich_country_distribution(rows)
    sorted_rows = sorted(enriched, key=lambda r: float(r.get("percentage") or 0), reverse=True)
    selected: list[dict[str, Any]] = []
    cumulative = 0.0
    for row in sorted_rows:
        selected.append(row)
        cumulative += float(row.get("percentage") or 0)
        if cumulative >= target_pct:
            break
    return selected, cumulative
