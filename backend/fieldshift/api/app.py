"""FastAPI application. Phase 1 exposes only ``/health``; Phase 6 adds the core endpoints.

With ``FIELDSHIFT_OFFLINE=1`` (``make offline-demo``) the app reads only the committed
snapshot under ``data/snapshots/`` and never opens a network connection.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from fieldshift.api.logs import AccessLogMiddleware, ErrorEnvelopeMiddleware, install_scrub_filter
from fieldshift.api.routes import router as core_router
from fieldshift.api.schemas import (
    HealthResponse,
    InvalidInputResponse,
    ServerErrorResponse,
    WeatherUnavailableResponse,
)
from fieldshift.compare import locations as places
from fieldshift.compare.context import Context, get_context
from fieldshift.compare.text import reason_text
from fieldshift.field.routes import router as field_router
from fieldshift.planner.routes import router as planner_router
from fieldshift.report.http import issue
from fieldshift.report.meta import response_meta
from fieldshift.report.routes import router as report_router
from fieldshift.tools.routes import router as tools_router
from fieldshift.weather.locations import get_index as get_location_index
from fieldshift.weather.power_client import is_offline
from fieldshift.weather.snapshot import load_snapshot, set_active_snapshot_dir

# Frontend origins: GitHub Pages (public demo) and the Vite dev server.
# Override with a comma-separated FIELDSHIFT_CORS_ORIGINS for other hosts.
DEFAULT_CORS_ORIGINS = (
    "https://abhijandyala.github.io",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",  # Vite falls back to 5174 when 5173 is taken
    "http://127.0.0.1:5174",
)


def cors_origins() -> list[str]:
    raw = os.environ.get("FIELDSHIFT_CORS_ORIGINS")
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(DEFAULT_CORS_ORIGINS)


class LocationProblem(Exception):
    """The request names a place the backend cannot answer for (see ``compare.locations``)."""

    def __init__(self, choice: places.Choice) -> None:
        self.choice = choice


_BAD = object()


def _float(v: Any) -> Any:
    """``None`` when absent, a float, or ``_BAD`` when present but not a number."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, bool) or not isinstance(v, int | float | str):
        return _BAD
    try:
        return float(v)
    except ValueError:
        return _BAD


async def _location_hints(request: Request) -> tuple[Any, Any, Any]:
    """``location_id`` and a point from the query string or a JSON body (``location_id``,
    ``location: {latitude, longitude}``, or top-level ``latitude``/``longitude``; ``lat``/``lon``
    are accepted too). Absent hints are ``None``; a present but malformed one is ``_BAD`` so the
    request is answered ``invalid_input`` instead of silently using the Union County default."""
    q = request.query_params
    loc_id: Any = q.get("location_id")
    lat: Any = q.get("latitude") or q.get("lat")
    lon: Any = q.get("longitude") or q.get("lon")
    if request.method in {"POST", "PUT", "PATCH"}:
        try:
            body = json.loads(await request.body())
        except (ValueError, UnicodeDecodeError):
            body = None
        if isinstance(body, dict):
            loc_id = body.get("location_id", loc_id)
            raw_loc = body.get("location")
            if raw_loc is not None and not isinstance(raw_loc, dict):
                return None, _BAD, _BAD
            inner = raw_loc if isinstance(raw_loc, dict) else body
            lat = inner.get("latitude", inner.get("lat", lat))
            lon = inner.get("longitude", inner.get("lon", lon))
            if isinstance(raw_loc, dict) and lat is None and lon is None:
                return None, _BAD, _BAD  # a `location` that names no coordinates
    if loc_id is not None and not isinstance(loc_id, str):
        loc_id = _BAD
    elif isinstance(loc_id, str) and not loc_id.strip():
        loc_id = None
    return loc_id, _float(lat), _float(lon)


async def _meta_for_request(request: Request) -> dict[str, Any]:
    """Response metadata for an error raised before the route ran (schema validation): the
    ``snapshot_hash`` is the one of the place the request names, or null when it names none that
    resolves; with no place named it is the Union County default's, as before."""
    meta = response_meta()
    loc_id, lat, lon = await _location_hints(request)
    if loc_id is None and lat is None and lon is None:
        return meta
    if _BAD in (loc_id, lat, lon):
        return {**meta, "snapshot_hash": None}
    choice = places.choose(loc_id, lat, lon)
    return {**meta, "snapshot_hash": choice.ctx.snapshot_hash if choice.ok and choice.ctx else None}


async def request_context(request: Request) -> Context:
    """The weather context of this request: the snapshot of the place it names, else the Union
    County default. Installed over ``get_context`` so every route (including the planner, report
    and field-note routes) follows the request's place without being edited."""
    loc_id, lat, lon = await _location_hints(request)
    if loc_id is None and lat is None and lon is None:
        return get_context()
    if _BAD in (loc_id, lat, lon):
        raise LocationProblem(places.Choice("invalid", issues=[issue(
            "location", "invalid_location",
            "location_id must be a string and latitude and longitude numbers")]))  # fmt: skip
    choice = places.choose(loc_id, lat, lon)
    if not choice.ok:
        raise LocationProblem(choice)
    assert choice.ctx is not None
    if choice.entry is not None:
        set_active_snapshot_dir(choice.entry.directory)  # response meta follows the snapshot
    return choice.ctx


def create_app() -> FastAPI:
    app = FastAPI(title="Field Shift backend", version="1.0.0")
    install_scrub_filter()
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(ErrorEnvelopeMiddleware)  # inside CORS (added below) so 500s get CORS headers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def _invalid_input(_: Request, exc: RequestValidationError) -> JSONResponse:
        """Typed bodies/queries report ``invalid_input`` (HTTP 400) like the hand-parsed routes."""
        issues = [
            issue(".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path"))
                  or "body", e["type"], e["msg"])
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=400,
            content={"status": "invalid_input", "issues": issues,
                     **await _meta_for_request(_)},
        )

    def envelope(
        status_code: int, status: str, field: str, code: str, message: str,
        headers: dict[str, str] | None = None,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={"status": status, "issues": [issue(field, code, message)], **response_meta()},
            headers=headers,
        )

    @app.exception_handler(LocationProblem)
    async def _location_problem(_: Request, exc: LocationProblem) -> JSONResponse:
        """No usable weather for the place. A bad ``location_id`` or point is ``invalid_input``
        (400); a place outside NC or with no snapshot is a result (200) with a code."""
        c = exc.choice
        if c.kind == "invalid":
            return JSONResponse(
                status_code=400,
                content={"status": "invalid_input", "issues": c.issues,
                         **{**response_meta(), "snapshot_hash": None}},
            )  # fmt: skip
        rt = reason_text(c.reason)
        body = WeatherUnavailableResponse(
            meta={**response_meta(), "snapshot_hash": None},  # type: ignore[arg-type]
            status=places.weather_location(c).status,
            code=c.code,
            reason=c.reason,
            reason_text=rt,
            weather_location=places.weather_location(c, rt),
        )
        return JSONResponse(status_code=200, content=body.model_dump(mode="json"))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        """404/405 and friends carry the same metadata envelope as every other error."""
        field = "method" if exc.status_code == 405 else "path"
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return envelope(exc.status_code, "invalid_input", field, code, str(exc.detail),
                        headers=getattr(exc, "headers", None))

    error_docs = {400: {"model": InvalidInputResponse}, 500: {"model": ServerErrorResponse}}
    for r in (core_router, planner_router, report_router, field_router, tools_router):
        app.include_router(r, responses=error_docs)
    # Routes that depend on ``get_context`` follow the request's place (location_id / point).
    app.dependency_overrides[get_context] = request_context

    @app.get("/health", response_model=HealthResponse, responses=error_docs)
    def health() -> dict:
        snap = load_snapshot()
        cov = snap.manifest["coverage"]
        return {
            "meta": response_meta(),
            "status": "complete",
            "offline": is_offline(),
            "snapshot_hash": snap.snapshot_hash,
            "weather": {
                "reference_point": snap.manifest["reference_point"]["id"],
                "first_date": cov["first_date"],
                "last_date": cov["last_date"],
                "source": "NASA POWER Daily (snapshot)",
            },
            "locations": [e.as_public() for e in get_location_index().entries],
        }

    _drop_422(app)
    return app



def _drop_422(app: FastAPI) -> None:
    """Validation errors are reported as HTTP 400 ``invalid_input``; document that, not FastAPI's 422."""
    original = app.openapi

    def openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        spec = original()
        for methods in spec.get("paths", {}).values():
            for op in methods.values():
                op.get("responses", {}).pop("422", None)
        for name in ("HTTPValidationError", "ValidationError"):
            spec.get("components", {}).get("schemas", {}).pop(name, None)
        app.openapi_schema = spec
        return spec

    app.openapi = openapi  # type: ignore[method-assign]


app = create_app()
