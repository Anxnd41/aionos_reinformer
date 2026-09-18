"""
loader.py — reads data/sources.json and yields one normalised record per source.

Each record has the shape:
    {
        "id":        str,          # e.g. "meeting-1", "thread-1", "voice-1", "calendar-arjun"
        "type":      str,          # "meeting_transcript" | "email_thread" | "voice_note" | "calendar"
        "timestamp": str,          # ISO-8601 string of the earliest date/time for the source
        "owner":     str,          # name of the person this source belongs to (or "all" for broadcasts)
        "content":   str | dict,   # raw content — callers serialise to string as needed
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generator

SOURCES_PATH = Path(__file__).parent.parent / "data" / "sources.json"


def _load_raw() -> dict:
    """Load and return the raw sources.json dict."""
    with SOURCES_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def iter_sources() -> Generator[dict, None, None]:
    """Yield one flat record per source item in sources.json."""
    data = _load_raw()

    # --- Meeting transcripts ---
    for meeting in data.get("meeting_transcripts", []):
        yield {
            "id": meeting["id"],
            "type": "meeting_transcript",
            "timestamp": meeting.get("start", meeting.get("date", "")),
            "owner": data["user"]["name"],
            "content": meeting,
        }

    # --- Email threads ---
    for thread in data.get("email_threads", []):
        # Use the timestamp of the first email as the source timestamp
        first_ts = thread["emails"][0]["timestamp"] if thread["emails"] else ""
        yield {
            "id": thread["id"],
            "type": "email_thread",
            "timestamp": first_ts,
            "owner": data["user"]["name"],
            "content": thread,
        }

    # --- Voice notes ---
    for note in data.get("voice_notes", []):
        yield {
            "id": note["id"],
            "type": "voice_note",
            "timestamp": note.get("timestamp", ""),
            "owner": note.get("recorded_by", data["user"]["name"]),
            "content": note,
        }

    # --- Calendars (one record per person) ---
    for person_name, events in data.get("calendars", {}).items():
        safe_id = "calendar-" + person_name.lower().replace(" ", "-")
        # Use the date of the earliest event
        first_date = events[0]["date"] if events else ""
        yield {
            "id": safe_id,
            "type": "calendar",
            "timestamp": first_date,
            "owner": person_name,
            "content": {"person": person_name, "events": events},
        }


def get_meta() -> dict:
    """Return the meta block from sources.json."""
    return _load_raw()["meta"]


def get_user() -> dict:
    """Return the user block from sources.json."""
    return _load_raw()["user"]


if __name__ == "__main__":
    for rec in iter_sources():
        print(f"[{rec['type']}] {rec['id']} — {rec['timestamp']}")
