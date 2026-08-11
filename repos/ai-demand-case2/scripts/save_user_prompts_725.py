#!/usr/bin/env python3
"""Read prompts from stdin (one per line) and save + build JSON."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
TXT = PROJECT / "inputs" / "digit_user_batch_prompts.txt"
JSON_OUT = PROJECT / "inputs" / "digit_user_batch_prompts.json"
BUILD = PROJECT / "scripts" / "build_prompts_json_from_list.py"


def main() -> None:
    lines = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
    TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved {len(lines)} prompts -> {TXT}")
    subprocess.run(
        [sys.executable, str(BUILD), str(TXT), "-o", str(JSON_OUT)],
        check=True,
        cwd=PROJECT,
    )


if __name__ == "__main__":
    main()
