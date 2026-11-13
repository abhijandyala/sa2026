"""Per-variable coverage report for a normalized daily table."""

from __future__ import annotations

from typing import Any

import pandas as pd

from fieldshift.weather.sources import VARIABLES


def _iso(ts: pd.Timestamp | None) -> str | None:
    return None if ts is None or pd.isna(ts) else pd.Timestamp(ts).strftime("%Y-%m-%d")


def coverage_report(daily: pd.DataFrame) -> dict[str, Any]:
    """First/last valid date, valid and missing day counts for each variable."""
    per_variable: dict[str, dict[str, Any]] = {}
    for column in VARIABLES:
        valid = daily.loc[daily[column].notna(), "date"]
        per_variable[column] = {
            "first_valid": _iso(valid.min() if len(valid) else None),
            "last_valid": _iso(valid.max() if len(valid) else None),
            "valid_days": int(len(valid)),
            "missing_days": int(daily[column].isna().sum()),
        }
    any_missing = daily[VARIABLES].isna().any(axis=1)
    return {
        "first_date": _iso(daily["date"].min()),
        "last_date": _iso(daily["date"].max()),
        "n_days": int(len(daily)),
        "days_with_any_missing": int(any_missing.sum()),
        "per_variable": per_variable,
    }


def missing_dates(daily: pd.DataFrame) -> dict[str, list[str]]:
    """ISO dates with a missing value, per variable (empty lists when complete)."""
    return {
        column: [d.strftime("%Y-%m-%d") for d in daily.loc[daily[column].isna(), "date"]]
        for column in VARIABLES
    }
