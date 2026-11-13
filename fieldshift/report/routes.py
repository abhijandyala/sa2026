"""Phase 9 HTTP routes: calendar, backup plan and field note (JSON only; the front end renders it).

* ``POST /v1/plans/calendar``       dated actions for a plan; with ``previous_plan`` also a diff of
                                    what changed and why when a crop or date is edited.
* ``POST /v1/plans/backup``         a default plan + fallback: switch condition, next check date,
                                    decision deadline, fixed-plan comparison.
* ``GET  /v1/plans/{plan_id}/note`` the field note for a sample plan (``?alternative=<plan_id>``).
* ``POST /v1/plans/note``           the field note for any plan, optionally with one alternative.

Plans are given inline (``plan``) or by sample id (``plan_id``). Bad input is a 400 with typed
issues and the response metadata. A plan the catalog or weather cannot evaluate is a 200 whose body
says ``unsupported`` / ``unavailable``.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from fieldshift.api.samples import load_samples
from fieldshift.compare.context import Context, get_context
from fieldshift.contracts import FieldIssue, Plan
from fieldshift.planner.backup import build_backup_plan, compare_fixed_plans
from fieldshift.planner.calendar import (
    add_scenarios,
    build_action_calendar,
    diff_calendars,
    plan_year_issues,
)
from fieldshift.planner.checker import default_planting_year, plan_version
from fieldshift.report.field_note import build_field_note
from fieldshift.report.http import invalid, issue, read_object
from fieldshift.report.meta import response_meta

router = APIRouter(prefix="/v1", tags=["decision-tools"])
MIN_YEAR, MAX_YEAR = 1900, 2200


def _plan_issues(exc: ValidationError, prefix: str) -> list[dict[str, str]]:
    return [
        issue(prefix + (".".join(str(p) for p in e["loc"]) or "body"), e["type"], e["msg"])
        for e in exc.errors()
    ]


def _resolve_plan(
    body: dict[str, Any], plan_key: str, id_key: str, required: bool
) -> tuple[Plan | None, dict[str, Any], list[dict[str, str]]]:
    """A plan from ``body[plan_key]`` (inline) or ``body[id_key]`` (sample id)."""
    inline, pid = body.get(plan_key), body.get(id_key)
    if inline is not None and pid is not None:
        return None, {}, [issue(plan_key, "ambiguous", f"give {plan_key} or {id_key}, not both")]
    if inline is not None:
        try:
            plan = Plan.model_validate(inline)
        except ValidationError as exc:
            return None, {}, _plan_issues(exc, f"{plan_key}.")
        sample = load_samples().plans.get(plan.plan_id)
        # an edited plan keeps the sample's "assumed dates" label only while its dates are untouched
        return (
            plan,
            {
                "dates_assumed": False
                if sample is None
                else sample.meta.get("dates_assumed") and sample.plan == plan
            },
            [],
        )
    if pid is not None:
        if not isinstance(pid, str):
            return None, {}, [issue(id_key, "invalid_type", f"{id_key} must be a string")]
        sp = load_samples().plans.get(pid)
        if sp is None:
            known = ", ".join(sorted(load_samples().plans))
            return (
                None,
                {},
                [issue(id_key, "unknown_plan", f"unknown plan '{pid}'; known plans: {known}")],
            )
        if sp.plan is None:
            return None, sp.meta, [
                issue(id_key, "plan_unavailable", f"sample plan '{pid}' is not available: "
                      f"{(sp.meta.get('unavailable') or {}).get('reason', 'unavailable')}")
            ]  # fmt: skip
        return sp.plan, sp.meta, []
    if required:
        return None, {}, [issue(plan_key, "required", f"give {plan_key} or {id_key}")]
    return None, {}, []


def _common(body: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    year = body.get("year")
    if year is not None and (
        isinstance(year, bool) or not isinstance(year, int) or not MIN_YEAR <= year <= MAX_YEAR
    ):
        issues.append(
            issue("year", "invalid_year", f"year must be an integer in {MIN_YEAR}-{MAX_YEAR}")
        )
    as_of = body.get("as_of")
    parsed_as_of: date | None = None
    if as_of is not None:
        try:
            parsed_as_of = date.fromisoformat(as_of) if isinstance(as_of, str) else None
        except ValueError:
            parsed_as_of = None
        if parsed_as_of is None:
            issues.append(issue("as_of", "invalid_date", "as_of must be an ISO date (YYYY-MM-DD)"))
    inputs = body.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, dict):
            issues.append(issue("inputs", "not_an_object", "inputs must be an object"))
        else:
            for k, v in inputs.items():
                ok = v is None or (
                    not isinstance(v, bool) and isinstance(v, int | float | str) and _finite(v)
                )
                if not ok:
                    issues.append(
                        issue(f"inputs.{k}", "invalid_value", "input values must be finite numbers")
                    )
    return {"year": year, "as_of": parsed_as_of, "inputs": inputs}, issues


def _finite(v: Any) -> bool:
    if isinstance(v, str) and not v.strip():
        return True
    try:
        return math.isfinite(float(v))
    except (ValueError, OverflowError):
        return False


def _check_plan_errors(plan: Plan, field: str, year: int, ctx: Context) -> list[dict[str, str]]:
    """Typed issues for the requested year AND every historical planting year (the replay runs
    them all, and a Feb 28/29 window can be valid in one year and impossible in another)."""
    from fieldshift.compare.engine import YEARS

    found = plan_year_issues(plan, [year, *YEARS])
    return [issue(f"{field}.{i['field']}", i["code"], i["message"]) for i in found]


@router.post("/plans/calendar")
async def post_calendar(request: Request, ctx: Annotated[Context, Depends(get_context)]) -> Any:
    """Body: ``{plan | plan_id, previous_plan?, year?, inputs?, scenarios?: bool}``."""
    body, err = await read_object(request)
    if err is not None:
        return err
    assert body is not None
    plan, _m, issues = _resolve_plan(body, "plan", "plan_id", required=True)
    prev, _pm, issues2 = _resolve_plan(body, "previous_plan", "previous_plan_id", required=False)
    common, issues3 = _common(body)
    want_scen = body.get("scenarios", True)
    issues += issues2 + issues3
    if not isinstance(want_scen, bool):
        issues.append(issue("scenarios", "invalid_type", "scenarios must be true or false"))
    if issues or plan is None:
        return invalid(issues)
    year = common["year"] or default_planting_year()
    problems = (
        _check_plan_errors(plan, "plan", year, ctx) if plan.winter.kind != "winter_grain" else []
    )
    if prev is not None and prev.winter.kind != "winter_grain":
        problems += _check_plan_errors(prev, "previous_plan", year, ctx)
    if problems:
        return invalid(problems)
    cal = build_action_calendar(plan, ctx.index, year=year, inputs=common["inputs"])
    if want_scen:
        cal = add_scenarios(cal, plan, ctx)
    out: dict[str, Any] = {
        "meta": response_meta(plan_version(plan, year, common["inputs"])),
        "calendar": cal.model_dump(mode="json"),
    }
    if prev is not None:
        pcal = build_action_calendar(prev, ctx.index, year=year, inputs=common["inputs"])
        out["diff"] = diff_calendars(pcal, cal, prev, plan)
    return out


@router.post("/plans/backup")
async def post_backup(request: Request, ctx: Annotated[Context, Depends(get_context)]) -> Any:
    """Body: ``{plan | plan_id, fallback? | fallback_id?, year?, as_of?, inputs?}``.

    Without a fallback the catalog-supported one is suggested (``fallback_source: "suggested"``).
    """
    body, err = await read_object(request)
    if err is not None:
        return err
    assert body is not None
    plan, _m, issues = _resolve_plan(body, "plan", "plan_id", required=True)
    fb, _fm, issues2 = _resolve_plan(body, "fallback", "fallback_id", required=False)
    common, issues3 = _common(body)
    issues += issues2 + issues3
    if issues or plan is None:
        return invalid(issues)
    year = common["year"] or default_planting_year()
    problems = _check_plan_errors(plan, "plan", year, ctx)
    if fb is not None:
        problems += _check_plan_errors(fb, "fallback", year, ctx)
    if problems:
        return invalid(problems)
    backup = build_backup_plan(
        plan, fb, ctx.index, year=year, as_of=common["as_of"], inputs=common["inputs"]
    )
    if backup.status == "complete":
        used_fb = fb or _suggested(backup, plan, ctx, year)
        if used_fb is not None:
            backup = compare_fixed_plans(backup, plan, used_fb, ctx)
    return {
        "meta": response_meta(plan_version(plan, year, common["inputs"])),
        "backup": backup.model_dump(mode="json"),
    }


def _suggested(backup: Any, plan: Plan, ctx: Context, year: int) -> Plan | None:
    from fieldshift.planner.backup import suggest_fallback

    return suggest_fallback(plan, ctx.index, year=year)


def _note(body: dict[str, Any], ctx: Context, alt_id: str | None) -> Any:
    plan, meta, issues = _resolve_plan(body, "plan", "plan_id", required=True)
    alt, ameta, issues2 = (
        _resolve_plan({"alternative_id": alt_id}, "alternative", "alternative_id", required=False)
        if alt_id is not None
        else _resolve_plan(body, "alternative", "alternative_id", required=False)
    )
    common, issues3 = _common(body)
    issues += issues2 + issues3
    if issues or plan is None:
        return invalid(issues)
    year = common["year"] or default_planting_year()
    problems = (
        _check_plan_errors(plan, "plan", year, ctx) if plan.winter.kind != "winter_grain" else []
    )
    if alt is not None and alt.winter.kind != "winter_grain":
        problems += _check_plan_errors(alt, "alternative", year, ctx)
    if problems:
        return invalid(problems)
    return build_field_note(
        plan, ctx, alternative=alt, year=year, as_of=common["as_of"], inputs=common["inputs"],
        dates_assumed=bool(meta.get("dates_assumed")),
        alt_dates_assumed=bool(ameta.get("dates_assumed")) if alt is not None else None,
    )  # fmt: skip


@router.post("/plans/note")
async def post_note(request: Request, ctx: Annotated[Context, Depends(get_context)]) -> Any:
    """Body: ``{plan | plan_id, alternative? | alternative_id?, year?, as_of?, inputs?}``."""
    body, err = await read_object(request)
    if err is not None:
        return err
    assert body is not None
    return _note(body, ctx, None)


@router.get("/plans/{plan_id}/note")
def get_note(
    plan_id: str,
    ctx: Annotated[Context, Depends(get_context)],
    alternative: str | None = None,
    year: str | None = None,
    as_of: str | None = None,
) -> Any:
    """The field note for a sample plan; ``alternative`` is another sample plan id."""
    body: dict[str, Any] = {"plan_id": plan_id}
    if year is not None:
        try:
            body["year"] = int(year)
        except ValueError:
            return invalid([issue("year", "invalid_year", "year must be an integer")])
    if as_of is not None:
        body["as_of"] = as_of
    return _note(body, ctx, alternative)


__all__ = ["FieldIssue", "router"]
