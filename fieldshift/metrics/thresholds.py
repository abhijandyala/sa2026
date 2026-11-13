"""Frozen thresholds. Each one is computed once from the full record and shared everywhere.

Heavy-rain day (Phase 3)
------------------------
ASSUMPTION: the handbook / published-product rule is not in the workspace yet
(``docs/handbooks/`` is empty), so a relative rule is used and labelled assumed:

    heavy-rain day  <=>  precip_mm >= P95 of wet-day precipitation

* wet day: ``precip_mm >= 1.0`` mm;
* reference days: every valid day from Sep 1 through May 31 (the union of plausible winter
  windows) over the whole record, so the value never depends on a plan or an era;
* the threshold is inclusive (a day exactly at the value is heavy);
* value rounded to 3 decimals so the hash of the frozen set is stable.

To switch to the handbook rule, change :data:`HEAVY_RAIN_RULE` (``fixed_mm`` is supported).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from fieldshift.contracts import Status, Threshold, ThresholdSet
from fieldshift.weather.series import DailySeries

HEAVY_RAIN_NAME = "heavy_rain_mm"
SPRING_DRY_PREFIX = "spring_dry_mm@"


@dataclass(frozen=True)
class HeavyRainRule:
    method: str  # "percentile_of_wet_days" | "fixed_mm"
    percentile: float = 95.0
    wet_day_min_mm: float = 1.0
    months: tuple[int, ...] = (9, 10, 11, 12, 1, 2, 3, 4, 5)
    fixed_mm: float | None = None
    assumed: bool = True
    note: str = (
        "ASSUMED relative rule (95th percentile of wet days, Sep-May, full record) because "
        "the handbook heavy-rain rule is not available yet."
    )


HEAVY_RAIN_RULE = HeavyRainRule(method="percentile_of_wet_days")


def heavy_rain_threshold(series: DailySeries, rule: HeavyRainRule = HEAVY_RAIN_RULE) -> Threshold:
    span = f"{series.first_date.isoformat()}..{series.last_date.isoformat()}"
    params: dict[str, Any] = {"assumed": rule.assumed, "inclusive": True}
    if rule.method == "fixed_mm":
        assert rule.fixed_mm is not None
        return Threshold(
            name=HEAVY_RAIN_NAME, method="fixed_mm", value=float(rule.fixed_mm), unit="mm/day",
            parameters=params, reference_span=span, n_reference=0, note=rule.note,
        )
    frame = series.frame
    months = frame.index.month.isin(rule.months)
    precip = frame.loc[months, "precip_mm"].dropna()
    wet = precip[precip >= rule.wet_day_min_mm]
    params.update(
        percentile=rule.percentile, wet_day_min_mm=rule.wet_day_min_mm, months=list(rule.months)
    )
    if wet.empty:
        return Threshold(
            name=HEAVY_RAIN_NAME, method=rule.method, value=None, unit="mm/day", parameters=params,
            reference_span=span, n_reference=0, status=Status.UNAVAILABLE,
            note="no wet days in the reference record",
        )
    value = round(float(np.percentile(wet.to_numpy(), rule.percentile)), 3)
    return Threshold(
        name=HEAVY_RAIN_NAME, method=rule.method, value=value, unit="mm/day", parameters=params,
        reference_span=span, n_reference=int(len(wet)), note=rule.note,
    )


def is_heavy(precip_mm: float | None, threshold: Threshold) -> bool | None:
    """True/False for a valid value; ``None`` when the value or threshold is missing."""
    if precip_mm is None or threshold.value is None or (
        isinstance(precip_mm, float) and math.isnan(precip_mm)
    ):
        return None
    return precip_mm >= threshold.value


def build_threshold_set(
    series: DailySeries, snapshot_hash: str, plant_mds: tuple[str, ...] | list[str] = ()
) -> ThresholdSet:
    """Compute every threshold once. Spring dry cutoffs are added per planting MM-DD (Phase 4a)."""
    thresholds: dict[str, Threshold] = {HEAVY_RAIN_NAME: heavy_rain_threshold(series)}
    if plant_mds:
        from fieldshift.metrics.spring import spring_dry_threshold

        for md in sorted(set(plant_mds)):
            t = spring_dry_threshold(series, md)
            thresholds[t.name] = t
    return ThresholdSet(snapshot_hash=snapshot_hash, thresholds=thresholds)
