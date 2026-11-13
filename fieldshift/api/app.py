"""FastAPI application. Phase 1 exposes only ``/health``; Phase 6 adds the core endpoints.

With ``FIELDSHIFT_OFFLINE=1`` (``make offline-demo``) the app reads only the committed
snapshot under ``data/snapshots/`` and never opens a network connection.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    app = FastAPI(title="Field Shift backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health() -> dict:
        snap = load_snapshot()
        cov = snap.manifest["coverage"]
        return {
            "status": "ok",
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
