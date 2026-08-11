"""Generate CompanyProfile from brand name using LLM (OpenRouter)."""

from __future__ import annotations

import json
import re
from typing import Optional

from case2_demand.config import Settings
from case2_demand.schemas import CompanyProfile

PROFILE_GEN_SYSTEM = """You are a business research assistant. Given a brand/company name, generate a detailed company profile in JSON format for AI search demand estimation.

Output ONLY valid JSON matching this schema. No markdown, no explanation.
Required fields: company_name, aliases (list), description, industry, sub_industry, products_services (list of {name, description, key_features, target_users, pricing_notes}), customer_personas (list of {name, role, seniority, goals, pains, typical_workflow, constraints}), primary_geos, primary_languages, competitors (list of {name, aliases, notes}), differentiators, common_misconceptions, regulated_or_sensitive_topics, seed_queries (5-8 example search queries users might type), must_include_terms, must_avoid_terms.

Use your knowledge. If the brand is obscure, infer from the name and industry. Be specific and accurate."""


def _ensure_list(val: object) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        s = val.strip()
        return [s] if s else []
    return []


def _ensure_str(val: object) -> str | None:
    if val is None:
        return None
    if isinstance(val, str):
        return val.strip() or None
    if isinstance(val, list):
        return " ".join(str(x).strip() for x in val if x).strip() or None
    return str(val) if val else None


def _normalize_llm_output(data: dict) -> dict:
    data = dict(data)
    list_keys = (
        "aliases", "differentiators", "common_misconceptions", "regulated_or_sensitive_topics",
        "primary_geos", "primary_languages", "seed_queries", "must_include_terms", "must_avoid_terms",
    )
    for key in list_keys:
        if key in data and data[key] is not None:
            raw = data[key]
            if isinstance(raw, str):
                parts = [s.strip() for s in raw.split("\n") if s.strip()]
                data[key] = parts if parts else []
            else:
                data[key] = _ensure_list(raw)

    if "customer_personas" in data and isinstance(data["customer_personas"], list):
        for p in data["customer_personas"]:
            if isinstance(p, dict) and "typical_workflow" in p and p["typical_workflow"] is not None:
                p["typical_workflow"] = _ensure_str(p["typical_workflow"])

    if "products_services" in data and isinstance(data["products_services"], list):
        for ps in data["products_services"]:
            if isinstance(ps, dict):
                for key in ("key_features", "target_users"):
                    if key in ps and ps[key] is not None:
                        ps[key] = _ensure_list(ps[key])

    if "customer_personas" in data and isinstance(data["customer_personas"], list):
        for p in data["customer_personas"]:
            if isinstance(p, dict):
                for key in ("goals", "pains", "constraints"):
                    if key in p and p[key] is not None:
                        p[key] = _ensure_list(p[key])

    return data


def _parse_json(s: str) -> dict | None:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    s = re.sub(r",\s*([}\]])", r"\1", s.strip())
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    try:
        import json_repair
        obj = json_repair.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    return None


def _extract_json(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("LLM returned empty response")
    candidates = [text]
    for pattern in (r"```(?:json)?\s*\n?(.*?)\n?```", r"```\s*\n?(.*?)\n?```"):
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            candidates.append(match.group(1).strip())
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        candidates.append(match.group(0))
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i, c in enumerate(text[start:], start):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : i + 1])
                    break
    seen = set()
    for raw in candidates:
        if not raw or raw in seen:
            continue
        seen.add(raw)
        result = _parse_json(raw)
        if result is not None and isinstance(result, dict):
            return result
    raise ValueError(f"Could not extract valid JSON from LLM response: {text[:500]}...")


def generate_profile_from_brand(brand_name: str, settings: Optional[Settings] = None) -> CompanyProfile:
    """Generate CompanyProfile from brand name using LLM (OpenRouter)."""
    settings = settings or Settings()
    api_key = settings.OPENROUTER_API_KEY
    if not api_key:
        raise RuntimeError("Set OPENROUTER_API_KEY in .env for profile generation")
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("Install openai: pip install openai")

    client = OpenAI(
        api_key=api_key,
        base_url=settings.OPENROUTER_BASE_URL or None,
    )
    model = settings.CASE2_LLM_MODEL

    user_msg = f"""Generate a company profile for: {brand_name}

Output valid JSON only. Include realistic products, personas, competitors, and seed_queries based on your knowledge of this company."""

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": PROFILE_GEN_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
    )
    text = resp.choices[0].message.content or ""
    data = _extract_json(text)
    data = _normalize_llm_output(data)
    return CompanyProfile.model_validate(data)
