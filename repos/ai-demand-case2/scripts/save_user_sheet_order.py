#!/usr/bin/env python3
"""Save prompt order from a text file (one prompt per line; skip header 'Prompt')."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
OUT = PROJECT / "inputs" / "digit_user_sheet_order_may21.txt"


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if src and src.exists():
        text = src.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    lines = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if ln.lower() == "prompt":
            continue
        if ln.startswith(", create"):
            break
        lines.append(ln)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved {len(lines)} -> {OUT}")


if __name__ == "__main__":
    main()
