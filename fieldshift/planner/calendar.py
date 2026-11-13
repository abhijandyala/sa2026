"""Action calendar (Phase 9): dated actions for one plan, with zone, trigger, evidence and status.

Actions are the plan's own dates (harvest, seed, terminate, plant) plus **checks**: catalog rules
that a person must act on or look at, dated to the day the decision falls due. Every action carries:

* ``zone``     ``None`` = the whole field, otherwise a zone id (only for zone-specific checks),
* ``trigger``  what makes it appear (a plan date, or a rule and its condition),
* ``evidence`` the rule results behind it, each with its source,
* ``status``   ``complete`` (nothing open), ``manual_check`` (a person checks) or ``unknown``
               (an input is missing; the missing inputs are listed).

Scenarios replay the plan's own dates in a typical, a dry and a wet historical spring (from the
years shortcuts). The **dry** scenario lists the decisions that could change versus the typical
year; the **wet** scenario lists drainage and access checks when zones are available. Weather never
changes the dates; it changes which checks fire.

``diff_calendars`` explains what changed, and why, when a crop or date is edited.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from fieldshift.catalogs.index import CatalogIndex
from fieldshift.contracts import Plan, SeasonCalendar, Status
from fieldshift.field.zones import ZoneSet, collection_assessment, load_zones
from fieldshift.metrics.rules import GATES, RuleCheck
from fieldshift.planner.checker import CheckResult, check_plan, default_planting_year
from fieldshift.seasons.align import build_calendar

ActionKind = Literal["harvest", "seed", "terminate", "plant", "window", "check"]
_ORDER = {"harvest": 0, "seed": 1, "window": 2, "check": 3, "terminate": 4, "plant": 5}
#: Checks are shown only when a person has something to do or look at.
_IN_SEASON_STAGES = frozenset({"season", "reproductive", "silking", "flowering"})
_IN_SEASON_TYPES = frozenset({"weather_tolerance", "water_demand", "light_requirement"})
_SUITABILITY_WITH_ACTION = {"caution", "avoid", "preferred", "acceptable"}


class Evidence(BaseModel):
    rule_id: str
    status: Status
    verdict: str | None = None
    reason: str
    reference: dict[str, Any] | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    source: dict[str, Any]


class Action(BaseModel):
    action_id: str
    kind: ActionKind
    date: date
    end_date: date | None = None  # windows only
    label: str
    zone: str | None = None
    trigger: str
    evidence: list[Evidence] = Field(default_factory=list)
    status: Status = Status.COMPLETE
    flagged: bool = False


class ActionCalendar(BaseModel):
    status: Status  # complete | invalid_input | unsupported
    plan_id: str | None = None
    year: int | None = None
    actions: list[Action] = Field(default_factory=list)
    scenarios: dict[str, Any] = Field(default_factory=dict)
    zones: dict[str, Any] | None = None
    notes: list[str] = Field(default_factory=list)
    check_result: CheckResult | None = Field(default=None, exclude=True)

    def action(self, action_id: str) -> Action | None:
        return next((a for a in self.actions if a.action_id == action_id), None)


def _src(c: RuleCheck) -> dict[str, Any]:
    return c.source.model_dump(mode="json")


def _evidence(c: RuleCheck) -> Evidence:
    return Evidence(
        rule_id=c.rule_id, status=c.status, verdict=str(c.verdict) if c.verdict else None,
        reason=c.reason, reference=c.reference, missing_inputs=list(c.missing_inputs),
        source=_src(c),
    )  # fmt: skip


def _check_date(c: RuleCheck, rule_action: str | None, cal: SeasonCalendar) -> tuple[date, str]:
    """The day a rule's decision falls due, with the reason that day was chosen."""
    cover = cal.cover
    if cover is not None and c.crop_id == cover.crop_id:
        if c.rule_type == "termination_timing":
            return cover.terminate, "the cover crop's termination date"
        return cover.seed, "the cover crop's seeding date"
    if cal.grain is not None and c.crop_id == cal.grain.crop_id:
        return cal.grain.plant, "the winter grain's planting date"
    return cal.plant, "the planting date"


def _label(rule_text: str | None, fallback: str) -> str:
    text = (rule_text or fallback).strip()
    return text if len(text) <= 160 else text[:157].rstrip() + "..."


def _check_actions(check: CheckResult, cal: SeasonCalendar, index: CatalogIndex) -> list[Action]:
    out: list[Action] = []
    for c in sorted(check.rules, key=lambda r: r.rule_id):
        if c.status in ("inapplicable", "invalid_input"):
            continue
        rule = index.rule(c.rule_id)
        if rule is None:
            continue
        in_season_watch = (
            rule.growth_stage in _IN_SEASON_STAGES and c.rule_type in _IN_SEASON_TYPES
        )  # monitoring, not a dated action (the irrigation tools cover it)
        needs_person = (
            c.status in ("manual_check", "unknown")
            and not in_season_watch
            and (c.suitability in _SUITABILITY_WITH_ACTION or c.reference is not None)
            and not (c.reference is not None and c.rule_type != "nutrient_guidance"
                     and c.suitability is None)
        )  # fmt: skip
        if not (c.flagged or needs_person):
            continue
        due, why = _check_date(c, rule.management_action, cal)
        trigger = f"rule {c.rule_id}" + (f" ({rule.applies_when})" if rule.applies_when else "")
        if c.rule_id in GATES:
            trigger += "; fires when the spring is dry or the grower reports the concern"
        status = (
            Status.UNKNOWN if c.status == "unknown"
            else Status.MANUAL_CHECK if c.status == "manual_check" or c.flagged
            else Status.COMPLETE
        )  # fmt: skip
        out.append(
            Action(
                action_id=f"check:{c.rule_id}", kind="check", date=due,
                label=_label(rule.guidance, rule.rule_id), trigger=f"{trigger}; due on {why}",
                evidence=[_evidence(c)], status=status, flagged=c.flagged,
            )
        )  # fmt: skip
    return out


def _plan_actions(plan: Plan, cal: SeasonCalendar) -> list[Action]:
    acts = [
        Action(action_id="harvest", kind="harvest", date=cal.prev_harvest,
               label=f"Harvest {plan.previous_crop_id}", trigger="plan date (prev_harvest)"),
    ]  # fmt: skip
    if cal.cover is not None:
        acts.append(Action(action_id="seed", kind="seed", date=cal.cover.seed,
                           label=f"Seed {cal.cover.crop_id}", trigger="plan date (winter.seed)"))  # fmt: skip
        acts.append(Action(action_id="terminate", kind="terminate", date=cal.cover.terminate,
                           label=f"Terminate {cal.cover.crop_id}",
                           trigger="plan date (winter.terminate)"))  # fmt: skip
    if cal.grain is not None:
        acts.append(Action(action_id="seed", kind="seed", date=cal.grain.plant,
                           label=f"Plant {cal.grain.crop_id}", trigger="plan date (winter.plant)"))  # fmt: skip
        acts.append(Action(action_id="terminate", kind="terminate", date=cal.grain.harvest,
                           label=f"Harvest {cal.grain.crop_id}",
                           trigger="plan date (winter.harvest)"))  # fmt: skip
    acts.append(Action(action_id="plant", kind="plant", date=cal.plant,
                       label=f"Plant {plan.next_crop_id}", trigger="plan date (next_plant)"))  # fmt: skip
    acts.append(Action(action_id="spring_window", kind="window", date=cal.spring_start,
                       end_date=cal.spring_end,
                       label="Spring dryness window (the 30 days before planting)",
                       trigger="30 days before next_plant, inclusive"))  # fmt: skip
    return acts


def plan_year_issues(plan: Plan, years: Any) -> list[dict[str, str]]:
    """Typed issues for the first historical (or requested) year in which ``plan`` is invalid.

    A plan can be valid in one year and impossible in another (a Feb 28/29 cover window that
    collapses in a non-leap year), and the historical replay runs every year.
    """
    from fieldshift.contracts import InvalidPlanError

    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for y in years:
        try:
            build_calendar(plan, y)
        except InvalidPlanError as exc:
            for i in exc.issues:
                key = f"{i.field}:{i.code}"
                if key not in seen:
                    seen.add(key)
                    out.append(
                        {
                            "field": i.field,
                            "code": i.code,
                            "message": f"{i.message} (planting year {y})",
                        }
                    )
    return out


def _sort(actions: list[Action]) -> list[Action]:
    return sorted(actions, key=lambda a: (a.date, _ORDER[a.kind], a.action_id))


def build_action_calendar(
    plan: Plan,
    index: CatalogIndex,
    *,
    year: int | None = None,
    inputs: dict[str, Any] | None = None,
) -> ActionCalendar:
    """Dated actions and checks for ``plan`` in planting year ``year`` (default: next season).

    Weather-free: scenarios are added by :func:`add_scenarios`.
    """
    year = year or default_planting_year()
    check = check_plan(plan, index, year=year, inputs=inputs)
    if check.status != Status.COMPLETE or check.calendar is None:
        return ActionCalendar(
            status=check.status, plan_id=plan.plan_id, year=year,
            notes=[*check.unsupported, *[i.message for i in check.issues]], check_result=check,
        )  # fmt: skip
    cal = check.calendar
    actions = _sort([*_plan_actions(plan, cal), *_check_actions(check, cal, index)])
    notes = [p.reason for p in check.path_notes]
    return ActionCalendar(
        status=Status.COMPLETE,
        plan_id=plan.plan_id,
        year=year,
        actions=actions,
        notes=notes,
        check_result=check,
    )


# --------------------------------------------------------------------------- scenarios


def _decisions_for(
    flagged_ids: set[str], cal_actions: dict[str, Action], evals: dict[str, RuleCheck]
) -> list[dict[str, Any]]:
    out = []
    for rid in sorted(flagged_ids):
        act = cal_actions.get(f"check:{rid}")
        c = evals[rid]
        out.append(
            {
                "rule_id": rid,
                "date": act.date.isoformat() if act else None,
                "question": act.label if act else rid,
                "reason": c.reason,
                "source": _src(c),
            }
        )
    return out


def add_scenarios(
    calendar: ActionCalendar,
    plan: Plan,
    ctx: Any,
    *,
    zones: ZoneSet | None = None,
) -> ActionCalendar:
    """Attach typical / dry / wet scenarios using the plan's own dates against past springs."""
    from fieldshift.compare import engine
    from fieldshift.compare.years import years_payload

    if calendar.status != Status.COMPLETE:
        return calendar
    if plan.winter.kind == "winter_grain":
        calendar.scenarios = {
            "status": Status.UNAVAILABLE.value,
            "reason": "dry/wet scenarios are not computed for winter-grain plans; "
            "use the wheat double-crop path (POST /v1/plans/wheat)",
        }
        return calendar
    ts = engine.threshold_set_for(ctx, [plan.next_plant])
    ref = engine.reference_for(ctx, plan.next_plant)
    shortcuts = years_payload(plan, ctx)["shortcuts"]
    acts = {a.action_id: a for a in calendar.actions}
    bundles: dict[str, Any] = {}
    for name in ("typical", "dry", "wet"):
        y = shortcuts.get(name)
        if y is not None:
            bundles[name] = engine.season_bundle(plan, y, ctx, ts, ref)

    def flagged(b: Any) -> set[str]:
        return {c.rule_id for c in b.evaluation.checks if c.flagged}

    base = flagged(bundles["typical"]) if "typical" in bundles else set()
    zs = zones if zones is not None else load_zones()
    scen: dict[str, Any] = {"status": Status.COMPLETE.value}
    for name, b in bundles.items():
        evals = {c.rule_id: c for c in b.evaluation.checks}
        s = b.spring
        entry: dict[str, Any] = {
            "year": b.year,
            "spring": {
                "total_mm": s.total_mm,
                "rank": s.rank,
                "of": s.n_eligible,
                "is_dry": s.is_dry,
                "cutoff_mm": s.cutoff_mm,
                "status": str(s.status),
            },
            "wetness": {
                "gwettop_window_mean": s.wetness.gwettop,
                "gwetroot_window_mean": s.wetness.gwetroot,
                "label": "modeled",
                "status": str(s.wetness.status),
            },
            "winter": {
                "rain_outside_cover_mm": b.winter.rain_outside_cover_mm,
                "heavy_rain_days_outside_cover": b.winter.heavy_rain_days_outside_cover,
            },
            "replay": f"/v1/seasons/{b.year}/replay",
        }
        if name == "dry":
            entry["decisions_that_could_change"] = _decisions_for(flagged(b) - base, acts, evals)
            entry["decisions_note"] = (
                "Checks that fire in this dry spring but not in the typical one. The plan's dates "
                "do not move; these are the decisions that become live."
            )
        elif name == "wet":
            entry["drainage_access_checks"] = _wet_checks(zs, calendar, b)
        scen[name] = entry
    calendar.scenarios = scen
    calendar.zones = {"label": zs.label, "field_id": zs.field_id}
    return calendar


def _wet_checks(zs: ZoneSet, calendar: ActionCalendar, bundle: Any) -> dict[str, Any]:
    if not zs.zones:
        return {
            "status": Status.UNAVAILABLE.value,
            "reason": "no zones for this field",
            "items": [],
        }
    plant = next(a.date for a in calendar.actions if a.kind == "plant")
    items = []
    for z in zs.zones:
        plausible, why = collection_assessment(z, zs)
        if plausible:
            items.append(
                {
                    "zone": z.zone_id,
                    "name": z.name,
                    "due": plant.isoformat(),
                    "check": "inspect drainage and field access before planting",
                    "why": why,
                    "status": Status.MANUAL_CHECK.value,
                }
            )
    return {
        "status": Status.COMPLETE.value if zs.zones else Status.UNAVAILABLE.value,
        "basis": "zone terrain and drainage (sample zones)",
        "heavy_rain_days_outside_cover": bundle.winter.heavy_rain_days_outside_cover,
        "items": items,
    }


# --------------------------------------------------------------------------- diff


_PLAN_FIELDS = (
    "previous_crop_id", "prev_harvest", "next_crop_id", "next_plant", "region",
    "production_system", "winter.kind", "winter.crop_id", "winter.seed", "winter.terminate",
    "winter.plant", "winter.harvest",
)  # fmt: skip


def _get(plan: Plan, path: str) -> Any:
    cur: Any = plan
    for part in path.split("."):
        cur = getattr(cur, part)
    return cur


def plan_changes(before: Plan, after: Plan) -> list[dict[str, Any]]:
    return [
        {"field": f, "before": _get(before, f), "after": _get(after, f)}
        for f in _PLAN_FIELDS
        if _get(before, f) != _get(after, f)
    ]


def diff_calendars(
    before: ActionCalendar, after: ActionCalendar, before_plan: Plan, after_plan: Plan
) -> dict[str, Any]:
    """What changed between two calendars and why (the edited plan fields behind each change)."""
    edits = plan_changes(before_plan, after_plan)
    edited = {e["field"]: e for e in edits}
    changes: list[dict[str, Any]] = []
    b = {a.action_id: a for a in before.actions}
    a_ = {a.action_id: a for a in after.actions}

    cause_fields = {
        "harvest": ["prev_harvest", "previous_crop_id"],
        "seed": ["winter.seed", "winter.plant", "winter.crop_id", "winter.kind", "prev_harvest"],
        "terminate": ["winter.terminate", "winter.harvest", "winter.crop_id", "winter.kind"],
        "plant": ["next_plant", "next_crop_id"],
        "spring_window": ["next_plant"],
    }

    def cause(action_id: str) -> list[str]:
        # a check depends on crops, dates and the production system, so any edit may explain it
        fields = list(edited) if action_id.startswith("check:") else cause_fields.get(action_id, [])
        return [
            f"{f}: {edited[f]['before']} -> {edited[f]['after']}" for f in fields if f in edited
        ]

    for aid in sorted(set(b) | set(a_), key=lambda x: (x not in a_, x)):
        old, new = b.get(aid), a_.get(aid)
        if old is None and new is not None:
            changes.append({"action_id": aid, "change": "added", "date": new.date.isoformat(),
                            "label": new.label, "status": str(new.status),
                            "why": cause(aid) or ["a changed input made this action apply"]})  # fmt: skip
        elif new is None and old is not None:
            changes.append({"action_id": aid, "change": "removed", "date": old.date.isoformat(),
                            "label": old.label,
                            "why": cause(aid) or ["a changed input made this action stop applying"]})  # fmt: skip
        elif old is not None and new is not None:
            moved = (old.date, old.end_date) != (new.date, new.end_date)
            restat = (old.status, old.flagged) != (new.status, new.flagged)
            relabel = old.label != new.label
            if moved or restat or relabel:
                changes.append(
                    {
                        "action_id": aid,
                        "change": "changed",
                        "date_before": old.date.isoformat(),
                        "date_after": new.date.isoformat(),
                        "days_moved": (new.date - old.date).days,
                        "status_before": str(old.status),
                        "status_after": str(new.status),
                        "flagged_before": old.flagged,
                        "flagged_after": new.flagged,
                        "label_after": new.label,
                        "why": cause(aid) or ["inputs this action depends on changed"],
                    }
                )
    gap_before = (
        before.check_result.calendar.termination_gap_days
        if before.check_result and before.check_result.calendar
        else None
    )
    gap_after = (
        after.check_result.calendar.termination_gap_days
        if after.check_result and after.check_result.calendar
        else None
    )
    return {
        "status": Status.COMPLETE.value,
        "plan_edits": edits,
        "changes": changes,
        "termination_gap_days": {"before": gap_before, "after": gap_after},
        "unchanged": not edits and not changes,
    }
