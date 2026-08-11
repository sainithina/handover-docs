#!/usr/bin/env python3
"""
Map extracted prompt keywords to client seed keywords (embedding cosine similarity).

Each **our** keyword string and each **client** keyword may appear in at most one output row
(global uniqueness). Assignment is greedy: candidates sorted by similarity (then importance),
first valid win.

Optional `lob` in the client TSV is not used for matching.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


def load_client_keywords(path: Path) -> list[str]:
    """One client keyword per row. Supports TSV with `keyword` (optional `lob` unused)."""
    keywords: list[str] = []
    with path.open(encoding="utf-8", newline="") as f:
        r = csv.DictReader(f, delimiter="\t")
        for row in r:
            kw = (row.get("keyword") or row.get("Keyword") or "").strip()
            if not kw:
                continue
            keywords.append(kw)
    if not keywords:
        raise ValueError(f"No client keywords in {path}")
    return keywords


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Map extractions to client keywords (unique our + client strings, greedy by sim)."
    )
    parser.add_argument("--run-dir", type=Path, required=True, help="Run dir with keyword_extractions.jsonl")
    parser.add_argument(
        "--client-tsv",
        type=Path,
        default=None,
        help="TSV with `keyword` column (default: <run-dir>/client_keywords_lob.tsv)",
    )
    parser.add_argument("--model", default="all-MiniLM-L6-v2", help="sentence-transformers model")
    parser.add_argument("--out", type=Path, default=None, help="Output CSV path")
    args = parser.parse_args()

    run_dir = args.run_dir.expanduser().resolve()
    ext_path = run_dir / "keyword_extractions.jsonl"
    if not ext_path.is_file():
        raise SystemExit(f"Missing {ext_path}")

    client_path = args.client_tsv or (run_dir / "client_keywords_lob.tsv")
    if not client_path.is_file():
        raise SystemExit(f"Missing client TSV: {client_path}")

    out_path = args.out or (run_dir / "prompt_client_keyword_mapping.csv")
    client_kws = load_client_keywords(client_path)

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(args.model)
    client_emb = model.encode(client_kws, normalize_embeddings=True, show_progress_bar=False)
    if not isinstance(client_emb, np.ndarray):
        client_emb = np.asarray(client_emb)

    # Parse extractions in file order
    ordered: list[dict] = []
    with ext_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            ordered.append(json.loads(line))

    candidates: list[tuple[float, float, int, str, str, str, str, str]] = []
    # sim, importance, orig_idx, pid, prompt, icn, our_kw, client_kw

    for orig_idx, row in enumerate(ordered):
        pid = row.get("prompt_id", "")
        prompt = row.get("prompt", "")
        icn = row.get("intent_cluster_name", "")
        kws = row.get("keywords") or []
        texts: list[str] = []
        scores: list[float] = []
        for kd in kws:
            if not isinstance(kd, dict):
                continue
            t = (kd.get("keyword") or "").strip()
            if not t:
                continue
            texts.append(t)
            try:
                scores.append(float(kd.get("importance_score", 0.0)))
            except (TypeError, ValueError):
                scores.append(0.0)
        if not texts:
            continue
        gen_emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        if not isinstance(gen_emb, np.ndarray):
            gen_emb = np.asarray(gen_emb)
        sims = gen_emb @ client_emb.T
        for gi, our_kw in enumerate(texts):
            imp = scores[gi] if gi < len(scores) else 0.0
            for ci, client_kw in enumerate(client_kws):
                sim = float(sims[gi, ci])
                candidates.append((sim, imp, orig_idx, pid, prompt, icn, our_kw, client_kw))

    # Greedy: best similarity first; tie-break higher importance; earlier prompt index as last tie
    candidates.sort(key=lambda t: (-t[0], -t[1], t[2]))

    used_our: set[str] = set()
    used_client: set[str] = set()
    assigned: dict[str, dict] = {}

    for sim, imp_score, orig_idx, pid, prompt, icn, our_kw, client_kw in candidates:
        if pid in assigned:
            continue
        if our_kw in used_our:
            continue
        if client_kw in used_client:
            continue
        assigned[pid] = {
            "prompt_id": pid,
            "intent_cluster_name": icn,
            "prompt": prompt,
            "our_keyword": our_kw,
            "client_keyword": client_kw,
            "prompt_with_client_keyword": f"{prompt} || {client_kw}",
            "importance_score": f"{imp_score:.6f}",
            "cosine_similarity": f"{sim:.6f}",
        }
        used_our.add(our_kw)
        used_client.add(client_kw)

    empty_row = {
        "prompt_id": "",
        "intent_cluster_name": "",
        "prompt": "",
        "our_keyword": "",
        "client_keyword": "",
        "prompt_with_client_keyword": "",
        "importance_score": "",
        "cosine_similarity": "",
    }

    rows_out: list[dict] = []
    for row in ordered:
        pid = row.get("prompt_id", "")
        if pid in assigned:
            rows_out.append(assigned[pid])
        else:
            rows_out.append({
                **empty_row,
                "prompt_id": pid,
                "intent_cluster_name": row.get("intent_cluster_name", ""),
                "prompt": row.get("prompt", ""),
            })

    fieldnames = [
        "prompt_id",
        "intent_cluster_name",
        "prompt",
        "our_keyword",
        "client_keyword",
        "prompt_with_client_keyword",
        "importance_score",
        "cosine_similarity",
    ]

    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)

    n_ok = sum(1 for r in rows_out if r.get("our_keyword"))
    print(f"Wrote {len(rows_out)} rows -> {out_path} ({n_ok} matched, {len(rows_out) - n_ok} unmatched)")


if __name__ == "__main__":
    main()
