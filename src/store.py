"""
store.py — persists and loads the canonical commitments list.

File: data/commitments.json
Schema: list of commitment objects (see extractor.py for the per-item shape).

The store also maintains a simple extraction-cache section so that
re-running the pipeline does not re-call the Gemini API for sources
whose content has not changed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

COMMITMENTS_PATH = Path(__file__).parent.parent / "data" / "commitments.json"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_store() -> dict:
    if COMMITMENTS_PATH.exists():
        with COMMITMENTS_PATH.open("r", encoding="utf-8") as fh:
            try:
                return json.load(fh)
            except json.JSONDecodeError:
                pass
    return {"commitments": [], "extraction_cache": {}}


def _save_store(store: dict) -> None:
    COMMITMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with COMMITMENTS_PATH.open("w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=2, ensure_ascii=False)


def _content_hash(content: Any) -> str:
    """Stable SHA-256 of a JSON-serialisable value."""
    blob = json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Commitments CRUD
# ---------------------------------------------------------------------------

def save_commitments(commitments: list[dict]) -> None:
    """Overwrite the commitments list in the store."""
    store = _load_store()
    store["commitments"] = commitments
    _save_store(store)


def load_commitments() -> list[dict]:
    """Return the stored commitments list (empty list if none yet)."""
    return _load_store().get("commitments", [])


# ---------------------------------------------------------------------------
# Extraction cache
# ---------------------------------------------------------------------------

def get_cached_extraction(source_id: str, content: Any) -> list[dict] | None:
    """
    Return cached extraction for source_id if the content hash matches.
    Returns None on cache miss.
    """
    store = _load_store()
    cache = store.get("extraction_cache", {})
    entry = cache.get(source_id)
    if entry is None:
        return None
    if entry.get("hash") != _content_hash(content):
        return None
    return entry.get("commitments", [])


def set_cached_extraction(source_id: str, content: Any, commitments: list[dict]) -> None:
    """Persist extraction results for a source."""
    store = _load_store()
    cache = store.setdefault("extraction_cache", {})
    cache[source_id] = {
        "hash": _content_hash(content),
        "commitments": commitments,
    }
    _save_store(store)


def clear_cache() -> None:
    """Wipe the extraction cache (forces full re-extraction on next run)."""
    store = _load_store()
    store["extraction_cache"] = {}
    _save_store(store)
