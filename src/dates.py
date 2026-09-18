"""
dates.py — PURE PYTHON, no LLM.

Responsibilities:
  - Define the fixed reference week (Mon 21 Sep – Fri 25 Sep 2026).
  - Resolve natural-language deadline strings ("Wednesday", "EOD tomorrow",
    "end of day Friday", etc.) to real datetime objects within that week,
    given an anchor datetime (usually the source timestamp).
  - Determine whether a commitment is overdue, due-today, upcoming, or done
    relative to a caller-supplied "today" date.
  - Expose helpers used by extractor / brief / app layers.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# Fixed week constants
# ---------------------------------------------------------------------------

WEEK_START = date(2026, 9, 21)   # Monday
WEEK_END   = date(2026, 9, 25)   # Friday
DEFAULT_TODAY = date(2026, 9, 25)

_WEEKDAY_NAMES = {
    "monday":    0,
    "tuesday":   1,
    "wednesday": 2,
    "thursday":  3,
    "friday":    4,
    "saturday":  5,
    "sunday":    6,
    # abbreviations
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

# End-of-day sentinel time
EOD = time(23, 59, 59)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _date_for_weekday(weekday_index: int, anchor: date) -> date:
    """
    Return the date within the fixed week that matches weekday_index (0=Mon).
    If the anchor is outside the fixed week, clamp to the nearest week boundary.
    """
    # Find Monday of the week containing anchor (or just use WEEK_START if
    # anchor falls outside the fixed week).
    if WEEK_START <= anchor <= WEEK_END:
        week_monday = anchor - timedelta(days=anchor.weekday())
    else:
        week_monday = WEEK_START

    target = week_monday + timedelta(days=weekday_index)
    # Clamp to week boundaries
    return max(WEEK_START, min(WEEK_END, target))


def _parse_iso_flexible(value: str) -> Optional[datetime]:
    """Try several ISO-like formats and return a datetime or None."""
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_today(value: str | date | None) -> date:
    """
    Accept a date object, an ISO string "YYYY-MM-DD", or None.
    Returns a date, defaulting to DEFAULT_TODAY.
    """
    if value is None:
        return DEFAULT_TODAY
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    parsed = _parse_iso_flexible(str(value))
    return parsed.date() if parsed else DEFAULT_TODAY


def resolve_deadline(
    raw_deadline: str,
    anchor_timestamp: str,
) -> Optional[datetime]:
    """
    Resolve a natural-language or ISO deadline string to a real datetime.

    Understands:
      - ISO datetimes / dates as-is
      - "Monday" … "Friday" (or abbreviated)  → that weekday in the fixed week
      - "today"                               → anchor date at EOD
      - "tomorrow"                            → anchor date + 1 at EOD
      - "end of day [weekday]" / "EOD [weekday]"
      - "this week" / "by end of week"        → Friday EOD
      - "morning" / "afternoon" suffixes      → 09:00 / 14:00
      - "by [weekday] morning/afternoon"

    Returns None if resolution fails.
    """
    if not raw_deadline:
        return None

    raw = raw_deadline.strip()

    # --- Try ISO parse first ---
    parsed = _parse_iso_flexible(raw)
    if parsed:
        return parsed

    # Normalise
    text = raw.lower()

    # Determine anchor datetime
    anchor_dt = _parse_iso_flexible(anchor_timestamp) or datetime.combine(DEFAULT_TODAY, time(9, 0))
    anchor_date = anchor_dt.date()

    # Helper: map a date + optional time-of-day word to datetime
    def _with_time(d: date, tod: str = "") -> datetime:
        if "morning" in tod:
            return datetime.combine(d, time(9, 0))
        if "afternoon" in tod:
            return datetime.combine(d, time(14, 0))
        return datetime.combine(d, EOD)

    # "end of day" / "eod" prefix
    eod_match = re.match(
        r"(?:end of day|eod)\s*(.*)",
        text,
    )
    if eod_match:
        remainder = eod_match.group(1).strip()
        # remainder might be a weekday name or empty
        if not remainder or remainder in ("today",):
            return datetime.combine(anchor_date, EOD)
        if remainder == "tomorrow":
            return datetime.combine(anchor_date + timedelta(days=1), EOD)
        if remainder in _WEEKDAY_NAMES:
            d = _date_for_weekday(_WEEKDAY_NAMES[remainder], anchor_date)
            return datetime.combine(d, EOD)

    # "by [weekday] [morning|afternoon]?"
    by_match = re.match(
        r"by\s+(\w+)(?:\s+(morning|afternoon))?",
        text,
    )
    if by_match:
        day_word = by_match.group(1)
        tod = by_match.group(2) or ""
        if day_word in _WEEKDAY_NAMES:
            d = _date_for_weekday(_WEEKDAY_NAMES[day_word], anchor_date)
            return _with_time(d, tod)
        if day_word == "tomorrow":
            return _with_time(anchor_date + timedelta(days=1), tod)
        if day_word == "today":
            return _with_time(anchor_date, tod)

    # Bare weekday name (e.g. "Wednesday", "Thursday morning")
    weekday_match = re.match(
        r"(\w+)(?:\s+(morning|afternoon))?$",
        text,
    )
    if weekday_match:
        day_word = weekday_match.group(1)
        tod = weekday_match.group(2) or ""
        if day_word in _WEEKDAY_NAMES:
            d = _date_for_weekday(_WEEKDAY_NAMES[day_word], anchor_date)
            return _with_time(d, tod)

    # "today" / "tomorrow"
    if text in ("today", "eod today", "end of day today"):
        return datetime.combine(anchor_date, EOD)
    if text in ("tomorrow", "eod tomorrow", "end of day tomorrow"):
        return datetime.combine(anchor_date + timedelta(days=1), EOD)

    # "this week" / "end of week" / "by end of week"
    if any(kw in text for kw in ("this week", "end of week", "by end of week", "by friday")):
        return datetime.combine(WEEK_END, EOD)

    return None


def commitment_status(
    deadline_iso: Optional[str],
    completed: bool,
    today: date | str | None = None,
) -> str:
    """
    Return one of: "done" | "overdue" | "due_today" | "upcoming" | "unknown"

    deadline_iso — ISO datetime string or None
    completed    — whether the commitment has been marked done
    today        — reference date (defaults to DEFAULT_TODAY)
    """
    ref = parse_today(today)

    if completed:
        return "done"

    if not deadline_iso:
        return "unknown"

    parsed = _parse_iso_flexible(deadline_iso)
    if parsed is None:
        return "unknown"

    deadline_date = parsed.date()

    if deadline_date < ref:
        return "overdue"
    if deadline_date == ref:
        return "due_today"
    return "upcoming"


def iso_date(d: date) -> str:
    """Return YYYY-MM-DD string."""
    return d.strftime("%Y-%m-%d")


def iso_datetime(dt: datetime) -> str:
    """Return ISO datetime string without microseconds."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


if __name__ == "__main__":
    # Quick smoke test
    cases = [
        ("Wednesday", "2026-09-21T09:00:00"),
        ("EOD tomorrow", "2026-09-21T09:00:00"),
        ("by Thursday morning", "2026-09-21T09:00:00"),
        ("end of day Friday", "2026-09-21T09:00:00"),
        ("this week", "2026-09-21T09:00:00"),
        ("2026-09-23T18:00:00", "2026-09-21T09:00:00"),
    ]
    for raw, anchor in cases:
        result = resolve_deadline(raw, anchor)
        print(f"  {raw!r:35s} -> {result}")
