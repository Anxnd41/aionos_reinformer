"""
qa.py — answer natural-language questions against stored commitments.

The Q&A flow:
  1. Load stored commitments + annotate with status for a given "today".
  2. Call OpenRouter API with the qa prompt, passing the question and the
     annotated commitments as context.
  3. Return the answer as a string.

If prompts/qa.txt is empty a built-in fallback prompt is used.
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

def answer(question: str, today: date | str | None = None) -> str:
    """
    Answer a free-form question about commitments and return a string.

    question — natural-language query from the user
    today    — reference date for status annotation (defaults to DEFAULT_TODAY)
    """
    ref_date = dates.parse_today(today)
    commitments = store.load_commitments()

    if not commitments:
        return (
            "No commitments are loaded yet. "
            "Please run the pipeline first (`python run_pipeline.py`)."
        )

    # Annotate with status
    annotated = []
    for c in commitments:
        status = dates.commitment_status(
            deadline_iso=c.get("deadline_iso"),
            completed=c.get("completed", False),
            today=ref_date,
        )
        annotated.append({**c, "status": status})

    system_prompt = _load_prompt("system.txt")
    qa_template   = _load_prompt("qa.txt")

    context_json = json.dumps(
        {
            "today": dates.iso_date(ref_date),
            "commitments": annotated,
        },
        indent=2,
        ensure_ascii=False,
    )

    if qa_template:
        user_prompt = (
            qa_template
            .replace("{{CONTEXT_JSON}}", context_json)
            .replace("{{QUESTION}}", question)
        )
    else:
        user_prompt = _build_default_qa_prompt(context_json, question)

    raw: Any = gemini_client.generate_json(system_prompt, user_prompt)

    # Normalise response
    if isinstance(raw, dict):
        answer_text = (
            raw.get("answer")
            or raw.get("text")
            or raw.get("response")
            or json.dumps(raw, indent=2)
        )
    elif isinstance(raw, str):
        answer_text = raw
    else:
        answer_text = str(raw)

    return answer_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_default_qa_prompt(context_json: str, question: str) -> str:
    return f"""
You are an executive assistant AI with full knowledge of the executive's
commitments for the current work week.

Answer the user's question accurately and concisely based ONLY on the
commitment data provided below. If the answer cannot be determined from
the data, say so clearly rather than guessing.

Return a JSON object with a single key "answer" containing a plain-text
(or lightly Markdown-formatted) answer string.

CONTEXT:
{context_json}

QUESTION:
{question}
"""
