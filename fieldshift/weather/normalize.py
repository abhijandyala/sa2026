"""Normalize a POWER daily response into a full-calendar daily table.

Rules (CLAUDE.md "blank and zero"):

* a missing value is ``NaN`` in the value column **plus** a reason string in ``<col>_reason``;
* a real ``0.0`` stays ``0.0`` and has no reason;
* fill values, negative precipitation/wetness, wetness above 1 and NaN are missing;
* duplicate dates are de-duplicated (first occurrence wins) and logged;
* the table is reindexed to every calendar day, so a gap is an explicit all-missing row.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from fieldshift.weather.sources import (
    FRACTION_COLUMNS,
    NON_NEGATIVE_COLUMNS,
    PARAMETER_TO_COLUMN,
    POWER_FILL_VALUE,
    VARIABLES,
)

REASON_FILL = "fill_value"
REASON_NEGATIVE = "negative"
REASON_OUT_OF_RANGE = "out_of_range"
REASON_NAN = "nan"
REASON_ABSENT = "absent_from_source"
MISSING_REASONS = (REASON_FILL, REASON_NEGATIVE, REASON_OUT_OF_RANGE, REASON_NAN, REASON_ABSENT)

DAILY_COLUMNS = ["date"] + [c for v in VARIABLES for c in (v, f"{v}_reason")]


@dataclass
class NormalizeLog:
    """What normalization changed or dropped. Serialized into the snapshot manifest."""

    duplicates: list[dict[str, Any]] = field(default_factory=list)
    invalid_dates: list[str] = field(default_factory=list)
    missing_by_reason: dict[str, dict[str, int]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "duplicates": self.duplicates,
            "invalid_dates": self.invalid_dates,
            "missing_by_reason": self.missing_by_reason,
        }


@dataclass
class NormalizeResult:
    daily: pd.DataFrame
    log: NormalizeLog


class PowerFormatError(ValueError):
    """The raw payload is not a POWER daily point response."""


def parse_power_json(raw: bytes | str | dict[str, Any]) -> pd.DataFrame:
    """Flatten a POWER response to one row per date with the raw (un-normalized) values.

    Returns columns ``date`` (string as found, e.g. ``19810101``) and one column per
    normalized variable. A date present for some parameters but absent for others yields NaN
    for the absent ones. JSON ``null`` becomes NaN.
    """
    payload = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
    try:
        parameter_block = payload["properties"]["parameter"]
    except (KeyError, TypeError) as exc:
        raise PowerFormatError("response has no properties.parameter block") from exc
    frames = []
    for parameter, column in PARAMETER_TO_COLUMN.items():
        series = parameter_block.get(parameter)
        if series is None:
            continue
        values = [np.nan if v is None else float(v) for v in series.values()]
        frames.append(pd.DataFrame({"date": list(series.keys()), column: values}))
    if not frames:
        raise PowerFormatError("none of the expected parameters are in the response")
    wide = frames[0]
    for frame in frames[1:]:
        wide = wide.merge(frame, on="date", how="outer")
    for column in VARIABLES:
        if column not in wide:
            wide[column] = np.nan
    return wide[["date", *VARIABLES]]


def _classify(column: str, value: float, fill_value: float) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return REASON_NAN
    if value == fill_value:
        return REASON_FILL
    if column in NON_NEGATIVE_COLUMNS and value < 0:
        return REASON_NEGATIVE
    if column in FRACTION_COLUMNS and value > 1:
        return REASON_OUT_OF_RANGE
    return None


def normalize_daily(
    records: pd.DataFrame,
    *,
    start: str | None = None,
    end: str | None = None,
    fill_value: float = POWER_FILL_VALUE,
) -> NormalizeResult:
    """Normalize raw per-date records. ``start``/``end`` (ISO) force the calendar span."""
    log = NormalizeLog()
    frame = records.copy()
    parsed = pd.to_datetime(frame["date"].astype(str), format="mixed", errors="coerce")
    bad = parsed.isna()
    if bad.any():
        log.invalid_dates = [str(v) for v in frame.loc[bad, "date"]]
    frame = frame.loc[~bad].copy()
    frame["date"] = parsed.loc[~bad].dt.normalize()

    # De-duplicate: first occurrence wins; note whether the dropped rows disagreed.
    dup_mask = frame["date"].duplicated(keep="first")
    if dup_mask.any():
        for day in sorted(frame.loc[dup_mask, "date"].unique()):
            rows = frame.loc[frame["date"] == day, VARIABLES]
            conflicting = bool(len(rows.drop_duplicates()) > 1)
            log.duplicates.append(
                {
                    "date": pd.Timestamp(day).strftime("%Y-%m-%d"),
                    "occurrences": int(len(rows)),
                    "conflicting_values": conflicting,
                    "kept": "first",
                }
            )
        frame = frame.loc[~dup_mask]

    first = pd.Timestamp(start) if start else frame["date"].min()
    last = pd.Timestamp(end) if end else frame["date"].max()
    calendar = pd.date_range(first, last, freq="D")
    frame = frame.set_index("date").sort_index()
    present = frame.index.isin(calendar)
    frame = frame.loc[present]
    absent_dates = calendar.difference(frame.index)
    is_absent = calendar.isin(absent_dates)
    frame = frame.reindex(calendar)
    frame.index.name = "date"

    out = pd.DataFrame({"date": calendar})
    counts: dict[str, dict[str, int]] = {}
    for column in VARIABLES:
        raw_values = frame[column].to_numpy(dtype="float64")
        values = np.full(len(calendar), np.nan)
        reasons: list[str | None] = []
        tally: dict[str, int] = {}
        for i, value in enumerate(raw_values):
            if is_absent[i]:
                reason: str | None = REASON_ABSENT
            else:
                reason = _classify(column, float(value), fill_value)
            if reason is None:
                values[i] = value
            else:
                tally[reason] = tally.get(reason, 0) + 1
            reasons.append(reason)
        out[column] = values
        out[f"{column}_reason"] = pd.Series(reasons, dtype="object")
        counts[column] = tally
    log.missing_by_reason = counts
    return NormalizeResult(daily=out[DAILY_COLUMNS], log=log)


def normalize_power_response(
    raw: bytes | str | dict[str, Any],
    *,
    start: str | None = None,
    end: str | None = None,
) -> NormalizeResult:
    """Parse and normalize a raw POWER response in one step."""
    payload = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
    fill = float(payload.get("header", {}).get("fill_value", POWER_FILL_VALUE))
    return normalize_daily(parse_power_json(payload), start=start, end=end, fill_value=fill)
