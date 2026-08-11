"""I/O utilities."""

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple, Union

JsonLike = Union[Dict[str, Any], Any]


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj: JsonLike) -> None:
    ensure_parent_dir(path)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def export_prompt_estimates_to_csv(rows: list[Dict[str, Any]], out_path: Path) -> None:
    """Export prompt estimates to CSV, grouped by intent cluster, with cluster totals."""
    from itertools import groupby

    sorted_rows = sorted(
        rows,
        key=lambda r: (
            r.get("intent_cluster_name") or "",
            r.get("prompt") or "",
        ),
    )

    fieldnames = [
        "intent_cluster_name",
        "intent_cluster_id",
        "prompt_id",
        "prompt",
        "ai_demand_median",
        "ai_demand_mean",
        "ai_demand_std",
        "interval_90_low",
        "interval_90_high",
    ]

    ensure_parent_dir(out_path)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in sorted_rows:
            interval = r.get("interval_90") or [None, None]
            writer.writerow({
                "intent_cluster_name": r.get("intent_cluster_name", ""),
                "intent_cluster_id": r.get("intent_cluster_id", ""),
                "prompt_id": r.get("prompt_id", ""),
                "prompt": r.get("prompt", ""),
                "ai_demand_median": round(r.get("Y_median", 0), 2),
                "ai_demand_mean": round(r.get("Y_mean", 0), 2),
                "ai_demand_std": round(r.get("Y_std", 0), 2),
                "interval_90_low": round(interval[0], 2) if interval[0] is not None else "",
                "interval_90_high": round(interval[1], 2) if interval[1] is not None else "",
            })

    # Append cluster totals
    def _cluster_key(r: dict) -> str:
        return r.get("intent_cluster_name") or ""

    grouped = groupby(sorted_rows, key=_cluster_key)
    summary_rows = []
    for cluster_name, group in grouped:
        group_list = list(group)
        total_median = sum(r.get("Y_median", 0) for r in group_list)
        total_mean = sum(r.get("Y_mean", 0) for r in group_list)
        n_prompts = len(group_list)
        summary_rows.append({
            "intent_cluster_name": cluster_name or "[Unknown]",
            "intent_cluster_id": group_list[0].get("intent_cluster_id", "") if group_list else "",
            "prompt_id": "",
            "prompt": f"[CLUSTER TOTAL: {n_prompts} prompts]",
            "ai_demand_median": round(total_median, 2),
            "ai_demand_mean": round(total_mean, 2),
            "ai_demand_std": "",
            "interval_90_low": "",
            "interval_90_high": "",
        })

    if summary_rows:
        with out_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow({k: "" for k in fieldnames})
            for r in summary_rows:
                writer.writerow(r)


def export_keyword_volumes_to_csv(
    *,
    keyword_to_sv: Dict[str, float],
    keyword_to_asv: Dict[str, float],
    out_path: Path,
    sv_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    location_code: Optional[int] = None,
    language_code: Optional[str] = None,
) -> None:
    """Export one row per keyword with classic SV and AI ASV (same values as sv_data / asv_data jsonl)."""
    all_kw = sorted(set(keyword_to_sv) | set(keyword_to_asv))
    fieldnames = [
        "keyword",
        "sv",
        "asv",
        "cpc",
        "competition",
        "location_code",
        "language_code",
    ]
    ensure_parent_dir(out_path)
    meta = sv_metadata or {}
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for kw in all_kw:
            m = meta.get(kw) or {}
            cpc = m.get("cpc")
            comp = m.get("competition")
            cpc_cell = ""
            if cpc is not None:
                try:
                    cpc_cell = round(float(cpc), 4)
                except (TypeError, ValueError):
                    cpc_cell = str(cpc)
            comp_cell = ""
            if comp is not None:
                try:
                    comp_cell = round(float(comp), 6)
                except (TypeError, ValueError):
                    comp_cell = str(comp)
            writer.writerow({
                "keyword": kw,
                "sv": round(float(keyword_to_sv.get(kw, 0.0)), 2),
                "asv": round(float(keyword_to_asv.get(kw, 0.0)), 2),
                "cpc": cpc_cell,
                "competition": comp_cell,
                "location_code": location_code if location_code is not None else "",
                "language_code": language_code if language_code is not None else "",
            })


def importance_by_prompt_keyword_from_extractions(
    extractions: Iterable[Dict[str, Any]],
) -> Dict[Tuple[str, str], float]:
    """Map (prompt_id, keyword) -> importance_score from keyword_extractions rows."""
    out: Dict[Tuple[str, str], float] = {}
    for ext in extractions:
        pid = ext.get("prompt_id", "")
        for kw in ext.get("keywords") or []:
            if isinstance(kw, dict):
                keyword = kw.get("keyword", "")
                score = kw.get("importance_score")
            else:
                keyword = getattr(kw, "keyword", "")
                score = getattr(kw, "importance_score", None)
            if keyword and score is not None:
                out[(pid, keyword)] = float(score)
    return out


def export_prompt_keyword_volumes_to_csv(
    prompt_rows: list[Dict[str, Any]],
    *,
    keyword_to_sv: Dict[str, float],
    keyword_to_asv: Dict[str, float],
    importance_by_prompt_keyword: Optional[Dict[tuple[str, str], float]] = None,
    out_path: Path,
) -> int:
    """Export one row per (prompt, keyword) with raw SV/ASV and fused keyword-level AI demand."""
    fieldnames = [
        "intent_cluster_name",
        "intent_cluster_id",
        "prompt_id",
        "prompt",
        "prompt_ai_demand_median",
        "prompt_ai_demand_mean",
        "prompt_ai_demand_linear_median",
        "prompt_ai_demand_linear_mean",
        "keyword",
        "importance_score",
        "fusion_weight",
        "sv",
        "asv",
        "keyword_ai_demand_median",
        "keyword_ai_demand_mean",
        "keyword_ai_demand_std",
        "keyword_interval_90_low",
        "keyword_interval_90_high",
        "cpc",
        "competition",
    ]
    imp_lookup = importance_by_prompt_keyword or {}
    out_rows: list[Dict[str, Any]] = []

    for pr in prompt_rows:
        prompt_id = pr.get("prompt_id", "")
        weights = pr.get("weights") or {}
        keyword_estimates = pr.get("keyword_estimates") or []
        kept_estimates = [
            ke for ke in keyword_estimates if (ke.get("keyword") or "").strip()
        ]

        linear_median = sum(float(ke.get("A_median", 0) or 0) for ke in kept_estimates)
        linear_mean = sum(float(ke.get("A_mean", 0) or 0) for ke in kept_estimates)
        linear_median_r = round(linear_median, 2)
        linear_mean_r = round(linear_mean, 2)

        for ke in kept_estimates:
            kw = ke.get("keyword", "")
            interval = ke.get("interval_90") or [None, None]
            variance = ke.get("variance")
            std_cell = ""
            if variance is not None:
                try:
                    std_cell = round(float(variance) ** 0.5, 4)
                except (TypeError, ValueError):
                    std_cell = ""
            imp = imp_lookup.get((prompt_id, kw))
            out_rows.append({
                "intent_cluster_name": pr.get("intent_cluster_name", ""),
                "intent_cluster_id": pr.get("intent_cluster_id", ""),
                "prompt_id": prompt_id,
                "prompt": pr.get("prompt", ""),
                "prompt_ai_demand_median": round(float(pr.get("Y_median", 0)), 2),
                "prompt_ai_demand_mean": round(float(pr.get("Y_mean", 0)), 2),
                "prompt_ai_demand_linear_median": linear_median_r,
                "prompt_ai_demand_linear_mean": linear_mean_r,
                "keyword": kw,
                "importance_score": round(float(imp), 4) if imp is not None else "",
                "fusion_weight": round(float(weights.get(kw, 0)), 6),
                "sv": round(float(keyword_to_sv.get(kw, 0.0)), 2),
                "asv": round(float(keyword_to_asv.get(kw, 0.0)), 2),
                "keyword_ai_demand_median": round(float(ke.get("A_median", 0)), 2),
                "keyword_ai_demand_mean": round(float(ke.get("A_mean", 0)), 2),
                "keyword_ai_demand_std": std_cell,
                "keyword_interval_90_low": round(interval[0], 2) if interval[0] is not None else "",
                "keyword_interval_90_high": round(interval[1], 2) if interval[1] is not None else "",
                "cpc": ke.get("cpc") if ke.get("cpc") is not None else "",
                "competition": ke.get("competition") if ke.get("competition") is not None else "",
            })

    out_rows.sort(
        key=lambda r: (
            r.get("intent_cluster_name") or "",
            r.get("prompt") or "",
            -(float(r.get("keyword_ai_demand_median") or 0)),
        ),
    )

    ensure_parent_dir(out_path)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)
    return len(out_rows)


def merge_funnel_segment_into_prompt_keyword_volumes_csv(
    csv_path: Path,
    funnel_by_prompt: Dict[str, str],
) -> None:
    """Add funnel_segment column from prompt text -> segment map."""
    if not csv_path.exists() or not funnel_by_prompt:
        return
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8", newline="")))
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    if "funnel_segment" not in fieldnames:
        fieldnames.insert(2, "funnel_segment")
    for r in rows:
        r["funnel_segment"] = funnel_by_prompt.get((r.get("prompt") or "").strip(), "")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_prompt_keyword_volumes_for_run(
    *,
    prompt_rows: List[Dict[str, Any]],
    extractions: List[Dict[str, Any]],
    keyword_to_sv: Dict[str, float],
    keyword_to_asv: Dict[str, float],
    run_dir: Path,
    filename: str = "prompt_keyword_volumes.csv",
) -> int:
    """Write prompt_keyword_volumes.csv under run_dir (default pipeline output)."""
    importance = importance_by_prompt_keyword_from_extractions(extractions)
    out_path = run_dir / filename
    n = export_prompt_keyword_volumes_to_csv(
        prompt_rows,
        keyword_to_sv=keyword_to_sv,
        keyword_to_asv=keyword_to_asv,
        importance_by_prompt_keyword=importance,
        out_path=out_path,
    )
    funnel_path = run_dir / "funnel_segment_by_prompt.json"
    if funnel_path.exists():
        funnel = json.loads(funnel_path.read_text(encoding="utf-8"))
        merge_funnel_segment_into_prompt_keyword_volumes_csv(out_path, funnel)
    return n
