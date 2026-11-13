"""Termination-date sensitivity sweep (Phase 6).

Sweeps the cover termination date over its valid range (the day after seeding through the
planting day, in the reference year 2025 calendar) and reports, per date: living-cover days,
median winter rain outside cover, and how many historical seasons the check would have fired.

With the fixed 14-day rule and no grower concern the check count is a step function: the
dry-year count for gaps below 14 days and 0 at or above. Winter totals use cumulative sums so a
full sweep over 45 seasons takes milliseconds; ``tests`` assert they equal ``compute_winter``.
"""

from __future__ import annotations

import statistics
from datetime import timedelta
from typing import Any

import numpy as np

from fieldshift.compare.context import Context
from fieldshift.compare.engine import (
    CHECK_META,
    REFERENCE_YEAR,
    YEARS,
    reference_for,
    thresholds_view,
)
from fieldshift.compare.models import SensitivityPoint
from fieldshift.contracts import FieldIssue, InvalidPlanError, Plan, Status, ThresholdSet
from fieldshift.metrics.rules import evaluate_season
from fieldshift.metrics.spring import compute_spring
from fieldshift.metrics.thresholds import HEAVY_RAIN_NAME
from fieldshift.seasons.align import build_calendar
from fieldshift.seasons.coverage import season_coverage
from fieldshift.seasons.facts import build_season_facts

DEFAULT_RULE = "cr_tt_03"


def _leap_gap(plan: Plan) -> int | None:
    """Gap in a leap-year season (2020); differs from the reference year only across Feb 29."""
    try:
        return build_calendar(plan, 2020).termination_gap_days
    except InvalidPlanError:
        return None


def sweep_termination(
    plan: Plan, ctx: Context, ts: ThresholdSet, rule_id: str = DEFAULT_RULE
) -> dict[str, Any]:
    if plan.winter.kind != "cover":
        raise InvalidPlanError([FieldIssue(
            field="plan.winter.kind", code="not_a_cover_plan",
            message="termination sensitivity needs a plan with a winter cover crop")])
    ref_cal = build_calendar(plan, REFERENCE_YEAR)
    assert ref_cal.cover is not None
    heavy = ts.get(HEAVY_RAIN_NAME).value
    ref = reference_for(ctx, plan.next_plant)

    per_year = []
    for y in YEARS:
        base = build_calendar(plan, y)
        cov = season_coverage(base, ctx.series)
        spring = compute_spring(plan, base, ctx.series, ts, ctx.snapshot_hash, ref)
        rain = ctx.series.window(["precip_mm"], base.prev_harvest, base.plant)["precip_mm"].to_numpy()
        winter_ok = cov.metrics["winter"].eligible
        cum = np.concatenate([[0.0], np.cumsum(np.nan_to_num(rain))])
        hv = np.concatenate([[0.0], np.cumsum((rain >= heavy) if heavy is not None else 0)])
        per_year.append((y, base, cov, spring, winter_ok, cum, hv))

    seed_ref = ref_cal.cover.seed
    seen: set[Status] = set()
    points: list[SensitivityPoint] = []
    d = seed_ref + timedelta(days=1)
    while d <= ref_cal.plant:
        md = d.strftime("%m-%d")
        p2 = plan.model_copy(update={"winter": plan.winter.model_copy(update={"terminate": md})})
        rains: list[float] = []
        heavies: list[float] = []
        count = denom = 0
        for y, _base, cov, spring, winter_ok, cum, hv in per_year:
            try:
                cal = build_calendar(p2, y)
            except InvalidPlanError:
                continue
            assert cal.cover is not None
            if winter_ok:
                i_seed = (cal.cover.seed - cal.prev_harvest).days
                i_term = (cal.cover.terminate - cal.prev_harvest).days
                rains.append(float(cum[i_seed] + (cum[-1] - cum[i_term])))
                if heavy is not None:
                    heavies.append(float(hv[i_seed] + (hv[-1] - hv[i_term])))
            facts = build_season_facts(p2, cal, spring, cov)
            chk = evaluate_season(facts, ctx.index, rule_ids=[rule_id]).check(rule_id)
            if chk is not None:
                seen.add(Status(chk.status))
            if chk is not None and chk.status == Status.COMPLETE:
                denom += 1
                count += bool(chk.flagged)
        gap_ref = (ref_cal.plant - d).days
        leap_gap = _leap_gap(p2)
        points.append(SensitivityPoint(
            terminate=md, gap_days=gap_ref,
            gap_days_in_leap_years=leap_gap if leap_gap != gap_ref else None,
            living_cover_days_planned=(d - seed_ref).days,
            rain_outside_cover_mm_median=round(statistics.median(rains), 3) if rains else None,
            heavy_rain_days_outside_cover_median=(
                round(statistics.median(heavies), 1) if heavies else None
            ),
            checks_count=count, denominator=denom,
        ))
        d += timedelta(days=1)

    dry_years = [y for y, _, _, s, _, _, _ in per_year if s.is_dry]
    if any(p.denominator > 0 for p in points):
        status = Status.COMPLETE
    elif seen and seen <= {Status.INAPPLICABLE}:
        status = Status.INAPPLICABLE
    elif Status.MANUAL_CHECK in seen:
        status = Status.MANUAL_CHECK
    else:
        status = Status.UNKNOWN
    return {
        "status": status,
        "base_plan_id": plan.plan_id,
        "varied": "terminate",
        "fixed": {"seed": plan.winter.seed, "next_plant": plan.next_plant,
                  "prev_harvest": plan.prev_harvest,
                  "low_moisture_concern": plan.grower.low_moisture_concern},
        "check_id": CHECK_META.get(rule_id, (rule_id,))[0],
        "rule_ids": [rule_id],
        "denominator": max((p.denominator for p in points), default=0),
        "dry_years": dry_years,
        "reference_year": REFERENCE_YEAR,
        "points": points,
        "thresholds": thresholds_view(ts),
        "note": "One point per valid termination date (reference-year calendar). A date that "
        "crosses Feb 29 has a different real gap in leap years (`gap_days_in_leap_years`); each "
        "historical season is evaluated with its own real gap. With the fixed "
        "14-day rule the check count is a step: the dry-year count below 14 days, 0 at or above "
        "(unless the grower reports a low-moisture concern, which fires every evaluable season "
        "below 14 days).",
    }
