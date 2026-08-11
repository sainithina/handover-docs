#!/usr/bin/env python3
"""
Confidence interval overlap analysis for Case 2 prompt volume estimates.

Per-intent overlap across runs: for each intent cluster, compute overlap% between
90% CIs from runs with different n_prompts_per_intent (10, 50, 100).

Formula: overlap% = 100 * overlap_size / (size1 + size2 - overlap_size)

Usage:
  # Compare two runs (any pair of 10, 50, 100 prompts per intent)
  python scripts/overlap_analysis.py compare --run-a RUN_ID_A --run-b RUN_ID_B [--label-a 10] [--label-b 50]

  # Analyze 3 runs (10, 50, 100 prompts) - full pairwise matrix
  python scripts/overlap_analysis.py analyze --run-10 RUN_ID_10 --run-50 RUN_ID_50 --run-100 RUN_ID_100

  # Prepare runs with same intents, then analyze
  python scripts/overlap_analysis.py prepare-and-analyze --company-profile path/to/profile.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def _runs_dir(runs_dir: Path | None = None) -> Path:
    """Resolve runs directory (same as case2 config)."""
    if runs_dir is not None:
        return Path(runs_dir).expanduser().resolve()
    project_root = Path(__file__).resolve().parent.parent
    return (project_root / "runs").resolve()


def _compute_overlap_pct(interval1: list[float], interval2: list[float]) -> float:
    """
    Compute overlap% between two intervals.
    overlap% = 100 * overlap_size / (size1 + size2 - overlap_size)
    """
    lo1, hi1 = interval1[0], interval1[1]
    lo2, hi2 = interval2[0], interval2[1]
    size1 = hi1 - lo1
    size2 = hi2 - lo2
    overlap_lo = max(lo1, lo2)
    overlap_hi = min(hi1, hi2)
    overlap_size = max(0.0, overlap_hi - overlap_lo)
    denom = size1 + size2 - overlap_size
    if denom <= 0:
        return 100.0 if overlap_size > 0 else 0.0
    return 100.0 * overlap_size / denom


def _load_intent_estimates(run_dir: Path) -> list[dict]:
    """Load intent cluster estimates from a run."""
    path = run_dir / "intent_cluster_estimates.json"
    if not path.exists():
        path = run_dir / "metrics.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("intent_cluster_estimates", [])
        raise FileNotFoundError(f"No intent_cluster_estimates or metrics in {run_dir}")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_run_path(run_id_or_path: str, runs_dir: Path) -> Path:
    """Resolve run ID or absolute path to run directory."""
    p = Path(run_id_or_path).expanduser()
    if p.is_absolute() and p.exists():
        return p.resolve()
    return (runs_dir / run_id_or_path).resolve()


def _run_compare_two(
    run_a: str,
    run_b: str,
    label_a: str,
    label_b: str,
    runs_dir: Path | None,
) -> None:
    """Compare two runs: overlap% per intent cluster."""
    base = _runs_dir(runs_dir)
    dir_a = _resolve_run_path(run_a, base)
    dir_b = _resolve_run_path(run_b, base)

    for d, name in [(dir_a, label_a), (dir_b, label_b)]:
        if not d.exists():
            print(f"Error: Run dir not found: {d}", file=sys.stderr)
            sys.exit(1)

    est_a = {e["intent_cluster_id"]: e for e in _load_intent_estimates(dir_a)}
    est_b = {e["intent_cluster_id"]: e for e in _load_intent_estimates(dir_b)}

    common_intents = set(est_a) & set(est_b)
    if not common_intents:
        print("No intent clusters common to both runs.", file=sys.stderr)
        sys.exit(1)

    results = []
    for iid in sorted(common_intents):
        ea, eb = est_a[iid], est_b[iid]
        name = ea.get("intent_cluster_name", iid)
        n_a = ea.get("num_prompts", "?")
        n_b = eb.get("num_prompts", "?")
        ov = _compute_overlap_pct(ea["interval_90"], eb["interval_90"])
        results.append({
            "intent_cluster_id": iid,
            "intent_cluster_name": name,
            "num_prompts_a": n_a,
            "num_prompts_b": n_b,
            "overlap_pct": round(ov, 2),
        })

    col = max(40, max(len(r["intent_cluster_name"] or r["intent_cluster_id"]) for r in results) + 2)
    print("\n" + "=" * (col + 20))
    print("Per-Intent Confidence Interval Overlap Analysis (Case 2)")
    print("=" * (col + 20))
    print(f"Run A: {run_a} ({label_a} prompts/intent, {len(est_a)} intents)")
    print(f"Run B: {run_b} ({label_b} prompts/intent, {len(est_b)} intents)")
    print(f"\nFormula: overlap% = 100 * overlap_size / (size1 + size2 - overlap_size)\n")
    print(f"{'Intent':<{col}} {'Overlap %':>10}")
    print("-" * (col + 12))
    for r in results:
        name = (r["intent_cluster_name"] or r["intent_cluster_id"])[: col - 2]
        print(f"{name:<{col}} {r['overlap_pct']:>9.1f}%")
    print("-" * (col + 12))
    avg_ov = sum(r["overlap_pct"] for r in results) / len(results)
    print(f"{'Overall mean':<{col}} {avg_ov:>9.1f}%")

    out_path = base / f"overlap_{label_a}_vs_{label_b}.json"
    out_path.write_text(json.dumps({
        "run_a": run_a,
        "run_b": run_b,
        "label_a": label_a,
        "label_b": label_b,
        "per_intent": results,
        "overall_mean_overlap_pct": round(avg_ov, 2),
    }, indent=2))
    print(f"\nSaved: {out_path}")


def _run_analyze(run_10: str, run_50: str, run_100: str, runs_dir: Path | None) -> None:
    """Analyze overlap% per intent across the 3 runs (10, 50, 100 prompts)."""
    base = _runs_dir(runs_dir)
    dir_10 = _resolve_run_path(run_10, base)
    dir_50 = _resolve_run_path(run_50, base)
    dir_100 = _resolve_run_path(run_100, base)

    for d, name in [(dir_10, "10"), (dir_50, "50"), (dir_100, "100")]:
        if not d.exists():
            print(f"Error: Run dir not found: {d}", file=sys.stderr)
            sys.exit(1)

    est_10 = {e["intent_cluster_id"]: e for e in _load_intent_estimates(dir_10)}
    est_50 = {e["intent_cluster_id"]: e for e in _load_intent_estimates(dir_50)}
    est_100 = {e["intent_cluster_id"]: e for e in _load_intent_estimates(dir_100)}

    common_intents = set(est_10) & set(est_50) & set(est_100)
    if not common_intents:
        print("No intent clusters common to all 3 runs.", file=sys.stderr)
        sys.exit(1)

    results = []
    for iid in sorted(common_intents):
        e10, e50, e100 = est_10[iid], est_50[iid], est_100[iid]
        name = e10.get("intent_cluster_name", iid)

        ov_10_50 = _compute_overlap_pct(e10["interval_90"], e50["interval_90"])
        ov_10_100 = _compute_overlap_pct(e10["interval_90"], e100["interval_90"])
        ov_50_100 = _compute_overlap_pct(e50["interval_90"], e100["interval_90"])
        mean_ov = (ov_10_50 + ov_10_100 + ov_50_100) / 3

        results.append({
            "intent_cluster_id": iid,
            "intent_cluster_name": name,
            "overlap_10_50_pct": round(ov_10_50, 2),
            "overlap_10_100_pct": round(ov_10_100, 2),
            "overlap_50_100_pct": round(ov_50_100, 2),
            "mean_overlap_pct": round(mean_ov, 2),
        })

    # Print report
    print("\n## Per-Intent Confidence Interval Overlap Analysis (Case 2)", "=" * 60)
    print(f"Runs: {run_10} (10 prompts), {run_50} (50 prompts), {run_100} (100 prompts)\n")
    print(f"{'Intent':<40} {'10↔50':>8} {'10↔100':>8} {'50↔100':>8} {'Mean':>8}")
    print("-" * 76)
    for r in results:
        name = (r["intent_cluster_name"] or r["intent_cluster_id"])[:38]
        print(f"{name:<40} {r['overlap_10_50_pct']:>7.1f}% {r['overlap_10_100_pct']:>7.1f}% {r['overlap_50_100_pct']:>7.1f}% {r['mean_overlap_pct']:>7.1f}%")
    print("-" * 76)
    avg_mean = sum(r["mean_overlap_pct"] for r in results) / len(results)
    print(f"{'Overall mean':<40} {'':>8} {'':>8} {'':>8} {avg_mean:>7.1f}%")

    # Save JSON
    out_path = base / "overlap_analysis.json"
    out_path.write_text(json.dumps({"runs": {"10": run_10, "50": run_50, "100": run_100}, "per_intent": results}, indent=2))
    print(f"\nSaved: {out_path}")


def _run_prepare_and_analyze(company_profile: Path, runs_dir: Path | None, dry_run: bool = False) -> None:
    """
    Prepare 3 runs with same intents (10, 50, 100 prompts) then run overlap analysis.
    """
    base = _runs_dir(runs_dir)
    project_root = Path(__file__).resolve().parent.parent

    # Step 1: Generate intents (creates base run)
    print("Step 1: Generating intent clusters...")
    result = subprocess.run(
        [sys.executable, "-m", "case2_demand.cli", "generate-intents", "--company-profile", str(company_profile)],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    # Get the run_id from the most recent run with intent_cluster_plan (exclude overlap_*)
    run_dirs = [
        p for p in base.iterdir()
        if p.is_dir() and not p.name.startswith("overlap_") and (p / "intent_cluster_plan.json").exists()
    ]
    run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if not run_dirs:
        print("No run dir with intent_cluster_plan found.", file=sys.stderr)
        sys.exit(1)
    base_run_id = run_dirs[0].name
    base_dir = base / base_run_id

    if not (base_dir / "intent_cluster_plan.json").exists():
        print("intent_cluster_plan.json not found.", file=sys.stderr)
        sys.exit(1)

    # Step 2: Create 3 run dirs with same intent plan
    run_ids = {}
    for n in [10, 50, 100]:
        run_id = f"overlap_{n}"
        run_dir = base / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(base_dir / "intent_cluster_plan.json", run_dir / "intent_cluster_plan.json")
        shutil.copy(base_dir / "company_profile.json", run_dir / "company_profile.json")
        run_ids[n] = run_id

    # Step 3: For each n, run generate-prompts with n, then run-all --from-run
    for n in [10, 50, 100]:
        run_id = run_ids[n]
        print(f"\nStep 2.{n}: Running pipeline with {n} prompts per intent...")
        env = {"CASE2_RUN_ID": run_id, **__import__("os").environ}
        # generate-prompts
        r1 = subprocess.run(
            [sys.executable, "-m", "case2_demand.cli", "generate-prompts", "--n-prompts-per-intent", str(n)],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
        )
        if r1.returncode != 0:
            print(r1.stderr, file=sys.stderr)
            sys.exit(1)
        # run-all --from-run
        cmd = [sys.executable, "-m", "case2_demand.cli", "run-all", "--from-run", run_id]
        if not dry_run:
            cmd.append("--with-calibration")
        if dry_run:
            cmd.append("--dry-run")
        r2 = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)
        if r2.returncode != 0:
            print(r2.stderr, file=sys.stderr)
            sys.exit(1)

    # Step 4: Analyze
    print("\nStep 3: Running overlap analysis...")
    _run_analyze(run_ids[10], run_ids[50], run_ids[100], base)


def main() -> None:
    parser = argparse.ArgumentParser(description="CI overlap analysis for Case 2 prompt volume estimates")
    sub = parser.add_subparsers(dest="cmd", required=True)

    compare = sub.add_parser("compare", help="Compare two runs: overlap%% per intent")
    compare.add_argument("--run-a", required=True, help="Run ID or path (e.g. 20260309T120615Z or runs/20260309T120615Z)")
    compare.add_argument("--run-b", required=True, help="Run ID or path")
    compare.add_argument("--label-a", default="A", help="Label for run A (e.g. 10 for 10 prompts/intent)")
    compare.add_argument("--label-b", default="B", help="Label for run B (e.g. 50 for 50 prompts/intent)")
    compare.add_argument("--runs-dir", type=Path, default=None, help="Runs directory (default: ./runs)")

    analyze = sub.add_parser("analyze", help="Analyze overlap from 3 existing runs (10, 50, 100 prompts)")
    analyze.add_argument("--run-10", required=True, help="Run ID with 10 prompts per intent")
    analyze.add_argument("--run-50", required=True, help="Run ID with 50 prompts per intent")
    analyze.add_argument("--run-100", required=True, help="Run ID with 100 prompts per intent")
    analyze.add_argument("--runs-dir", type=Path, default=None, help="Runs directory (default: ./runs)")

    prep = sub.add_parser("prepare-and-analyze", help="Prepare 3 runs with same intents, then analyze")
    prep.add_argument("--company-profile", type=Path, required=True, help="Company profile JSON")
    prep.add_argument("--runs-dir", type=Path, default=None, help="Runs directory (default: ./runs)")
    prep.add_argument("--dry-run", action="store_true", help="Use placeholder SV/ASV (no DataForSEO)")

    args = parser.parse_args()

    if args.cmd == "compare":
        _run_compare_two(
            args.run_a,
            args.run_b,
            getattr(args, "label_a", "A"),
            getattr(args, "label_b", "B"),
            getattr(args, "runs_dir", None),
        )
    elif args.cmd == "analyze":
        _run_analyze(args.run_10, args.run_50, args.run_100, getattr(args, "runs_dir", None))
    elif args.cmd == "prepare-and-analyze":
        _run_prepare_and_analyze(args.company_profile, args.runs_dir, dry_run=getattr(args, "dry_run", False))


if __name__ == "__main__":
    main()
