"""Data models for Case 2 pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --- Company & Intent (for prompt generation, same as Case 1) ---


class CompanyProduct(BaseModel):
    name: str
    description: str
    key_features: List[str] = Field(default_factory=list)
    target_users: List[str] = Field(default_factory=list)
    pricing_notes: Optional[str] = None


class CompanyPersona(BaseModel):
    name: str
    role: str
    seniority: Optional[str] = None
    goals: List[str] = Field(default_factory=list)
    pains: List[str] = Field(default_factory=list)
    typical_workflow: Optional[str] = None
    constraints: List[str] = Field(default_factory=list)


class CompanyCompetitor(BaseModel):
    name: str
    aliases: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class CompanyProfile(BaseModel):
    """Company/brand input for intent and prompt generation."""
    company_name: str
    aliases: List[str] = Field(default_factory=list)
    description: str
    industry: str
    sub_industry: Optional[str] = None
    products_services: List[CompanyProduct] = Field(default_factory=list)
    customer_personas: List[CompanyPersona] = Field(default_factory=list)
    primary_geos: List[str] = Field(default_factory=list)
    primary_languages: List[str] = Field(default_factory=list)
    competitors: List[CompanyCompetitor] = Field(default_factory=list)
    differentiators: List[str] = Field(default_factory=list)
    common_misconceptions: List[str] = Field(default_factory=list)
    regulated_or_sensitive_topics: List[str] = Field(default_factory=list)
    seed_queries: List[str] = Field(default_factory=list)
    must_include_terms: List[str] = Field(default_factory=list)
    must_avoid_terms: List[str] = Field(default_factory=list)
    explicit_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords to always include in SV/ASV fetch (in addition to extracted keywords)",
    )


class IntentCluster(BaseModel):
    """Intent cluster from LLM."""
    cluster_id: Optional[str] = None
    name: str
    user_mindset: str
    example_prompt: str
    description: Optional[str] = None


class IntentClusterPlan(BaseModel):
    rationale: str
    clusters: List[IntentCluster]


class SyntheticPrompt(BaseModel):
    """One synthetic prompt with intent cluster."""
    prompt_id: str
    prompt: str
    intent_cluster_id: str
    intent_cluster_name: str
    weight: float = Field(..., gt=0.0)


# --- Keyword extraction & estimation ---


class KeywordWithImportance(BaseModel):
    """Keyword with importance score (0-1)."""
    keyword: str
    importance_score: float = Field(..., ge=0.0, le=1.0)


class PromptKeywordExtraction(BaseModel):
    """Keywords extracted from a prompt with importance scores."""
    prompt_id: str
    prompt: str
    keywords: List[KeywordWithImportance]
    intent_cluster_id: Optional[str] = None
    intent_cluster_name: Optional[str] = None


class KeywordEstimate(BaseModel):
    """Bayesian posterior estimate for a keyword (Case 2: SV+ASV fusion)."""
    keyword: str
    mu_post: float
    sigma_post: float
    A_median: float
    A_mean: float
    variance: float
    interval_90: tuple[float, float]
    cpc: Optional[float] = None
    competition: Optional[float] = None


class PromptDemandEstimate(BaseModel):
    """Demand estimate for a prompt."""
    prompt_id: str
    prompt: str
    Y_median: float
    Y_mean: float
    Y_std: float
    interval_90: tuple[float, float]
    keyword_estimates: List[Dict[str, Any]] = Field(default_factory=list)
    weights: Dict[str, float] = Field(default_factory=dict)
    intent_cluster_id: Optional[str] = None
    intent_cluster_name: Optional[str] = None
    keyword_filter: Optional[str] = None
    keyword_filter_levels: Optional[int] = None
    importance_cutoff: Optional[float] = None
    keywords_before_filter: Optional[int] = None
    keywords_kept: Optional[int] = None


class IntentClusterDemandEstimate(BaseModel):
    """Aggregated demand estimate per intent cluster."""
    intent_cluster_id: str
    intent_cluster_name: str
    num_prompts: int
    Y_median: float
    Y_mean: float
    Y_std: float
    interval_90: tuple[float, float]
    # overlap_discount method metadata (optional for legacy rows)
    volume_method: Optional[str] = None
    overlap_discount: Optional[float] = None
    average_keyword_similarity: Optional[float] = None
    union_keyword_count: Optional[int] = None
    overlap_discount_volume: Optional[float] = None
    sum_prompt_y_mean: Optional[float] = None
    prompts_matched: Optional[int] = None
    # representative_incremental method metadata
    representative_prompt_id: Optional[str] = None
    representative_volume: Optional[float] = None
    incremental_volume: Optional[float] = None
    prompts_with_incremental: Optional[int] = None
    incremental_prompt_details: Optional[List[Dict[str, Any]]] = None


class RunMetrics(BaseModel):
    """Final run metrics."""
    run_id: str
    total_prompts: int
    total_keywords: int
    total_estimated_volume: float
    prompt_estimates: List[Dict[str, Any]] = Field(default_factory=list)
    intent_cluster_estimates: List[Dict[str, Any]] = Field(default_factory=list)
    company_name: Optional[str] = None
