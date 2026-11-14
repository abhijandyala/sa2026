"""Field note for a winter-wheat -> double-crop soybean plan (Phase 9 follow-up).

Same rules as the main note (``report.field_note``): JSON only, every number is an audited object,
a missing value is ``null`` and a real 0 stays 0, years and ids are strings. What differs:

* the dates are the grower's (``dates_basis`` is ``grower`` or ``assumed`` for demo defaults);
* the spring numbers use the plan's OWN planting window and baseline;
* the maturity-group checks come first, then the unresolved ``manual_check`` rows;
* ``organic_grain`` rows that do not apply are listed as ``inapplicable``, with reasons;
* any comparison with full-season soybean is labeled ``different-calendar`` and shows raw totals
  only (no shared rank, percentile, dry label or era result);
* with catalog v1 (no wheat rows) the note is ``unavailable`` and carries no numbers.

It does not call ``compare.engine.analyze_plan``; it uses ``planner.wheat_path`` so it works
whether or not the compare engine supports winter-grain plans.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

from fieldshift.compare import engine
from fieldshift.compare.context import Context
from fieldshift.compare.eras import EraComparison
from fieldshift.contracts import Plan, Status
from fieldshift.metrics.spring import SPRING_DRY_PREFIX
from fieldshift.planner.backup import (
    build_backup_plan,
    compare_fixed_plans,
    distinct_ids,
)
from fieldshift.planner.calendar import add_scenarios, build_action_calendar
from fieldshift.planner.checker import default_planting_year, plan_version
from fieldshift.planner.wheat import wheat_catalog_state
from fieldshift.planner.wheat_path import evaluate_wheat_double_crop
from fieldshift.report import field_note as fn
from fieldshift.report.audit import AuditBook, finalize, source_ref
from fieldshift.report.meta import response_meta


def _empty(
    meta: dict[str, Any], plan: Plan, status: str, reason: str | None, **extra: Any
) -> dict[str, Any]:
    """A note with a status and no numbers (unavailable / unsupported / invalid)."""
    return {
        "meta": meta,
        "note_version": fn.NOTE_VERSION,
        "status": status,
        "path": "winter_wheat_double_crop",
        "plan": {"plan_id": plan.plan_id},
        "reason": reason,
        **extra,
        "unresolved_checks": [],
        "adviser_note": fn._adviser(),
        "limits": fn._limits(False, []),
        "audit": AuditBook().as_dict(),
    }


def _rule_line(line: dict[str, Any], n: fn._Nums) -> dict[str, Any]:
    return {
        "rule_id": line["rule_id"],
        "status": str(line["status"]),
        "verdict": line.get("verdict"),
        "flagged": line["flagged"],
        "condition_met": line.get("condition_met"),
        "suitability": line.get("suitability"),
        "reason": line["reason"],
        "text": line.get("text", ""),
        "print": bool(line.get("print", False)),
        "missing_inputs": line.get("missing_inputs", []),
        "reference": fn._reference(line.get("reference"), n, line["rule_id"]),
        "source": line.get("source"),
    }


def _mg_number(value: Any, n: fn._Nums) -> dict[str, Any] | None:
    if value is None:
        return None
    return n.book.num(
        value, "maturity group", "grower", source_ref("grower_input", "maturity_group"),
        {"what": "soybean maturity group entered by the grower"},
    )  # fmt: skip


def build_wheat_note(
    plan: Plan,
    ctx: Context,
    *,
    year: int | None = None,
    as_of: date | None = None,
    inputs: dict[str, Any] | None = None,
    maturity_group: Any = None,
    dates_assumed: bool = False,
    alternative: Plan | None = None,
    alt_dates_assumed: bool | None = None,
    compare_to_plan: Plan | None = None,
) -> dict[str, Any]:
    index = ctx.index
    year = year or default_planting_year()
    mg_in = maturity_group if maturity_group is not None else (inputs or {}).get("maturity_group")
    versioned = {**(inputs or {}), "maturity_group": mg_in}
    if compare_to_plan is not None:
        versioned["_compare_to_plan"] = compare_to_plan.model_dump(mode="json")
    meta = response_meta(plan_version(plan, year, versioned))

    state, why = wheat_catalog_state(index)
    if state == Status.UNAVAILABLE:
        return _empty(meta, plan, str(Status.UNAVAILABLE), "catalog_missing", detail=why)

    res = evaluate_wheat_double_crop(
        plan, ctx, maturity_group=maturity_group, year=year, inputs=inputs,
        full_season_plan=compare_to_plan,
    )  # fmt: skip
    if res["status"] not in (str(Status.COMPLETE), str(Status.PARTIAL)):
        return _empty(
            meta, plan, res["status"], res.get("reason"),
            issues=res.get("issues", []),
        )  # fmt: skip

    book = AuditBook()
    n = fn._Nums(book, ctx, plan, "assumed" if dates_assumed else "grower")
    ts = engine.threshold_set_for(ctx, [plan.next_plant])
    n.ts = ts

    eff_inputs = {k: v for k, v in (inputs or {}).items() if k != "maturity_group"}
    mg_value = res["maturity_group"]["input"]
    if mg_value is not None:
        eff_inputs["maturity_group"] = mg_value
    cal = add_scenarios(build_action_calendar(plan, index, year=year, inputs=eff_inputs), plan, ctx)

    d = res["dates"]
    w = res["soybean_planting_window"]
    spring = res["spring"]
    name = f"{SPRING_DRY_PREFIX}{plan.next_plant}"
    mgb = res["maturity_group"]
    rc = res["rule_checks"]

    note: dict[str, Any] = {
        "meta": meta,
        "note_version": fn.NOTE_VERSION,
        "status": res["status"],
        "path": "winter_wheat_double_crop",
        "plan": {
            "plan_id": plan.plan_id,
            "label": plan.label,
            "previous_crop": plan.previous_crop_id,
            "prev_harvest": plan.prev_harvest,
            "winter": plan.winter.model_dump(mode="json", exclude_none=True),
            "next_crop": plan.next_crop_id,
            "next_plant": plan.next_plant,
            "region": plan.region,
            "production_system": plan.production_system,
            "dates_basis": n.dates_basis,
            "grower_inputs": plan.grower.model_dump(mode="json"),
            "planting_year": str(year),
            "dates": {
                "previous_harvest": d["previous_harvest"],
                "wheat_plant": d["wheat_plant"],
                "wheat_harvest": d["wheat_harvest"],
                "soybean_plant": d["soybean_plant"],
                "wheat_season_days": n.plan_calc(
                    d["wheat_season_days"], "days", "wheat planting to harvest"
                ),
                "harvest_to_plant_days": n.plan_calc(
                    d["harvest_to_plant_days"], "days", "soybean planting - wheat harvest"
                ),
                "winter_days": n.plan_calc(
                    d["winter_days"], "days", "previous harvest to soybean planting"
                ),
            },
            "catalog_state": res["catalog_state"],
        },
        "soybean_planting_window": {
            "moved_to_after_wheat_harvest": w["moved_to_after_wheat_harvest"],
            "earliest_planting_date": w["earliest_planting_date"],
            "planting_date": w["planting_date"],
            "days_after_wheat_harvest": n.plan_calc(
                w["days_after_wheat_harvest"], "days", "soybean planting - wheat harvest"
            ),
            "basis": w["basis"],
            "catalog_context": _rule_line(w["catalog_context"], n)
            if w["catalog_context"]
            else None,
            "delay_caution": _rule_line(w["delay_caution"], n) if w["delay_caution"] else None,
            "notes": w["notes"],
        },
        "maturity_group": {
            "input": _mg_number(mgb["input"], n),
            "status": mgb["status"],
            "missing": mgb["missing"],
            "planting_context": mgb["planting_context"],
            "checks": [_rule_line(c, n) for c in mgb["checks"]],
        },
        "inapplicable_checks": [
            {
                "rule_id": x["rule_id"],
                "status": "inapplicable",
                "reason": x["reason"],
                "source": x["source"],
            }
            for x in rc["inapplicable_to_this_production_system"]
        ],
        "spring": {
            "status": spring["status"],
            "label": spring["label"],
            "baseline": spring["baseline"],
            "baseline_note": spring["baseline_note"],
            "window": {
                "plant_md": spring["window"]["plant_md"],
                "days": n.plan_calc(
                    spring["window"]["days"],
                    "days",
                    "30 days before the soybean planting date, inclusive",
                ),
                "example": spring["window"]["example"],
            },
            "dry_cutoff_mm": n.threshold(name, spring["cutoff_mm"]),
            "eligible_seasons": n.calc(
                spring["eligible_seasons"], "seasons", "seasons with a complete window"
            ),
            "dry_seasons": n.calc(
                spring["dry_seasons"], "seasons", "seasons at or below the dry cutoff"
            ),
            "dry_years": fn._years(spring["dry_years"]),
            "median_total_mm": n.calc(
                spring["median_total_mm"],
                "mm",
                "median 30-day precipitation over eligible seasons",
                ref=n.snapshot,
            ),
        },
        "eras": fn._eras_section(
            SimpleNamespace(
                eras={"dry_spring": EraComparison.model_validate(spring["era_dry_spring"])}
            ),
            n,
        ),
        "thresholds": fn._thresholds_section(ts, n),
        "calendar": fn._calendar_section(cal, n),
        "wetness": {
            "label": "modeled (a model estimate, not a field measurement)",
            "replay": "/v1/seasons/{year}/replay",
        },
    }
    if "cross_calendar" in res:
        note["cross_calendar"] = _cross_section(
            res["cross_calendar"], plan, compare_to_plan, ctx, n
        )
    note["unresolved_checks"] = _unresolved(res, cal, n)
    alts: list[dict[str, Any]] = []
    if alternative is not None:
        alts.append(
            _alternative(
                plan,
                alternative,
                ctx,
                index,
                year,
                as_of,
                eff_inputs,
                dates_assumed,
                alt_dates_assumed,
                book,
            )
        )
    note["alternatives"] = alts
    note["sources"] = fn._collect_sources(note, ctx)
    note["adviser_note"] = fn._adviser()
    note["limits"] = _limits(dates_assumed, bool(alts), "cross_calendar" in note)
    note = finalize(note, book)
    note["audit"] = book.as_dict()
    return note


def _cross_section(
    cc: dict[str, Any], dc_plan: Plan, full: Plan | None, ctx: Context, n: fn._Nums
) -> dict[str, Any]:
    """Comparison with full-season soybean: raw totals only, labeled different-calendar."""
    out: dict[str, Any] = {"label": cc["label"], "status": cc["status"], "note": cc["note"]}
    if cc["status"] != str(Status.COMPLETE) or full is None:
        return {**out, "reason": cc.get("reason")}
    full_ts = engine.threshold_set_for(ctx, [full.next_plant])
    full_n = fn._Nums(n.book, ctx, full, n.dates_basis)
    full_n.ts = full_ts

    def side(block: dict[str, Any], nums: fn._Nums, plan: Plan) -> dict[str, Any]:
        return {
            "plan_id": block["plan_id"],
            "label": block["label"],
            "baseline": block["baseline"],
            "window": {
                "plant_md": block["window"]["plant_md"],
                "days": nums.plan_calc(
                    block["window"]["days"], "days", "30 days before planting, inclusive"
                ),
                "example": block["window"]["example"],
            },
            "median_total_mm": nums.calc(
                block["median_total_mm"],
                "mm",
                "median 30-day precipitation, own window",
                ref=nums.snapshot,
            ),
            "eligible_seasons": nums.calc(
                block["eligible_seasons"], "seasons", "seasons with a complete window (own window)"
            ),
        }

    return {
        **out,
        "full_season": side(cc["full_season"], full_n, full),
        "double_crop": side(cc["double_crop"], n, dc_plan),
        "median_total_mm_difference": n.calc(
            cc["median_total_mm_difference"],
            "mm",
            "double-crop minus full-season raw median totals",
            ref=n.snapshot,
        ),
        "difference_label": cc["difference_label"],
    }


def _unresolved(res: dict[str, Any], cal: Any, n: fn._Nums) -> list[dict[str, Any]]:
    """What a person must still resolve: manual_check and unknown rows, plus anything flagged."""
    due = {
        a.action_id.removeprefix("check:"): a.date.isoformat()
        for a in cal.actions
        if a.kind == "check"
    }
    rc = res["rule_checks"]
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for group in ("flagged", "unknown", "manual_check"):
        for line in rc[group]:
            if line["rule_id"] in seen:
                continue
            seen.add(line["rule_id"])
            items.append(
                {
                    "rule_id": line["rule_id"], "status": str(line["status"]),
                    "flagged": bool(line["flagged"]), "due": due.get(line["rule_id"]),
                    "what": line["reason"], "reason": line["reason"],
                    "text": line.get("text", ""), "print": bool(line.get("print", False)),
                    "missing_inputs": line.get("missing_inputs", []),
                    "reference": fn._reference(line.get("reference"), n, line["rule_id"]),
                    "source": line.get("source"),
                }
            )  # fmt: skip
    for p in cal.check_result.path_notes if cal.check_result else []:
        items.append({"rule_id": p.path, "status": str(p.status), "flagged": False, "due": None,
                      "what": "path not fully evaluable", "reason": p.reason, "text": p.text,
                      "print": False, "missing_inputs": [], "reference": None, "source": None})  # fmt: skip
    items.sort(key=lambda i: (not i["print"], not i["flagged"]))  # the printable ones first
    return items


def _alternative(
    plan: Plan,
    alt: Plan,
    ctx: Context,
    index: Any,
    year: int,
    as_of: date | None,
    inputs: dict[str, Any],
    dates_assumed: bool,
    alt_dates_assumed: bool | None,
    book: AuditBook,
) -> dict[str, Any]:
    alt = distinct_ids(plan, alt)
    basis = (
        "assumed"
        if (alt_dates_assumed if alt_dates_assumed is not None else dates_assumed)
        else "grower"
    )
    an = fn._Nums(book, ctx, alt, basis)
    backup = build_backup_plan(plan, alt, index, year=year, as_of=as_of, inputs=inputs)
    backup = compare_fixed_plans(backup, plan, alt, ctx)
    return fn._cross_calendar_alternative(plan, alt, backup, an, ctx, index, year, inputs)


def _limits(dates_assumed: bool, has_alt: bool, has_cross: bool) -> list[str]:
    out = fn._limits(dates_assumed, [])
    out.append(
        "The catalog has no numeric Piedmont wheat windows: the wheat planting, wheat harvest and "
        "soybean planting dates are the grower's. Catalog timing for double-crop soybean is context only."
    )
    out.append("Spring dry/wet numbers use this plan's own planting window and baseline.")
    if has_cross:
        out.append(
            "The comparison with full-season soybean is different-calendar: raw totals only, no shared dry label."
        )
    if has_alt:
        out.append(
            "The alternative is shown with its own window; plans in different calendars are not ranked against each other."
        )
    return out
