"""Phase 8 HTTP routes: ``POST /v1/locations/resolve`` and ``GET /v1/soil``.

Mounted by the API app (owner: Agent A) with ``app.include_router(router)``. Invalid input is a 400
with typed issues; an SDA failure is a 200 whose ``soil.status`` is ``unavailable``.
"""

from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, Request

from fieldshift.contracts import Status
from fieldshift.field.location import resolve_location
from fieldshift.field.soil import get_soil, unavailable
from fieldshift.report.http import invalid, issue, read_object
from fieldshift.report.meta import response_meta

router = APIRouter(prefix="/v1", tags=["field"])


def _coord(value: Any, name: str, lo: float, hi: float) -> tuple[float | None, dict | None]:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None, issue(name, "invalid_coordinate", f"{name} must be a number")
    try:
        x = float(value)
    except OverflowError:
        x = math.inf
    if not math.isfinite(x) or not lo <= x <= hi:
        return None, issue(name, "invalid_coordinate", f"{name} must be within [{lo:g}, {hi:g}]")
    return x, None


@router.post("/locations/resolve")
async def post_resolve(request: Request) -> Any:
    """Body: ``{"lat": float, "lon": float, "region": str?, "fetch_history": bool?}``."""
    body, err = await read_object(request)
    if err is not None:
        return err
    assert body is not None
    problems: list[dict[str, str]] = []
    lat, p1 = _coord(body.get("lat"), "lat", -90, 90)
    lon, p2 = _coord(body.get("lon"), "lon", -180, 180)
    problems += [p for p in (p1, p2) if p]
    region = body.get("region")
    if region is not None and not isinstance(region, str):
        problems.append(issue("region", "invalid_type", "region must be a string"))
    fetch = body.get("fetch_history", False)
    if not isinstance(fetch, bool):
        problems.append(
            issue("fetch_history", "invalid_type", "fetch_history must be true or false")
        )
    if problems:
        return invalid(problems)
    res = resolve_location(lat, lon, region=region, fetch_history=fetch)
    return {"meta": response_meta(), "location": res.model_dump(mode="json")}


@router.get("/soil")
def get_soil_route(lat: str, lon: str) -> Any:
    """Soil map unit at a point. Query values are parsed here so bad ones are typed 400s."""
    problems: list[dict[str, str]] = []
    parsed: list[float] = []
    for name, raw, lo, hi in (("lat", lat, -90, 90), ("lon", lon, -180, 180)):
        try:
            value: Any = float(raw)
        except ValueError:
            value = None
        x, p = _coord(value, name, lo, hi)
        if p:
            problems.append(p)
        else:
            parsed.append(x)  # type: ignore[arg-type]
    if problems:
        return invalid(problems)
    la, lo_ = parsed
    loc = resolve_location(la, lo_)
    if loc.status == Status.UNSUPPORTED:
        return {
            "meta": response_meta(),
            "status": "unsupported",
            "code": loc.code,
            "reason": loc.reason,
            "soil": unavailable("outside North Carolina").model_dump(mode="json"),
        }
    soil = get_soil(la, lo_)  # follows FIELDSHIFT_OFFLINE; never raises
    return {"meta": response_meta(), "status": "complete", "soil": soil.model_dump(mode="json")}
