"""Phase 7 HTTP routes: ``POST /v1/plans/check``, ``POST /v1/plans/find``, ``GET /v1/crops``.

Mounted by the API app (owner: Agent A) with ``app.include_router(router)``.
Every response carries ``meta = {plan_version, catalog_version, snapshot_hash, request_id}``.
Invalid input (malformed JSON, a non-object body, a bad field, an impossible chronology) is a 400
with typed ``{field, code, message}`` issues and the same metadata, never a stack trace. A plan that
is *unsupported* (an unknown crop, a region outside NC) is a 200 with ``status: "unsupported"``,
because that is a result about the plan rather than a malformed request.
"""

from __future__ import annotations

import json
import math
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from fieldshift.contracts import FieldIssue, Plan
from fieldshift.planner.checker import check_plan, default_planting_year, plan_version
from fieldshift.planner.crops import list_crops
from fieldshift.planner.finder import PRIORITIES, find_plans
from fieldshift.report.meta import get_index, response_meta

router = APIRouter(prefix="/v1", tags=["planner"])

MIN_YEAR, MAX_YEAR = 1900, 2200


def _issue(field: str, code: str, message: str) -> dict[str, str]:
    return FieldIssue(field=field, code=code, message=message).model_dump()


def _prefixed(issue: FieldIssue) -> dict[str, str]:
    """Chronology issues name plan fields; the request field path starts with ``plan.``."""
    return _issue(f"plan.{issue.field}", issue.code, issue.message)


def _invalid(issues: list[dict[str, str]]) -> JSONResponse:
    return JSONResponse(
        status_code=400, content={"status": "invalid_input", "issues": issues, **response_meta()}
    )


def _validation_issues(exc: ValidationError, prefix: str = "") -> list[dict[str, str]]:
    return [
        _issue(
            prefix + (".".join(str(p) for p in e["loc"]) or "body"),
            e["type"],
            e["msg"],
        )
        for e in exc.errors()
    ]


async def _read_object(request: Request) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    try:
        body = json.loads(await request.body())
    except (ValueError, UnicodeDecodeError):
        return None, _invalid([_issue("body", "invalid_json", "request body is not valid JSON")])
    if not isinstance(body, dict):
        return None, _invalid(
            [_issue("body", "not_an_object", "request body must be a JSON object")]
        )
    return body, None


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
            _issue("year", "invalid_year", f"year must be an integer in {MIN_YEAR}-{MAX_YEAR}")
        )
    inputs = body.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, dict):
            issues.append(_issue("inputs", "not_an_object", "inputs must be an object"))
        else:
            for k, v in inputs.items():
                if v is not None and not isinstance(v, int | float | str) or isinstance(v, bool):
                    issues.append(
                        _issue(f"inputs.{k}", "invalid_value", "input values must be numbers")
                    )
                elif isinstance(v, float) and not math.isfinite(v):
                    issues.append(_issue(f"inputs.{k}", "invalid_value", "value must be finite"))
    if issues:
        return None, issues
    return {"plan": plan, "year": year, "inputs": inputs}, []


@router.post("/plans/check")
async def post_check(request: Request) -> Any:
    """Body: ``{"plan": Plan, "year": int?, "inputs": {soil_temp_f: ..., ...}?}``."""
    body, err = await _read_object(request)
    if err is not None:
        return err
    parsed, issues = _parse_common(body)  # type: ignore[arg-type]
    if parsed is None:
        return _invalid(issues)
    plan, inputs = parsed["plan"], parsed["inputs"]
    year = parsed["year"] or default_planting_year()
    result = check_plan(plan, get_index(), year=year, inputs=inputs)
    if result.status == "invalid_input":
        return _invalid([_prefixed(i) for i in result.issues])
    return {
        "meta": response_meta(plan_version(plan, result.year, inputs)),
        "result": result.model_dump(mode="json"),
    }


@router.post("/plans/find")
async def post_find(request: Request) -> Any:
    """Body: ``{"plan": Plan (winter ignored), "priorities": [...]?, "year": int?}``."""
    body, err = await _read_object(request)
    if err is not None:
        return err
    parsed, issues = _parse_common(body)  # type: ignore[arg-type]
    priorities = body.get("priorities") if parsed is not None else None
    if parsed is not None and priorities is not None:
        if not isinstance(priorities, list) or any(p not in PRIORITIES for p in priorities):
            issues.append(
                _issue(
                    "priorities",
                    "invalid_priority",
                    f"priorities must be a list drawn from {list(PRIORITIES)}; got {priorities!r}",
                )
            )
    if parsed is None or issues:
        return _invalid(issues)
    plan, inputs = parsed["plan"], parsed["inputs"]
    year = parsed["year"] or default_planting_year()
    result = find_plans(plan, get_index(), priorities=priorities, year=year, inputs=inputs)
    if result.status == "invalid_input" and result.check is not None:
        return _invalid([_prefixed(i) for i in result.check.issues])
    # plan_version excludes priorities on purpose: they only reorder the same facts.
    return {
        "meta": response_meta(plan_version(plan, result.year, inputs)),
        "result": result.model_dump(mode="json"),
    }


@router.get("/crops")
def get_crops() -> dict[str, Any]:
    out = list_crops(get_index())
    return {"meta": response_meta(), **out.model_dump(mode="json")}
