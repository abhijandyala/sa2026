"""Live conditions: NWS forecast and alerts, and the U.S. Drought Monitor for the county.

This is a separate ``live`` block with fetch time and validity. **Live data never feeds historical
checks** (replay, eras, season rules). Each source is independent: if one is down only it is
``unavailable``; the block reports ``partial`` and the rest still shows.

Cache policy (Phase 10): NWS forecast 15 min, NWS alerts 5 min, Drought Monitor 6 h. Freshness
labels: ``fresh``, ``cached(<fetched_at>)``, ``unavailable``. The NWS period forecast carries a
chance of precipitation but no rainfall depth, so rules that need forecast inches (``fc_wt_01``)
stay ``unknown`` rather than being filled in.
"""

from __future__ import annotations

import csv
import io
import math
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel

from fieldshift.contracts import Status
from fieldshift.weather.power_client import is_offline

NWS_POINTS = "https://api.weather.gov/points/{lat},{lon}"
NWS_ALERTS = "https://api.weather.gov/alerts/active"
USDM_URL = "https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent"
#: A generic client name, as NWS requires a User-Agent. No contact details are sent.
USER_AGENT = "fieldshift-backend"
NWS_TIMEOUT_S = 10.0
USDM_TIMEOUT_S = 10.0
TTL = {
    "forecast": timedelta(minutes=15),
    "alerts": timedelta(minutes=5),
    "drought": timedelta(hours=6),
}
NC_STATE_FIPS = "37"
FORECAST_PERIODS = 14  # seven days of day/night periods


class LivePart(BaseModel):
    status: Status  # complete | unavailable
    freshness: str  # fresh | cached(<time>) | unavailable
    fetched_at: str | None = None
    valid_until: str | None = None
    source: str
    reason: str | None = None
    data: dict[str, Any] | list[Any] | None = None


class LiveBlock(BaseModel):
    status: Status  # complete | partial | unavailable
    note: str = "Live data. It is never used in historical checks, replay or era comparisons."
    county_fips: str | None = None
    forecast: LivePart
    alerts: LivePart
    drought: LivePart
    derivation: str = "nws+usdm"


class LiveCache:
    """Tiny in-memory TTL cache so repeated requests do not hammer NWS / USDM."""

    def __init__(self) -> None:
        self._data: dict[tuple[str, str], tuple[datetime, Any]] = {}

    def get(self, key: tuple[str, str]) -> tuple[datetime, Any] | None:
        return self._data.get(key)

    def put(self, key: tuple[str, str], at: datetime, value: Any) -> None:
        self._data[key] = (at, value)

    def clear(self) -> None:
        self._data.clear()


DEFAULT_CACHE = LiveCache()


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _down(source: str, reason: str) -> LivePart:
    return LivePart(
        status=Status.UNAVAILABLE, freshness="unavailable", source=source, reason=reason
    )


def _part(kind: str, source: str, at: datetime, data: Any, *, cached: bool) -> LivePart:
    return LivePart(
        status=Status.COMPLETE,
        freshness=f"cached({_iso(at)})" if cached else "fresh",
        fetched_at=_iso(at),
        valid_until=_iso(at + TTL[kind]),
        source=source,
        data=data,
    )


def _cached_or_fetch(
    kind: str, key: str, source: str, now: datetime, cache: LiveCache, fetch: Any, offline: bool
) -> LivePart:
    hit = cache.get((kind, key))
    if hit is not None and now - hit[0] <= TTL[kind]:
        return _part(kind, source, hit[0], hit[1], cached=True)
    if offline:
        return _down(source, "offline mode: live sources were not queried")
    try:
        data = fetch()
    except Exception as exc:  # noqa: BLE001 - any provider failure becomes "unavailable"
        return _down(source, f"{type(exc).__name__}: {exc}")
    cache.put((kind, key), now, data)
    return _part(kind, source, now, data, cached=False)


# --------------------------------------------------------------------------- NWS


def _get_json(http: httpx.Client, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    r = http.get(
        url, params=params, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    )
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} from {url.split('?')[0]}")
    body = r.json()
    if not isinstance(body, dict):
        raise ValueError("unexpected response shape")
    return body


def _points(http: httpx.Client, lat: float, lon: float) -> dict[str, Any]:
    props = _get_json(http, NWS_POINTS.format(lat=f"{lat:.4f}", lon=f"{lon:.4f}")).get("properties")
    if not isinstance(props, dict) or "forecast" not in props:
        raise ValueError("NWS points response has no forecast link")
    return props


def county_fips(props: dict[str, Any]) -> str | None:
    """``https://api.weather.gov/zones/county/NCC179`` -> ``37179`` (NC only)."""
    url = props.get("county")
    if not isinstance(url, str):
        return None
    code = url.rstrip("/").rsplit("/", 1)[-1]  # e.g. NCC179
    if len(code) == 6 and code[:2] == "NC" and code[2] == "C" and code[3:].isdigit():
        return NC_STATE_FIPS + code[3:]
    return None


def _forecast(http: httpx.Client, props: dict[str, Any]) -> dict[str, Any]:
    body = _get_json(http, props["forecast"])
    periods = body.get("properties", {}).get("periods")
    if not isinstance(periods, list):
        raise ValueError("NWS forecast has no periods")
    out = []
    for p in periods[:FORECAST_PERIODS]:
        pop = (p.get("probabilityOfPrecipitation") or {}).get("value")
        out.append(
            {
                "name": p.get("name"),
                "start": p.get("startTime"),
                "end": p.get("endTime"),
                "temperature": p.get("temperature"),
                "temperature_unit": p.get("temperatureUnit"),
                "precip_probability_pct": pop,  # None = not given; 0 is a real 0 %
                "short_forecast": p.get("shortForecast"),
            }
        )
    return {
        "periods": out,
        "grid": f"{props.get('gridId')}/{props.get('gridX')},{props.get('gridY')}",
        "note": "NWS period forecast: chance of precipitation only, no rainfall depth",
    }


def _alerts(http: httpx.Client, lat: float, lon: float) -> list[dict[str, Any]]:
    body = _get_json(http, NWS_ALERTS, {"point": f"{lat:.4f},{lon:.4f}"})
    feats = body.get("features")
    if not isinstance(feats, list):
        raise ValueError("NWS alerts response has no features")
    out = []
    for f in feats:
        p = f.get("properties", {})
        out.append(
            {
                "event": p.get("event"),
                "severity": p.get("severity"),
                "headline": p.get("headline"),
                "starts": p.get("onset") or p.get("effective"),
                "ends": p.get("ends") or p.get("expires"),
            }
        )
    return out


# --------------------------------------------------------------------------- USDM


_CATS = ("D0", "D1", "D2", "D3", "D4")


def parse_usdm_csv(text: str) -> dict[str, Any]:
    """Most recent weekly row. Values are percent of county area in that category or worse."""
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or "MapDate" not in rows[0]:
        raise ValueError("Drought Monitor returned no rows")
    row = max(rows, key=lambda r: r["MapDate"])
    cats: dict[str, float] = {}
    for c in ("None", *_CATS):
        try:
            cats[c] = float(row[c])
        except (KeyError, ValueError, TypeError):
            raise ValueError(f"Drought Monitor row has no value for {c}") from None
        if not (math.isfinite(cats[c]) and 0.0 <= cats[c] <= 100.0):
            raise ValueError(f"Drought Monitor value for {c} is not a percentage: {cats[c]}")
    present = [c for c in _CATS if cats[c] > 0]
    return {
        "map_date": row["MapDate"],
        "valid_start": row.get("ValidStart"),
        "valid_end": row.get("ValidEnd"),
        "county": row.get("County"),
        "fips": row.get("FIPS"),
        "percent_area_at_or_worse": cats,
        "highest_category": present[-1] if present else "None",
        "label": "U.S. Drought Monitor, cumulative percent of county area (D0 = abnormally dry or worse)",
    }


def _drought(http: httpx.Client, fips: str, now: datetime) -> dict[str, Any]:
    start, end = now - timedelta(days=28), now
    r = http.get(
        USDM_URL,
        params={
            "aoi": fips,
            "startdate": f"{start.month}/{start.day}/{start.year}",
            "enddate": f"{end.month}/{end.day}/{end.year}",
            "statisticsType": "1",
        },
        headers={"User-Agent": USER_AGENT},
    )
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} from Drought Monitor")
    return parse_usdm_csv(r.text)


# --------------------------------------------------------------------------- entry point


def get_live(
    lat: float,
    lon: float,
    *,
    client: httpx.Client | None = None,
    now: datetime | None = None,
    cache: LiveCache | None = None,
    offline: bool | None = None,
) -> LiveBlock:
    """Forecast, alerts and drought for a point. Never raises."""
    now = now or datetime.now(UTC)
    cache = DEFAULT_CACHE if cache is None else cache
    offline = is_offline() if offline is None else offline
    key = f"{lat:.4f},{lon:.4f}"  # ~10 m: alerts and the county depend on the exact point
    owns = client is None
    http = client or httpx.Client(timeout=NWS_TIMEOUT_S)
    try:
        props_box: dict[str, Any] = {}

        def props() -> dict[str, Any]:
            if "p" not in props_box:
                props_box["p"] = _points(http, lat, lon)
            return props_box["p"]

        forecast = _cached_or_fetch(
            "forecast", key, "NWS api.weather.gov forecast", now, cache,
            lambda: _forecast(http, props()), offline,
        )  # fmt: skip
        alerts = _cached_or_fetch(
            "alerts", key, "NWS api.weather.gov alerts", now, cache,
            lambda: _alerts(http, lat, lon), offline,
        )  # fmt: skip

        fips: str | None = None
        hit = cache.get(("county", key))
        if hit is not None:
            fips = hit[1]
        elif not offline:
            try:
                fips = county_fips(props())
                cache.put(("county", key), now, fips)
            except Exception:  # noqa: BLE001
                fips = None
        if fips is None:
            drought = _down("U.S. Drought Monitor", "the county could not be determined")
        else:
            drought = _cached_or_fetch(
                "drought", fips, "U.S. Drought Monitor (UNL data services)", now, cache,
                lambda: _drought(http, fips, now), offline,
            )  # fmt: skip
    finally:
        if owns:
            http.close()

    # NWS (forecast + alerts) is the live feed: when it is down the block is unavailable, even if
    # an older drought reading is still cached (each part keeps showing its own state).
    nws_up = Status.COMPLETE in (forecast.status, alerts.status)
    parts = [forecast, alerts, drought]
    n_ok = sum(p.status == Status.COMPLETE for p in parts)
    if not nws_up:
        status = Status.UNAVAILABLE
    else:
        status = Status.COMPLETE if n_ok == 3 else Status.PARTIAL
    return LiveBlock(
        status=status, county_fips=fips, forecast=forecast, alerts=alerts, drought=drought
    )
