"""
deduper.py — merge duplicate commitments across sources using OpenRouter API.

Strategy:
  1. Build a condensed text representation of all extracted commitments.
  2. Call OpenRouter API with the dedupe prompt, asking it to group items that refer
     to the same real-world commitment.
  3. For each group, merge the records: combine their "sources" lists,
     pick the most specific deadline, keep the most informative title/
     description, and union the owners.
  4. Assign clean sequential IDs to the merged output.

If the dedupe prompt (prompts/dedupe.txt) is empty, a built-in fallback
prompt is used so the pipeline works end-to-end without prompt files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src import gemini_client

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

def _merge_group(items: list[dict]) -> dict:
    """
    Merge a list of commitment dicts that Gemini identified as duplicates.
    Returns a single merged commitment.
    """
    if len(items) == 1:
        return items[0]

    # Pick the item with the most specific (earliest) non-null deadline
    deadlines = [i["deadline_iso"] for i in items if i.get("deadline_iso")]
    best_deadline_iso = min(deadlines) if deadlines else None

    raw_deadlines = [i["raw_deadline"] for i in items if i.get("raw_deadline")]
    best_raw = raw_deadlines[0] if raw_deadlines else None

    # Longest title tends to be most informative
    best_title = max((i.get("title", "") for i in items), key=len)
    best_desc  = max((i.get("description", "") for i in items), key=len)

    # Owner: prefer the user's name (first item's owner as fallback)
    owners = list({i.get("owner", "") for i in items if i.get("owner")})
    owner = owners[0] if owners else ""

    counterparties = list({i.get("counterparty") for i in items if i.get("counterparty")})
    counterparty = counterparties[0] if counterparties else None

    # Completed if ANY source says completed
    completed = any(i.get("completed", False) for i in items)

    # Union all sources lists, de-duplicated by source_id + timestamp
    seen_source_keys: set[str] = set()
    merged_sources: list[dict] = []
    for item in items:
        for s in item.get("sources", []):
            key = f"{s['source_id']}|{s['timestamp']}"
            if key not in seen_source_keys:
                seen_source_keys.add(key)
                merged_sources.append(s)

    return {
        "id":           items[0]["id"],   # will be reassigned by dedupe()
        "title":        best_title,
        "description":  best_desc,
        "owner":        owner,
        "counterparty": counterparty,
        "raw_deadline": best_raw,
        "deadline_iso": best_deadline_iso,
        "completed":    completed,
        "sources":      merged_sources,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def dedupe(commitments: list[dict]) -> list[dict]:
    """
    Merge duplicate commitments.
    Returns a new list with clean sequential IDs ("commit-001", …).
    """
    if not commitments:
        return []

    system_prompt  = _load_prompt("system.txt")
    dedupe_template = _load_prompt("dedupe.txt")

    # Build condensed JSON for the LLM
    condensed = json.dumps(
        [
            {
                "id":          c["id"],
                "title":       c["title"],
                "description": c["description"],
                "owner":       c.get("owner", ""),
                "raw_deadline": c.get("raw_deadline", ""),
            }
            for c in commitments
        ],
        indent=2,
        ensure_ascii=False,
    )

    if dedupe_template:
        user_prompt = dedupe_template.replace("{{COMMITMENTS_JSON}}", condensed)
    else:
        user_prompt = _build_default_dedupe_prompt(condensed)

    # --- Call Gemini ---
    raw: Any = gemini_client.generate_json(system_prompt, user_prompt)

    # Gemini should return {"groups": [[id, id, ...], ...]}
    if isinstance(raw, dict):
        groups_raw: list[list[str]] = raw.get("groups", [])
    else:
        groups_raw = []

    # Fall back: if LLM returns nothing useful, treat each item as its own group
    if not groups_raw:
        groups_raw = [[c["id"]] for c in commitments]

    # Build an id → commitment lookup
    by_id = {c["id"]: c for c in commitments}

    # Merge each group
    merged: list[dict] = []
    seen_ids: set[str] = set()

    for group_ids in groups_raw:
        valid_items = [by_id[gid] for gid in group_ids if gid in by_id]
        if not valid_items:
            continue
        merged.append(_merge_group(valid_items))
        seen_ids.update(c["id"] for c in valid_items)

    # Any commitment the LLM omitted passes through unchanged
    for c in commitments:
        if c["id"] not in seen_ids:
            merged.append(c)

    # Assign clean sequential IDs
    for idx, item in enumerate(merged, start=1):
        item["id"] = f"commit-{idx:03d}"

    return merged


# ---------------------------------------------------------------------------
# Default prompt fallback
# ---------------------------------------------------------------------------

def _build_default_dedupe_prompt(condensed_json: str) -> str:
    return f"""
You are an executive assistant AI. Below is a list of commitment items extracted
from multiple sources (meetings, emails, voice notes, calendars).

Group together items that refer to the SAME real-world commitment or task.
Items are duplicates if they describe the same action by the same person with
a similar deadline, even if the wording differs.

Return a JSON object with a single key "groups". The value is a list of lists —
each inner list contains the "id" values of items in the same group.
Items that have no duplicate still appear as a single-element inner list.

COMMITMENTS:
{condensed_json}
"""
