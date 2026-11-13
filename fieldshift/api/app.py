"""FastAPI application. Phase 1 exposes only ``/health``; Phase 6 adds the core endpoints.

With ``FIELDSHIFT_OFFLINE=1`` (``make offline-demo``) the app reads only the committed
snapshot under ``data/snapshots/`` and never opens a network connection.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from fieldshift.api.logs import AccessLogMiddleware, install_scrub_filter
from fieldshift.api.routes import router as core_router
from fieldshift.field.routes import router as field_router
from fieldshift.planner.routes import router as planner_router
from fieldshift.report.http import issue
from fieldshift.report.meta import response_meta
from fieldshift.tools.routes import router as tools_router
from fieldshift.weather.power_client import is_offline
from fieldshift.weather.snapshot import load_snapshot

# Frontend origins: GitHub Pages (public demo) and the Vite dev server.
# Override with a comma-separated FIELDSHIFT_CORS_ORIGINS for other hosts.
DEFAULT_CORS_ORIGINS = (
    "https://abhijandyala.github.io",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def cors_origins() -> list[str]:
    raw = os.environ.get("FIELDSHIFT_CORS_ORIGINS")
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(DEFAULT_CORS_ORIGINS)


def create_app() -> FastAPI:
    app = FastAPI(title="Field Shift backend", version="1.0.0")
    install_scrub_filter()
    app.add_middleware(AccessLogMiddleware)
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
            content={"status": "invalid_input", "issues": issues, **response_meta()},
        )

    for r in (core_router, planner_router, field_router, tools_router):
        app.include_router(r)

    @app.get("/health")
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
        }

    return app


app = create_app()
