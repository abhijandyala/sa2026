"""Phase 7 HTTP routes: ``POST /v1/plans/check``, ``POST /v1/plans/find``, ``GET /v1/crops``.

Mounted by the API app (owner: Agent A) with ``app.include_router(router)``.
Every response carries ``meta = {plan_version, catalog_version, snapshot_hash, request_id}``.
Invalid input (malformed JSON, a non-object body, a bad field, an impossible chronology) is a 400
with typed ``{field, code, message}`` issues and the same metadata, never a stack trace. A plan that
is *unsupported* (an unknown crop, a region outside NC) is a 200 with ``status: "unsupported"``,
because that is a result about the plan rather than a malformed request.
"""

from __future__ import annotations

import math
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from fieldshift.compare.context import Context, get_context
from fieldshift.contracts import FieldIssue, Plan
from fieldshift.planner.checker import check_plan, default_planting_year, plan_version
from fieldshift.planner.crops import list_crops
from fieldshift.planner.finder import PRIORITIES, find_plans
from fieldshift.planner.wheat_path import demo_plan, evaluate_wheat_double_crop, plan_from_dates
from fieldshift.report.http import invalid, issue, read_object
from fieldshift.report.meta import get_index, response_meta

router = APIRouter(prefix="/v1", tags=["planner"])

MIN_YEAR, MAX_YEAR = 1900, 2200


def _prefixed(i: FieldIssue) -> dict[str, str]:
    """Chronology issues name plan fields; the request field path starts with ``plan.``."""
    return issue(f"plan.{i.field}", i.code, i.message)


def _validation_issues(exc: ValidationError, prefix: str = "") -> list[dict[str, str]]:
    return [
        issue(
            prefix + (".".join(str(p) for p in e["loc"]) or "body"),
            e["type"],
            e["msg"],
        )
        for e in exc.errors()
    ]


def _valid_input_value(v: Any) -> bool:
    """``None`` and blank strings mean "not provided"; anything else must be a finite number."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return True
    if isinstance(v, bool) or not isinstance(v, int | float | str):
        return False
    try:
        return math.isfinite(float(v))
    except (ValueError, OverflowError):
        return False


def _parse_common(body: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Validate ``plan``, ``year`` and ``inputs``. Returns ``(parsed, issues)``."""
    issues: list[dict[str, str]] = []
    plan = None
    try:
        plan = Plan.model_validate(body.get("plan"))
    except ValidationError as exc:
        issues += _validation_issues(exc, "plan.")
    year = body.get("year")
    if year is not None and (
        isinstance(year, bool) or not isinstance(year, int) or not MIN_YEAR <= year <= MAX_YEAR
    ):
        issues.append(
            issue("year", "invalid_year", f"year must be an integer in {MIN_YEAR}-{MAX_YEAR}")
        )
    inputs = body.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, dict):
            issues.append(issue("inputs", "not_an_object", "inputs must be an object"))
        else:
            for k, v in inputs.items():
                if not _valid_input_value(v):
                    issues.append(
                        issue(f"inputs.{k}", "invalid_value", "input values must be finite numbers")
                    )
    if issues:
        return None, issues
    return {"plan": plan, "year": year, "inputs": inputs}, []


@router.post("/plans/check")
async def post_check(request: Request) -> Any:
    """Body: ``{"plan": Plan, "year": int?, "inputs": {soil_temp_f: ..., ...}?}``."""
    body, err = await read_object(request)
    if err is not None:
        return err
    parsed, issues = _parse_common(body)  # type: ignore[arg-type]
    if parsed is None:
        return invalid(issues)
    plan, inputs = parsed["plan"], parsed["inputs"]
    year = parsed["year"] or default_planting_year()
    result = check_plan(plan, get_index(), year=year, inputs=inputs)
    if result.status == "invalid_input":
        return invalid([_prefixed(i) for i in result.issues])
    return {
        "meta": response_meta(plan_version(plan, result.year, inputs)),
        "result": result.model_dump(mode="json"),
    }


@router.post("/plans/find")
async def post_find(request: Request) -> Any:
    """Body: ``{"plan": Plan (winter ignored), "priorities": [...]?, "year": int?}``."""
    body, err = await read_object(request)
    if err is not None:
        return err
    parsed, issues = _parse_common(body)  # type: ignore[arg-type]
    priorities = body.get("priorities") if parsed is not None else None
    if parsed is not None and priorities is not None:
        if not isinstance(priorities, list) or any(p not in PRIORITIES for p in priorities):
            issues.append(
                issue(
                    "priorities",
                    "invalid_priority",
                    f"priorities must be a list drawn from {list(PRIORITIES)}; got {priorities!r}",
                )
            )
    if parsed is None or issues:
        return invalid(issues)
    plan, inputs = parsed["plan"], parsed["inputs"]
    year = parsed["year"] or default_planting_year()
    result = find_plans(plan, get_index(), priorities=priorities, year=year, inputs=inputs)
    if result.status == "invalid_input" and result.check is not None:
        return invalid([_prefixed(i) for i in result.check.issues])
    # plan_version excludes priorities on purpose: they only reorder the same facts.
    return {
        "meta": response_meta(plan_version(plan, result.year, inputs)),
        "result": result.model_dump(mode="json"),
    }


@router.get("/crops")
def get_crops() -> dict[str, Any]:
    out = list_crops(get_index())
    return {"meta": response_meta(), **out.model_dump(mode="json")}


# --------------------------------------------------------------------------- wheat double-crop

_WHEAT_FLAT = ("prev_harvest", "wheat_plant", "wheat_harvest", "soybean_plant")
_WHEAT_OPTIONAL = ("previous_crop_id", "region", "production_system", "grower", "plan_id", "label")


@router.get("/plans/wheat/template")
def get_wheat_template() -> dict[str, Any]:
    """Demo dates for the wheat -> double-crop soybean path. ASSUMED, not grower-entered."""
    return {
        "meta": response_meta(),
        "dates_basis": "assumed",
        "plan": demo_plan().model_dump(mode="json"),
        "enter": list(_WHEAT_FLAT),
        "note": "The catalog has no numeric Piedmont wheat windows; the grower enters the dates.",
    }


@router.post("/plans/wheat")
async def post_wheat(request: Request, ctx: Annotated[Context, Depends(get_context)]) -> Any:
    """Wheat -> double-crop soybean. Body: ``{plan}`` (a winter_grain plan) or the flat dates
    ``{prev_harvest, wheat_plant, wheat_harvest, soybean_plant}`` (MM-DD), plus optional
    ``maturity_group``, ``year``, ``inputs``, ``compare_to_plan_id`` or ``compare_to_plan`` (a
    full-season soybean plan, compared as different-calendar only)."""
    body, err = await read_object(request)
    if err is not None:
        return err
    assert body is not None
    issues: list[dict[str, str]] = []
    plan: Plan | None = None
    if body.get("plan") is not None:
        try:
            plan = Plan.model_validate(body["plan"])
        except ValidationError as exc:
            issues += _validation_issues(exc, "plan.")
    else:
        missing = [k for k in _WHEAT_FLAT if body.get(k) is None]
        if missing:
            issues += [issue(k, "required", f"{k} is required (MM-DD)") for k in missing]
        else:
            try:
                plan = plan_from_dates(
                    **{k: body[k] for k in _WHEAT_FLAT},
                    **{k: body[k] for k in _WHEAT_OPTIONAL if body.get(k) is not None},
                )
            except ValidationError as exc:
                rename = {"harvest": "wheat_harvest", "plant": "wheat_plant", "winter.harvest": "wheat_harvest",
                          "winter.plant": "wheat_plant", "next_plant": "soybean_plant"}  # fmt: skip
                issues += [
                    {**i, "field": rename.get(i["field"], i["field"])}
                    for i in _validation_issues(exc, "")
                ]
            except TypeError as exc:
                issues.append(issue("body", "invalid_type", str(exc)))
    year = body.get("year")
    if year is not None and (
        isinstance(year, bool) or not isinstance(year, int) or not MIN_YEAR <= year <= MAX_YEAR
    ):
        issues.append(
            issue("year", "invalid_year", f"year must be an integer in {MIN_YEAR}-{MAX_YEAR}")
        )
    inputs = body.get("inputs")
    if inputs is not None and (
        not isinstance(inputs, dict) or not all(_valid_input_value(v) for v in inputs.values())
    ):
        issues.append(
            issue("inputs", "invalid_value", "inputs must be an object of finite numbers")
        )
    full: Plan | None = None
    if body.get("compare_to_plan") is not None and body.get("compare_to_plan_id") is not None:
        issues.append(
            issue(
                "compare_to_plan",
                "ambiguous",
                "give compare_to_plan or compare_to_plan_id, not both",
            )
        )
    elif body.get("compare_to_plan") is not None:
        try:
            full = Plan.model_validate(body["compare_to_plan"])
        except ValidationError as exc:
            issues += _validation_issues(exc, "compare_to_plan.")
    elif body.get("compare_to_plan_id") is not None:
        from fieldshift.api.samples import load_samples

        sp = load_samples().plans.get(str(body["compare_to_plan_id"]))
        if sp is None or sp.plan is None:
            issues.append(
                issue("compare_to_plan_id", "unknown_plan", "unknown or unavailable sample plan")
            )
        else:
            full = sp.plan
    if issues or plan is None:
        return invalid(issues)
    result = evaluate_wheat_double_crop(
        plan, ctx, maturity_group=body.get("maturity_group"), year=year or default_planting_year(),
        inputs=inputs, full_season_plan=full,
    )  # fmt: skip
    if result["status"] == "invalid_input":
        return invalid(
            [
                issue(
                    f"plan.{i['field']}" if i["field"] != "maturity_group" else "maturity_group",
                    i["code"],
                    i["message"],
                )
                for i in result["issues"]
            ]
        )
    return {"meta": response_meta(plan_version(plan, result["year"], inputs)), "result": result}
