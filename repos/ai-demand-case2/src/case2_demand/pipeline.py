"""Case 2 pipeline: Intent clusters -> Prompts -> Keywords -> SV+ASV -> Bayesian fusion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from case2_demand.config import RunContext, Settings
from case2_demand.llm.openai_client import OpenAIClient
from case2_demand.schemas import (
    CompanyProfile,
    IntentCluster,
    IntentClusterPlan,
    SyntheticPrompt,
)
from case2_demand.util.ids import make_id
from case2_demand.util.io import write_json, write_jsonl

console = Console()


def load_company_profile(path: Path) -> CompanyProfile:
    return CompanyProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))


def generate_intent_clusters_step(
    *,
    ctx: RunContext,
    company: CompanyProfile,
    settings: Settings,
    prompt_path: Path,
    n_intents: Optional[int] = None,
) -> IntentClusterPlan:
    """Generate intent clusters using DeepSeek R1 (or configured LLM)."""
    api_key = settings.OPENROUTER_API_KEY
    base_url = settings.OPENROUTER_BASE_URL
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY is required for intent generation. "
            "Set it in .env or environment."
        )

    client = OpenAIClient(api_key=api_key, base_url=base_url)
    plan = client.generate_intent_clusters(
        model=settings.CASE2_LLM_MODEL,
        company=company,
        system_prompt_path=prompt_path,
        n_intents=n_intents,
    )

    fixed_clusters = []
    for i, c in enumerate(plan.clusters):
        cid = (
            c.cluster_id
            or c.name.lower().replace(" ", "_").replace("/", "_")[:30]
            or f"cluster_{i}"
        )
        desc = c.description or f"Searches related to {c.name}: {c.user_mindset}"
        fixed_clusters.append(
            IntentCluster(
                cluster_id=cid,
                name=c.name,
                user_mindset=c.user_mindset,
                example_prompt=c.example_prompt,
                description=desc,
            )
        )
    plan = IntentClusterPlan(rationale=plan.rationale, clusters=fixed_clusters)
    write_json(ctx.intent_cluster_plan_path, plan.model_dump())
    console.print(f"[green]Generated[/green] {len(plan.clusters)} intent clusters (DeepSeek R1)")
    return plan


def generate_prompts_step(
    *,
    ctx: RunContext,
    company: CompanyProfile,
    intent_plan: IntentClusterPlan,
    settings: Settings,
    n_prompts_per_intent: int,
    prompt_path: Path,
) -> List[SyntheticPrompt]:
    """Generate synthetic prompts per intent using DeepSeek R1."""
    api_key = settings.OPENROUTER_API_KEY
    base_url = settings.OPENROUTER_BASE_URL
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY is required for prompt generation. "
            "Set it in .env or environment."
        )

    client = OpenAIClient(api_key=api_key, base_url=base_url)
    all_prompts: List[SyntheticPrompt] = []
    clusters = intent_plan.clusters

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=20),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("[dim]({task.completed}/{task.total} intents)"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating prompts...", total=len(clusters), completed=0)
        for cluster in clusters:
            progress.update(task, description=f"[cyan]{cluster.name[:40]}...")
            prompts = client.generate_prompts_for_intent(
                model=settings.CASE2_LLM_MODEL,
                company=company,
                intent_cluster=cluster,
                n_prompts=n_prompts_per_intent,
                system_prompt_path=prompt_path,
            )
            weight = 1.0 / max(len(prompts), 1)
            for p in prompts:
                if not p or not p.strip():
                    continue
                pid = make_id("prm", f"{company.company_name}|{p}|{cluster.cluster_id}")
                all_prompts.append(
                    SyntheticPrompt(
                        prompt_id=pid,
                        prompt=p.strip(),
                        intent_cluster_id=cluster.cluster_id,
                        intent_cluster_name=cluster.name,
                        weight=weight,
                    )
                )
            progress.advance(task)

    write_jsonl(ctx.synthetic_prompts_path, [p.model_dump() for p in all_prompts])
    console.print(f"[green]Generated[/green] {len(all_prompts)} prompts across {len(clusters)} intents")
    return all_prompts
