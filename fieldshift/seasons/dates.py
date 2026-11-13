"""MM-DD date helpers.

Leap-day rule (documented, Phase 2): plans store dates as ``MM-DD`` and resolve them per
year. ``02-29`` resolves to **Feb 28** in non-leap years. Window lengths are always computed
from real calendar dates, so a winter window that spans a Feb 29 has one more day.
"""

from __future__ import annotations

import calendar
from datetime import date

_CYCLE_DAYS = 366
_REF_YEAR = 2000  # leap reference year: Feb 29 is a distinct day for chronology checks


def split_md(md: str) -> tuple[int, int]:
    month, day = md.split("-")
    return int(month), int(day)


def resolve_md(year: int, md: str) -> date:
    """Resolve ``MM-DD`` in ``year``; Feb 29 becomes Feb 28 in non-leap years."""
    month, day = split_md(md)
    if month == 2 and day == 29 and not calendar.isleap(year):
        day = 28
    return date(year, month, day)


def cycle_ordinal(md: str) -> int:
    """Day-of-year of ``md`` in the leap reference year (Feb 29 is its own day, 1..366)."""
    return resolve_md(_REF_YEAR, md).timetuple().tm_yday


def cycle_offset(anchor_md: str, md: str) -> int:
    """Days from ``anchor_md`` forward to ``md`` around the 366-day cycle (0..365)."""
    return (cycle_ordinal(md) - cycle_ordinal(anchor_md)) % _CYCLE_DAYS


CYCLE_DAYS = _CYCLE_DAYS
