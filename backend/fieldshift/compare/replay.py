"""Season replay (Phase 6): the exact days of one season for one plan, plus triggered checks."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pandas as pd

from fieldshift.compare.context import Context
from fieldshift.compare.engine import reference_for, season_bundle, thresholds_view
from fieldshift.compare.models import KeyRainDay, ReplayDay, TriggeredCheck
from fieldshift.contracts import Plan, ThresholdSet
from fieldshift.metrics.rules import GATES
from fieldshift.metrics.thresholds import HEAVY_RAIN_NAME
from fieldshift.metrics.winter import (
    AFTER_TERMINATION,
    BEFORE_ESTABLISHMENT,
    LIVING_COVER,
    winter_day_segments,
)

_COVER_STATUS = {
    LIVING_COVER: "planned_living_cover",
    AFTER_TERMINATION: "terminated",
    BEFORE_ESTABLISHMENT: "no_planned_cover",
}
_VARS = ["precip_mm", "tmax_c", "tmin_c", "gwettop", "gwetroot"]


def _val(x: Any) -> float | None:
    return None if x is None or pd.isna(x) else float(x)


def replay_season(plan: Plan, year: int, ctx: Context, ts: ThresholdSet) -> dict[str, Any]:
    """Payload for ``GET /v1/seasons/{year}/replay``. Depends only on (plan, year, snapshot)."""
    b = season_bundle(plan, year, ctx, ts, reference_for(ctx, plan.next_plant))
    cal = b.cal
    heavy = ts.get(HEAVY_RAIN_NAME).value
    labels = winter_day_segments(cal)
    frame = ctx.series.frame
    end_excl = cal.plant
    days = pd.date_range(cal.prev_harvest, end_excl - timedelta(days=1), freq="D")
    rows = frame.reindex(days)
    in_record = days.isin(frame.index)

    daily: list[ReplayDay] = []
    key_days: list[KeyRainDay] = []
    for i, ts_day in enumerate(days):
        seg = str(labels[ts_day])
        vals = {v: _val(rows[v].iloc[i]) for v in _VARS}
        missing = [v for v, x in vals.items() if x is None]
        reasons: dict[str, str] = {}
        for v in missing:
            if not in_record[i]:
                reasons[v] = "outside_record"
            else:
                reasons[v] = str(rows[f"{v}_reason"].iloc[i] or "missing")
        precip = vals["precip_mm"]
        is_heavy = None if precip is None or heavy is None else precip >= heavy
        d = ts_day.date()
        daily.append(ReplayDay(
            date=d, **vals, cover_status=_COVER_STATUS.get(seg, "no_planned_cover"), segment=seg,
            in_spring_window=cal.spring_start <= d <= cal.spring_end, heavy_rain=is_heavy,
            missing=missing, missing_reasons=reasons,
        ))
        if is_heavy:
            key_days.append(KeyRainDay(date=d, precip_mm=precip, segment=seg, heavy=True))  # type: ignore[arg-type]

    spring = b.spring
    triggered: list[TriggeredCheck] = []
    from fieldshift.compare.engine import CHECK_META

    ordered = sorted(b.evaluation.checks, key=lambda c: (c.rule_id not in GATES, c.rule_id))
    for c in ordered:
        if c.flagged:
            cid = CHECK_META.get(c.rule_id, (c.rule_id,))[0]
            triggered.append(TriggeredCheck(
                check_id=cid, rule_ids=[c.rule_id], reason=c.reason,
                inputs_used=c.inputs_used, source=c.source.model_dump(mode="json"),
            ))
    return {
        "year": year,
        "plan_id": plan.plan_id,
        "dates": {
            "prev_harvest": cal.prev_harvest.isoformat(),
            "seed": cal.cover.seed.isoformat() if cal.cover else None,
            "terminate": cal.cover.terminate.isoformat() if cal.cover else None,
            "next_plant": cal.plant.isoformat(),
            "spring_window": {"start": cal.spring_start.isoformat(),
                              "end": cal.spring_end.isoformat()},
            "termination_gap_days": cal.termination_gap_days,
        },
        "coverage": b.coverage.status_map(),
        "spring": {
            "total_mm": spring.total_mm, "rank": spring.rank, "of": spring.n_eligible,
            "percentile": spring.percentile, "cutoff_mm": spring.cutoff_mm,
            "is_dry": spring.is_dry, "status": spring.status,
            "classification_status": spring.classification_status, "reasons": spring.reasons,
        },
        "wetness": {
            "gwettop_window_mean": spring.wetness.gwettop,
            "gwetroot_window_mean": spring.wetness.gwetroot,
            "unit": "fraction (0-1)", "label": "modeled", "status": spring.wetness.status,
        },
        "winter": b.winter.model_dump(mode="json", exclude={"heavy_rain_events"}),
        "thresholds": thresholds_view(ts, ctx),
        "checks_triggered": triggered,
        "key_rain_days": key_days,
        "daily": daily,
    }
