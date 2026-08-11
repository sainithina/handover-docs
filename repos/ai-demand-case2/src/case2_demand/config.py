"""Configuration for Case 2 pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    CASE2_RUN_ID: Optional[str] = None
    CASE2_RUNS_DIR: str = "runs"

    # LLM for intent/prompt generation (OpenRouter-compatible; any chat model id)
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    # OpenRouter: use `openrouter/free` to route to any current free model (avoids 404 when a :free slug is retired).
    # Paid: set e.g. google/gemini-2.5-flash-lite (requires credits — 402 if balance empty).
    CASE2_LLM_MODEL: str = "openrouter/free"

    DATAFORSEO_LOGIN: Optional[str] = None
    DATAFORSEO_PASSWORD: Optional[str] = None
    DATAFORSEO_BASE_URL: str = "https://api.dataforseo.com/v3"

    # SV sensor (classic search volume)
    CASE2_NU_C: Optional[float] = None  # νc = log(prior median SV)
    CASE2_OMEGA_C: Optional[float] = None  # ωc
    CASE2_B_S: Optional[float] = None  # bS
    CASE2_SIGMA_S_C: Optional[float] = None  # σS,c

    # ASV sensor
    CASE2_B_A: Optional[float] = None  # bA
    CASE2_SIGMA_A_C: Optional[float] = None  # σA,c

    # Coupling
    CASE2_DELTA_C: Optional[float] = None  # δc
    CASE2_SIGMA_DELTA: Optional[float] = None  # σδ
    CASE2_BETA: Optional[float] = 5  # softmax sharpness; None → uses 60.0 default in cli
    CASE2_RHO: Optional[float] = None  # AI-share (if fixed)
    CASE2_MU_ETA: Optional[float] = None  # log(η) prior mean
    CASE2_SIGMA_ETA: Optional[float] = None  # log(η) prior std

    CASE2_CROSS_ENCODER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    CASE2_MAX_KEYWORDS: int = 20
    # LLM extraction: hard cap on keywords per prompt (system prompt enforces 2–3)
    CASE2_LLM_MAX_KEYWORDS: int = 3
    CASE2_DEFAULT_MISSING_VOLUME: float = 0.0  # Fallback when DataForSEO returns no data
    # SV source: "clickstream" (default) or "google_ads" (DataForSEO Google Ads search_volume/live)
    CASE2_SV_SOURCE: str = "clickstream"

    # Keyword extraction: "ngram", "llm", or "ngram_llm_filter" (n-gram candidates → LLM filter → cross-encoder)
    CASE2_KEYWORD_EXTRACTION: str = "llm"
    # LLM filter step (ngram_llm_filter): max keywords kept per prompt after LLM dedup
    CASE2_NGRAM_LLM_FILTER_MAX_KEYWORDS: int = 6
    # Minimum keywords to keep per prompt after LLM + validation (2 is fine)
    CASE2_LLM_MIN_KEYWORDS: int = 1
    # When False, never fall back to ngram if LLM extraction is configured
    CASE2_ALLOW_NGRAM_FALLBACK: bool = False

    # LLM rate limiting: delay (seconds) between requests when using llm extraction (OpenRouter free tier ~8 req/min)
    CASE2_LLM_REQUEST_DELAY_SEC: float = 8.0
    # Smaller batches = faster responses and less JSON truncation on free models
    CASE2_LLM_MAX_PROMPTS_PER_CALL: int = 10
    # Per-request HTTP timeout (seconds); avoids hung runs when a free model stalls
    CASE2_LLM_REQUEST_TIMEOUT_SEC: float = 180.0

    # Intent-level (topic) volume method: representative_incremental (default), overlap_discount, or fusion (legacy)
    CASE2_INTENT_VOLUME_METHOD: str = "representative_incremental"
    CASE2_OVERLAP_DISCOUNT_ALPHA: float = 0.7

    # Legacy fusion path: union keywords → semantic dedupe → single Case2 fusion per intent
    CASE2_INTENT_DEDUP_SIM_THRESHOLD: float = 0.4
    CASE2_INTENT_DEDUP_MODEL: str = "all-MiniLM-L6-v2"

    # Pre-fusion keyword filter on importance_score: none | top_n | median | binary_search
    CASE2_KEYWORD_FILTER: str = "none"
    # binary_search: iterative median cutoff depth (1 or 2 levels), not keyword count
    CASE2_KEYWORD_FILTER_LEVELS: int = 1
    # top_n only: max keywords to keep when CASE2_KEYWORD_FILTER=top_n
    CASE2_KEYWORD_FILTER_TOP_N: int = 2


@dataclass(frozen=True)
class RunContext:
    run_id: str
    runs_dir: Path
    run_dir: Path
    company_profile_path: Path
    intent_cluster_plan_path: Path
    synthetic_prompts_path: Path
    keyword_extractions_path: Path
    sv_data_path: Path
    asv_data_path: Path
    prompt_estimates_path: Path
    intent_estimates_path: Path
    metrics_path: Path
    insights_path: Path


def _default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def resolve_run_context(settings: Settings) -> RunContext:
    run_id = settings.CASE2_RUN_ID or os.getenv("RUN_ID") or _default_run_id()
    runs_dir = Path(settings.CASE2_RUNS_DIR).expanduser().resolve()
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    return RunContext(
        run_id=run_id,
        runs_dir=runs_dir,
        run_dir=run_dir,
        company_profile_path=run_dir / "company_profile.json",
        intent_cluster_plan_path=run_dir / "intent_cluster_plan.json",
        synthetic_prompts_path=run_dir / "synthetic_prompts.jsonl",
        keyword_extractions_path=run_dir / "keyword_extractions.jsonl",
        sv_data_path=run_dir / "sv_data.jsonl",
        asv_data_path=run_dir / "asv_data.jsonl",
        prompt_estimates_path=run_dir / "prompt_estimates.jsonl",
        intent_estimates_path=run_dir / "intent_cluster_estimates.json",
        metrics_path=run_dir / "metrics.json",
        insights_path=run_dir / "insights.md",
    )
