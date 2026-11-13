"""Backup plan (Phase 9): a default plan plus a fallback, with a switch condition and dates.

The first release compares the two as **fixed plans**: both are run over every historical season
with the same frozen thresholds and weather rows, and the differences are reported. Nothing here
forecasts which plan will do better. The optional backtest (a replay that may use only data
available at the decision date, with cutoffs frozen in advance) is not part of this release and is
reported as ``unavailable``.

Timing:

* ``divergence``        the first date on which the two plans do something different;
* ``decision_deadline`` the day before it (the last day to decide);
* ``next_check_date``   ``CHECK_LEAD_DAYS`` before the deadline, never earlier than ``as_of``.
  ``CHECK_LEAD_DAYS`` = 7 is an assumption (labeled), not a catalog value.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from fieldshift.catalogs.index import CatalogIndex
from fieldshift.contracts import Plan, Status
from fieldshift.metrics.rules import GATES
from fieldshift.planner.calendar import ActionCalendar, build_action_calendar
from fieldshift.planner.checker import default_planting_year
from fieldshift.planner.finder import find_plans

CHECK_LEAD_DAYS = 7  # ASSUMED: how long before the deadline the deciding check is scheduled
PLAN_ACTIONS = ("harvest", "seed", "terminate", "plant")
Timing = Literal["upcoming", "due", "past_deadline"]


class Divergence(BaseModel):
    action_id: str
    default_date: date | None
    fallback_date: date | None
    first_date: date
    what: str


class SwitchCondition(BaseModel):
    kind: Literal["dry_or_moisture_concern", "unresolved_flags", "grower_decision"]
    text: str
    rule_ids: list[str] = Field(default_factory=list)
    inputs_needed: list[str] = Field(default_factory=list)


class BackupPlan(BaseModel):
    status: Status  # complete | invalid_input | unsupported
    year: int | None = None
    default_plan_id: str | None = None
    fallback_plan_id: str | None = None
    fallback_source: Literal["grower", "suggested"] | None = None
    divergence: Divergence | None = None
    switch_condition: SwitchCondition | None = None
    decision_deadline: date | None = None
    next_check_date: date | None = None
    timing: Timing | None = None
    as_of: date | None = None
    comparison: dict[str, Any] | None = None  # fixed-plan comparison (filled with a Context)
    backtest: dict[str, Any] = Field(
        default_factory=lambda: {
            "status": Status.UNAVAILABLE.value,
            "reason": "the first release compares the two plans as fixed plans; an optional "
            "backtest using only data available at the decision date is not built",
        }
    )
    assumptions: list[str] = Field(
        default_factory=lambda: [
            f"next_check_date is {CHECK_LEAD_DAYS} days before the decision deadline (assumed, "
            "not from the catalog)"
        ]
    )
    notes: list[str] = Field(default_factory=list)
    issues: list[dict[str, str]] = Field(default_factory=list)


def _plan_dates(cal: ActionCalendar) -> dict[str, date]:
    return {a.action_id: a.date for a in cal.actions if a.action_id in PLAN_ACTIONS}


def _divergence(default: ActionCalendar, fallback: ActionCalendar) -> Divergence | None:
    d, f = _plan_dates(default), _plan_dates(fallback)
    best: Divergence | None = None
    for aid in PLAN_ACTIONS:
        dd, fd = d.get(aid), f.get(aid)
        if dd == fd:
            continue
        first = min(x for x in (dd, fd) if x is not None)
        what = (
            f"{aid}: default {dd.isoformat() if dd else 'none'} vs fallback "
            f"{fd.isoformat() if fd else 'none'}"
        )
        cand = Divergence(
            action_id=aid, default_date=dd, fallback_date=fd, first_date=first, what=what
        )
        if best is None or cand.first_date < best.first_date:
            best = cand
    return best


def _switch_condition(
    default: ActionCalendar, fallback: ActionCalendar, div: Divergence | None, deadline: date | None
) -> SwitchCondition:
    gated = sorted(
        a.action_id.removeprefix("check:")
        for a in default.actions
        if a.action_id.startswith("check:") and a.action_id.removeprefix("check:") in GATES
    )
    d_flags = {a.action_id.removeprefix("check:") for a in default.actions if a.flagged}
    f_flags = {a.action_id.removeprefix("check:") for a in fallback.actions if a.flagged}
    when = f"by {deadline.isoformat()}" if deadline else "before the plans diverge"
    if div is not None and div.action_id == "terminate" and gated:
        return SwitchCondition(
            kind="dry_or_moisture_concern",
            text=(
                f"Switch to the fallback {when} if the spring is running dry or the grower reports "
                f"a low-moisture concern: {div.what}."
            ),
            rule_ids=gated,
            inputs_needed=["a field moisture check or a grower-reported concern"],
        )
    cleared = sorted(d_flags - f_flags)
    if cleared:
        return SwitchCondition(
            kind="unresolved_flags",
            text=(
                f"Switch to the fallback {when} if the default plan's flagged checks "
                f"({', '.join(cleared)}) cannot be resolved: they do not fire in the fallback."
            ),
            rule_ids=cleared,
        )
    return SwitchCondition(
        kind="grower_decision",
        text=f"No catalog rule decides this switch; it is the grower's call {when}.",
    )


def suggest_fallback(plan: Plan, index: CatalogIndex, *, year: int | None = None) -> Plan | None:
    """A catalog-supported alternative winter option for the same cash-crop pair, or ``None``.

    Prefers the option with the fewest moisture flags and then the most living cover; never the
    default's own winter management.
    """
    cover = plan.winter
    if cover.kind == "cover" and cover.crop_id and cover.terminate:
        # The natural fallback keeps the seeding and only ends the cover earlier, so the decision
        # is made in spring, when the dry signal is known.
        from datetime import timedelta as _td

        from fieldshift.planner.finder import _gaps
        from fieldshift.seasons.align import build_calendar

        try:
            cal = build_calendar(plan, year or default_planting_year())
        except Exception:  # noqa: BLE001 - invalid plans are reported by the caller
            return None
        if cal.cover is not None and cal.termination_gap_days is not None:
            larger = [g for g in _gaps(index, cover.crop_id, plan.next_crop_id, plan.region)
                      if g > cal.termination_gap_days]  # fmt: skip
            if larger:
                terminate = cal.plant - _td(days=min(larger))
                new = cover.model_copy(
                    update={"terminate": f"{terminate.month:02d}-{terminate.day:02d}"}
                )
                return plan.model_copy(
                    update={"winter": new, "plan_id": f"{plan.plan_id}__fallback_gap{min(larger)}"}
                )
    res = find_plans(plan, index, priorities=["limited_water", "soil_protection"], year=year)
    for opt in res.options:
        w, cur = opt.winter, plan.winter
        if (w.kind, w.crop_id, w.seed, w.terminate) != (
            cur.kind,
            cur.crop_id,
            cur.seed,
            cur.terminate,
        ):
            return plan.model_copy(
                update={"winter": w, "plan_id": f"{plan.plan_id}__fallback_{opt.option_id}"}
            )
    return None


def build_backup_plan(
    default: Plan,
    fallback: Plan | None,
    index: CatalogIndex,
    *,
    year: int | None = None,
    as_of: date | None = None,
    inputs: dict[str, Any] | None = None,
) -> BackupPlan:
    """Default + fallback, divergence, switch condition and dates. Comparison needs a Context."""
    source: Literal["grower", "suggested"] = "grower"
    if fallback is None:
        fallback = suggest_fallback(default, index, year=year)
        source = "suggested"
        if fallback is None:
            return BackupPlan(
                status=Status.UNSUPPORTED, year=year, default_plan_id=default.plan_id,
                notes=["the catalog supports no other winter option for this cash-crop pair"],
            )  # fmt: skip
    a = build_action_calendar(default, index, year=year, inputs=inputs)
    b = build_action_calendar(fallback, index, year=year, inputs=inputs)
    bad = [x for x in (a, b) if x.status != Status.COMPLETE]
    if bad:
        issues = [
            {"field": ("default" if x is a else "fallback"), "code": str(x.status), "message": m}
            for x in bad for m in (x.notes or [str(x.status)])
        ]  # fmt: skip
        return BackupPlan(
            status=bad[0].status, year=year, default_plan_id=default.plan_id,
            fallback_plan_id=fallback.plan_id, fallback_source=source, issues=issues,
        )  # fmt: skip
    div = _divergence(a, b)
    deadline = div.first_date - timedelta(days=1) if div else None
    timing: Timing | None = None
    next_check: date | None = None
    today = as_of or date.today()
    if deadline is not None:
        planned = deadline - timedelta(days=CHECK_LEAD_DAYS)
        if today > deadline:
            timing = "past_deadline"
        else:
            next_check = max(planned, today)
            timing = "due" if today >= planned else "upcoming"
    notes = []
    if div is None:
        notes.append("the two plans have identical dates; there is nothing to switch")
    return BackupPlan(
        status=Status.COMPLETE, year=a.year, default_plan_id=default.plan_id,
        fallback_plan_id=fallback.plan_id, fallback_source=source, divergence=div,
        switch_condition=_switch_condition(a, b, div, deadline), decision_deadline=deadline,
        next_check_date=next_check, timing=timing, as_of=today, notes=notes,
    )  # fmt: skip


def compare_fixed_plans(backup: BackupPlan, default: Plan, fallback: Plan, ctx: Any) -> BackupPlan:
    """Attach the fixed-plan comparison (both plans over every season, one frozen ThresholdSet)."""
    from fieldshift.compare import engine

    if backup.status != Status.COMPLETE:
        return backup
    results, ts, shared = engine.compare_plans([default, fallback], ctx)
    plans = {r.plan_id: r for r in results}

    def brief(pid: str) -> dict[str, Any]:
        r = plans[pid]
        if (
            r.status != Status.COMPLETE
            or r.calendar is None
            or r.winter is None
            or r.spring is None
        ):
            return {"plan_id": pid, "status": str(r.status), "reason": r.reason}
        return {
            "plan_id": pid,
            "status": str(r.status),
            "living_cover_days_planned": r.calendar.living_cover_days_planned,
            "days_without_planned_cover": r.calendar.days_without_planned_cover,
            "termination_gap_days": r.calendar.termination_gap_days,
            "rain_mm_outside_cover_median": r.winter.per_season_median.get("rain_mm_outside_cover"),
            "heavy_rain_days_outside_cover_median": r.winter.per_season_median.get(
                "heavy_rain_days_outside_cover"
            ),
            "spring_checks": [
                {
                    "check_id": c.check_id,
                    "count": c.count,
                    "denominator": c.denominator,
                    "pct": c.pct,
                }
                for c in r.spring_checks
            ],
            "flagged_other_checks": [x.rule_id for x in r.other_checks if x.flagged],
        }

    d, f = brief(default.plan_id), brief(fallback.plan_id)
    diff: dict[str, Any] = {}
    if d.get("status") == "complete" and f.get("status") == "complete":
        for k in ("living_cover_days_planned", "rain_mm_outside_cover_median",
                  "heavy_rain_days_outside_cover_median", "termination_gap_days"):  # fmt: skip
            if d[k] is not None and f[k] is not None:
                diff[k] = round(f[k] - d[k], 3)
        dc = {c["check_id"]: c for c in d["spring_checks"]}
        fc = {c["check_id"]: c for c in f["spring_checks"]}
        diff["spring_check_counts"] = {
            cid: {"default": dc[cid]["count"], "fallback": fc[cid]["count"],
                  "denominator": dc[cid]["denominator"]}
            for cid in sorted(set(dc) & set(fc))
        }  # fmt: skip
    backup.comparison = {
        "basis": "fixed_plans",
        "threshold_set_id": ts.threshold_set_id,
        "shared_eligible_years": shared.model_dump(mode="json"),
        "default": d,
        "fallback": f,
        "fallback_minus_default": diff,
        "note": "Both plans were run over the same seasons with the same frozen thresholds. This "
        "is a descriptive comparison of fixed plans, not a forecast of which will do better.",
    }
    return backup
