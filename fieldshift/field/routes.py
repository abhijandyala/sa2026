"""Phase 8 HTTP routes: ``POST /v1/locations/resolve`` and ``GET /v1/soil``.

Mounted by the API app (owner: Agent A) with ``app.include_router(field_router)``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

from fieldshift.contracts import FieldIssue, Status
from fieldshift.field.location import resolve_location
from fieldshift.field.soil import get_soil, unavailable
from fieldshift.report.meta import response_meta

router = APIRouter(prefix="/v1", tags=["field"])


def _bad(resolved: Any) -> JSONResponse:
    issue = FieldIssue(field="lat/lon", code="invalid_coordinates", message=resolved.reason or "")
    return JSONResponse(
        status_code=400,
        content={"status": "invalid_input", "issues": [issue.model_dump()], **response_meta()},
    )


@router.post("/locations/resolve")
def post_resolve(body: dict[str, Any] = Body(...)) -> Any:  # noqa: B008
    """Body: ``{"lat": float, "lon": float, "region": str?, "fetch_history": bool?}``."""
    res = resolve_location(
        body.get("lat"),
        body.get("lon"),
        region=body.get("region"),
        fetch_history=bool(body.get("fetch_history", False)),
    )
    if res.status == Status.INVALID_INPUT:
        return _bad(res)
    return {"meta": response_meta(), "location": res.model_dump(mode="json")}


@router.get("/soil")
def get_soil_route(lat: float = Query(...), lon: float = Query(...)) -> Any:  # noqa: B008
    """Soil map unit at a point. SDA failures are a 200 with ``soil.status = unavailable``."""
    loc = resolve_location(lat, lon)
    if loc.status == Status.INVALID_INPUT:
        return _bad(loc)
    if loc.status == Status.UNSUPPORTED:
        return {
            "meta": response_meta(),
            "status": "unsupported",
            "code": loc.code,
            "reason": loc.reason,
            "soil": unavailable("outside North Carolina").model_dump(mode="json"),
        }
    soil = get_soil(lat, lon)
    return {"meta": response_meta(), "status": "complete", "soil": soil.model_dump(mode="json")}
