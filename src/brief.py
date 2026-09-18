"""
brief.py — generate the daily action brief for a given "today" date.

The brief is produced by:
  1. Loading stored commitments (store.load_commitments).
  2. Annotating each with its status relative to "today" (dates.commitment_status).
  3. Calling OpenRouter API with the brief prompt, passing the annotated commitments.

If the brief prompt (prompts/brief.txt) is empty a built-in fallback is used.

Returns a plain-text (Markdown-formatted) brief string.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from src import dates, gemini_client, store

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_brief(today: date | str | None = None) -> str:
    """
    Build and return the daily action brief as a Markdown string.

    today — the reference date. Defaults to dates.DEFAULT_TODAY.
    """
    ref_date = dates.parse_today(today)
    commitments = store.load_commitments()

    if not commitments:
        return (
            f"## Daily Brief — {dates.iso_date(ref_date)}\n\n"
            "No commitments found. Run the pipeline first (`python run_pipeline.py`)."
        )

    # Annotate each commitment with its current status
    annotated = []
    for c in commitments:
        status = dates.commitment_status(
            deadline_iso=c.get("deadline_iso"),
            completed=c.get("completed", False),
            today=ref_date,
        )
        annotated.append({**c, "status": status})

    system_prompt = _load_prompt("system.txt")
    brief_template = _load_prompt("brief.txt")

    payload = json.dumps(
        {
            "today": dates.iso_date(ref_date),
            "commitments": annotated,
        },
        indent=2,
        ensure_ascii=False,
    )

    if brief_template:
        user_prompt = brief_template.replace("{{PAYLOAD_JSON}}", payload)
    else:
        user_prompt = _build_default_brief_prompt(payload)

    raw: Any = gemini_client.generate_json(system_prompt, user_prompt)

    # The LLM might return {"brief": "..."} or {"text": "..."} or just a string
    if isinstance(raw, dict):
        brief_text = (
            raw.get("brief")
            or raw.get("text")
            or raw.get("content")
            or json.dumps(raw, indent=2)
        )
    elif isinstance(raw, str):
        brief_text = raw
    else:
        brief_text = str(raw)

    return brief_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_default_brief_prompt(payload_json: str) -> str:
    return f"""
You are a sharp executive assistant. Produce a concise daily action brief for
the executive based on today's date and their commitments.

Structure the brief as Markdown with these sections (omit any empty section):
## ⚠ Overdue
## 📅 Due Today
## 🔜 Upcoming This Week
## ✅ Completed

For each item include: the commitment title, owner, deadline, and the source(s)
it came from. Keep language crisp and professional.

Return a JSON object with a single key "brief" containing the full Markdown string.

DATA:
{payload_json}
"""
