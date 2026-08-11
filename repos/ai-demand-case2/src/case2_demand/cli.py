"""CLI for Case 2: SV + ASV Bayesian fusion."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from pathlib import Path

from rich.console import Console

from case2_demand.calibration import (
    ETA_CALIBRATION_FLOOR,
    RHO_CALIBRATION_FLOOR,
    SIGMA_A_CALIBRATION_FLOOR,
    apply_rho_eta_floors_to_calibration_dict,
    floor_sigma_a_c,
    load_calibration,
    run_calibration,
    save_calibration,
)
from case2_demand.config import Settings, resolve_run_context
from case2_demand.pipeline import (
    generate_intent_clusters_step,
    generate_prompts_step,
    load_company_profile,
)
from case2_demand.estimation.bayesian_sv_asv import Case2Estimator, Case2Hyperparameters
from case2_demand.keyword_extraction.keyword_validation import is_generic_phrase
from case2_demand.keyword_filter import apply_keyword_filter
from case2_demand.overlap_discount import estimate_intent_cluster_overlap_discount
from case2_demand.topic_volume_representative import estimate_intent_cluster_representative_incremental
from case2_demand.intent_keyword_union import (
    dedupe_keywords_semantic,
    fallback_keyword_from_extractions,
    max_importance_scores_for_intent,
)
from case2_demand.keyword_extraction.extractor import (
    extract_keywords_with_importance,
    extract_keywords_with_importance_llm,
    extract_keywords_with_importance_llm_batch,
)
from case2_demand.keyword_extraction.ngram_llm_filter import (
    extract_ngram_llm_filtered_keywords,
    extract_ngram_llm_filtered_keywords_batch,
)
from case2_demand.keyword_volume.base import KeywordVolumeResult
from case2_demand.keyword_volume.dataforseo import (
    DataForSEOASVClient,
    DataForSEOSVClient,
)
from case2_demand.schemas import (
    IntentClusterDemandEstimate,
    IntentClusterPlan,
    PromptDemandEstimate,
    RunMetrics,
)
from case2_demand.util.io import (
    export_keyword_volumes_to_csv,
    export_prompt_estimates_to_csv,
    export_prompt_keyword_volumes_for_run,
    iter_jsonl,
    write_json,
    write_jsonl,
)
from case2_demand.util.locations import (
    aggregate_intent_estimates,
    aggregate_prompt_estimates,
    location_subdir,
    parse_location_codes,
    write_locations_manifest,
)

console = Console()

KEYWORD_EXTRACTION_METHODS = ("ngram", "llm", "ngram_llm_filter")


def _prompts_dir() -> Path:
    return Path(__file__).resolve().parent / "prompts"


def _keyword_objects_to_dicts(kw_list: list) -> list[dict]:
    """Convert KeywordWithImportance or dict entries to {keyword, importance_score}."""
    out: list[dict] = []
    for k in kw_list:
        if isinstance(k, dict):
            keyword = str(k.get("keyword", "")).strip()
            score = k.get("importance_score", 0.7)
        elif hasattr(k, "keyword"):
            keyword = str(k.keyword).strip()
            score = k.importance_score
        else:
            continue
        if keyword:
            out.append({"keyword": keyword, "importance_score": score})
    return out


def _llm_min_keywords(settings) -> int:
    return max(1, int(getattr(settings, "CASE2_LLM_MIN_KEYWORDS", 1)))


def _allow_ngram_fallback(settings) -> bool:
    return bool(getattr(settings, "CASE2_ALLOW_NGRAM_FALLBACK", False))


def _require_openrouter_for_llm(settings) -> str:
    api_key = settings.OPENROUTER_API_KEY or ""
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is required for LLM keyword extraction (Gemini). "
            "Set it in .env or pass --keyword-extraction ngram explicitly."
        )
    model = (settings.CASE2_LLM_MODEL or "").lower()
    if "gemini" not in model:
        console.print(
            f"[yellow]CASE2_LLM_MODEL={settings.CASE2_LLM_MODEL!r} is not Gemini; "
            "set CASE2_LLM_MODEL=google/gemini-2.5-flash-lite for extraction[/yellow]"
        )
    return api_key


def _max_keywords_for_method(settings, method: str) -> int:
    if method == "llm":
        return int(getattr(settings, "CASE2_LLM_MAX_KEYWORDS", 3) or 3)
    if method == "ngram_llm_filter":
        return int(getattr(settings, "CASE2_NGRAM_LLM_FILTER_MAX_KEYWORDS", 6) or 6)
    return int(settings.CASE2_MAX_KEYWORDS)


def _ngram_llm_filter_prompt_path() -> Path:
    return _prompts_dir() / "keyword_filter_ngram_system.txt"


def _extract_keywords_for_prompt(
    prompt: str,
    *,
    method: str,
    settings,
    max_keywords: int,
) -> list:
    """Extract keywords using ngram, llm, or ngram_llm_filter. Returns list of {keyword, importance_score} dicts."""
    if method == "ngram_llm_filter":
        api_key = _require_openrouter_for_llm(settings)
        try:
            kw_list, _meta = extract_ngram_llm_filtered_keywords(
                prompt,
                api_key=api_key,
                base_url=settings.OPENROUTER_BASE_URL,
                model=settings.CASE2_LLM_MODEL,
                system_prompt_path=_ngram_llm_filter_prompt_path(),
                max_keywords=max_keywords,
                cross_encoder_model=settings.CASE2_CROSS_ENCODER_MODEL,
                timeout_sec=settings.CASE2_LLM_REQUEST_TIMEOUT_SEC,
            )
            return _keyword_objects_to_dicts(kw_list)
        except Exception as e:
            if not _allow_ngram_fallback(settings):
                raise RuntimeError(f"ngram+LLM filter keyword extraction failed: {e}") from e
            console.print(f"[yellow]ngram+LLM filter failed ({e}); falling back to ngram[/yellow]")
            method = "ngram"

    if method == "llm":
        api_key = _require_openrouter_for_llm(settings)
        try:
            kw_list = extract_keywords_with_importance_llm(
                prompt,
                api_key=api_key,
                base_url=settings.OPENROUTER_BASE_URL,
                model=settings.CASE2_LLM_MODEL,
                system_prompt_path=_prompts_dir() / "keyword_extraction_system.txt",
                max_keywords=max_keywords,
                timeout_sec=settings.CASE2_LLM_REQUEST_TIMEOUT_SEC,
                cross_encoder_model=settings.CASE2_CROSS_ENCODER_MODEL,
            )
            return [
                {"keyword": k.keyword, "importance_score": k.importance_score}
                for k in kw_list
            ]
        except Exception as e:
            if not _allow_ngram_fallback(settings):
                raise RuntimeError(f"LLM keyword extraction failed: {e}") from e
            console.print(f"[yellow]LLM keyword extraction failed ({e}); falling back to ngram[/yellow]")
            method = "ngram"

    kw_list = extract_keywords_with_importance(
        prompt,
        max_keywords=max_keywords,
        model_name=settings.CASE2_CROSS_ENCODER_MODEL,
    )
    return [{"keyword": k.keyword, "importance_score": k.importance_score} for k in kw_list]


def _extract_keywords_batch_by_intent(
    prompt_items: list[dict],
    *,
    method: str,
    settings,
    max_keywords: int,
    checkpoint_path: Path | None = None,
) -> list[dict]:
    """Extract keywords using LLM once per intent cluster (batch). Returns list of extraction dicts."""
    if method != "llm":
        return None  # Caller should use per-prompt extraction
    api_key = _require_openrouter_for_llm(settings)
    min_kw = _llm_min_keywords(settings)

    # Group by intent_cluster_id (use "_unknown" for None)
    from collections import defaultdict
    groups: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for i, item in enumerate(prompt_items):
        intent_id = item.get("intent_cluster_id") or "_unknown"
        groups[intent_id].append((i, item))

    # Build extractions in original order
    extractions: list[dict] = [None] * len(prompt_items)  # type: ignore
    batch_path = _prompts_dir() / "keyword_extraction_batch_system.txt"
    delay = getattr(settings, "CASE2_LLM_REQUEST_DELAY_SEC", 8.0)

    n_chunks_total = sum(
        (len(items) + settings.CASE2_LLM_MAX_PROMPTS_PER_CALL - 1)
        // settings.CASE2_LLM_MAX_PROMPTS_PER_CALL
        for items in groups.values()
    )
    chunk_idx = 0
    for intent_id, items in groups.items():
        try:
            prompts = [item["prompt"] for _, item in items]
            n_chunks = (
                (len(prompts) + settings.CASE2_LLM_MAX_PROMPTS_PER_CALL - 1)
                // settings.CASE2_LLM_MAX_PROMPTS_PER_CALL
            )
            console.print(
                f"[cyan]LLM keyword batch[/cyan] intent={intent_id} "
                f"prompts={len(prompts)} chunks={n_chunks} model={settings.CASE2_LLM_MODEL}"
            )
            kw_lists = extract_keywords_with_importance_llm_batch(
                prompts,
                api_key=api_key,
                base_url=settings.OPENROUTER_BASE_URL,
                model=settings.CASE2_LLM_MODEL,
                system_prompt_path=batch_path,
                max_keywords=max_keywords,
                max_prompts_per_call=settings.CASE2_LLM_MAX_PROMPTS_PER_CALL,
                request_delay_sec=settings.CASE2_LLM_REQUEST_DELAY_SEC,
                timeout_sec=settings.CASE2_LLM_REQUEST_TIMEOUT_SEC,
                cross_encoder_model=settings.CASE2_CROSS_ENCODER_MODEL,
            )
            chunk_idx += n_chunks
            console.print(
                f"[green]LLM keyword batch done[/green] intent={intent_id} "
                f"({chunk_idx}/{n_chunks_total} chunks total)"
            )
            for (orig_idx, item), kw_list in zip(items, kw_lists):
                prompt_text = item["prompt"]
                kw_dicts = _keyword_objects_to_dicts(kw_list if isinstance(kw_list, list) else [])
                if len(kw_dicts) < min_kw:
                    retry = _extract_keywords_for_prompt(
                        prompt_text,
                        method="llm",
                        settings=settings,
                        max_keywords=max_keywords,
                    )
                    if len(retry) > len(kw_dicts):
                        kw_dicts = retry
                    elif len(kw_dicts) < min_kw:
                        console.print(
                            f"[dim]LLM returned {len(kw_dicts)} keyword(s) for "
                            f"{item.get('prompt_id')} (min {min_kw} preferred)[/dim]"
                        )
                extractions[orig_idx] = {
                    "prompt_id": item.get("prompt_id") or f"prm_{orig_idx}",
                    "prompt": prompt_text,
                    "intent_cluster_id": item.get("intent_cluster_id"),
                    "intent_cluster_name": item.get("intent_cluster_name"),
                    "keywords": kw_dicts,
                }
            if checkpoint_path is not None:
                done = [e for e in extractions if e is not None]
                write_jsonl(checkpoint_path, done)
                console.print(f"[dim]Checkpoint[/dim] {len(done)} extractions -> {checkpoint_path}")
        except Exception as e:
            if not _allow_ngram_fallback(settings):
                console.print(
                    f"[yellow]LLM batch failed for intent {intent_id} ({e}); "
                    "retrying per-prompt LLM[/yellow]"
                )
                for orig_idx, item in items:
                    kw_dicts = _extract_keywords_for_prompt(
                        item["prompt"],
                        method="llm",
                        settings=settings,
                        max_keywords=max_keywords,
                    )
                    extractions[orig_idx] = {
                        "prompt_id": item.get("prompt_id") or f"prm_{orig_idx}",
                        "prompt": item["prompt"],
                        "intent_cluster_id": item.get("intent_cluster_id"),
                        "intent_cluster_name": item.get("intent_cluster_name"),
                        "keywords": kw_dicts,
                    }
            else:
                console.print(
                    f"[yellow]LLM batch extraction failed for intent {intent_id} ({e}); "
                    "falling back to ngram[/yellow]"
                )
                for orig_idx, item in items:
                    kw_list = extract_keywords_with_importance(
                        item["prompt"],
                        max_keywords=max_keywords,
                        model_name=settings.CASE2_CROSS_ENCODER_MODEL,
                    )
                    extractions[orig_idx] = {
                        "prompt_id": item.get("prompt_id") or f"prm_{orig_idx}",
                        "prompt": item["prompt"],
                        "intent_cluster_id": item.get("intent_cluster_id"),
                        "intent_cluster_name": item.get("intent_cluster_name"),
                        "keywords": [
                            {"keyword": k.keyword, "importance_score": k.importance_score}
                            for k in kw_list
                        ],
                    }
        if len(groups) > 1:
            time.sleep(delay)

    return extractions


def _extract_keywords_ngram_llm_filter_batch(
    prompt_items: list[dict],
    *,
    settings,
    max_keywords: int,
    checkpoint_path: Path | None = None,
) -> list[dict]:
    """Batch n-gram candidates → LLM filter → cross-encoder importance."""
    api_key = _require_openrouter_for_llm(settings)
    filter_path = _ngram_llm_filter_prompt_path()
    all_prompts = [item["prompt"] for item in prompt_items]
    console.print(
        f"[cyan]ngram+LLM filter batch[/cyan] prompts={len(all_prompts)} "
        f"model={settings.CASE2_LLM_MODEL}"
    )
    kw_lists, _logs = extract_ngram_llm_filtered_keywords_batch(
        all_prompts,
        api_key=api_key,
        base_url=settings.OPENROUTER_BASE_URL,
        model=settings.CASE2_LLM_MODEL,
        system_prompt_path=filter_path,
        max_keywords=max_keywords,
        max_items_per_call=settings.CASE2_LLM_MAX_PROMPTS_PER_CALL,
        request_delay_sec=settings.CASE2_LLM_REQUEST_DELAY_SEC,
        cross_encoder_model=settings.CASE2_CROSS_ENCODER_MODEL,
        timeout_sec=settings.CASE2_LLM_REQUEST_TIMEOUT_SEC,
    )
    extractions = []
    for i, (item, kw_list) in enumerate(zip(prompt_items, kw_lists)):
        extractions.append({
            "prompt_id": item.get("prompt_id") or f"prm_{i}",
            "prompt": item["prompt"],
            "intent_cluster_id": item.get("intent_cluster_id"),
            "intent_cluster_name": item.get("intent_cluster_name"),
            "keywords": _keyword_objects_to_dicts(kw_list),
        })
    if checkpoint_path is not None:
        write_jsonl(checkpoint_path, extractions)
        console.print(f"[dim]Checkpoint[/dim] {len(extractions)} extractions -> {checkpoint_path}")
    console.print(f"[green]ngram+LLM filter batch done[/green] ({len(extractions)} prompts)")
    return extractions


async def _run_all(args) -> None:
    """Full pipeline: company -> intents -> prompts -> SV+ASV -> estimate."""
    from dotenv import load_dotenv
    if getattr(args, "env_file", None) and args.env_file.exists():
        load_dotenv(args.env_file, override=True)
    else:
        load_dotenv()

    prompt_items: list[dict]
    company_name: str | None = None
    if getattr(args, "from_run", None):
        import os
        os.environ["CASE2_RUN_ID"] = args.from_run
        settings = Settings()
        ctx = resolve_run_context(settings)
        prompts_path = ctx.synthetic_prompts_path
        if not prompts_path.exists():
            console.print(f"[red]No synthetic_prompts.jsonl in {ctx.run_dir}[/red]")
            return
        prompt_items = []
        for line in prompts_path.read_text().strip().split("\n"):
            if not line.strip():
                continue
            row = json.loads(line)
            prompt_items.append({
                "prompt": row["prompt"],
                "prompt_id": row.get("prompt_id", f"prm_{len(prompt_items)}"),
                "intent_cluster_id": row.get("intent_cluster_id"),
                "intent_cluster_name": row.get("intent_cluster_name"),
            })
        if ctx.company_profile_path.exists():
            company = load_company_profile(ctx.company_profile_path)
            company_name = company.company_name
        console.print(f"[cyan]Resumed from {args.from_run}[/cyan]: {len(prompt_items)} prompts")
    elif getattr(args, "from_run_intents", None):
        import os
        from_run_intents = args.from_run_intents
        settings = Settings()
        ctx = resolve_run_context(settings)
        src_dir = ctx.runs_dir / from_run_intents
        if not src_dir.exists():
            console.print(f"[red]Run dir not found: {src_dir}[/red]")
            return
        plan_path = src_dir / "intent_cluster_plan.json"
        profile_path = src_dir / "company_profile.json"
        if not plan_path.exists():
            console.print(f"[red]No intent_cluster_plan.json in {src_dir}[/red]")
            return
        if not profile_path.exists():
            console.print(f"[red]No company_profile.json in {src_dir}[/red]")
            return
        ctx.run_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy(plan_path, ctx.intent_cluster_plan_path)
        shutil.copy(profile_path, ctx.company_profile_path)
        company = load_company_profile(ctx.company_profile_path)
        company_name = company.company_name
        plan = IntentClusterPlan.model_validate(json.loads(ctx.intent_cluster_plan_path.read_text()))
        prompts_list = generate_prompts_step(
            ctx=ctx,
            company=company,
            intent_plan=plan,
            settings=settings,
            n_prompts_per_intent=args.n_prompts_per_intent,
            prompt_path=_prompts_dir() / "prompt_batch_for_intent_system.txt",
        )
        prompt_items = [
            {
                "prompt": p.prompt,
                "prompt_id": p.prompt_id,
                "intent_cluster_id": p.intent_cluster_id,
                "intent_cluster_name": p.intent_cluster_name,
            }
            for p in prompts_list
        ]
        os.environ["CASE2_RUN_ID"] = ctx.run_id
        console.print(f"[cyan]Using intents from {from_run_intents}[/cyan]: {len(plan.clusters)} clusters, {len(prompt_items)} prompts")
    else:
        settings = Settings()
        ctx = resolve_run_context(settings)
        if not getattr(args, "company_profile", None):
            console.print("[red]--company-profile required (or use --from-run)[/red]")
            return
        company = load_company_profile(args.company_profile)
        company_name = company.company_name
        ctx.company_profile_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(ctx.company_profile_path, company.model_dump())

        intent_prompt_path = _prompts_dir() / "intent_cluster_generation_system.txt"
        batch_prompt_path = _prompts_dir() / "prompt_batch_for_intent_system.txt"

        plan = generate_intent_clusters_step(
            ctx=ctx,
            company=company,
            settings=settings,
            prompt_path=intent_prompt_path,
            n_intents=getattr(args, "n_intents", None),
        )
        prompts_list = generate_prompts_step(
            ctx=ctx,
            company=company,
            intent_plan=plan,
            settings=settings,
            n_prompts_per_intent=args.n_prompts_per_intent,
            prompt_path=batch_prompt_path,
        )
        prompt_items = [
            {
                "prompt": p.prompt,
                "prompt_id": p.prompt_id,
                "intent_cluster_id": p.intent_cluster_id,
                "intent_cluster_name": p.intent_cluster_name,
            }
            for p in prompts_list
        ]

    # Use run-all-with-calibration when requested (fetch SV/ASV, calibrate, estimate)
    if getattr(args, "with_calibration", False):
        extractions_path = ctx.keyword_extractions_path if ctx.keyword_extractions_path.exists() else None
        await _run_all_with_calibration(
            prompt_items=prompt_items,
            company_name=company_name,
            ctx=ctx,
            settings=settings,
            args=args,
            extractions_from_path=extractions_path,
        )
    else:
        import os
        os.environ["CASE2_RUN_ID"] = ctx.run_id
        resolved_locations = _resolve_location_codes(
            args.location,
            getattr(args, "locations", None),
        )
        await run_pipeline(
            prompt_items=prompt_items,
            company_name=company_name,
            location_code=resolved_locations[0],
            location_codes=resolved_locations if len(resolved_locations) > 1 else None,
            language_code=args.language,
            dry_run=args.dry_run,
            calibrated_from=getattr(args, "calibrated_from", None),
        )


def _build_asv_lookup(
    asv_items: list[dict],
    keywords_list: list[str],
    default_vol: float,
) -> dict[str, float]:
    """Map keyword -> ASV from DataForSEO history rows."""
    asv_lookup: dict[str, float] = {}
    for item in asv_items:
        kw = item.get("keyword", "")
        if not kw:
            continue
        vol = item.get("ai_search_volume")
        if vol is not None:
            asv_lookup[kw] = float(max(vol, default_vol))
        else:
            monthly = item.get("ai_monthly_searches") or item.get("monthly_searches") or []
            if monthly:
                sorted_m = sorted(monthly, key=lambda m: (m.get("year", 0), m.get("month", 0)))
                last = sorted_m[-1] if sorted_m else {}
                v = last.get("ai_search_volume") or last.get("search_volume")
                asv_lookup[kw] = float(max(v, default_vol)) if v is not None else default_vol
            else:
                asv_lookup[kw] = default_vol
    for kw in keywords_list:
        if kw not in asv_lookup:
            asv_lookup[kw] = default_vol
    return asv_lookup


def _count_nonempty_asv_items(asv_items: list[dict]) -> int:
    """Keywords with ai_search_volume > 0 or positive latest monthly ASV."""
    n = 0
    for item in asv_items:
        v = item.get("ai_search_volume")
        if v is not None and float(v) > 0:
            n += 1
            continue
        monthly = item.get("ai_monthly_searches") or item.get("monthly_searches") or []
        if monthly:
            sorted_m = sorted(monthly, key=lambda m: (m.get("year", 0), m.get("month", 0)))
            last = sorted_m[-1] if sorted_m else {}
            lv = last.get("ai_search_volume") or last.get("search_volume")
            if lv is not None and float(lv) > 0:
                n += 1
    return n


def _build_historical_sv_asv(sv_results, asv_items) -> tuple[list[list[float]], list[list[float]], list[str], dict[str, dict], list[tuple[int, int]], list[tuple[int, int]]]:
    """Build historical_sv and historical_asv arrays (keywords × time periods) for calibration file.
    Also returns keyword_metadata with cpc and competition per keyword from SV results.
    Fallback: when API returns only current volume (no monthly history), synthesize 2-period history
    so calibration can run (requires min_periods=2)."""
    import datetime
    now = datetime.datetime.utcnow()
    y1, m1 = now.year, now.month
    m2 = m1 - 1 if m1 > 1 else 12
    y2 = y1 if m1 > 1 else y1 - 1

    kw_to_sv: dict[str, list[tuple[int, int, float]]] = {}
    kw_to_asv: dict[str, list[tuple[int, int, float]]] = {}
    keyword_metadata: dict[str, dict] = {}
    for r in sv_results:
        if not r.keyword:
            continue
        keyword_metadata[r.keyword] = {"cpc": r.cpc, "competition": r.competition}
        for m in (r.monthly_searches or []):
            y, mo = m.get("year"), m.get("month")
            v = m.get("search_volume")
            if y is not None and mo is not None and v is not None:
                kw_to_sv.setdefault(r.keyword, []).append((y, mo, float(max(v, 0))))
        if r.keyword not in kw_to_sv and (r.search_volume or 0) > 0:
            v = float(max(r.search_volume, 1))
            kw_to_sv[r.keyword] = [(y2, m2, v), (y1, m1, v)]
    for item in asv_items:
        kw = item.get("keyword", "")
        if not kw:
            continue
        for m in (item.get("ai_monthly_searches") or item.get("monthly_searches") or []):
            y, mo = m.get("year"), m.get("month")
            v = m.get("ai_search_volume") or m.get("search_volume")
            if y is not None and mo is not None and v is not None:
                kw_to_asv.setdefault(kw, []).append((y, mo, float(max(v, 0))))
        if kw not in kw_to_asv:
            v = item.get("ai_search_volume") or item.get("search_volume")
            if v is not None and float(v) > 0:
                vol = float(max(v, 1))
                kw_to_asv[kw] = [(y2, m2, vol), (y1, m1, vol)]
    keywords_out: list[str] = []
    historical_sv: list[list[float]] = []
    historical_asv: list[list[float]] = []
    periods_sv: list[tuple[int, int]] = []
    periods_asv: list[tuple[int, int]] = []
    all_kw = sorted(set(kw_to_sv) | set(kw_to_asv))
    for kw in all_kw:
        sv_vals = kw_to_sv.get(kw, [])
        asv_vals = kw_to_asv.get(kw, [])
        if not sv_vals and not asv_vals:
            continue
        sv_sorted = sorted(sv_vals, key=lambda x: (x[0], x[1]))
        asv_sorted = sorted(asv_vals, key=lambda x: (x[0], x[1]))
        if sv_sorted or asv_sorted:
            keywords_out.append(kw)
            historical_sv.append([v for _, _, v in sv_sorted])
            historical_asv.append([v for _, _, v in asv_sorted])
            if sv_sorted and not periods_sv:
                periods_sv = [(y, m) for y, m, _ in sv_sorted]
            if asv_sorted and not periods_asv:
                periods_asv = [(y, m) for y, m, _ in asv_sorted]
    return historical_sv, historical_asv, keywords_out, keyword_metadata, periods_sv, periods_asv


def _make_sv_client(settings: Settings, login: str, password: str, sv_source: str | None = None) -> DataForSEOSVClient:
    source = (sv_source or settings.CASE2_SV_SOURCE or "clickstream").strip().lower()
    return DataForSEOSVClient(login=login, password=password, sv_source=source)


def _add_location_cli_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--locations",
        default=None,
        metavar="CODES",
        help="Comma-separated DataForSEO location codes (1–5 markets, volumes summed)",
    )
    parser.add_argument("--location", type=int, default=2840, help="Single location code (default: 2840 US)")


def _resolve_location_codes(
    location: int | None = None,
    locations: str | None = None,
) -> list[int]:
    try:
        return parse_location_codes(location=location, locations=locations)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1) from exc


def _hp_for_intent(
    intent_id: str | None,
    *,
    hp: Case2Hyperparameters,
    sv_params_by_intent: dict | None,
    asv_params_by_intent: dict | None,
) -> Case2Hyperparameters:
    svp = (sv_params_by_intent or {}).get(intent_id or "_unknown") or (sv_params_by_intent or {}).get("_global")
    avp = (asv_params_by_intent or {}).get(intent_id or "_unknown") or (asv_params_by_intent or {}).get("_global")
    return Case2Hyperparameters(
        nu_c=svp["nu_c"] if svp else hp.nu_c,
        omega_c=svp["omega_c"] if svp else hp.omega_c,
        b_S=svp["b_S"] if svp else hp.b_S,
        sigma_S_c=svp["sigma_S_c"] if svp else hp.sigma_S_c,
        b_A=avp["b_A"] if avp else hp.b_A,
        sigma_A_c=floor_sigma_a_c(avp["sigma_A_c"] if avp else hp.sigma_A_c),
        delta_c=hp.delta_c,
        sigma_delta=hp.sigma_delta,
        beta=hp.beta,
        rho=hp.rho,
        mu_eta=hp.mu_eta,
        sigma_eta=hp.sigma_eta,
    )


def _load_calibration_state(
    calibrated_from: Path | None,
    hp: Case2Hyperparameters,
) -> tuple[
    dict[str, float] | None,
    dict | None,
    dict | None,
    Case2Hyperparameters,
]:
    rho_by_keyword: dict[str, float] | None = None
    sv_params_by_intent: dict | None = None
    asv_params_by_intent: dict | None = None
    if not calibrated_from or not calibrated_from.exists():
        return rho_by_keyword, sv_params_by_intent, asv_params_by_intent, hp

    cal = load_calibration(calibrated_from)
    floor_stats = apply_rho_eta_floors_to_calibration_dict(cal)
    if (
        floor_stats["rho_keywords_raised"]
        or floor_stats["eta_floor_applied"]
        or floor_stats.get("sigma_a_intents_raised")
    ):
        console.print(
            f"[dim]Applied calibration floors[/dim] "
            f"(ρ≥{RHO_CALIBRATION_FLOOR}, η≥{ETA_CALIBRATION_FLOOR}, "
            f"σ_A,c≥{SIGMA_A_CALIBRATION_FLOOR}): "
            f"{floor_stats['rho_keywords_raised']} keywords ρ raised, "
            f"η floor={'yes' if floor_stats['eta_floor_applied'] else 'no'}, "
            f"{floor_stats.get('sigma_a_intents_raised', 0)} intents σ_A,c raised"
        )
    sv_params_by_intent = cal.get("sv_params_by_intent")
    asv_params_by_intent = cal.get("asv_params_by_intent")
    if not sv_params_by_intent and cal.get("sv_params"):
        sv_params_by_intent = {"_global": cal["sv_params"]}
    if not asv_params_by_intent and cal.get("asv_params"):
        asv_params_by_intent = {"_global": cal["asv_params"]}
    rho_by_keyword = cal.get("rho_by_keyword")
    hp = Case2Hyperparameters(
        nu_c=hp.nu_c,
        omega_c=hp.omega_c,
        b_S=hp.b_S,
        sigma_S_c=hp.sigma_S_c,
        b_A=hp.b_A,
        sigma_A_c=hp.sigma_A_c,
        delta_c=hp.delta_c,
        sigma_delta=hp.sigma_delta,
        beta=hp.beta,
        rho=hp.rho,
        mu_eta=cal.get("mu_eta", hp.mu_eta),
        sigma_eta=cal.get("sigma_eta", hp.sigma_eta),
    )
    console.print(f"[green]Using calibration from {calibrated_from}[/green]")
    return rho_by_keyword, sv_params_by_intent, asv_params_by_intent, hp


def _estimate_volumes(
    *,
    extractions: list[dict],
    sv_lookup: dict[str, float],
    asv_lookup: dict[str, float],
    sv_metadata: dict[str, dict],
    rho_by_keyword: dict[str, float] | None,
    hp: Case2Hyperparameters,
    sv_params_by_intent: dict | None,
    asv_params_by_intent: dict | None,
    settings: Settings,
) -> tuple[list[PromptDemandEstimate], list[IntentClusterDemandEstimate]]:
    prompt_estimates: list[PromptDemandEstimate] = []
    filter_method = (getattr(settings, "CASE2_KEYWORD_FILTER", None) or "none").strip().lower()
    filter_levels = int(getattr(settings, "CASE2_KEYWORD_FILTER_LEVELS", 1) or 1)
    filter_top_n = int(getattr(settings, "CASE2_KEYWORD_FILTER_TOP_N", 2) or 2)

    for ext in extractions:
        kw_list = [
            (k["keyword"], float(k["importance_score"]))
            for k in ext.get("keywords") or []
            if not is_generic_phrase(k.get("keyword", ""))
        ]
        if not kw_list:
            kw_list = [(ext["prompt"][:50] or "general", 0.7)]
        n_before = len(kw_list)
        cutoff: float | None = None
        if filter_method not in ("none", ""):
            kw_list, cutoff = apply_keyword_filter(
                kw_list,
                method=filter_method,
                levels=filter_levels,
                top_n=filter_top_n,
            )
            if not kw_list:
                kw_list = [(ext["prompt"][:50] or "general", 0.7)]
                cutoff = kw_list[0][1]
        keywords = [k[0] for k in kw_list]
        similarities = [k[1] for k in kw_list]
        sv_values = [sv_lookup.get(kw, 1) for kw in keywords]
        asv_values = [asv_lookup.get(kw, 1) for kw in keywords]

        prompt_hp = _hp_for_intent(
            ext.get("intent_cluster_id"),
            hp=hp,
            sv_params_by_intent=sv_params_by_intent,
            asv_params_by_intent=asv_params_by_intent,
        )
        estimator = Case2Estimator(prompt_hp)
        Y_median, Y_mean, Y_std, interval, kw_estimates, weights = estimator.estimate_demand(
            prompt=ext["prompt"],
            keywords=keywords,
            similarities=similarities,
            sv_values=sv_values,
            asv_values=asv_values,
            rho_by_keyword=rho_by_keyword,
        )
        enriched_estimates = []
        for e in kw_estimates:
            meta = sv_metadata.get(e.keyword, {})
            enriched_estimates.append(
                e.model_copy(update={"cpc": meta.get("cpc"), "competition": meta.get("competition")})
            )
        prompt_estimates.append(
            PromptDemandEstimate(
                prompt_id=ext["prompt_id"],
                prompt=ext["prompt"],
                Y_median=Y_median,
                Y_mean=Y_mean,
                Y_std=Y_std,
                interval_90=interval,
                keyword_estimates=[e.model_dump() for e in enriched_estimates],
                weights=weights,
                intent_cluster_id=ext.get("intent_cluster_id"),
                intent_cluster_name=ext.get("intent_cluster_name"),
                keyword_filter=filter_method if filter_method not in ("none", "") else None,
                keyword_filter_levels=filter_levels if filter_method == "binary_search" else None,
                importance_cutoff=cutoff,
                keywords_before_filter=n_before if filter_method not in ("none", "") else None,
                keywords_kept=len(keywords) if filter_method not in ("none", "") else None,
            )
        )

    intent_estimates: list[IntentClusterDemandEstimate] = []
    by_intent_ext: dict[str, list[dict]] = {}
    for ext in extractions:
        key = ext.get("intent_cluster_id") or "_unknown"
        by_intent_ext.setdefault(key, []).append(ext)

    prompt_estimates_by_id = {p.prompt_id: p for p in prompt_estimates}
    intent_volume_method = (
        (getattr(settings, "CASE2_INTENT_VOLUME_METHOD", None) or "representative_incremental")
        .strip()
        .lower()
    )
    overlap_alpha = float(getattr(settings, "CASE2_OVERLAP_DISCOUNT_ALPHA", 0.7) or 0.7)
    dedup_model = settings.CASE2_INTENT_DEDUP_MODEL or "all-MiniLM-L6-v2"
    dedup_thresh = float(settings.CASE2_INTENT_DEDUP_SIM_THRESHOLD)

    if intent_volume_method == "representative_incremental":
        by_intent_prompts: dict[str, list[PromptDemandEstimate]] = {}
        for pe in prompt_estimates:
            key = pe.intent_cluster_id or "_unknown"
            by_intent_prompts.setdefault(key, []).append(pe)
        for cluster_id, cluster_prompts in by_intent_prompts.items():
            intent_name = (
                cluster_prompts[0].intent_cluster_name or cluster_id
                if cluster_prompts
                else str(cluster_id)
            )
            intent_estimates.append(
                estimate_intent_cluster_representative_incremental(
                    cluster_id=cluster_id,
                    intent_name=str(intent_name),
                    prompt_estimates=cluster_prompts,
                    model_name=dedup_model,
                    sim_threshold=dedup_thresh,
                    alpha=overlap_alpha,
                )
            )
        console.print(
            f"[cyan]Intent volumes[/cyan]: representative_incremental "
            f"(max prompt + discounted non-overlapping keywords, "
            f"sim>{dedup_thresh} dropped, α={overlap_alpha}, model={dedup_model}), "
            f"{len(intent_estimates)} cluster(s)"
        )
    elif intent_volume_method == "overlap_discount":
        for cluster_id, exts in by_intent_ext.items():
            intent_name = (exts[0].get("intent_cluster_name") or cluster_id) if exts else str(cluster_id)
            intent_estimates.append(
                estimate_intent_cluster_overlap_discount(
                    cluster_id=cluster_id,
                    intent_name=str(intent_name),
                    extractions=exts,
                    prompt_estimates_by_id=prompt_estimates_by_id,
                    model_name=dedup_model,
                    alpha=overlap_alpha,
                )
            )
        console.print(
            f"[cyan]Intent volumes[/cyan]: overlap_discount "
            f"(sum prompt Y_mean × 1/(1+{overlap_alpha}×avg_keyword_sim), "
            f"model={dedup_model}), {len(intent_estimates)} cluster(s)"
        )
    else:
        default_vol = float(settings.CASE2_DEFAULT_MISSING_VOLUME)
        for cluster_id, exts in by_intent_ext.items():
            scores = max_importance_scores_for_intent(exts)
            if not scores:
                scores = fallback_keyword_from_extractions(exts)
            kws, sims = dedupe_keywords_semantic(
                scores,
                model_name=dedup_model,
                sim_threshold=dedup_thresh,
            )
            if not kws:
                scores = fallback_keyword_from_extractions(exts)
                kws, sims = list(scores.keys()), list(scores.values())

            intent_name = (exts[0].get("intent_cluster_name") or cluster_id) if exts else str(cluster_id)
            sv_vals = [float(sv_lookup.get(kw, default_vol)) for kw in kws]
            asv_vals = [float(asv_lookup.get(kw, default_vol)) for kw in kws]

            intent_hp = _hp_for_intent(
                cluster_id if cluster_id != "_unknown" else None,
                hp=hp,
                sv_params_by_intent=sv_params_by_intent,
                asv_params_by_intent=asv_params_by_intent,
            )
            estimator_intent = Case2Estimator(intent_hp)
            Y_median, Y_mean, Y_std, interval, _, _ = estimator_intent.estimate_demand(
                prompt=str(intent_name),
                keywords=kws,
                similarities=sims,
                sv_values=sv_vals,
                asv_values=asv_vals,
                rho_by_keyword=rho_by_keyword,
            )
            intent_estimates.append(
                IntentClusterDemandEstimate(
                    intent_cluster_id=cluster_id,
                    intent_cluster_name=str(intent_name),
                    num_prompts=len(exts),
                    Y_median=Y_median,
                    Y_mean=Y_mean,
                    Y_std=Y_std,
                    interval_90=interval,
                    volume_method="fusion",
                )
            )
        console.print(
            f"[cyan]Intent volumes[/cyan]: keyword union + semantic dedupe + fusion "
            f"(model={dedup_model}, drop if cos sim > {dedup_thresh}), "
            f"{len(intent_estimates)} cluster(s)"
        )
    return prompt_estimates, intent_estimates


def _write_market_volume_files(
    *,
    output_dir: Path,
    sv_lookup: dict[str, float],
    asv_lookup: dict[str, float],
    sv_metadata: dict[str, dict],
    location_code: int,
    language_code: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if sv_metadata:
        sv_rows = [
            {
                "keyword": k,
                "search_volume": v,
                "cpc": sv_metadata.get(k, {}).get("cpc"),
                "competition": sv_metadata.get(k, {}).get("competition"),
            }
            for k, v in sv_lookup.items()
        ]
    else:
        sv_rows = [{"keyword": k, "search_volume": v} for k, v in sv_lookup.items()]
    asv_rows = [{"keyword": k, "search_volume": v} for k, v in asv_lookup.items()]
    write_jsonl(output_dir / "sv_data.jsonl", sv_rows)
    write_jsonl(output_dir / "asv_data.jsonl", asv_rows)
    export_keyword_volumes_to_csv(
        keyword_to_sv=dict(sv_lookup),
        keyword_to_asv=dict(asv_lookup),
        out_path=output_dir / "keyword_volumes.csv",
        sv_metadata=sv_metadata if sv_metadata else None,
        location_code=location_code,
        language_code=language_code,
    )


def _write_market_estimate_files(
    *,
    output_dir: Path,
    extractions: list[dict],
    prompt_estimates: list[PromptDemandEstimate],
    intent_estimates: list[IntentClusterDemandEstimate],
    sv_lookup: dict[str, float],
    asv_lookup: dict[str, float],
) -> None:
    dump_rows = [p.model_dump() for p in prompt_estimates]
    write_jsonl(output_dir / "prompt_estimates.jsonl", dump_rows)
    export_prompt_estimates_to_csv(dump_rows, output_dir / "prompt_estimates.csv")
    n_pkv = export_prompt_keyword_volumes_for_run(
        prompt_rows=dump_rows,
        extractions=extractions,
        keyword_to_sv=dict(sv_lookup),
        keyword_to_asv=dict(asv_lookup),
        run_dir=output_dir,
    )
    write_json(output_dir / "intent_cluster_estimates.json", [e.model_dump() for e in intent_estimates])
    console.print(
        f"[green]Saved[/green] {n_pkv} prompt×keyword rows -> {output_dir / 'prompt_keyword_volumes.csv'}"
    )


def _write_run_summary(
    *,
    ctx,
    company_name: str | None,
    prompt_estimates: list[dict],
    intent_estimates: list[dict],
    location_codes: list[int],
    language_code: str,
    sv_source: str | None,
    settings: Settings,
) -> None:
    total_vol = (
        sum(float(e.get("Y_median", 0) or 0) for e in intent_estimates)
        if intent_estimates
        else sum(float(p.get("Y_median", 0) or 0) for p in prompt_estimates)
    )
    metrics = RunMetrics(
        run_id=ctx.run_id,
        total_prompts=len(prompt_estimates),
        total_keywords=sum(len(p.get("weights") or {}) for p in prompt_estimates),
        total_estimated_volume=total_vol,
        prompt_estimates=prompt_estimates,
        intent_cluster_estimates=intent_estimates,
        company_name=company_name,
    )
    write_json(ctx.metrics_path, metrics.model_dump())

    sv_source_label = (sv_source or settings.CASE2_SV_SOURCE or "clickstream").strip().lower()
    loc_label = (
        ", ".join(str(c) for c in location_codes)
        if len(location_codes) > 1
        else str(location_codes[0])
    )
    filter_method = (getattr(settings, "CASE2_KEYWORD_FILTER", None) or "none").strip().lower()
    filter_levels = int(getattr(settings, "CASE2_KEYWORD_FILTER_LEVELS", 1) or 1)
    insights_lines = [
        "Case 2: AI Demand Estimation (SV + ASV Bayesian Fusion)",
        "=" * 60,
        "",
        f"Company: {company_name or 'N/A'}",
        f"Run ID: {ctx.run_id}",
        f"SV source: {sv_source_label}",
        f"Language: {language_code}",
        f"Location code(s): {loc_label}",
    ]
    if filter_method not in ("none", ""):
        if filter_method == "binary_search":
            insights_lines.append(
                f"Keyword filter: binary_search median cutoff (levels={filter_levels})"
            )
        else:
            insights_lines.append(f"Keyword filter: {filter_method}")
    if len(location_codes) > 1:
        insights_lines.append(
            f"Aggregation: sum of per-market fused volumes ({len(location_codes)} markets)"
        )
        insights_lines.append(f"Per-market outputs: by_location/<code>/")
    insights_lines.extend([
        "",
        "## Summary",
        f"- Intent clusters: {len(intent_estimates)}",
        f"- Total prompts: {len(prompt_estimates)}",
        f"- Total estimated volume: {total_vol:,.0f} units/month",
        "",
        "## Intent Cluster Estimates",
        "",
    ])
    for e in intent_estimates:
        if e.get("intent_cluster_id") != "_unknown":
            interval = e.get("interval_90") or (0, 0)
            insights_lines.append(f"### {e.get('intent_cluster_name', '')}")
            insights_lines.append(f"- Prompts: {e.get('num_prompts', 0)}")
            method = e.get("volume_method") or "fusion"
            if method == "representative_incremental":
                insights_lines.append(
                    f"- Estimated volume (representative + incremental): "
                    f"{float(e.get('Y_median', 0)):,.0f} units/month"
                )
                if e.get("representative_prompt_id") is not None:
                    insights_lines.append(
                        f"- Representative prompt: {e.get('representative_prompt_id')} "
                        f"(volume {float(e.get('representative_volume', 0)):,.0f})"
                    )
                if e.get("incremental_volume") is not None:
                    insights_lines.append(
                        f"- Incremental from other prompts: {float(e['incremental_volume']):,.0f}"
                    )
            elif method == "overlap_discount":
                insights_lines.append(
                    f"- Estimated volume (overlap discount): {float(e.get('Y_median', 0)):,.0f} units/month"
                )
                if e.get("sum_prompt_y_mean") is not None and e.get("overlap_discount") is not None:
                    insights_lines.append(
                        f"- Sum prompt Y_mean × discount: "
                        f"{float(e['sum_prompt_y_mean']):,.0f} × {float(e['overlap_discount']):.3f}"
                    )
            else:
                insights_lines.append(
                    f"- Estimated volume: {float(e.get('Y_median', 0)):,.0f} units/month"
                )
            insights_lines.append(
                f"- 90% CI: [{float(interval[0]):,.0f}, {float(interval[1]):,.0f}]"
            )
            insights_lines.append("")
    ctx.insights_path.write_text("\n".join(insights_lines), encoding="utf-8")
    console.print(f"[green]Done.[/green] Outputs in {ctx.run_dir}")
    console.print(f"  Total AI demand: {total_vol:,.0f} units/month")


async def _fetch_sv_asv_for_market(
    *,
    keywords_list: list[str],
    location_code: int,
    language_code: str,
    sv_client: DataForSEOSVClient,
    asv_client: DataForSEOASVClient,
    settings: Settings,
    with_history: bool = False,
) -> tuple[list[KeywordVolumeResult], list, dict[str, float], dict[str, float], dict[str, dict]]:
    default_vol = float(settings.CASE2_DEFAULT_MISSING_VOLUME)
    sv_results = await sv_client.get_volume(keywords_list, location_code, language_code)
    if with_history:
        asv_items = await asv_client.get_volume_with_history(keywords_list, location_code, language_code)
        min_asv = max(10, int(0.05 * len(keywords_list)))
        asv_nonempty = _count_nonempty_asv_items(asv_items)
        if asv_nonempty < min_asv:
            console.print(
                f"[yellow]ASV sparse for location {location_code} "
                f"({asv_nonempty}/{len(keywords_list)}); retrying...[/yellow]"
            )
            await asyncio.sleep(1.0)
            retry_items = await asv_client.get_volume_with_history(
                keywords_list, location_code, language_code
            )
            retry_nonempty = _count_nonempty_asv_items(retry_items)
            if retry_nonempty > asv_nonempty:
                asv_items = retry_items
    else:
        asv_results = await asv_client.get_volume(keywords_list, location_code, language_code)
        asv_items = [
            {"keyword": r.keyword, "ai_search_volume": r.search_volume, "search_volume": r.search_volume}
            for r in asv_results
        ]

    sv_lookup: dict[str, float] = {}
    for r in sv_results:
        sv_lookup[r.keyword] = float(r.search_volume or default_vol)
    for kw in keywords_list:
        if kw not in sv_lookup:
            sv_lookup[kw] = default_vol
    asv_lookup = _build_asv_lookup(asv_items, keywords_list, default_vol)
    sv_metadata = {r.keyword: {"cpc": r.cpc, "competition": r.competition} for r in sv_results}
    return sv_results, asv_items, sv_lookup, asv_lookup, sv_metadata


async def _run_market_with_calibration(
    *,
    location_code: int,
    language_code: str,
    keywords_list: list[str],
    extractions: list[dict],
    output_dir: Path,
    settings: Settings,
    sv_client: DataForSEOSVClient,
    asv_client: DataForSEOASVClient,
    hp: Case2Hyperparameters,
) -> tuple[list[PromptDemandEstimate], list[IntentClusterDemandEstimate]]:
    sv_results, asv_items, sv_lookup, asv_lookup, sv_metadata = await _fetch_sv_asv_for_market(
        keywords_list=keywords_list,
        location_code=location_code,
        language_code=language_code,
        sv_client=sv_client,
        asv_client=asv_client,
        settings=settings,
        with_history=True,
    )

    rho_by_kw, calibrated_eta, rho_coeffs, sv_params_by_intent, asv_params_by_intent, residuals = await run_calibration(
        keywords=keywords_list,
        sv_client=sv_client,
        asv_client=asv_client,
        location_code=location_code,
        language_code=language_code,
        sv_results=sv_results,
        asv_items=asv_items,
        extractions=extractions,
    )
    calibrated_path = output_dir / "calibrated.json"
    save_calibration(
        calibrated_path,
        mu_eta=calibrated_eta.mu_eta,
        sigma_eta=calibrated_eta.sigma_eta,
        rho_coeffs=rho_coeffs,
        rho_by_keyword=rho_by_kw,
        num_samples=calibrated_eta.num_samples,
        var_u=calibrated_eta.var_u,
        residuals=residuals,
        keywords=keywords_list,
        location_code=location_code,
        language_code=language_code,
        sv_params_by_intent=sv_params_by_intent,
        asv_params_by_intent=asv_params_by_intent,
    )
    console.print(f"[green]Calibrated[/green] location {location_code} -> {calibrated_path}")

    historical_sv, historical_asv, keywords_with_history, keyword_metadata, periods_sv, periods_asv = _build_historical_sv_asv(
        sv_results, asv_items
    )
    if keywords_with_history:
        payload: dict = {
            "description": "Historical SV and ASV from DataForSEO (keywords × time periods)",
            "keywords": keywords_with_history,
            "historical_sv": historical_sv,
            "historical_asv": historical_asv,
            "keyword_metadata": keyword_metadata,
            "location_code": location_code,
        }
        if periods_sv:
            payload["periods_sv"] = [{"year": y, "month": m} for y, m in periods_sv]
        if periods_asv:
            payload["periods_asv"] = [{"year": y, "month": m} for y, m in periods_asv]
        write_json(output_dir / "historical_sv_asv.json", payload)

    _, sv_params_by_intent, asv_params_by_intent, hp_cal = _load_calibration_state(calibrated_path, hp)
    _write_market_volume_files(
        output_dir=output_dir,
        sv_lookup=sv_lookup,
        asv_lookup=asv_lookup,
        sv_metadata=sv_metadata,
        location_code=location_code,
        language_code=language_code,
    )
    prompt_estimates, intent_estimates = _estimate_volumes(
        extractions=extractions,
        sv_lookup=sv_lookup,
        asv_lookup=asv_lookup,
        sv_metadata=sv_metadata,
        rho_by_keyword=rho_by_kw,
        hp=hp_cal,
        sv_params_by_intent=sv_params_by_intent,
        asv_params_by_intent=asv_params_by_intent,
        settings=settings,
    )
    _write_market_estimate_files(
        output_dir=output_dir,
        extractions=extractions,
        prompt_estimates=prompt_estimates,
        intent_estimates=intent_estimates,
        sv_lookup=sv_lookup,
        asv_lookup=asv_lookup,
    )
    return prompt_estimates, intent_estimates


async def _finalize_multilocation_run(
    *,
    ctx,
    company_name: str | None,
    location_codes: list[int],
    language_code: str,
    sv_source: str | None,
    settings: Settings,
    per_loc_prompts: list[list[PromptDemandEstimate]],
    per_loc_intents: list[list[IntentClusterDemandEstimate]],
) -> None:
    breakdown_rows: list[dict] = []
    for loc, prompts in zip(location_codes, per_loc_prompts):
        for p in prompts:
            row = p.model_dump()
            row["location_code"] = loc
            breakdown_rows.append(row)

    agg_prompt_rows = aggregate_prompt_estimates(per_loc_prompts)
    agg_intent_rows = aggregate_intent_estimates(per_loc_intents)

    write_locations_manifest(
        ctx.run_dir,
        location_codes,
        language_code=language_code,
        sv_source=sv_source,
    )
    write_jsonl(ctx.run_dir / "prompt_estimates_by_location.jsonl", breakdown_rows)
    write_jsonl(ctx.prompt_estimates_path, agg_prompt_rows)
    export_prompt_estimates_to_csv(agg_prompt_rows, ctx.run_dir / "prompt_estimates.csv")
    write_json(ctx.intent_estimates_path, agg_intent_rows)
    _write_run_summary(
        ctx=ctx,
        company_name=company_name,
        prompt_estimates=agg_prompt_rows,
        intent_estimates=agg_intent_rows,
        location_codes=location_codes,
        language_code=language_code,
        sv_source=sv_source,
        settings=settings,
    )


async def _run_all_with_calibration(
    prompt_items: list[dict],
    company_name: str | None,
    ctx,
    settings,
    args,
    extractions_from_path: Path | None = None,
) -> None:
    """
    Full flow: extract keywords → fetch SV+ASV (with history) → calibrate ρ,η → estimate.
    Uses all keywords from all intents for calibration.
    If extractions_from_path is provided, load existing extractions instead of extracting.
    """
    # Step 1: Extract keywords or load from file
    extractions = []
    all_keywords = set()

    if extractions_from_path and extractions_from_path.exists():
        for row in iter_jsonl(extractions_from_path):
            extractions.append(row)
            all_keywords.update(k["keyword"] for k in row.get("keywords", []))
        write_jsonl(ctx.keyword_extractions_path, extractions)
        console.print(f"[green]Loaded[/green] {len(extractions)} keyword extractions from {extractions_from_path.name}")
    else:
        kw_method = getattr(args, "keyword_extraction", None) or settings.CASE2_KEYWORD_EXTRACTION
        if kw_method == "llm":
            batch_result = _extract_keywords_batch_by_intent(
                prompt_items,
                method=kw_method,
                settings=settings,
                max_keywords=_max_keywords_for_method(settings, kw_method),
                checkpoint_path=ctx.keyword_extractions_path,
            )
            if batch_result is not None:
                extractions = batch_result
                for ext in extractions:
                    if ext:
                        all_keywords.update(k["keyword"] for k in ext.get("keywords", []))
            else:
                kw_method = "ngram"
        elif kw_method == "ngram_llm_filter":
            try:
                batch_result = _extract_keywords_ngram_llm_filter_batch(
                    prompt_items,
                    settings=settings,
                    max_keywords=_max_keywords_for_method(settings, kw_method),
                    checkpoint_path=ctx.keyword_extractions_path,
                )
                extractions = batch_result
                for ext in extractions:
                    if ext:
                        all_keywords.update(k["keyword"] for k in ext.get("keywords", []))
            except Exception as e:
                if not _allow_ngram_fallback(settings):
                    raise
                console.print(f"[yellow]ngram+LLM filter failed ({e}); falling back to ngram[/yellow]")
                kw_method = "ngram"

        if not extractions:
            for i, item in enumerate(prompt_items):
                prompt = item["prompt"]
                pid = item.get("prompt_id") or f"prm_{i}"
                intent_cluster_id = item.get("intent_cluster_id")
                intent_cluster_name = item.get("intent_cluster_name")
                kw_dicts = _extract_keywords_for_prompt(
                    prompt,
                    method=kw_method,
                    settings=settings,
                    max_keywords=_max_keywords_for_method(settings, kw_method),
                )
                extractions.append({
                    "prompt_id": pid,
                    "prompt": prompt,
                    "intent_cluster_id": intent_cluster_id,
                    "intent_cluster_name": intent_cluster_name,
                    "keywords": kw_dicts,
                })
                all_keywords.update(k["keyword"] for k in kw_dicts)

        write_jsonl(ctx.keyword_extractions_path, extractions)
        console.print(f"[green]Extracted[/green] keywords for {len(extractions)} prompts ({kw_method}) -> {ctx.keyword_extractions_path}")

    # Add explicit keywords from company profile (if any)
    if ctx.company_profile_path.exists():
        company = load_company_profile(ctx.company_profile_path)
        explicit = getattr(company, "explicit_keywords", None) or []
        if explicit:
            all_keywords.update(explicit)
            console.print(f"[green]Added[/green] {len(explicit)} explicit keywords from company profile")

    keywords_list = list(all_keywords)
    if not keywords_list:
        console.print("[red]No keywords extracted. Cannot proceed.[/red]")
        return

    location_codes = _resolve_location_codes(
        getattr(args, "location", None),
        getattr(args, "locations", None),
    )
    language_code = getattr(args, "language", "en") or "en"

    login = settings.DATAFORSEO_LOGIN or ""
    password = settings.DATAFORSEO_PASSWORD or ""
    if not login or not password:
        console.print("[red]DataForSEO credentials required for run-all-with-calibration. Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD.[/red]")
        return

    sv_client = _make_sv_client(settings, login, password, getattr(args, "sv_source", None))
    asv_client = DataForSEOASVClient(login=login, password=password)
    sv_source = getattr(args, "sv_source", None) or settings.CASE2_SV_SOURCE or "clickstream"
    hp = _default_hp(settings)

    import os
    os.environ["CASE2_RUN_ID"] = ctx.run_id

    per_loc_prompts: list[list[PromptDemandEstimate]] = []
    per_loc_intents: list[list[IntentClusterDemandEstimate]] = []

    for idx, loc in enumerate(location_codes, start=1):
        output_dir = ctx.run_dir if len(location_codes) == 1 else location_subdir(ctx.run_dir, loc)
        console.print(
            f"[cyan]Market {idx}/{len(location_codes)}[/cyan]: location_code={loc} -> {output_dir.name if len(location_codes) == 1 else output_dir}"
        )
        prompts, intents = await _run_market_with_calibration(
            location_code=loc,
            language_code=language_code,
            keywords_list=keywords_list,
            extractions=extractions,
            output_dir=output_dir,
            settings=settings,
            sv_client=sv_client,
            asv_client=asv_client,
            hp=hp,
        )
        per_loc_prompts.append(prompts)
        per_loc_intents.append(intents)

    if len(location_codes) > 1:
        await _finalize_multilocation_run(
            ctx=ctx,
            company_name=company_name,
            location_codes=location_codes,
            language_code=language_code,
            sv_source=sv_source,
            settings=settings,
            per_loc_prompts=per_loc_prompts,
            per_loc_intents=per_loc_intents,
        )
    else:
        _write_run_summary(
            ctx=ctx,
            company_name=company_name,
            prompt_estimates=[p.model_dump() for p in per_loc_prompts[0]],
            intent_estimates=[e.model_dump() for e in per_loc_intents[0]],
            location_codes=location_codes,
            language_code=language_code,
            sv_source=sv_source,
            settings=settings,
        )


async def run_calibrate(
    keywords: list[str],
    output_path: Path,
    location_code: int = 2840,
    language_code: str = "en",
) -> None:
    """Run calibration and save to JSON."""
    from dotenv import load_dotenv
    load_dotenv()

    settings = Settings()
    login = settings.DATAFORSEO_LOGIN or ""
    password = settings.DATAFORSEO_PASSWORD or ""
    if not login or not password:
        console.print("[red]Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD[/red]")
        return

    sv_client = DataForSEOSVClient(login=login, password=password)
    asv_client = DataForSEOASVClient(login=login, password=password)

    rho_by_kw, calibrated_eta, rho_coeffs, sv_params_by_intent, asv_params_by_intent, residuals = await run_calibration(
        keywords=keywords,
        sv_client=sv_client,
        asv_client=asv_client,
        location_code=location_code,
        language_code=language_code,
    )
    save_calibration(
        output_path,
        mu_eta=calibrated_eta.mu_eta,
        sigma_eta=calibrated_eta.sigma_eta,
        rho_coeffs=rho_coeffs,
        rho_by_keyword=rho_by_kw,
        num_samples=calibrated_eta.num_samples,
        var_u=calibrated_eta.var_u,
        residuals=residuals,
        keywords=keywords,
        location_code=location_code,
        language_code=language_code,
        sv_params_by_intent=sv_params_by_intent,
        asv_params_by_intent=asv_params_by_intent,
    )
    console.print(f"[green]Calibration saved to {output_path}[/green]")
    console.print(f"  μ_η={calibrated_eta.mu_eta:.4f}, σ_η={calibrated_eta.sigma_eta:.4f}")
    console.print(f"  ρ samples: {len(rho_by_kw)}, η residuals: {calibrated_eta.num_samples}")
    if sv_params_by_intent:
        first = next(iter(sv_params_by_intent.values()))
        console.print(f"  SV: νc={first.nu_c:.4f}, ωc={first.omega_c:.4f}, σS,c={first.sigma_S_c:.4f} ({len(sv_params_by_intent)} intents)")


def _default_hp(settings: Settings) -> Case2Hyperparameters:
    import math
    return Case2Hyperparameters(
        nu_c=settings.CASE2_NU_C if settings.CASE2_NU_C is not None else math.log(50_000),
        omega_c=settings.CASE2_OMEGA_C if settings.CASE2_OMEGA_C is not None else 3.0,
        b_S=settings.CASE2_B_S if settings.CASE2_B_S is not None else 0.0,
        sigma_S_c=settings.CASE2_SIGMA_S_C if settings.CASE2_SIGMA_S_C is not None else 0.20,
        b_A=settings.CASE2_B_A if settings.CASE2_B_A is not None else 0.0,
        sigma_A_c=floor_sigma_a_c(
            settings.CASE2_SIGMA_A_C if settings.CASE2_SIGMA_A_C is not None else 0.20
        ),
        delta_c=settings.CASE2_DELTA_C if settings.CASE2_DELTA_C is not None else 0.20,
        sigma_delta=settings.CASE2_SIGMA_DELTA if settings.CASE2_SIGMA_DELTA is not None else 0.50,
        beta=settings.CASE2_BETA if settings.CASE2_BETA is not None else 60.0,
        rho=settings.CASE2_RHO if settings.CASE2_RHO is not None else 0.25,
        mu_eta=settings.CASE2_MU_ETA if settings.CASE2_MU_ETA is not None else 0.262364,  # log(1.3)
        sigma_eta=settings.CASE2_SIGMA_ETA if settings.CASE2_SIGMA_ETA is not None else 0.25,
    )


async def run_pipeline(
    prompt_items: list[dict],
    company_name: str | None = None,
    location_code: int = 2840,
    location_codes: list[int] | None = None,
    language_code: str = "en",
    dry_run: bool = False,
    calibrated_from: Path | None = None,
    sv_lookup: dict[str, float] | None = None,
    asv_lookup: dict[str, float] | None = None,
    sv_results: list[KeywordVolumeResult] | None = None,
    extractions: list[dict] | None = None,
    keyword_extraction: str | None = None,
    sv_source: str | None = None,
) -> None:
    """Run Case 2 pipeline: extract keywords (or use provided) → fetch SV+ASV (unless provided) → estimate."""
    from dotenv import load_dotenv
    load_dotenv()

    settings = Settings()
    ctx = resolve_run_context(settings)
    hp = _default_hp(settings)
    rho_by_keyword, sv_params_by_intent, asv_params_by_intent, hp = _load_calibration_state(
        calibrated_from, hp
    )
    resolved_codes = list(location_codes) if location_codes else [location_code]
    if extractions is not None:
        all_keywords = set()
        for ext in extractions:
            for kw in ext.get("keywords", []):
                k = kw.get("keyword") if isinstance(kw, dict) else getattr(kw, "keyword", None)
                if k:
                    all_keywords.add(k)
    else:
        kw_method = keyword_extraction or settings.CASE2_KEYWORD_EXTRACTION
        extractions = []
        all_keywords = set()

        if kw_method == "llm":
            batch_result = _extract_keywords_batch_by_intent(
                prompt_items,
                method=kw_method,
                settings=settings,
                max_keywords=_max_keywords_for_method(settings, kw_method),
                checkpoint_path=ctx.keyword_extractions_path,
            )
            if batch_result is not None:
                extractions = batch_result
                for ext in extractions:
                    if ext:
                        all_keywords.update(k["keyword"] for k in ext.get("keywords", []))
            else:
                kw_method = "ngram"
        elif kw_method == "ngram_llm_filter":
            try:
                batch_result = _extract_keywords_ngram_llm_filter_batch(
                    prompt_items,
                    settings=settings,
                    max_keywords=_max_keywords_for_method(settings, kw_method),
                    checkpoint_path=ctx.keyword_extractions_path,
                )
                extractions = batch_result
                for ext in extractions:
                    if ext:
                        all_keywords.update(k["keyword"] for k in ext.get("keywords", []))
            except Exception as e:
                if not _allow_ngram_fallback(settings):
                    raise
                console.print(f"[yellow]ngram+LLM filter failed ({e}); falling back to ngram[/yellow]")
                kw_method = "ngram"

        if not extractions:
            for i, item in enumerate(prompt_items):
                prompt = item["prompt"]
                pid = item.get("prompt_id") or f"prm_{i}"
                intent_cluster_id = item.get("intent_cluster_id")
                intent_cluster_name = item.get("intent_cluster_name")
                kw_dicts = _extract_keywords_for_prompt(
                    prompt,
                    method=kw_method,
                    settings=settings,
                    max_keywords=_max_keywords_for_method(settings, kw_method),
                )
                extractions.append({
                    "prompt_id": pid,
                    "prompt": prompt,
                    "intent_cluster_id": intent_cluster_id,
                    "intent_cluster_name": intent_cluster_name,
                    "keywords": kw_dicts,
                })
                all_keywords.update(k["keyword"] for k in kw_dicts)

    write_jsonl(ctx.keyword_extractions_path, extractions)
    console.print(f"[green]Saved[/green] keyword_extractions -> {ctx.keyword_extractions_path}")

    # Add explicit keywords from company profile (if any)
    if ctx.company_profile_path.exists():
        company = load_company_profile(ctx.company_profile_path)
        explicit = getattr(company, "explicit_keywords", None) or []
        if explicit:
            all_keywords.update(explicit)
            console.print(f"[green]Added[/green] {len(explicit)} explicit keywords from company profile")

    keywords_list = list(all_keywords)

    if len(resolved_codes) > 1:
        if sv_lookup and asv_lookup:
            console.print("[red]Pre-fetched SV/ASV cannot be used with multiple locations.[/red]")
            return
        if calibrated_from and calibrated_from.exists():
            console.print(
                "[yellow]Single calibration file is not applied across multiple locations; "
                "use --with-calibration for per-market calibration.[/yellow]"
            )
            rho_by_keyword = None
            sv_params_by_intent = None
            asv_params_by_intent = None
            hp = _default_hp(settings)
        await _run_pipeline_multilocation(
            ctx=ctx,
            extractions=extractions,
            keywords_list=keywords_list,
            location_codes=resolved_codes,
            language_code=language_code,
            company_name=company_name,
            dry_run=dry_run,
            sv_source=sv_source,
            settings=settings,
            hp=hp,
            rho_by_keyword=rho_by_keyword,
            sv_params_by_intent=sv_params_by_intent,
            asv_params_by_intent=asv_params_by_intent,
        )
        return

    sv_data = sv_lookup if sv_lookup is not None else {}
    asv_data = asv_lookup if asv_lookup is not None else {}
    _sv_results = sv_results

    if sv_data and asv_data:
        # Pre-fetched (e.g. from run-all-with-calibration)
        default_vol = float(settings.CASE2_DEFAULT_MISSING_VOLUME)
        sv_lookup = sv_data
        asv_lookup = asv_data
        for kw in keywords_list:
            if kw not in sv_lookup:
                sv_lookup[kw] = default_vol
            if kw not in asv_lookup:
                asv_lookup[kw] = default_vol
    elif dry_run:
        # Use placeholder values for dry-run without API
        sv_lookup = {kw: 5000.0 for kw in keywords_list}
        asv_lookup = {kw: 1200.0 for kw in keywords_list}
        console.print("[yellow]Dry-run: using placeholder SV/ASV (no API)[/yellow]")
    else:
        login = settings.DATAFORSEO_LOGIN or ""
        password = settings.DATAFORSEO_PASSWORD or ""
        if not login or not password:
            console.print("[red]Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD for real SV/ASV[/red]")
            return

        sv_client = _make_sv_client(settings, login, password, sv_source)
        asv_client = DataForSEOASVClient(login=login, password=password)

        resolved_sv_source = (sv_source or settings.CASE2_SV_SOURCE or "clickstream").strip().lower()
        console.print(f"[cyan]Fetching SV ({resolved_sv_source}) + ASV for {len(keywords_list)} keywords...[/cyan]")
        _sv_results = await sv_client.get_volume(keywords_list, location_code, language_code)
        asv_results = await asv_client.get_volume(keywords_list, location_code, language_code)

        default_vol = float(settings.CASE2_DEFAULT_MISSING_VOLUME)
        sv_lookup = {}
        asv_lookup = {}
        for r in _sv_results:
            sv_lookup[r.keyword] = float(r.search_volume or default_vol)
        for r in asv_results:
            asv_lookup[r.keyword] = float(r.search_volume or default_vol)

    # Build sv_metadata (cpc, competition) for enrichment and writing
    sv_metadata: dict[str, dict] = {}
    if _sv_results is not None:
        sv_metadata = {r.keyword: {"cpc": r.cpc, "competition": r.competition} for r in _sv_results}

    _write_market_volume_files(
        output_dir=ctx.run_dir,
        sv_lookup=sv_lookup,
        asv_lookup=asv_lookup,
        sv_metadata=sv_metadata,
        location_code=location_code,
        language_code=language_code,
    )
    console.print(f"[green]Saved[/green] SV -> {ctx.sv_data_path}, ASV -> {ctx.asv_data_path}")
    console.print(f"[green]Saved[/green] keyword volumes -> {ctx.run_dir / 'keyword_volumes.csv'}")

    # Estimate per prompt (use intent-specific hp when available)
    prompt_estimates, intent_estimates = _estimate_volumes(
        extractions=extractions,
        sv_lookup=sv_lookup,
        asv_lookup=asv_lookup,
        sv_metadata=sv_metadata,
        rho_by_keyword=rho_by_keyword,
        hp=hp,
        sv_params_by_intent=sv_params_by_intent,
        asv_params_by_intent=asv_params_by_intent,
        settings=settings,
    )
    _write_market_estimate_files(
        output_dir=ctx.run_dir,
        extractions=extractions,
        prompt_estimates=prompt_estimates,
        intent_estimates=intent_estimates,
        sv_lookup=sv_lookup,
        asv_lookup=asv_lookup,
    )
    _write_run_summary(
        ctx=ctx,
        company_name=company_name,
        prompt_estimates=[p.model_dump() for p in prompt_estimates],
        intent_estimates=[e.model_dump() for e in intent_estimates],
        location_codes=resolved_codes,
        language_code=language_code,
        sv_source=sv_source,
        settings=settings,
    )


async def _run_pipeline_multilocation(
    *,
    ctx,
    extractions: list[dict],
    keywords_list: list[str],
    location_codes: list[int],
    language_code: str,
    company_name: str | None,
    dry_run: bool,
    sv_source: str | None,
    settings: Settings,
    hp: Case2Hyperparameters,
    rho_by_keyword: dict[str, float] | None,
    sv_params_by_intent: dict | None,
    asv_params_by_intent: dict | None,
) -> None:
    per_loc_prompts: list[list[PromptDemandEstimate]] = []
    per_loc_intents: list[list[IntentClusterDemandEstimate]] = []

    if dry_run:
        for idx, loc in enumerate(location_codes, start=1):
            output_dir = location_subdir(ctx.run_dir, loc)
            console.print(f"[yellow]Dry-run market {idx}/{len(location_codes)}: location {loc}[/yellow]")
            sv_lookup = {kw: 5000.0 for kw in keywords_list}
            asv_lookup = {kw: 1200.0 for kw in keywords_list}
            _write_market_volume_files(
                output_dir=output_dir,
                sv_lookup=sv_lookup,
                asv_lookup=asv_lookup,
                sv_metadata={},
                location_code=loc,
                language_code=language_code,
            )
            prompts, intents = _estimate_volumes(
                extractions=extractions,
                sv_lookup=sv_lookup,
                asv_lookup=asv_lookup,
                sv_metadata={},
                rho_by_keyword=rho_by_keyword,
                hp=hp,
                sv_params_by_intent=sv_params_by_intent,
                asv_params_by_intent=asv_params_by_intent,
                settings=settings,
            )
            _write_market_estimate_files(
                output_dir=output_dir,
                extractions=extractions,
                prompt_estimates=prompts,
                intent_estimates=intents,
                sv_lookup=sv_lookup,
                asv_lookup=asv_lookup,
            )
            per_loc_prompts.append(prompts)
            per_loc_intents.append(intents)
    else:
        login = settings.DATAFORSEO_LOGIN or ""
        password = settings.DATAFORSEO_PASSWORD or ""
        if not login or not password:
            console.print("[red]Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD for real SV/ASV[/red]")
            return
        sv_client = _make_sv_client(settings, login, password, sv_source)
        asv_client = DataForSEOASVClient(login=login, password=password)
        resolved_sv_source = (sv_source or settings.CASE2_SV_SOURCE or "clickstream").strip().lower()
        console.print(
            f"[cyan]Multi-market run[/cyan]: {len(location_codes)} locations, "
            f"SV source={resolved_sv_source}, {len(keywords_list)} keywords"
        )
        for idx, loc in enumerate(location_codes, start=1):
            output_dir = location_subdir(ctx.run_dir, loc)
            console.print(f"[cyan]Market {idx}/{len(location_codes)}[/cyan]: location_code={loc}")
            _sv_results, _, sv_lookup, asv_lookup, sv_metadata = await _fetch_sv_asv_for_market(
                keywords_list=keywords_list,
                location_code=loc,
                language_code=language_code,
                sv_client=sv_client,
                asv_client=asv_client,
                settings=settings,
                with_history=False,
            )
            _write_market_volume_files(
                output_dir=output_dir,
                sv_lookup=sv_lookup,
                asv_lookup=asv_lookup,
                sv_metadata=sv_metadata,
                location_code=loc,
                language_code=language_code,
            )
            prompts, intents = _estimate_volumes(
                extractions=extractions,
                sv_lookup=sv_lookup,
                asv_lookup=asv_lookup,
                sv_metadata=sv_metadata,
                rho_by_keyword=rho_by_keyword,
                hp=hp,
                sv_params_by_intent=sv_params_by_intent,
                asv_params_by_intent=asv_params_by_intent,
                settings=settings,
            )
            _write_market_estimate_files(
                output_dir=output_dir,
                extractions=extractions,
                prompt_estimates=prompts,
                intent_estimates=intents,
                sv_lookup=sv_lookup,
                asv_lookup=asv_lookup,
            )
            per_loc_prompts.append(prompts)
            per_loc_intents.append(intents)

    await _finalize_multilocation_run(
        ctx=ctx,
        company_name=company_name,
        location_codes=location_codes,
        language_code=language_code,
        sv_source=sv_source,
        settings=settings,
        per_loc_prompts=per_loc_prompts,
        per_loc_intents=per_loc_intents,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Case 2: SV + ASV Bayesian fusion")
    parser.add_argument("--env-file", type=Path, help="Path to .env file for credentials")
    sub = parser.add_subparsers(dest="cmd", help="Commands")

    dry = sub.add_parser("dry-run", help="Run spec dry-run (fully worked example, no API)")

    run = sub.add_parser("run", help="Run pipeline on prompts")
    run.add_argument("prompts", nargs="+", help="Prompts to estimate")
    _add_location_cli_args(run)
    run.add_argument("--language", default="en", help="Language code")
    run.add_argument("--dry-run", action="store_true", help="Use placeholder SV/ASV (no API)")
    run.add_argument("--calibrated-from", type=Path, help="Path to calibration JSON")
    run.add_argument("--keyword-extraction", choices=list(KEYWORD_EXTRACTION_METHODS), default=None,
                     help="Keyword extraction: llm, ngram, or ngram_llm_filter (n-gram + LLM filter)")

    cal = sub.add_parser("calibrate", help="Calibrate ρ and η from SV+ASV monthly data")
    cal.add_argument("keywords", nargs="+", help="Keywords for calibration")
    cal.add_argument("--output", "-o", type=Path, required=True, help="Output calibration JSON")
    _add_location_cli_args(cal)
    cal.add_argument("--language", default="en", help="Language code")

    # Intent & prompt generation (DeepSeek R1)
    gen_int = sub.add_parser("generate-intents", help="Generate intent clusters (DeepSeek R1)")
    gen_int.add_argument("--company-profile", type=Path, required=True, help="Path to company profile JSON")
    gen_int.add_argument("--n-intents", type=int, default=None, help="Number of intent clusters (default: 18-20)")

    gen_prm = sub.add_parser("generate-prompts", help="Generate prompts per intent (DeepSeek R1)")
    gen_prm.add_argument("--company-profile", type=Path, default=None, help="Path to company profile (default: from run dir)")
    gen_prm.add_argument("--n-prompts-per-intent", type=int, default=10, help="Prompts per intent cluster")

    run_all = sub.add_parser("run-all", help="Full pipeline: company -> intents -> prompts -> SV+ASV -> estimate")
    run_all.add_argument("--env-file", type=Path, help="Path to .env for OPENROUTER_API_KEY, DATAFORSEO_*")
    run_all.add_argument("--company-profile", type=Path, help="Path to company profile JSON (required unless --from-run)")
    run_all.add_argument("--from-run", type=str, help="Run ID to resume from (use existing intents + prompts, skip LLM)")
    run_all.add_argument("--from-run-intents", type=str, help="Run ID to copy intent clusters from (same clusters, generate new prompts)")
    run_all.add_argument("--n-intents", type=int, default=None, help="Number of intent clusters")
    run_all.add_argument("--n-prompts-per-intent", type=int, default=10, help="Prompts per intent")
    _add_location_cli_args(run_all)
    run_all.add_argument("--language", default="en", help="Language code")
    run_all.add_argument("--dry-run", action="store_true", help="Use placeholder SV/ASV (no DataForSEO)")
    run_all.add_argument("--calibrated-from", type=Path, help="Path to calibration JSON (when not using --with-calibration)")
    run_all.add_argument("--with-calibration", action="store_true",
                         help="Fetch SV+ASV, calibrate ρ,η, then estimate")
    run_all.add_argument("--keyword-extraction", choices=list(KEYWORD_EXTRACTION_METHODS), default=None,
                         help="Keyword extraction: llm, ngram, or ngram_llm_filter")

    args = parser.parse_args()

    if getattr(args, "env_file", None):
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=True)

    if args.cmd == "dry-run":
        import runpy
        # Resolve path: cli.py -> case2_demand -> src -> project_root
        pkg_dir = Path(__file__).resolve().parent
        script_path = pkg_dir.parent.parent / "scripts" / "dry_run.py"
        if not script_path.exists():
            # Fallback: run inline dry-run
            from case2_demand.estimation.bayesian_sv_asv import Case2Estimator, Case2Hyperparameters
            import math
            hp = Case2Hyperparameters(
                nu_c=math.log(50_000), omega_c=3.0, b_S=0.0, sigma_S_c=0.20,
                b_A=0.0, sigma_A_c=0.20, delta_c=0.20, sigma_delta=0.50,
                beta=60.0, rho=0.25, mu_eta=math.log(1.3), sigma_eta=0.25,
            )
            est = Case2Estimator(hp)
            Y_median, _, _, interval, _, _ = est.estimate_demand(
                prompt="best running shoes for flat feet",
                keywords=["running shoes flat feet", "stability running shoes"],
                similarities=[0.88, 0.78],
                sv_values=[90_000, 40_000],
                asv_values=[22_000, 9_500],
            )
            console.print(f"[green]Y(p) ≈ {Y_median:,.0f}[/green] AI-units/month")
            console.print(f"90% CI: [{interval[0]:,.0f}, {interval[1]:,.0f}]")
        else:
            runpy.run_path(str(script_path))
    elif args.cmd == "run":
        prompt_items = [{"prompt": p, "prompt_id": f"prm_{i}"} for i, p in enumerate(args.prompts)]
        location_codes = _resolve_location_codes(args.location, getattr(args, "locations", None))
        asyncio.run(run_pipeline(
            prompt_items=prompt_items,
            location_code=location_codes[0],
            location_codes=location_codes if len(location_codes) > 1 else None,
            language_code=args.language,
            dry_run=args.dry_run,
            calibrated_from=getattr(args, "calibrated_from", None),
            keyword_extraction=getattr(args, "keyword_extraction", None),
        ))
    elif args.cmd == "calibrate":
        asyncio.run(run_calibrate(
            keywords=args.keywords,
            output_path=args.output,
            location_code=args.location,
            language_code=args.language,
        ))
    elif args.cmd == "generate-intents":
        from dotenv import load_dotenv
        load_dotenv()
        settings = Settings()
        ctx = resolve_run_context(settings)
        company = load_company_profile(args.company_profile)
        ctx.company_profile_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(ctx.company_profile_path, company.model_dump())
        generate_intent_clusters_step(
            ctx=ctx,
            company=company,
            settings=settings,
            prompt_path=_prompts_dir() / "intent_cluster_generation_system.txt",
            n_intents=getattr(args, "n_intents", None),
        )
        console.print(f"Saved to {ctx.intent_cluster_plan_path}")
    elif args.cmd == "generate-prompts":
        from dotenv import load_dotenv
        load_dotenv()
        settings = Settings()
        ctx = resolve_run_context(settings)
        company_path = getattr(args, "company_profile") or ctx.company_profile_path
        company = load_company_profile(company_path)
        plan = IntentClusterPlan.model_validate(
            json.loads(ctx.intent_cluster_plan_path.read_text())
        )
        n = getattr(args, "n_prompts_per_intent", 10)
        generate_prompts_step(
            ctx=ctx,
            company=company,
            intent_plan=plan,
            settings=settings,
            n_prompts_per_intent=n,
            prompt_path=_prompts_dir() / "prompt_batch_for_intent_system.txt",
        )
        console.print(f"Saved to {ctx.synthetic_prompts_path}")
    elif args.cmd == "run-all":
        asyncio.run(_run_all(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
