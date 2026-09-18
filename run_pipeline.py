#!/usr/bin/env python3
"""
run_pipeline.py — CLI entry point to extract, dedupe, and store commitments.

Usage:
    python run_pipeline.py [--clear-cache] [--today YYYY-MM-DD]

Steps:
  1. Load all sources from data/sources.json (via loader.iter_sources).
  2. Extract commitments from each source (via extractor.extract_all).
     Results are cached per source so re-runs are fast.
  3. Dedupe the extracted commitments (via deduper.dedupe).
  4. Save the final list to data/commitments.json (via store.save_commitments).
"""

from __future__ import annotations

import argparse
import sys

from src import deduper, extractor, loader, store


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract, dedupe, and store commitments from sources.json"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Force full re-extraction by clearing the extraction cache",
    )
    parser.add_argument(
        "--today",
        type=str,
        default=None,
        help="Reference date for status annotations (YYYY-MM-DD). Defaults to 2026-09-25.",
    )
    args = parser.parse_args()

    if args.clear_cache:
        print("[pipeline] Clearing extraction cache...")
        store.clear_cache()

    print("[pipeline] Loading sources from data/sources.json...")
    sources = list(loader.iter_sources())
    print(f"[pipeline] Loaded {len(sources)} sources.")

    print("[pipeline] Extracting commitments (cached per source)...")
    all_commitments = extractor.extract_all(sources)
    print(f"[pipeline] Extracted {len(all_commitments)} raw commitments.")

    print("[pipeline] Deduplicating commitments...")
    deduplicated = deduper.dedupe(all_commitments)
    print(f"[pipeline] After deduplication: {len(deduplicated)} unique commitments.")

    print("[pipeline] Saving to data/commitments.json...")
    store.save_commitments(deduplicated)

    print("[pipeline] ✓ Done.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[pipeline] Interrupted by user.")
        sys.exit(130)
    except Exception as exc:
        print(f"[pipeline] FATAL: {exc}", file=sys.stderr)
        sys.exit(1)
