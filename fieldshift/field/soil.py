"""USDA Soil Data Access (SDA) lookup for the map unit at a point.

SDA is a REST SQL endpoint. One query returns the map unit's components and horizons; we keep the
dominant component (largest ``comppct_r``), its surface texture, drainage class and available water
capacity (AWC) by depth, plus the survey version and provenance.

Failure is a result, not an exception: a timeout, HTTP error, empty or malformed response gives
``status="unavailable"`` with a reason, and callers carry on without soil. Results are cached on
disk for 30 days (Phase 10 cache policy); a failed refresh falls back to an older cached copy,
labeled with its fetch time.

Units: depths are cm (as published); AWC is published as cm of water per cm of soil (a fraction).
``awc_in`` converts one horizon to inches of water. A published ``0`` (bedrock) stays ``0``; a blank
stays ``None``.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from fieldshift.contracts import Status

SDA_URL = "https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest"
SDA_TIMEOUT_S = 15.0
SDA_CACHE_DAYS = 30
CM_PER_INCH = 2.54
#: Reference depth for the AWC total: the 24 in maximum rooting depth in the catalog (fc_wd_04).
AWC_REFERENCE_DEPTH_IN = 24.0
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "sda"

SQL_TEMPLATE = (
    "SELECT mu.mukey, mu.muname, l.areasymbol, l.areaname, sc.saverest, c.cokey, c.compname, "
    "c.comppct_r, c.majcompflag, c.drainagecl, c.hydgrp, h.hzname, h.hzdept_r, h.hzdepb_r, "
    "h.awc_r, tg.texdesc, tg.texture "
    "FROM mapunit mu "
    "INNER JOIN SDA_Get_Mukey_from_intersection_with_WktWgs84('point ({lon} {lat})') i "
    "ON i.mukey = mu.mukey "
    "INNER JOIN legend l ON l.lkey = mu.lkey "
    "INNER JOIN sacatalog sc ON sc.areasymbol = l.areasymbol "
    "INNER JOIN component c ON c.mukey = mu.mukey "
    "LEFT JOIN chorizon h ON h.cokey = c.cokey "
    "LEFT JOIN chtexturegrp tg ON tg.chkey = h.chkey AND tg.rvindicator = 'Yes' "
    "ORDER BY c.comppct_r DESC, c.cokey, h.hzdept_r"
)


class SoilHorizon(BaseModel):
    name: str | None
    top_cm: float | None
    bottom_cm: float | None
    texture: str | None
    texture_code: str | None
    awc_cm_per_cm: float | None  # published fraction; None = not published
    awc_in: float | None  # inches of water in this horizon; None when AWC or depths are missing


class DominantComponent(BaseModel):
    cokey: str
    name: str | None
    percent: float | None
    drainage_class: str | None
    hydrologic_group: str | None


class AwcSummary(BaseModel):
    depth_in: float
    value_in: float | None
    status: Status  # complete | partial | unavailable
    note: str | None = None


class SoilProvenance(BaseModel):
    source: str = "USDA NRCS Soil Data Access (SDA)"
    endpoint: str = SDA_URL
    query_sha256: str
    fetched_at: str
    freshness: str  # fresh | cached(<iso time>) | unavailable
    stale: bool = False
    derivation: str = "usda"


class SoilResult(BaseModel):
    status: Status  # complete | partial | unavailable
    reason: str | None = None
    mukey: str | None = None
    map_unit_name: str | None = None
    survey_area: str | None = None
    survey_area_name: str | None = None
    survey_version: str | None = None  # SDA ``saverest`` (survey area version date)
    dominant_component: DominantComponent | None = None
    surface_texture: str | None = None
    horizons: list[SoilHorizon] = Field(default_factory=list)
    awc: AwcSummary | None = None
    other_components: list[DominantComponent] = Field(default_factory=list)
    provenance: SoilProvenance | None = None
    notes: list[str] = Field(default_factory=list)


def unavailable(reason: str) -> SoilResult:
    return SoilResult(status=Status.UNAVAILABLE, reason=reason)


# --------------------------------------------------------------------------- parsing


def _num(v: Any) -> float | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _rows(table: list[list[Any]]) -> list[dict[str, Any]]:
    header, *body = table
    return [dict(zip(header, row, strict=False)) for row in body]


def _horizon(r: dict[str, Any]) -> SoilHorizon | None:
    if r.get("hzname") is None and r.get("hzdept_r") is None:
        return None
    top, bottom, awc = _num(r.get("hzdept_r")), _num(r.get("hzdepb_r")), _num(r.get("awc_r"))
    awc_in = None
    if awc is not None and top is not None and bottom is not None and bottom >= top:
        awc_in = round(awc * (bottom - top) / CM_PER_INCH, 4)
    return SoilHorizon(
        name=r.get("hzname"),
        top_cm=top,
        bottom_cm=bottom,
        texture=r.get("texdesc"),
        texture_code=r.get("texture"),
        awc_cm_per_cm=awc,
        awc_in=awc_in,
    )


def awc_to_depth(
    horizons: list[SoilHorizon], depth_in: float = AWC_REFERENCE_DEPTH_IN
) -> AwcSummary:
    """Total AWC (inches) down to ``depth_in``, prorating the horizon that crosses it."""
    limit_cm = depth_in * CM_PER_INCH
    total = 0.0
    covered = 0.0
    missing = False
    for h in horizons:
        if h.top_cm is None or h.bottom_cm is None or h.top_cm >= limit_cm:
            continue
        thick = min(h.bottom_cm, limit_cm) - h.top_cm
        if thick <= 0:
            continue
        if h.awc_cm_per_cm is None:
            missing = True
            continue
        total += h.awc_cm_per_cm * thick / CM_PER_INCH
        covered += thick
    if covered == 0:
        return AwcSummary(
            depth_in=depth_in, value_in=None, status=Status.UNAVAILABLE,
            note="no horizon with published AWC reaches this depth",
        )  # fmt: skip
    note = f"horizons cover {covered / CM_PER_INCH:.1f} of {depth_in:g} in"
    if missing or covered + 1e-9 < limit_cm:
        return AwcSummary(
            depth_in=depth_in, value_in=round(total, 3), status=Status.PARTIAL,
            note=note + "; the rest is missing or has no published AWC",
        )  # fmt: skip
    return AwcSummary(
        depth_in=depth_in, value_in=round(total, 3), status=Status.COMPLETE, note=note
    )


def parse_sda_table(table: list[list[Any]]) -> SoilResult:
    """Turn an SDA ``JSON+COLUMNNAME`` table into a :class:`SoilResult` (no provenance yet)."""
    if not table or len(table) < 2:
        return unavailable("no soil map unit was returned for this point")
    rows = _rows(table)
    by_component: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_component.setdefault(str(r["cokey"]), []).append(r)

    def pct(rs: list[dict[str, Any]]) -> float:
        return _num(rs[0].get("comppct_r")) or -1.0

    ordered = sorted(by_component.values(), key=pct, reverse=True)
    top = ordered[0]
    first = top[0]

    def comp(rs: list[dict[str, Any]]) -> DominantComponent:
        r = rs[0]
        return DominantComponent(
            cokey=str(r["cokey"]),
            name=r.get("compname"),
            percent=_num(r.get("comppct_r")),
            drainage_class=r.get("drainagecl"),
            hydrologic_group=r.get("hydgrp"),
        )

    horizons = [h for r in top if (h := _horizon(r)) is not None]
    surface = next((h for h in horizons if h.top_cm == 0), None)
    notes: list[str] = []
    status = Status.COMPLETE
    reason = None
    if not horizons:
        status, reason = Status.PARTIAL, "the dominant component has no horizon data"
    elif comp(top).drainage_class is None:
        status, reason = Status.PARTIAL, "the dominant component has no drainage class"
    if (_num(first.get("comppct_r")) or 0) < 50:
        notes.append("the dominant component is under 50% of the map unit; the field may differ")
    return SoilResult(
        status=status,
        reason=reason,
        mukey=str(first["mukey"]),
        map_unit_name=first.get("muname"),
        survey_area=first.get("areasymbol"),
        survey_area_name=first.get("areaname"),
        survey_version=first.get("saverest"),
        dominant_component=comp(top),
        surface_texture=surface.texture if surface else None,
        horizons=horizons,
        awc=awc_to_depth(horizons) if horizons else None,
        other_components=[comp(rs) for rs in ordered[1:]],
        notes=notes,
    )


# --------------------------------------------------------------------------- fetch + cache


def build_query(lat: float, lon: float) -> str:
    return SQL_TEMPLATE.format(lat=f"{lat:.6f}", lon=f"{lon:.6f}")


def _cache_path(cache_dir: Path, query: str) -> Path:
    return cache_dir / f"{hashlib.sha256(query.encode()).hexdigest()[:32]}.json"


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_cache(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _finish(
    result: SoilResult, query: str, fetched_at: str, freshness: str, stale: bool
) -> SoilResult:
    result.provenance = SoilProvenance(
        query_sha256=hashlib.sha256(query.encode()).hexdigest(),
        fetched_at=fetched_at,
        freshness=freshness,
        stale=stale,
    )
    return result


def get_soil(
    lat: float,
    lon: float,
    *,
    client: httpx.Client | None = None,
    cache_dir: Path | str | None = DEFAULT_CACHE_DIR,
    now: datetime | None = None,
    offline: bool = False,
    timeout_s: float = SDA_TIMEOUT_S,
) -> SoilResult:
    """Soil for a point. Never raises: failures become ``status="unavailable"``."""
    now = now or datetime.now(UTC)
    query = build_query(lat, lon)
    path = _cache_path(Path(cache_dir), query) if cache_dir is not None else None
    cached = _read_cache(path) if path is not None else None

    def from_cache(stale: bool) -> SoilResult:
        assert cached is not None
        res = parse_sda_table(cached["table"])
        label = f"cached({cached['fetched_at']})" + (" stale" if stale else "")
        return _finish(res, query, cached["fetched_at"], label, stale)

    if cached is not None:
        try:
            age = now - datetime.strptime(cached["fetched_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC
            )
        except (KeyError, ValueError):
            cached = None
        else:
            if age <= timedelta(days=SDA_CACHE_DAYS):
                return from_cache(stale=False)

    if offline:
        return (
            from_cache(stale=True) if cached else unavailable("offline mode: SDA was not queried")
        )

    owns = client is None
    http = client or httpx.Client(timeout=timeout_s)
    try:
        resp = http.post(
            SDA_URL, json={"query": query, "format": "JSON+COLUMNNAME"}, timeout=timeout_s
        )
        if resp.status_code != 200:
            raise RuntimeError(f"SDA returned HTTP {resp.status_code}")
        body = resp.json()
        table = body.get("Table") if isinstance(body, dict) else None
        if table is None:
            # SDA returns an empty body when the query matches nothing (point off the survey).
            result = unavailable("no soil survey data was returned for this point")
            return _finish(result, query, _iso(now), "fresh", False)
        result = parse_sda_table(table)
        fetched_at = _iso(now)
        if path is not None and result.status != Status.UNAVAILABLE:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps({"fetched_at": fetched_at, "table": table}), encoding="utf-8"
                )
            except OSError:
                pass  # caching is an optimization only
        return _finish(result, query, fetched_at, "fresh", False)
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        reason = f"SDA request failed: {type(exc).__name__}: {exc}"
        if cached is not None:
            res = from_cache(stale=True)
            res.notes.append(f"{reason}; showing the cached copy from {cached['fetched_at']}")
            return res
        return unavailable(reason)
    finally:
        if owns:
            http.close()
