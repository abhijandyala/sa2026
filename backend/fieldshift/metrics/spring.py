"""Spring planting-window dryness: 30-day precipitation total, rank, percentile, dry label.

Window: ``[next_plant - 30 d, next_plant - 1 d]`` (see ``seasons.align``).

Rules documented here and tested in ``tests/metrics/test_metrics_spring.py``:

* **Reference set** = every planting year 1981-2025 (``BASELINE_*``; later years in a longer
  record are scored against it but never change it) whose spring window is *complete*
  (every day has a valid ``precip_mm``). Incomplete windows are excluded from the ranking and
  from the denominator and are listed with a reason.
* **Rank**: 1 = driest. Ties share the lowest rank (rank = 1 + years strictly drier).
* **Percentile**: share of reference years at or below this year's total (drier or equal),
  0..1. Rank 9 of 45 with no ties gives 0.2.
* **Dry cutoff** (fixed, frozen in the ``ThresholdSet``): the k-th smallest reference total with
  ``k = ceil(0.20 * n)``, i.e. the bottom 20% of the full eligible record for that location and
  window. **Years equal to the cutoff count as dry** (``total <= cutoff``), so ties at the
  cutoff can make the dry share exceed 20%.
* **Wetness** (``gwettop``/``gwetroot`` window means) is modeled, reported separately and never
  used for the dry label.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict, Field

from fieldshift.contracts import Plan, SeasonCalendar, Status, Threshold, ThresholdSet
from fieldshift.seasons.align import SPRING_WINDOW_DAYS
from fieldshift.seasons.coverage import season_coverage
from fieldshift.seasons.dates import resolve_md
from fieldshift.weather.series import DailySeries

BASELINE_FIRST_YEAR = 1981
BASELINE_LAST_YEAR = 2025  # fixed reference record: planting years 1981-2025 only
DRY_FRACTION = 0.20
MIN_ELIGIBLE_YEARS = 10  # below this the fixed cutoff is not meaningful -> insufficient_data
SPRING_DRY_PREFIX = "spring_dry_mm@"


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExcludedYear(_M):
    year: int
    status: Status
    reasons: list[str]


class SpringReference(_M):
    """Complete-window totals for one planting MM-DD across the whole record."""

    plant_md: str
    series_fingerprint: str  # identifies the weather data this reference was built from
    totals: dict[int, float]  # eligible years only
    excluded: list[ExcludedYear]

    @property
    def n_eligible(self) -> int:
        return len(self.totals)


class WetnessSummary(_M):
    gwettop: float | None
    gwetroot: float | None
    status: Status
    label: str = "modeled"
    reasons: list[str] = Field(default_factory=list)


class SpringResult(_M):
    plan_id: str
    year: int
    window_start: date
    window_end: date  # inclusive
    window_days: int
    status: Status  # precip coverage of the window
    eligible: bool
    total_mm: float | None
    rank: int | None  # 1 = driest
    percentile: float | None  # share of eligible years at or below this total
    classification_status: Status  # complete | insufficient_data | unavailable (dry label)
    n_eligible: int  # denominator used for rank / percentile
    cutoff_mm: float | None
    is_dry: bool | None  # None unless the window is eligible and the cutoff exists
    reasons: list[str]
    snapshot_hash: str
    threshold_set_id: str
    wetness: WetnessSummary


def spring_window_for(year: int, plant_md: str) -> tuple[date, date]:
    """``(start, end_inclusive)`` of the 30-day spring window for ``year``."""
    plant = resolve_md(year, plant_md)
    return plant - timedelta(days=SPRING_WINDOW_DAYS), plant - timedelta(days=1)


def spring_reference(series: DailySeries, plant_md: str) -> SpringReference:
    totals: dict[int, float] = {}
    excluded: list[ExcludedYear] = []
    for year in range(BASELINE_FIRST_YEAR, BASELINE_LAST_YEAR + 1):
        start, end = spring_window_for(year, plant_md)
        end_excl = end + timedelta(days=1)
        stats = series.stats(["precip_mm"], start, end_excl)
        if stats.valid_days == stats.expected_days:
            window = series.window(["precip_mm"], start, end_excl)["precip_mm"]
            totals[year] = round(float(window.sum()), 3)
            continue
        reasons = []
        if start < series.first_date:
            reasons.append("record_starts_after_window_start")
        if end > series.last_date:
            reasons.append("record_ends_before_window_end")
        if stats.missing_days > stats.days_outside_record:
            reasons.append("missing_values_in_record")
        excluded.append(ExcludedYear(
            year=year,
            status=Status.PARTIAL if stats.valid_days else Status.UNAVAILABLE,
            reasons=reasons,
        ))
    return SpringReference(
        plant_md=plant_md, series_fingerprint=series.fingerprint, totals=totals, excluded=excluded
    )


def dry_cutoff(totals: list[float]) -> float | None:
    """k-th smallest total, k = ceil(20% of n); ``None`` below the minimum record."""
    n = len(totals)
    if n < MIN_ELIGIBLE_YEARS:
        return None
    k = math.ceil(DRY_FRACTION * n - 1e-9)
    return sorted(totals)[k - 1]


def spring_dry_threshold(series: DailySeries, plant_md: str) -> Threshold:
    ref = spring_reference(series, plant_md)
    years = sorted(ref.totals)
    span = f"{years[0]}..{years[-1]}" if years else "none"
    cutoff = dry_cutoff(list(ref.totals.values()))
    return Threshold(
        name=f"{SPRING_DRY_PREFIX}{plant_md}",
        method="bottom_20pct_order_statistic",
        value=cutoff,
        unit="mm",
        parameters={
            "fraction": DRY_FRACTION,
            "k": math.ceil(DRY_FRACTION * ref.n_eligible - 1e-9) if ref.n_eligible else 0,
            "tie_rule": "total <= cutoff counts as dry",
            "window_days": SPRING_WINDOW_DAYS,
            "plant_md": plant_md,
            "eligible_years": years,
            "excluded_years": [e.year for e in ref.excluded],
        },
        reference_span=span,
        n_reference=ref.n_eligible,
        status=Status.COMPLETE if cutoff is not None else Status.INSUFFICIENT_DATA,
        note=None if cutoff is not None else
        f"fewer than {MIN_ELIGIBLE_YEARS} eligible years; no fixed dry cutoff",
    )


def wetness_summary(cal: SeasonCalendar, series: DailySeries) -> WetnessSummary:
    cov = season_coverage(cal, series).metrics["wetness"]
    if cov.status != Status.COMPLETE:
        return WetnessSummary(gwettop=None, gwetroot=None, status=cov.status, reasons=cov.reasons)
    rows = series.window(["gwettop", "gwetroot"], cal.spring_start,
                         cal.spring_end + timedelta(days=1))
    return WetnessSummary(
        gwettop=round(float(rows["gwettop"].mean()), 4),
        gwetroot=round(float(rows["gwetroot"].mean()), 4),
        status=Status.COMPLETE,
    )


def compute_spring(
    plan: Plan,
    cal: SeasonCalendar,
    series: DailySeries,
    thresholds: ThresholdSet,
    snapshot_hash: str,
    reference: SpringReference | None = None,
) -> SpringResult:
    """Spring dryness for one season. ``reference`` may be passed to avoid recomputing it."""
    from fieldshift.metrics.winter import ThresholdMismatchError

    if thresholds.snapshot_hash != snapshot_hash:
        raise ThresholdMismatchError(
            "thresholds were frozen from a different snapshot than the one in use"
        )
    ref = reference or spring_reference(series, plan.next_plant)
    if ref.plant_md != plan.next_plant:
        raise ValueError(
            f"spring reference is for planting date {ref.plant_md}, plan uses {plan.next_plant}"
        )
    if ref.series_fingerprint != series.fingerprint:
        raise ValueError("spring reference was built from different weather data")
    cov = season_coverage(cal, series).metrics["spring"]
    threshold = thresholds.thresholds.get(f"{SPRING_DRY_PREFIX}{plan.next_plant}")
    if threshold is None:
        raise KeyError(f"ThresholdSet has no spring dry cutoff for planting date {plan.next_plant}")
    cutoff = threshold.value
    total: float | None = None
    if cov.eligible:
        window = series.window(
            ["precip_mm"], cal.spring_start, cal.spring_end + timedelta(days=1)
        )["precip_mm"]
        total = round(float(window.sum()), 3)
    rank = percentile = None
    is_dry: bool | None = None
    reasons = list(cov.reasons)
    in_baseline = cal.year in ref.totals
    if total is not None and in_baseline:
        values = list(ref.totals.values())
        rank = 1 + sum(v < total for v in values)
        percentile = round(sum(v <= total for v in values) / len(values), 4)
        is_dry = (total <= cutoff) if cutoff is not None else None
    elif total is not None:
        reasons.append("outside_baseline_years")
    if total is not None and in_baseline and cutoff is None:
        reasons.append("dry_cutoff_unavailable")
    if not cov.eligible:
        classification = Status.UNAVAILABLE
    elif is_dry is None:
        classification = Status.INSUFFICIENT_DATA
    else:
        classification = Status.COMPLETE
    return SpringResult(
        plan_id=plan.plan_id,
        year=cal.year,
        window_start=cal.spring_start,
        window_end=cal.spring_end,
        window_days=cal.spring_days,
        status=cov.status,
        eligible=cov.eligible,
        total_mm=total,
        rank=rank,
        percentile=percentile,
        classification_status=classification,
        n_eligible=ref.n_eligible,
        cutoff_mm=cutoff,
        is_dry=is_dry,
        reasons=reasons,
        snapshot_hash=snapshot_hash,
        threshold_set_id=thresholds.threshold_set_id,
        wetness=wetness_summary(cal, series),
    )
