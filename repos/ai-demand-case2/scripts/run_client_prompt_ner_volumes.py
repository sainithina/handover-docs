#!/usr/bin/env python3
"""
NER + noun-phrase chunking with configurable importance scorer for client prompt batches.

Supports Decklar / Indriya Excel inputs. Importance scoring can use:
  - cross_encoder (default production: ms-marco-MiniLM-L-6-v2)
  - bge_m3 (BAAI/bge-m3 dense cosine similarity)

Usage:
    PYTHONPATH=src python scripts/run_client_prompt_ner_volumes.py --client decklar --importance-scorer bge_m3
    PYTHONPATH=src python scripts/run_client_prompt_ner_volumes.py --client indriya --importance-scorer bge_m3
    PYTHONPATH=src python scripts/run_client_prompt_ner_volumes.py --client both --importance-scorer bge_m3
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from pathlib import Path
from typing import Callable

import pandas as pd
import spacy

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
from case2_demand.keyword_extraction.bge_m3_scorer import (  # noqa: E402
    score_keywords_with_bge_m3_importance,
)
from case2_demand.keyword_extraction.extractor import (  # noqa: E402
    score_keywords_with_importance,
)
from case2_demand.keyword_extraction.keyword_validation import is_generic_phrase  # noqa: E402
from case2_demand.keyword_volume.dataforseo import (  # noqa: E402
    DataForSEOASVClient,
    DataForSEOSVClient,
)
from case2_demand.schemas import KeywordWithImportance  # noqa: E402

REFERENCE_CALIBRATION = REPO_ROOT / "runs" / "20260617T170025Z" / "calibrated.json"
INPUT_SHEET = "Prompt – Performing Prompts"
SPACY_MODEL = "en_core_web_sm"
IMPORTANCE_THRESHOLD = 0.1

CLIENT_CONFIG = {
    "decklar": {
        "input": Path("/Users/sainithinartham/Downloads/decklar-prompts-20260728.xlsx"),
        "prefix": "decklar",
        "intent_id": "decklar_adhoc",
        "intent_name": "Decklar (adhoc prompt batch)",
        "location_code": 2840,
        "output_stem": "decklar-prompts-20260728-ner-volumes",
    },
    "indriya": {
        "input": Path("/Users/sainithinartham/Downloads/indriya-prompts-20260728.xlsx"),
        "prefix": "indriya",
        "intent_id": "indriya_adhoc",
        "intent_name": "Indriya (adhoc prompt batch)",
        "location_code": 2356,
        "output_stem": "indriya-prompts-20260728-ner-volumes",
    },
}

_LEADING_STRIP = {
    "a", "an", "the", "any", "some", "such", "this", "that", "these", "those",
    "other", "another", "each", "every", "no",
}
_NON_ENTITY_LABELS = {"CARDINAL", "ORDINAL", "DATE", "TIME", "PERCENT", "MONEY", "QUANTITY"}
_OBJECT_DEPS = {"dobj", "pobj", "attr", "acomp", "oprd"}
_NLP = None


def _get_nlp():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load(SPACY_MODEL)
    return _NLP


def _clean_chunk_text(text: str) -> str:
    words = [w for w in text.strip().split() if w]
    while words and words[0].lower().strip(".,!?") in _LEADING_STRIP:
        words = words[1:]
    return " ".join(words).strip().lower().strip(".,!?\"'")


def _is_redundant(a: str, b: str) -> bool:
    if not a or not b or a == b or a in b or b in a:
        return True
    wa, wb = set(a.split()), set(b.split())
    if not wa or not wb:
        return False
    if wa <= wb or wb <= wa:
        return True
    inter, union = len(wa & wb), len(wa | wb)
    return union > 0 and inter / union >= 0.75


def extract_ner_noun_chunk_candidates(prompt: str) -> list[dict]:
    nlp = _get_nlp()
    doc = nlp(prompt)
    raw: list[dict] = []
    for nc in doc.noun_chunks:
        cleaned = _clean_chunk_text(nc.text)
        if not cleaned:
            continue
        if len(cleaned.split()) == 1 and (nc.root.pos_ in ("PRON", "DET") or nc.root.is_stop):
            continue
        raw.append({"keyword": cleaned, "extraction_type": "noun_chunk", "spacy_label": ""})
    for tok in doc:
        if tok.pos_ != "VERB":
            continue
        for child in tok.children:
            if child.dep_ not in _OBJECT_DEPS:
                continue
            span_tokens = sorted(child.subtree, key=lambda t: t.i)
            phrase = " ".join(t.text for t in span_tokens)
            cleaned = _clean_chunk_text(f"{tok.lemma_} {phrase}")
            if cleaned:
                raw.append({"keyword": cleaned, "extraction_type": "verb_object", "spacy_label": ""})
    for ent in doc.ents:
        if ent.label_ in _NON_ENTITY_LABELS:
            continue
        cleaned = _clean_chunk_text(ent.text)
        if cleaned:
            raw.append({"keyword": cleaned, "extraction_type": "entity", "spacy_label": ent.label_})
    return raw


def _dedupe_candidates(raw: list[dict]) -> list[dict]:
    ordered = sorted(raw, key=lambda r: len(r["keyword"]), reverse=True)
    kept: list[dict] = []
    seen_text: set[str] = set()
    for cand in ordered:
        text = cand["keyword"]
        if text in seen_text or any(_is_redundant(text, k["keyword"]) for k in kept):
            continue
        seen_text.add(text)
        kept.append(cand)
    return kept


def run_ner_extraction(
    prompts: list[dict],
    *,
    max_keywords: int,
    score_fn: Callable[..., list[KeywordWithImportance]],
) -> tuple[dict[str, list[tuple[str, float, str, str]]], list[dict]]:
    out: dict[str, list[tuple[str, float, str, str]]] = {}
    extraction_log: list[dict] = []
    for p in prompts:
        pid, prompt = p["prompt_id"], p["prompt"]
        raw_candidates = extract_ner_noun_chunk_candidates(prompt)
        for c in raw_candidates:
            extraction_log.append({
                "prompt_id": pid, "prompt": prompt,
                "keyword": c["keyword"], "extraction_type": c["extraction_type"], "spacy_label": c["spacy_label"],
            })
        deduped = _dedupe_candidates(raw_candidates)
        filtered = [c for c in deduped if not is_generic_phrase(c["keyword"])]
        if not filtered:
            filtered = [{"keyword": prompt[:50].strip().lower(), "extraction_type": "fallback_prompt", "spacy_label": ""}]
        candidate_texts = [c["keyword"] for c in filtered]
        scored = score_fn(prompt, candidate_texts, max_keywords=max_keywords)
        type_lookup = {c["keyword"]: c["extraction_type"] for c in filtered}
        label_lookup = {c["keyword"]: c["spacy_label"] for c in filtered}
        if not scored:
            out[pid] = [(candidate_texts[0], 0.5, type_lookup.get(candidate_texts[0], ""), label_lookup.get(candidate_texts[0], ""))]
        else:
            out[pid] = [
                (s.keyword, s.importance_score, type_lookup.get(s.keyword, ""), label_lookup.get(s.keyword, ""))
                for s in scored
            ]
    return out, extraction_log


def apply_threshold(ner_results, threshold: float):
    filtered = {}
    fallback_flags = {}
    for pid, entries in ner_results.items():
        sorted_entries = sorted(entries, key=lambda e: e[1], reverse=True)
        kept = [e for e in sorted_entries if e[1] >= threshold]
        via_fallback = False
        if not kept:
            kept = sorted_entries[:1]
            via_fallback = True
        filtered[pid] = [(*e, via_fallback) for e in kept]
        fallback_flags[pid] = via_fallback
    return filtered, fallback_flags


def _build_hp(cal: dict, intent_id: str, beta: float):
    defaults = dict(
        nu_c=math.log(50_000), omega_c=3.0, b_S=0.0, sigma_S_c=0.20,
        b_A=0.0, sigma_A_c=0.20, delta_c=0.20, sigma_delta=0.50,
        rho=0.25, mu_eta=0.262364, sigma_eta=0.25,
    )
    sv_params_by_intent = cal.get("sv_params_by_intent") or {}
    asv_params_by_intent = cal.get("asv_params_by_intent") or {}
    svp = sv_params_by_intent.get(intent_id) or sv_params_by_intent.get("_global")
    avp = asv_params_by_intent.get(intent_id) or asv_params_by_intent.get("_global")
    hp = Case2Hyperparameters(
        nu_c=svp["nu_c"] if svp else defaults["nu_c"],
        omega_c=svp["omega_c"] if svp else defaults["omega_c"],
        b_S=svp["b_S"] if svp else defaults["b_S"],
        sigma_S_c=svp["sigma_S_c"] if svp else defaults["sigma_S_c"],
        b_A=avp["b_A"] if avp else defaults["b_A"],
        sigma_A_c=floor_sigma_a_c(avp["sigma_A_c"] if avp else defaults["sigma_A_c"]),
        delta_c=defaults["delta_c"], sigma_delta=defaults["sigma_delta"], beta=beta, rho=defaults["rho"],
        mu_eta=cal.get("mu_eta", defaults["mu_eta"]), sigma_eta=cal.get("sigma_eta", defaults["sigma_eta"]),
    )
    return hp, cal.get("rho_by_keyword") or {}


def estimate_rows(prompts, per_prompt_keywords, *, hp, rho_by_keyword, sv_map, asv_map, cpc_map, comp_map, source_meta, importance_scorer: str):
    rows = []
    estimator = Case2Estimator(hp)
    for p in prompts:
        pid, prompt, topic = p["prompt_id"], p["prompt"], p["topic"]
        entries = per_prompt_keywords.get(pid, [])
        if not entries:
            continue
        keywords = [e[0] for e in entries]
        similarities = [e[1] for e in entries]
        sv_values = [sv_map.get(kw, 1) for kw in keywords]
        asv_values = [asv_map.get(kw, 1) for kw in keywords]
        kept_via_fallback = entries[0][4] if entries else False
        Y_median, Y_mean, Y_std, interval, kw_estimates, weights = estimator.estimate_demand(
            prompt=prompt, keywords=keywords, similarities=similarities,
            sv_values=sv_values, asv_values=asv_values, rho_by_keyword=rho_by_keyword,
        )
        linear_median = sum(ke.A_median for ke in kw_estimates)
        linear_mean = sum(ke.A_mean for ke in kw_estimates)
        importance_lookup = dict(zip(keywords, similarities))
        extra_lookup = {e[0]: e for e in entries}
        meta = source_meta.get(pid, {})
        for ke in kw_estimates:
            extra = extra_lookup.get(ke.keyword, ("", 0.0, "", "", False))
            rows.append({
                "Topic": topic, "prompt_id": pid, "Prompt": prompt,
                "source_Volume": meta.get("Volume", ""), "source_Presence": meta.get("Presence", ""),
                "source_Funnel": meta.get("Funnel", ""), "importance_scorer": importance_scorer,
                "importance_threshold": IMPORTANCE_THRESHOLD, "kept_via_fallback": kept_via_fallback,
                "prompt_ai_demand_median": round(Y_median, 2), "prompt_ai_demand_mean": round(Y_mean, 2),
                "prompt_ai_demand_linear_median": round(linear_median, 2), "prompt_ai_demand_linear_mean": round(linear_mean, 2),
                "keyword": ke.keyword, "importance_score": round(float(importance_lookup.get(ke.keyword, 0.0)), 4),
                "fusion_weight": round(float(weights.get(ke.keyword, 0.0)), 6),
                "sv": round(float(sv_map.get(ke.keyword, 0.0)), 2), "asv": round(float(asv_map.get(ke.keyword, 0.0)), 2),
                "keyword_ai_demand_median": round(ke.A_median, 2), "keyword_ai_demand_mean": round(ke.A_mean, 2),
                "extraction_type": extra[2] if len(extra) > 2 else "", "spacy_label": extra[3] if len(extra) > 3 else "",
                "cpc": cpc_map.get(ke.keyword) if cpc_map.get(ke.keyword) is not None else "",
                "competition": comp_map.get(ke.keyword) if comp_map.get(ke.keyword) is not None else "",
            })
    return rows


def load_prompts(input_path: Path, prefix: str):
    df = pd.read_excel(input_path, sheet_name=INPUT_SHEET)
    prompts, source_meta = [], {}
    for i, row in df.iterrows():
        pid = f"{prefix}_{i + 1:04d}"
        topic = str(row.get("Topic", "") or "")
        prompt = str(row.get("Prompt", "") or "").strip()
        if not prompt or prompt == "nan":
            continue
        prompts.append({"prompt_id": pid, "topic": topic, "prompt": prompt})
        source_meta[pid] = {
            "Volume": row.get("Volume", ""), "Presence": row.get("Presence", ""),
            "Funnel": row.get("Funnel", ""), "Performance": row.get("Performance", ""),
            "Brand Mentions": row.get("Brand Mentions", ""),
        }
    return prompts, df, source_meta


def build_summary(prompts, detail_df, source_meta, sheet_prefix: str):
    rows = []
    y_col = f"{sheet_prefix}_y_median"
    for p in prompts:
        pid = p["prompt_id"]
        sub = detail_df[detail_df["prompt_id"] == pid] if len(detail_df) else detail_df
        meta = source_meta.get(pid, {})
        row = {
            "Topic": p["topic"], "prompt_id": pid, "Prompt": p["prompt"],
            "source_Volume": meta.get("Volume", ""), "source_Presence": meta.get("Presence", ""),
            "source_Funnel": meta.get("Funnel", ""), "source_Performance": meta.get("Performance", ""),
            y_col: float(sub["prompt_ai_demand_median"].iloc[0]) if len(sub) else None,
            f"{sheet_prefix}_y_mean": float(sub["prompt_ai_demand_mean"].iloc[0]) if len(sub) else None,
            f"{sheet_prefix}_keyword_count": len(sub),
            "kept_via_fallback": bool(sub["kept_via_fallback"].iloc[0]) if len(sub) else False,
        }
        if len(sub):
            contrib = sub["fusion_weight"] * sub["keyword_ai_demand_median"]
            top_idx = contrib.idxmax()
            row[f"{sheet_prefix}_top_keyword"] = sub.loc[top_idx, "keyword"]
            row[f"{sheet_prefix}_top_keyword_sv"] = sub.loc[top_idx, "sv"]
            row[f"{sheet_prefix}_top_keyword_asv"] = sub.loc[top_idx, "asv"]
        rows.append(row)
    return pd.DataFrame(rows)


async def run_client(client: str, importance_scorer: str) -> None:
    cfg = CLIENT_CONFIG[client]
    input_path = cfg["input"]
    if not input_path.exists():
        print(f"ERROR: input not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    suffix = "" if importance_scorer == "cross_encoder" else "-bge-m3"
    sheet_prefix = "ner_th_0.1" if importance_scorer == "cross_encoder" else "ner_th_0.1_bge_m3"
    output_stem = cfg["output_stem"] + suffix
    output_dir = REPO_ROOT / "runs" / f"{client}_ner_th0.1{suffix.replace('-', '_')}"
    output_paths = [
        output_dir / f"{output_stem}.xlsx",
        Path("/Users/sainithinartham/Downloads") / f"{output_stem}.xlsx",
    ]

    settings = Settings()
    login = settings.DATAFORSEO_LOGIN or ""
    password = settings.DATAFORSEO_PASSWORD or ""
    base_url = settings.DATAFORSEO_BASE_URL or "https://api.dataforseo.com/v3"
    if not login or not password:
        print("ERROR: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD not set", file=sys.stderr)
        sys.exit(1)

    if importance_scorer == "bge_m3":
        score_fn = score_keywords_with_bge_m3_importance
        scorer_label = "BAAI/bge-m3"
        print(f"[setup] loading BGE-M3 importance scorer ({scorer_label}) ...")
        score_keywords_with_bge_m3_importance("warmup query", ["warmup keyword"], max_keywords=1)
    else:
        ce_model = settings.CASE2_CROSS_ENCODER_MODEL
        score_fn = lambda prompt, kws, max_keywords: score_keywords_with_importance(
            prompt, kws, model_name=ce_model, max_keywords=max_keywords,
        )
        scorer_label = ce_model

    prompts, source_df, source_meta = load_prompts(input_path, cfg["prefix"])
    print(f"\n[{client}] {len(prompts)} prompts | importance_scorer={scorer_label} | location={cfg['location_code']}")

    cal = load_calibration(REFERENCE_CALIBRATION)
    apply_rho_eta_floors_to_calibration_dict(cal)
    beta = settings.CASE2_BETA if settings.CASE2_BETA is not None else 60.0
    hp, rho_by_keyword = _build_hp(cal, cfg["intent_id"], beta)
    max_keywords = settings.CASE2_MAX_KEYWORDS

    ner_results, extraction_log = run_ner_extraction(prompts, max_keywords=max_keywords, score_fn=score_fn)
    filtered_results, fallback_flags = apply_threshold(ner_results, IMPORTANCE_THRESHOLD)
    print(f"    fallback prompts: {sum(1 for v in fallback_flags.values() if v)}")

    all_keywords = sorted({e[0] for entries in filtered_results.values() for e in entries})
    print(f"[sv/asv] fetching {len(all_keywords)} keywords ...")
    sv_client = DataForSEOSVClient(login=login, password=password, base_url=base_url, sv_source=settings.CASE2_SV_SOURCE)
    asv_client = DataForSEOASVClient(login=login, password=password, base_url=base_url)
    sv_results = await sv_client.get_volume(all_keywords, location_code=cfg["location_code"], language_code="en")
    asv_results = await asv_client.get_volume(all_keywords, location_code=cfg["location_code"], language_code="en")
    sv_map = {r.keyword: (r.search_volume if r.search_volume is not None else 1) for r in sv_results}
    asv_map = {r.keyword: (r.search_volume if r.search_volume is not None else 1) for r in asv_results}
    cpc_map = {r.keyword: r.cpc for r in sv_results}
    comp_map = {r.keyword: r.competition for r in sv_results}

    detail_df = pd.DataFrame(estimate_rows(
        prompts, filtered_results, hp=hp, rho_by_keyword=rho_by_keyword,
        sv_map=sv_map, asv_map=asv_map, cpc_map=cpc_map, comp_map=comp_map,
        source_meta=source_meta, importance_scorer=scorer_label,
    ))
    summary_df = build_summary(prompts, detail_df, source_meta, sheet_prefix)

    output_dir.mkdir(parents=True, exist_ok=True)
    for out_path in output_paths:
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            summary_df.to_excel(writer, sheet_name=f"{sheet_prefix}_summary", index=False)
            detail_df.to_excel(writer, sheet_name=sheet_prefix, index=False)
            pd.DataFrame(extraction_log).to_excel(writer, sheet_name="extraction_log", index=False)
            source_df.to_excel(writer, sheet_name=INPUT_SHEET, index=False)
        print(f"Saved -> {out_path}")

    y_col = f"{sheet_prefix}_y_median"
    print(f"Mean Y_median: {summary_df[y_col].mean():.2f} | Median: {summary_df[y_col].median():.2f}")
    print(f"At floor (~1.1): {(summary_df[y_col].round(2) <= 1.2).sum()}/{len(summary_df)}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", choices=["decklar", "indriya", "both"], required=True)
    parser.add_argument("--importance-scorer", choices=["cross_encoder", "bge_m3"], default="bge_m3")
    args = parser.parse_args()

    clients = ["decklar", "indriya"] if args.client == "both" else [args.client]
    for client in clients:
        await run_client(client, args.importance_scorer)


if __name__ == "__main__":
    asyncio.run(main())
