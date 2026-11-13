"""Per-metric data coverage for one season.

Each metric depends only on its own inputs, so a missing input makes only that metric
unavailable. A window is ``complete`` only when every expected day is valid; a metric is
``eligible`` (usable for ranking/counting) only when complete.

Metrics and their inputs:

* ``winter``       ``precip_mm`` over ``[prev_harvest, plant)``
* ``spring``       ``precip_mm`` over the 30-day spring window
* ``wetness``      ``gwettop`` and ``gwetroot`` over the spring window (modeled)
* ``full_season``  ``precip_mm`` over ``[prev_harvest, plant]`` (planting day included)
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict

from fieldshift.contracts import SeasonCalendar, Status
from fieldshift.weather.series import DailySeries

METRIC_INPUTS: dict[str, list[str]] = {
    "winter": ["precip_mm"],
    "spring": ["precip_mm"],
    "wetness": ["gwettop", "gwetroot"],
    "full_season": ["precip_mm"],
}


class MetricCoverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str
    inputs: list[str]
    window_start: date
    window_end_exclusive: date
    expected_days: int
    valid_days: int
    missing_days: int
    status: Status
    eligible: bool
    reasons: list[str]


class SeasonCoverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    year: int
    metrics: dict[str, MetricCoverage]

    def status_map(self) -> dict[str, Status]:
        return {name: m.status for name, m in self.metrics.items()}


def _windows(cal: SeasonCalendar) -> dict[str, tuple[date, date]]:
    one_day = timedelta(days=1)
    return {
        "winter": (cal.prev_harvest, cal.plant),
        "spring": (cal.spring_start, cal.spring_end + one_day),
        "wetness": (cal.spring_start, cal.spring_end + one_day),
        "full_season": (cal.prev_harvest, cal.plant + one_day),
    }


def season_coverage(cal: SeasonCalendar, series: DailySeries) -> SeasonCoverage:
    out: dict[str, MetricCoverage] = {}
    for metric, (start, end) in _windows(cal).items():
        cols = METRIC_INPUTS[metric]
        stats = series.stats(cols, start, end)
        reasons: list[str] = []
        if stats.valid_days == stats.expected_days:
            status = Status.COMPLETE
        else:
            status = Status.PARTIAL if stats.valid_days > 0 else Status.UNAVAILABLE
            if start < series.first_date:
                reasons.append("record_starts_after_window_start")
            if end - timedelta(days=1) > series.last_date:
                reasons.append("record_ends_before_window_end")
            if stats.missing_days > stats.days_outside_record:
                reasons.append("missing_values_in_record")
        out[metric] = MetricCoverage(
            metric=metric,
            inputs=cols,
            window_start=start,
            window_end_exclusive=end,
            expected_days=stats.expected_days,
            valid_days=stats.valid_days,
            missing_days=stats.missing_days,
            status=status,
            eligible=status == Status.COMPLETE,
            reasons=reasons,
        )
    return SeasonCoverage(year=cal.year, metrics=out)


def planting_years(series: DailySeries) -> list[int]:
    """Every planting year from the record's first calendar year to its last (1981..2025).

    The mapping is fixed by the record span, not by the plan: a planting date after the end of
    the record keeps its year and simply reports ``partial``/``unavailable`` coverage.
    """
    return list(range(series.first_date.year, series.last_date.year + 1))
