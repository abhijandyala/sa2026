"""Winter wheat -> double-crop soybean path (Phase 12).

Catalog v2 has wheat and double-crop soybean rows but **no numeric Piedmont calendar windows**
(wheat planting is map-relative, harvest is context only, the double-crop soybean window is prose).
So the grower enters three dates (wheat planting, wheat harvest, soybean planting) and the path:

* moves the soybean planting window to **after the wheat harvest** (the grower's date, not a
  catalog window) and keeps the catalog's June-to-early-July timing as context only;
* checks the soybean **maturity group** with ``sb_v2_mg_mid_june``, ``sb_v2_mg_mid_july`` and
  ``sb_rc_03`` (MG below 4 is a caution), each row used only in its own planting-date context;
* shows qualitative and map-based wheat rows as ``manual_check`` and ``organic_grain`` rows as
  ``inapplicable`` to a conventional plan (the rule engine decides, with reasons);
* computes the double-crop spring dryness against **its own window baseline** (the 30 days before
  the soybean planting date over 1981-2025) and labels it that way;
* compares with full-season soybean only as **different-calendar**: raw totals side by side, never
  a shared percentile, rank or dry label.

If the catalog has no wheat planting rows (catalog v1) the path is
``unavailable: catalog_missing`` and everything else keeps working. SMAP is not included.
"""

from __future__ import annotations

import statistics
from datetime import date
from typing import Any

from fieldshift.catalogs.index import CatalogIndex
from fieldshift.contracts import FieldIssue, InvalidPlanError, Plan, Status, WinterManagement
from fieldshift.metrics.rules import RuleCheck, evaluate_season
from fieldshift.planner.checker import _unsupported, default_planting_year
from fieldshift.planner.wheat import WHEAT, wheat_catalog_state
from fieldshift.seasons.align import build_calendar

MG_RULES = ("sb_v2_mg_mid_june", "sb_v2_mg_mid_july", "sb_rc_03")
SOYBEAN_TIMING_CONTEXT = "sb_v2_pw_after_wheat_context"
DELAY_RULE = "sb_v2_pw_delay_yield"
DEMO_DATES = {
    "prev_harvest": "09-20",
    "wheat_plant": "10-25",
    "wheat_harvest": "06-05",
    "soybean_plant": "06-12",
}


def plan_from_dates(
    *,
    prev_harvest: str,
    wheat_plant: str,
    wheat_harvest: str,
    soybean_plant: str,
    previous_crop_id: str = "field_corn",
    plan_id: str = "corn_soy__wheat_dc",
    label: str | None = "Winter wheat, then double-crop soybean",
    region: str | None = "NC Piedmont",
    production_system: str | None = None,
    **extra: Any,
) -> Plan:
    """The grower's three dates as a ``winter_grain`` plan (raises ``ValidationError``)."""
    return Plan(
        plan_id=plan_id, label=label, previous_crop_id=previous_crop_id, prev_harvest=prev_harvest,
        winter=WinterManagement(kind="winter_grain", crop_id=WHEAT, plant=wheat_plant, harvest=wheat_harvest),
        next_crop_id="soybean", next_plant=soybean_plant, region=region,
        production_system=production_system, **extra,
    )  # fmt: skip


def demo_plan() -> Plan:
    """Demo dates for trying the path. ASSUMED, not grower-entered."""
    return plan_from_dates(**DEMO_DATES, production_system="conventional")


def _rule_line(c: RuleCheck) -> dict[str, Any]:
    return {
        "rule_id": c.rule_id, "status": c.status, "verdict": c.verdict, "flagged": c.flagged,
        "condition_met": c.condition_met, "reason": c.reason, "reference": c.reference,
        "missing_inputs": c.missing_inputs, "suitability": c.suitability, "source": c.source.model_dump(mode="json"),
    }  # fmt: skip


def _spring_block(plan: Plan, ctx: Any, ts: Any, label: str) -> dict[str, Any]:
    from fieldshift.compare import engine
    from fieldshift.compare.eras import compare_eras, dry_spring_indicator
    from fieldshift.metrics.spring import SPRING_DRY_PREFIX

    bundles = engine.season_bundles(plan, ctx, ts)
    springs = {b.year: b.spring for b in bundles}
    eligible = [s for s in springs.values() if s.eligible]
    dry_years = [s.year for s in springs.values() if s.is_dry]
    name = f"{SPRING_DRY_PREFIX}{plan.next_plant}"
    cutoff = ts.get(name)
    totals = sorted(s.total_mm for s in eligible if s.total_mm is not None)
    median = round(float(statistics.median(totals)), 3) if totals else None
    ind = dry_spring_indicator(springs)
    era = compare_eras("dry_spring", ind, ts, threshold_names=[name])
    first = bundles[0].cal
    return {
        "label": label,
        "baseline": "own_window_baseline",
        "baseline_note": (
            f"Dry/wet labels and ranks use only the 1981-2025 totals for this plan's own 30-day "
            f"window before {plan.next_plant}, not any other planting window."
        ),
        "window": {
            "plant_md": plan.next_plant,
            "days": 30,
            "example": {
                "year": first.year,
                "start": first.spring_start.isoformat(),
                "end": first.spring_end.isoformat(),
            },
        },  # fmt: skip
        "status": str(cutoff.status),
        "cutoff_mm": cutoff.value,
        "eligible_seasons": len(eligible),
        "dry_seasons": len(dry_years) if cutoff.value is not None else None,
        "dry_years": dry_years,
        "median_total_mm": median,
        "era_dry_spring": era.model_dump(mode="json"),
        "bundles": bundles,
    }


def evaluate_wheat_double_crop(
    plan: Plan,
    ctx: Any,
    *,
    maturity_group: Any = None,
    year: int | None = None,
    inputs: dict[str, Any] | None = None,
    full_season_plan: Plan | None = None,
) -> dict[str, Any]:
    """Evaluate a ``winter_grain`` wheat -> soybean plan. Never raises for plan problems."""
    from fieldshift.compare import engine

    index: CatalogIndex = ctx.index
    year = year or default_planting_year()
    base: dict[str, Any] = {
        "plan_id": plan.plan_id,
        "year": year,
        "path": "winter_wheat_double_crop",
    }

    w = plan.winter
    if w.kind != "winter_grain" or w.crop_id != WHEAT or plan.next_crop_id != "soybean":
        return {**base, "status": str(Status.UNSUPPORTED),
                "reason": "this path needs winter.kind=winter_grain with winter_wheat, then soybean"}  # fmt: skip
    state, why = wheat_catalog_state(index)
    if state == Status.UNAVAILABLE:
        return {
            **base,
            "status": str(Status.UNAVAILABLE),
            "reason": "catalog_missing",
            "detail": why,
        }
    problems = _unsupported(plan, index)
    if problems:
        return {**base, "status": str(Status.UNSUPPORTED), "reason": "; ".join(problems)}
    try:
        cal = build_calendar(plan, year)
    except InvalidPlanError as exc:
        return {
            **base,
            "status": str(Status.INVALID_INPUT),
            "issues": [{**i.model_dump(), "field": f"plan.{i.field}"} for i in exc.issues],
        }
    assert cal.grain is not None
    from fieldshift.compare.engine import YEARS
    from fieldshift.planner.calendar import plan_year_issues

    year_issues = [
        {**i, "field": f"plan.{i['field']}"} for i in plan_year_issues(plan, YEARS)
    ]  # the replay runs every historical year
    if year_issues:
        return {**base, "status": str(Status.INVALID_INPUT), "issues": year_issues}
    if full_season_plan is not None:
        bad = _comparison_issues(full_season_plan, YEARS, index)
        if bad:
            return {**base, "status": str(Status.INVALID_INPUT), "issues": bad}

    all_inputs, mg_issues = _effective_inputs(maturity_group, inputs)
    if mg_issues:
        return {**base, "status": str(Status.INVALID_INPUT), "issues": mg_issues}

    from fieldshift.planner.checker import facts_from_calendar

    facts = facts_from_calendar(plan, cal)
    ev = evaluate_season(facts, index, inputs=all_inputs)
    by_id = {c.rule_id: c for c in ev.checks}
    live = [c for c in ev.checks if c.status != "inapplicable"]
    inapplicable_system = [
        _rule_line(c) for c in ev.checks
        if c.status == "inapplicable" and "organic" in c.reason and c.crop_id == WHEAT
    ]  # fmt: skip
    manual = [_rule_line(c) for c in live if c.status == "manual_check" and c.crop_id in (WHEAT, "soybean")
              and (c.rule_id.startswith(("ww_", "sb_v2_")) or c.rule_id in MG_RULES)]  # fmt: skip
    mg_lines = [_rule_line(by_id[r]) for r in MG_RULES if r in by_id]

    harvest_to_plant = (cal.plant - cal.grain.harvest).days
    window = {
        "moved_to_after_wheat_harvest": True,
        "earliest_planting_date": cal.grain.harvest.isoformat(),
        "planting_date": cal.plant.isoformat(),
        "days_after_wheat_harvest": harvest_to_plant,
        "basis": "grower-entered wheat harvest and soybean planting dates; the catalog has no numeric Piedmont window",
        "catalog_context": _context_line(by_id.get(SOYBEAN_TIMING_CONTEXT)),
        "delay_caution": _rule_line(by_id[DELAY_RULE]) if DELAY_RULE in by_id else None,
        "notes": (["soybean is planted on the wheat harvest day"] if harvest_to_plant == 0 else []),
    }  # fmt: skip
    dates = {
        "previous_harvest": cal.prev_harvest.isoformat(),
        "wheat_plant": cal.grain.plant.isoformat(),
        "wheat_harvest": cal.grain.harvest.isoformat(),
        "soybean_plant": cal.plant.isoformat(),
        "wheat_season_days": cal.grain.days,
        "harvest_to_plant_days": harvest_to_plant,
        "winter_days": cal.winter_days,
        "basis": "grower",
    }

    ts = engine.threshold_set_for(ctx, [plan.next_plant])
    sp = _spring_block(plan, ctx, ts, "Double-crop soybean spring window (own baseline)")
    bundles = sp.pop("bundles")
    own_flags = _per_year_mg(bundles, index, all_inputs)

    out: dict[str, Any] = {
        **base,
        "status": str(Status.COMPLETE if state == Status.COMPLETE else Status.PARTIAL),
        "catalog_state": {"status": str(state), "reason": why},
        "dates": dates,
        "soybean_planting_window": window,
        "maturity_group": {
            "input": all_inputs.get("maturity_group"),
            "status": "complete" if "maturity_group" in all_inputs else str(Status.UNKNOWN),
            "missing": [] if "maturity_group" in all_inputs else ["maturity_group"],
            "planting_context": _planting_context(cal.plant),
            "checks": mg_lines,
        },
        "rule_checks": {
            "manual_check": manual,
            "inapplicable_to_this_production_system": inapplicable_system,
            # checks that cannot be decided yet, with what is missing (for example the
            # production system, which decides whether the organic_grain rows apply)
            "unknown": [_rule_line(c) for c in live if c.status == "unknown"],
            "flagged": [r for r in (_rule_line(c) for c in live) if r["flagged"]],
        },
        "spring": sp,
        "winter_exposure": {
            "status": str(Status.UNAVAILABLE),
            "reason": "rain-outside-cover exposure is not computed for harvested winter grain",
        },
        "wetness": {
            "label": "modeled",
            "note": "see the replay for aligned daily GWETTOP/GWETROOT",
        },
        "year_constant_checks": own_flags,
        "notes": [
            "Check results do not vary by season here: dates and maturity group are the grower's.",
            "SMAP soil-moisture comparison is not included.",
        ],
    }
    if full_season_plan is not None:
        out["cross_calendar"] = _cross_calendar(full_season_plan, plan, sp, ctx, index)
    return out


def _comparison_issues(full: Plan, years: Any, index: CatalogIndex) -> list[dict[str, str]]:
    """The comparison plan must be a supported, valid full-season soybean plan in every year."""
    from fieldshift.planner.calendar import plan_year_issues

    unsupported = _unsupported(full, index)  # unknown crops, wrong crop roles, non-NC region
    if unsupported:
        return [
            {"field": "compare_to_plan", "code": "unsupported", "message": m} for m in unsupported
        ]
    if full.next_crop_id != "soybean" or full.winter.kind == "winter_grain":
        return [{"field": "compare_to_plan", "code": "not_full_season_soybean",
                 "message": "the comparison plan must be a full-season soybean plan"}]  # fmt: skip
    return [{**i, "field": f"compare_to_plan.{i['field']}"} for i in plan_year_issues(full, years)]


def _effective_inputs(
    maturity_group: Any, inputs: dict[str, Any] | None
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Merge ``maturity_group`` and ``inputs`` into one validated input set.

    The top-level value and ``inputs.maturity_group`` must agree if both are given. A blank or
    null value means "not entered" (unknown), never 0; a real 0 is kept.
    """
    out = {k: v for k, v in (inputs or {}).items() if k != "maturity_group"}
    candidates: list[tuple[str, Any]] = []
    for field, raw in (
        ("maturity_group", maturity_group),
        ("inputs.maturity_group", (inputs or {}).get("maturity_group")),
    ):
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        issue = _mg_issue(raw, field)
        if issue is not None:
            return {}, [issue.model_dump()]
        candidates.append((field, float(raw)))
    values = {v for _, v in candidates}
    if len(values) > 1:
        return {}, [{"field": "inputs.maturity_group", "code": "conflict",
                     "message": "maturity_group and inputs.maturity_group disagree"}]  # fmt: skip
    if values:
        out["maturity_group"] = values.pop()
    return out, []


def _mg_issue(mg: Any, field: str = "maturity_group") -> FieldIssue | None:
    if mg is None or (isinstance(mg, str) and not mg.strip()):
        return None
    try:
        v = float(mg)
    except (TypeError, ValueError, OverflowError):
        v = float("nan")
    if isinstance(mg, bool) or v != v or v in (float("inf"), float("-inf")) or not 0 <= v <= 10:
        return FieldIssue(
            field=field,
            code="invalid_value",
            message="maturity_group must be a number from 0 to 10",
        )
    return None


def _context_line(c: RuleCheck | None) -> dict[str, Any] | None:
    if c is None:
        return None
    return {**_rule_line(c), "kind": "context only; not a calendar rule"}


def _planting_context(plant: date) -> dict[str, Any]:
    from fieldshift.metrics.rules import PLANTING_CONTEXT

    md = (plant.month, plant.day)
    inside = []
    for rid, (s, e) in PLANTING_CONTEXT.items():
        (sm, sd), (em, ed) = map(int, s.split("-")), map(int, e.split("-"))
        if (sm, sd) <= md <= (em, ed):
            inside.append(rid)
    return {
        "plant_date": plant.isoformat(),
        "rows_in_context": inside,
        "note": (
            "the planting date matches the " + " and ".join(inside) + " row(s)" if inside
            else "the planting date is between the mid-June and mid-July rows: both are manual_check"
        ),
        "contexts": {rid: list(v) for rid, v in PLANTING_CONTEXT.items()},
        "assumption": "mid-month is read as the 15th plus or minus one week",
    }  # fmt: skip


def _per_year_mg(bundles: list[Any], index: CatalogIndex, inputs: dict[str, Any]) -> dict[str, Any]:
    """The MG/rotation checks do not depend on the weather year; confirm with every season."""
    flagged_by_year: dict[int, list[str]] = {}
    for b in bundles:
        e = evaluate_season(b.facts, index, inputs=inputs)
        flagged_by_year[b.year] = sorted(c.rule_id for c in e.checks if c.flagged)
    distinct = {tuple(v) for v in flagged_by_year.values()}
    return {
        "constant_across_seasons": len(distinct) == 1,
        "flagged_rule_ids": sorted(next(iter(distinct))) if len(distinct) == 1 else None,
        "seasons_checked": len(flagged_by_year),
    }


def _cross_calendar(
    full: Plan, dc: Plan, dc_spring: dict[str, Any], ctx: Any, index: CatalogIndex
) -> dict[str, Any]:
    from fieldshift.compare import engine

    if full.next_crop_id != "soybean" or full.winter.kind == "winter_grain":
        return {"label": "different-calendar", "status": str(Status.INVALID_INPUT),
                "reason": "the comparison plan must be a full-season soybean plan"}  # fmt: skip
    ts = engine.threshold_set_for(ctx, [full.next_plant])
    fs = _spring_block(full, ctx, ts, "Full-season soybean spring window (own baseline)")
    fs.pop("bundles")
    keep = ("label", "baseline", "window", "cutoff_mm", "median_total_mm", "eligible_seasons")
    return {
        "label": "different-calendar",
        "status": str(Status.COMPLETE),
        "note": (
            "These plans plant in different calendar windows. Each has its own baseline, so ranks, "
            "percentiles and dry labels are NOT comparable across them. Only raw 30-day totals "
            "(mm) are shown side by side; no shared dry label or era result is computed."
        ),
        "full_season": {"plan_id": full.plan_id, **{k: fs[k] for k in keep}},
        "double_crop": {"plan_id": dc.plan_id, **{k: dc_spring[k] for k in keep}},
        "median_total_mm_difference": (
            round(dc_spring["median_total_mm"] - fs["median_total_mm"], 3)
            if dc_spring["median_total_mm"] is not None and fs["median_total_mm"] is not None else None
        ),
        "difference_label": "double-crop minus full-season, raw millimetres of rain in each plan's own 30-day window",
    }  # fmt: skip
