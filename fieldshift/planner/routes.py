"""Phase 7 HTTP routes: ``POST /v1/plans/check``, ``POST /v1/plans/find``, ``GET /v1/crops``.

Mounted by the API app (owner: Agent A) with ``app.include_router(planner_router)``.
Every response carries ``{plan_version, catalog_version, snapshot_hash, request_id}``.
Invalid input is a 400 with typed ``{field, code, message}`` issues, never a stack trace.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from fieldshift.catalogs import CatalogIndex, load_catalog
from fieldshift.contracts import FieldIssue, Plan
from fieldshift.planner.checker import CheckResult, check_plan, plan_version
from fieldshift.planner.crops import list_crops
from fieldshift.planner.finder import PRIORITIES, FindResult, find_plans

router = APIRouter(prefix="/v1", tags=["planner"])


@lru_cache(maxsize=1)
def get_index() -> CatalogIndex:
    return CatalogIndex(load_catalog())


def _snapshot_hash() -> str | None:
    try:  # the checker uses no weather; report the snapshot the service is running with
        from fieldshift.weather.snapshot import load_snapshot

        return load_snapshot().snapshot_hash
    except Exception:  # noqa: BLE001 - metadata only, never fail a check over it
        return None


def _meta(version: str | None) -> dict[str, Any]:
    idx = get_index()
    return {
        "plan_version": version,
        "catalog_version": f"{idx.version}:{idx.catalog.manifest.content_hash[:12]}",
        "snapshot_hash": _snapshot_hash(),
        "request_id": uuid.uuid4().hex,
    }


class CheckResponse(BaseModel):
    meta: dict[str, Any]
    result: CheckResult


class FindResponse(BaseModel):
    meta: dict[str, Any]
    result: FindResult


def _invalid(exc: ValidationError) -> JSONResponse:
    issues = [
        FieldIssue(
            field=".".join(str(p) for p in e["loc"]) or "body",
            code=e["type"],
            message=e["msg"],
        ).model_dump()
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=400, content={"status": "invalid_input", "issues": issues, **_meta(None)}
    )


@router.post("/plans/check")
def post_check(body: dict[str, Any] = Body(...)) -> Any:  # noqa: B008
    """Body: ``{"plan": Plan, "year": int?, "inputs": {soil_temp_f: ..., ...}?}``."""
    try:
        plan = Plan.model_validate(body.get("plan"))
    except ValidationError as exc:
        return _invalid(exc)
    year, inputs = body.get("year"), body.get("inputs")
    result = check_plan(plan, get_index(), year=year, inputs=inputs)
    meta = _meta(plan_version(plan, year, inputs))
    if result.status == "invalid_input":
        return JSONResponse(
            status_code=400,
            content={
                "status": "invalid_input",
                "issues": [i.model_dump() for i in result.issues],
                **meta,
            },
        )
    return CheckResponse(meta=meta, result=result)


@router.post("/plans/find")
def post_find(body: dict[str, Any] = Body(...)) -> Any:  # noqa: B008
    """Body: ``{"plan": Plan (winter ignored), "priorities": [...]?, "year": int?}``."""
    try:
        plan = Plan.model_validate(body.get("plan"))
    except ValidationError as exc:
        return _invalid(exc)
    year = body.get("year")
    priorities = body.get("priorities")
    bad = [p for p in (priorities or []) if p not in PRIORITIES]
    if bad or (priorities is not None and not isinstance(priorities, list)):
        issue = FieldIssue(
            field="priorities", code="invalid_priority",
            message=f"priorities must be a list drawn from {list(PRIORITIES)}; got {priorities!r}",
        ).model_dump()  # fmt: skip
        return JSONResponse(
            status_code=400, content={"status": "invalid_input", "issues": [issue], **_meta(None)}
        )
    result = find_plans(
        plan, get_index(), priorities=priorities, year=year, inputs=body.get("inputs")
    )
    # plan_version deliberately excludes priorities: they only reorder the same facts.
    return FindResponse(meta=_meta(plan_version(plan, year, body.get("inputs"))), result=result)


@router.get("/crops")
def get_crops() -> dict[str, Any]:
    out = list_crops(get_index())
    return {"meta": _meta(None), **out.model_dump(mode="json")}
