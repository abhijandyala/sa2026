"""FastAPI application. Phase 1 exposes only ``/health``; Phase 6 adds the core endpoints.

With ``FIELDSHIFT_OFFLINE=1`` (``make offline-demo``) the app reads only the committed
snapshot under ``data/snapshots/`` and never opens a network connection.
"""

from __future__ import annotations

from fastapi import FastAPI

from fieldshift.weather.power_client import is_offline
from fieldshift.weather.snapshot import load_snapshot


def create_app() -> FastAPI:
    app = FastAPI(title="Field Shift backend", version="0.1.0")

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
