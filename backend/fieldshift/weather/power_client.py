"""NASA POWER Daily API client. The raw response bytes are returned untouched."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from fieldshift.weather.sources import (
    POWER_COMMUNITY,
    POWER_DAILY_URL,
    POWER_PARAMETERS,
    POWER_TIME_STANDARD,
)

OFFLINE_ENV = "FIELDSHIFT_OFFLINE"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class OfflineError(RuntimeError):
    """Raised when a network fetch is attempted while FIELDSHIFT_OFFLINE=1."""


class PowerFetchError(RuntimeError):
    """The POWER API could not be read after retries."""


@dataclass(frozen=True)
class RawFetch:
    """One untouched POWER response plus everything needed to reproduce the query."""

    body: bytes
    url: str
    params: dict[str, str]
    status_code: int
    retrieved_at: str
    elapsed_s: float


def is_offline() -> bool:
    return os.environ.get(OFFLINE_ENV, "").strip().lower() in {"1", "true", "yes"}


def build_params(
    latitude: float,
    longitude: float,
    start: str,
    end: str,
    parameters: list[str] | None = None,
) -> dict[str, str]:
    """Query parameters for the point endpoint. ``start``/``end`` are ISO dates (YYYY-MM-DD)."""
    return {
        "parameters": ",".join(parameters or POWER_PARAMETERS),
        "community": POWER_COMMUNITY,
        "longitude": f"{longitude:g}",
        "latitude": f"{latitude:g}",
        "start": start.replace("-", ""),
        "end": end.replace("-", ""),
        "format": "JSON",
        "time-standard": POWER_TIME_STANDARD,
    }


def fetch_daily(
    latitude: float,
    longitude: float,
    start: str,
    end: str,
    *,
    parameters: list[str] | None = None,
    client: httpx.Client | None = None,
    timeout_s: float = 120.0,
    retries: int = 3,
    backoff_s: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> RawFetch:
    """Fetch daily POWER data for a point. Retries transport errors and 429/5xx responses.

    A 4xx other than 429 (for example 422 for an out-of-range start) is not retried and is
    raised immediately with the API's own message.
    """
    if is_offline():
        raise OfflineError(f"{OFFLINE_ENV}=1: network fetches are disabled")
    params = build_params(latitude, longitude, start, end, parameters)
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout_s)
    last_error: str = "unknown"
    try:
        for attempt in range(retries + 1):
            started = time.monotonic()
            try:
                response = http.get(POWER_DAILY_URL, params=params)
            except httpx.TransportError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code == 200:
                    return RawFetch(
                        body=response.content,
                        url=str(response.request.url),
                        params=params,
                        status_code=200,
                        retrieved_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        elapsed_s=round(time.monotonic() - started, 3),
                    )
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                if response.status_code not in RETRYABLE_STATUS:
                    raise PowerFetchError(last_error)
            if attempt < retries:
                sleep(backoff_s * (2**attempt))
        raise PowerFetchError(f"POWER fetch failed after {retries + 1} attempts: {last_error}")
    finally:
        if owns_client:
            http.close()
