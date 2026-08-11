#!/usr/bin/env python3
"""Run prompt volume estimation for GEO prompts (one-off)."""
import asyncio
import sys
from pathlib import Path

# Load .env from project root (before imports that use env vars)
project_root = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass

# Add src to path
src = project_root / "src"
sys.path.insert(0, str(src))

from case2_demand.cli import run_pipeline

PROMPTS_FILE = Path(__file__).resolve().parent.parent / "examples" / "geo_prompts.txt"
CALIBRATED = Path(__file__).resolve().parent.parent / "runs" / "20260305T174756Z" / "calibrated.json"


async def main():
    prompts = [p.strip() for p in PROMPTS_FILE.read_text().strip().split("\n") if p.strip()]
    prompt_items = [{"prompt": p, "prompt_id": f"prm_{i}"} for i, p in enumerate(prompts)]
    dry_run = "--dry-run" in sys.argv
    use_llm = "--llm" in sys.argv or "--keyword-extraction" in sys.argv and "llm" in sys.argv
    print(f"Running estimation for {len(prompt_items)} prompts (keyword extraction: {'llm' if use_llm else 'ngram'})...")
    await run_pipeline(
        prompt_items=prompt_items,
        location_code=2840,
        language_code="en",
        dry_run=dry_run,
        calibrated_from=CALIBRATED if CALIBRATED.exists() else None,
        keyword_extraction="llm" if use_llm else None,
    )
    print("Done. Check runs/ for output.")


if __name__ == "__main__":
    asyncio.run(main())
