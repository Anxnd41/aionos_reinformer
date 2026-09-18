"""
extractor.py — extract commitments from a single source record using OpenRouter API.

For each source yielded by loader.iter_sources(), this module:
  1. Checks the disk cache (store.get_cached_extraction).
  2. If a cache miss, calls OpenRouter API with the extract prompt.
  3. Enriches each returned commitment with resolved deadline datetimes
     (using dates.resolve_deadline — pure Python, no LLM).
  4. Writes results back to the cache.

Commitment schema (each item in the returned list):
{
  "id":             str,           # generated: "{source_id}_{index}"
  "title":          str,           # one-line summary of the commitment
  "description":    str,           # fuller context
  "owner":          str,           # person responsible
  "counterparty":   str | null,    # other party (if applicable)
  "raw_deadline":   str | null,    # deadline as it appeared in the source
  "deadline_iso":   str | null,    # resolved ISO datetime (dates.py)
  "completed":      bool,          # true if the source explicitly confirms done
  "sources": [
    {
      "source_id":  str,
      "source_type": str,
      "timestamp":  str
    }
  ]
}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src import gemini_client, dates, store

# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_from_source(source: dict) -> list[dict]:
    """
    Extract commitment records from a single source dict.
    Results are cached; re-running with the same source content is free.
    """
    source_id = source["id"]
    content    = source["content"]

    # --- Cache check ---
    cached = store.get_cached_extraction(source_id, content)
    if cached is not None:
        print(f"[extractor] Cache hit: {source_id}")
        return cached

    print(f"[extractor] Extracting from {source_id} ({source['type']})...")

    system_prompt = _load_prompt("system.txt")
    extract_prompt_template = _load_prompt("extract.txt")

    # Build the user prompt — embed the source as JSON
    source_json = json.dumps(
        {
            "source_id":   source_id,
            "source_type": source["type"],
            "timestamp":   source["timestamp"],
            "owner":       source["owner"],
            "content":     content,
        },
        indent=2,
        ensure_ascii=False,
    )

    if extract_prompt_template:
        user_prompt = extract_prompt_template.replace("{{SOURCE_JSON}}", source_json)
    else:
        # Fallback minimal prompt so the skeleton works even with empty prompts/
        user_prompt = _build_default_extract_prompt(source_json)

    # --- Call Gemini ---
    raw: Any = gemini_client.generate_json(system_prompt, user_prompt)

    # Normalise: Gemini might return {"commitments": [...]} or a bare list
    if isinstance(raw, dict):
        commitments_raw = raw.get("commitments", raw.get("items", []))
    elif isinstance(raw, list):
        commitments_raw = raw
    else:
        commitments_raw = []

    # --- Enrich each commitment ---
    enriched: list[dict] = []
    for idx, c in enumerate(commitments_raw):
        cid = f"{source_id}_{idx}"
        raw_deadline = c.get("raw_deadline") or c.get("deadline") or ""
        resolved = dates.resolve_deadline(raw_deadline, source["timestamp"])

        enriched.append(
            {
                "id":           cid,
                "title":        c.get("title", ""),
                "description":  c.get("description", ""),
                "owner":        c.get("owner", source["owner"]),
                "counterparty": c.get("counterparty"),
                "raw_deadline": raw_deadline,
                "deadline_iso": dates.iso_datetime(resolved) if resolved else None,
                "completed":    bool(c.get("completed", False)),
                "sources": [
                    {
                        "source_id":   source_id,
                        "source_type": source["type"],
                        "timestamp":   source["timestamp"],
                    }
                ],
            }
        )

    # --- Write to cache ---
    store.set_cached_extraction(source_id, content, enriched)
    return enriched


def extract_all(sources: list[dict]) -> list[dict]:
    """Run extraction across all sources and return the combined flat list."""
    all_commitments: list[dict] = []
    for source in sources:
        try:
            results = extract_from_source(source)
            all_commitments.extend(results)
        except Exception as exc:
            print(f"[extractor] ERROR on {source['id']}: {exc}")
    return all_commitments


# ---------------------------------------------------------------------------
# Default prompt (used only when prompts/extract.txt is empty)
# ---------------------------------------------------------------------------

def _build_default_extract_prompt(source_json: str) -> str:
    return f"""
You are an executive assistant AI. Extract every commitment, task, or action item
from the source below. A commitment is anything where a person has agreed to do
something, deliver something, or follow up on something.

Return a JSON object with a single key "commitments" containing a list. Each item:
{{
  "title": "<one-line summary>",
  "description": "<fuller context from the source>",
  "owner": "<person responsible>",
  "counterparty": "<other party or null>",
  "raw_deadline": "<deadline exactly as stated, or null>",
  "completed": <true if explicitly confirmed done, else false>
}}

SOURCE:
{source_json}
"""
