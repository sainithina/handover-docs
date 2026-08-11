#!/usr/bin/env python3
"""
Print aggregated SV and ASV for specific keywords (last 2 months) from historical_sv_asv.json.

Usage:
  # Top N keywords by SV and ASV (from sv_data.jsonl, asv_data.jsonl)
  python scripts/keyword_volume_agg.py top --run 20260309T164455Z --n 13

  # Default: use explicit_keywords from Tina Davies company profile
  python scripts/keyword_volume_agg.py --run 20260309T164455Z

  # Custom company profile for explicit_keywords
  python scripts/keyword_volume_agg.py --run 20260309T164455Z --company-profile examples/tina_davies_company_profile.json

  # Override with explicit keywords
  python scripts/keyword_volume_agg.py --run 20260309T164455Z --keywords "permanent makeup" "pmu pigments"

  # Keywords from file (one per line)
  python scripts/keyword_volume_agg.py --run 20260309T164455Z --keywords-file keywords.txt

  # All keywords (no filter)
  python scripts/keyword_volume_agg.py --run 20260309T164455Z --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _runs_dir(project_root: Path) -> Path:
    return (project_root / "runs").resolve()


def _fmt_vol(v: float) -> str:
    """Format volume as 15k, 2k, 1.5M, etc."""
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1000:
        return f"{round(v / 1000)}k"
    return f"{v:,.0f}"


def _resolve_historical_path(run_id: str | None, historical_file: Path | None, project_root: Path) -> Path:
    if historical_file is not None:
        p = Path(historical_file).expanduser().resolve()
        if not p.exists():
            print(f"Error: File not found: {p}", file=sys.stderr)
            sys.exit(1)
        return p
    if run_id:
        runs = _runs_dir(project_root)
        path = runs / run_id / "historical_sv_asv.json"
        if not path.exists():
            print(f"Error: historical_sv_asv.json not found in {path}", file=sys.stderr)
            sys.exit(1)
        return path
    print("Error: Provide --run or --historical-file", file=sys.stderr)
    sys.exit(1)


def _load_keywords(
    keywords: list[str] | None,
    keywords_file: Path | None,
    company_profile: Path | None,
    project_root: Path,
) -> list[str] | None:
    """Return list of keywords to filter, or None for all."""
    if keywords_file is not None:
        lines = keywords_file.read_text(encoding="utf-8").strip().splitlines()
        return [ln.strip() for ln in lines if ln.strip()]
    if keywords:
        return keywords
    if company_profile is not None:
        path = Path(company_profile).expanduser().resolve()
        if not path.is_absolute():
            path = (project_root / path).resolve()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            explicit = data.get("explicit_keywords", [])
            if explicit:
                return explicit
    return None


def _run_top(run_id: str, n: int, project_root: Path, runs_dir: Path) -> None:
    """Print top N keywords by SV and ASV from sv_data.jsonl and asv_data.jsonl."""
    run_dir = runs_dir / run_id
    sv_path = run_dir / "sv_data.jsonl"
    asv_path = run_dir / "asv_data.jsonl"
    if not sv_path.exists():
        print(f"Error: {sv_path} not found", file=sys.stderr)
        sys.exit(1)
    if not asv_path.exists():
        print(f"Error: {asv_path} not found", file=sys.stderr)
        sys.exit(1)

    sv_rows = []
    for line in sv_path.read_text().strip().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        sv_rows.append((r["keyword"], float(r.get("search_volume", 0))))
    asv_rows = []
    for line in asv_path.read_text().strip().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        asv_rows.append((r["keyword"], float(r.get("search_volume", 0))))

    sv_rows.sort(key=lambda x: -x[1])
    asv_rows.sort(key=lambda x: -x[1])

    col_w = max(20, max(len(kw) for kw, _ in sv_rows[:n] + asv_rows[:n]) + 2)
    print(f"\nTop {n} SV (search volume):")
    print("-" * (col_w + 12))
    for i, (kw, vol) in enumerate(sv_rows[:n], 1):
        print(f"{i:2}. {kw:<{col_w}} {_fmt_vol(vol):>8}")
    print(f"\nTop {n} ASV (AI search volume):")
    print("-" * (col_w + 12))
    for i, (kw, vol) in enumerate(asv_rows[:n], 1):
        print(f"{i:2}. {kw:<{col_w}} {_fmt_vol(vol):>8}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print aggregated SV and ASV for specific keywords (last 2 months)"
    )
    parser.add_argument("--run", type=str, help="Run ID (e.g. 20260309T164455Z)")
    parser.add_argument("--historical-file", type=Path, help="Path to historical_sv_asv.json")
    parser.add_argument(
        "--company-profile",
        type=Path,
        default=Path("examples/tina_davies_company_profile.json"),
        help="Company profile JSON with explicit_keywords (default: examples/tina_davies_company_profile.json)",
    )
    parser.add_argument("--keywords", nargs="+", help="Keywords to query (overrides company profile)")
    parser.add_argument("--keywords-file", type=Path, help="File with one keyword per line")
    parser.add_argument("--all", action="store_true", help="Show all keywords (no filter)")
    parser.add_argument("--n-months", type=int, default=2, help="Number of months to aggregate (default: 2)")
    parser.add_argument("--runs-dir", type=Path, default=None, help="Runs directory (default: ./runs)")
    parser.add_argument("--n", type=int, default=13, help="For 'top': number of keywords (default: 13)")
    sub = parser.add_subparsers(dest="cmd", help="Commands")
    top_parser = sub.add_parser("top", help="Top N keywords by SV and ASV")
    top_parser.add_argument("--run", type=str, required=True, help="Run ID")
    top_parser.add_argument("--n", type=int, default=13, help="Number of keywords (default: 13)")
    top_parser.add_argument("--runs-dir", type=Path, default=None, help="Runs directory")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    if args.runs_dir:
        runs_dir = Path(args.runs_dir).expanduser().resolve()
    else:
        runs_dir = _runs_dir(project_root)

    if getattr(args, "cmd", None) == "top":
        _run_top(
            run_id=getattr(args, "run") or args.run,
            n=getattr(args, "n", 13),
            project_root=project_root,
            runs_dir=runs_dir,
        )
        return

    path = _resolve_historical_path(args.run, args.historical_file, project_root)
    data = json.loads(path.read_text(encoding="utf-8"))

    keywords_list = data.get("keywords", [])
    historical_sv = data.get("historical_sv", [])
    historical_asv = data.get("historical_asv", [])
    periods_sv = data.get("periods_sv", [])
    periods_asv = data.get("periods_asv", [])

    if len(historical_sv) != len(keywords_list) or len(historical_asv) != len(keywords_list):
        print("Error: keywords and historical arrays length mismatch", file=sys.stderr)
        sys.exit(1)

    filter_kw = None
    if args.all:
        filter_kw = None  # Show all
    else:
        filter_kw = _load_keywords(
            args.keywords,
            args.keywords_file,
            args.company_profile,
            project_root,
        )
        if not filter_kw:
            print("Error: Provide --keywords, --keywords-file, --all, or ensure company profile has explicit_keywords", file=sys.stderr)
            sys.exit(1)

    n_months = max(1, args.n_months)
    kw_to_idx = {kw: i for i, kw in enumerate(keywords_list)}
    kw_lower_to_canonical = {kw.lower(): (kw, i) for kw, i in zip(keywords_list, range(len(keywords_list)))}

    if filter_kw:
        indices = []
        for kw in filter_kw:
            if kw in kw_to_idx:
                indices.append((kw, kw_to_idx[kw]))
            elif kw.lower() in kw_lower_to_canonical:
                canonical, idx = kw_lower_to_canonical[kw.lower()]
                indices.append((canonical, idx))
            else:
                print(f"[warn] Keyword not found: {kw!r}", file=sys.stderr)
    else:
        indices = [(kw, i) for i, kw in enumerate(keywords_list)]

    if not indices:
        print("No matching keywords.", file=sys.stderr)
        sys.exit(1)

    # Last N months = last N values in each array
    col_w = max(14, max(len(kw) for kw, _ in indices) + 2)
    print(f"\n{'Keyword':<{col_w}} {'SV (sum)':>10} {'SV (avg)':>10} {'ASV (sum)':>10} {'ASV (avg)':>10}")
    print("-" * (col_w + 44))

    total_sv_sum = 0.0
    total_asv_sum = 0.0
    n_with_data = 0

    for kw, idx in indices:
        sv_vals = historical_sv[idx] if idx < len(historical_sv) else []
        asv_vals = historical_asv[idx] if idx < len(historical_asv) else []

        sv_last = sv_vals[-n_months:] if sv_vals else []
        asv_last = asv_vals[-n_months:] if asv_vals else []

        sv_sum = sum(sv_last)
        sv_avg = sv_sum / len(sv_last) if sv_last else 0.0
        asv_sum = sum(asv_last)
        asv_avg = asv_sum / len(asv_last) if asv_last else 0.0

        total_sv_sum += sv_sum
        total_asv_sum += asv_sum
        if sv_last or asv_last:
            n_with_data += 1

        print(f"{kw:<{col_w}} {_fmt_vol(sv_sum):>10} {_fmt_vol(sv_avg):>10} {_fmt_vol(asv_sum):>10} {_fmt_vol(asv_avg):>10}")

    print("-" * (col_w + 44))
    print(f"{'TOTAL':<{col_w}} {_fmt_vol(total_sv_sum):>10} {'':>10} {_fmt_vol(total_asv_sum):>10} {'':>10}")

    if periods_sv or periods_asv:
        periods = periods_sv or periods_asv
        last_n = periods[-n_months:] if len(periods) >= n_months else periods
        period_str = ", ".join(f"{p.get('year', '?')}-{p.get('month', '?'):02d}" for p in last_n)
        print(f"\nPeriods (last {n_months} months): {period_str}")


if __name__ == "__main__":
    main()
