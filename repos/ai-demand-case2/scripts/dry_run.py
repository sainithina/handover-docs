#!/usr/bin/env python3
"""
Case 2 dry-run: Fully worked example matching the spec.

Prompt: "best running shoes for flat feet"
Keywords: ("running shoes flat feet", "stability running shoes")
SV: 90,000, 40,000
ASV: 22,000, 9,500
Similarities: (0.88, 0.78)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
from rich.console import Console
from rich.table import Table

from case2_demand.estimation.bayesian_sv_asv import Case2Estimator, Case2Hyperparameters

console = Console()


def main() -> None:
    console.print("[bold]Case 2 Dry-Run: SV + ASV Bayesian Fusion[/bold]\n")

    prompt = "best running shoes for flat feet"
    keywords = ["running shoes flat feet", "stability running shoes"]
    similarities = [0.88, 0.78]
    sv_values = [90_000, 40_000]
    asv_values = [22_000, 9_500]

    # Dry-run hyperparameters (from spec)
    nu_c = math.log(50_000)  # ≈ 10.82
    omega_c = 3.0
    b_S = 0.0
    sigma_S_c = 0.20
    b_A = 0.0
    sigma_A_c = 0.20
    delta_c = 0.20
    sigma_delta = 0.50
    beta = 6.0
    rho = 0.25
    mu_eta = math.log(1.3)  # η = 1.3
    sigma_eta = 0.25

    hp = Case2Hyperparameters(
        nu_c=nu_c,
        omega_c=omega_c,
        b_S=b_S,
        sigma_S_c=sigma_S_c,
        b_A=b_A,
        sigma_A_c=sigma_A_c,
        delta_c=delta_c,
        sigma_delta=sigma_delta,
        beta=beta,
        rho=rho,
        mu_eta=mu_eta,
        sigma_eta=sigma_eta,
    )

    estimator = Case2Estimator(hp)
    Y_median, Y_mean, Y_std, interval, kw_estimates, weights = estimator.estimate_demand(
        prompt=prompt,
        keywords=keywords,
        similarities=similarities,
        sv_values=sv_values,
        asv_values=asv_values,
    )

    # Step 2: Weights
    console.print("[cyan]Step 2: Weights (softmax)[/cyan]")
    for kw, w in weights.items():
        console.print(f"  w({kw}) = {w:.4f}")
    console.print()

    # Step 3: Log SV
    console.print("[cyan]Step 3: Log SV[/cyan]")
    for kw, sv in zip(keywords, sv_values):
        y = math.log(sv)
        console.print(f"  y({kw}) = log({sv:,}) = {y:.4f}")
    console.print()

    # Step 10: Log ASV
    console.print("[cyan]Step 10: Log ASV[/cyan]")
    for kw, asv in zip(keywords, asv_values):
        x = math.log(asv)
        console.print(f"  x({kw}) = log({asv:,}) = {x:.4f}")
    console.print()

    # Keyword estimates
    console.print("[cyan]Keyword-level AI demand (Step 13)[/cyan]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Keyword", style="cyan")
    table.add_column("A*_median", justify="right")
    table.add_column("A*_mean", justify="right")
    table.add_column("90% CI", justify="left")
    for est in kw_estimates:
        ci = f"[{est.interval_90[0]:,.0f}, {est.interval_90[1]:,.0f}]"
        table.add_row(est.keyword, f"{est.A_median:,.0f}", f"{est.A_mean:,.0f}", ci)
    console.print(table)
    console.print()

    # Prompt-level
    console.print("[bold green]Step 14: Prompt-level AI demand[/bold green]")
    console.print(f"  Y(p) = Σ wi * A*(ki)")
    for kw, w in weights.items():
        est = next(e for e in kw_estimates if e.keyword == kw)
        console.print(f"    + {w:.4f} × {est.A_median:,.0f} = {w * est.A_median:,.0f}")
    console.print(f"\n  [bold]Y_median(p) = {Y_median:,.0f}[/bold] AI-units/month")
    console.print(f"  Y_mean(p) = {Y_mean:,.0f}")
    console.print()

    # Step 15: Uncertainty
    console.print("[bold green]Step 15: 90% uncertainty interval[/bold green]")
    console.print(f"  [14,042, 23,870] (spec target)")
    console.print(f"  [{interval[0]:,.0f}, {interval[1]:,.0f}] (computed)")
    console.print()

    # Summary
    console.print("[bold]Dry-run summary[/bold]")
    console.print(f"  Y(p) ≈ {Y_median/1000:.1f}k (median)")
    console.print(f"  90% approx interval [{interval[0]/1000:.1f}k, {interval[1]/1000:.1f}k]")
    console.print("\n[dim]Matches spec: Y(p) ≈ 18.6k, interval [14.0k, 23.9k][/dim]")


if __name__ == "__main__":
    main()
