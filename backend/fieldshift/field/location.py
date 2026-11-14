"""Resolve a point: NC bounds, POWER grid cell, weather history source, and guidance region.

``weather_supported`` and ``guidance_supported`` are separate on purpose. A point can have weather
history (any NC grid cell can be fetched) while the catalog's guidance is unknown for its region,
and the reverse.

* **Bounds.** The NC check is a coarse bounding box (no offline polygon data), so a point just over
  the border can pass. It is reported as ``bounds_basis: "bounding_box"``.
* **Weather.** A point has weather when its POWER grid cell is in the committed snapshot index
  (``data/snapshots/index.json``, owned by Agent A): ``complete`` with the place's ``location_id``
  and ``snapshot_hash``. Any other cell is ``unavailable``. Nothing is fetched from POWER here,
  and the answer is the same online and offline.
* **Region.** A caller-provided region wins; the Union County snapshot cell is Piedmont; other
  points get a conservative, approximate region from coordinates (or ``None`` near boundaries).
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field

from fieldshift.contracts import Status
from fieldshift.field.regions import normalize_field_region, region_scope
from fieldshift.weather.locations import LocationIndex, get_index
from fieldshift.weather.snapshot import DEFAULT_SNAPSHOT_DIR
from fieldshift.weather.sources import derive_grid_cell

#: (south, north, west, east) in degrees. Coarse NC bounding box.
NC_BOUNDS = (33.84, 36.59, -84.32, -75.46)

# Approximate Fall Line (Piedmont / Coastal Plain boundary) as (latitude, longitude) vertices.
_FALL_LINE = [(34.9, -79.6), (35.05, -78.95), (35.8, -78.65), (36.5, -77.7)]
_FALL_LINE_MARGIN_DEG = 0.3
_MOUNTAIN_LON = -81.9  # west of this: mountains
_MOUNTAIN_MARGIN_DEG = 0.5  # between -81.9 and -81.4 the boundary is not decided


class Bounds(BaseModel):
    in_nc: bool
    basis: str = "coarse_polygon"
    tolerance_note: str = (
        "approximate NC outline (about 10 km tolerance at the border); not a legal boundary"
    )
    south: float = NC_BOUNDS[0]
    north: float = NC_BOUNDS[1]
    west: float = NC_BOUNDS[2]
    east: float = NC_BOUNDS[3]


class WeatherSupport(BaseModel):
    supported: bool
    status: Status  # complete | unavailable
    source: str  # snapshot | none
    freshness: str  # snapshot | unavailable
    reason: str | None = None
    location_id: str | None = None  # the index place that serves this grid cell
    snapshot_hash: str | None = None
    first_date: str | None = None
    last_date: str | None = None


class GuidanceSupport(BaseModel):
    supported: bool
    status: Status  # complete | partial | unknown
    region: str | None  # tag used for rule matching (piedmont, coastal_plain, ...)
    basis: str  # provided | reference_point | approximate | none
    reason: str | None = None


class LocationResult(BaseModel):
    status: Status  # complete | partial | unsupported | invalid_input
    code: str | None = None  # "unsupported_location" outside NC
    reason: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    bounds: Bounds | None = None
    grid_cell: dict[str, Any] | None = None
    cell_id: str | None = None
    weather: WeatherSupport | None = None
    guidance: GuidanceSupport | None = None
    notes: list[str] = Field(default_factory=list)


#: Coarse NC outline as (latitude, longitude) vertices, clockwise from the northeast corner.
#: Good to roughly 10 km at the border, which is enough to reject neighbouring-state cities.
NC_OUTLINE = [
    (36.55, -75.88), (36.54, -77.00), (36.54, -80.00), (36.59, -81.68),  # Virginia border
    (36.35, -81.90), (36.14, -82.20), (36.00, -82.40), (35.90, -82.95),  # Tennessee border
    (35.77, -83.15), (35.60, -83.50), (35.55, -83.90), (35.30, -84.25), (35.00, -84.32),
    (35.00, -83.10), (35.20, -82.40), (35.19, -81.04), (34.99, -80.93),  # Georgia / S. Carolina
    (34.82, -80.80), (34.80, -79.67), (33.85, -78.55),
    (33.90, -77.95), (34.50, -76.90), (34.70, -76.50), (35.25, -75.52),  # Atlantic coast
    (36.00, -75.50),
]  # fmt: skip


def _inside(lat: float, lon: float, poly: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon (x = longitude, y = latitude)."""
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        yi, xi = poly[i]
        yj, xj = poly[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def in_nc_bounds(lat: float, lon: float) -> bool:
    s, n, w, e = NC_BOUNDS
    return s <= lat <= n and w <= lon <= e and _inside(lat, lon, NC_OUTLINE)


def cell_id(cell: dict[str, Any]) -> str:
    return f"cell_{cell['center_latitude']:+.3f}_{cell['center_longitude']:+.3f}"


def _fall_line_lon(lat: float) -> float:
    pts = _FALL_LINE
    if lat <= pts[0][0]:
        return pts[0][1]
    if lat >= pts[-1][0]:
        return pts[-1][1]
    for (la, lo), (lb, lb_lon) in zip(pts, pts[1:], strict=False):
        if la <= lat <= lb:
            return lo + (lb_lon - lo) * (lat - la) / (lb - la)
    raise AssertionError  # pragma: no cover


def approximate_region(lat: float, lon: float) -> str | None:
    """Coarse region tag from coordinates, or ``None`` when too close to a boundary to say."""
    if lon < _MOUNTAIN_LON:
        return "mountains"
    if lon < _MOUNTAIN_LON + _MOUNTAIN_MARGIN_DEG:
        return None
    line = _fall_line_lon(lat)
    if lon < line - _FALL_LINE_MARGIN_DEG:
        return "piedmont"
    if lon > line + _FALL_LINE_MARGIN_DEG:
        return "coastal_plain"
    return None


def _support_from_entry(entry: Any) -> WeatherSupport:
    """``complete`` weather from an index row; raises when the row lacks usable metadata."""
    for name in ("id", "snapshot_hash", "first_date", "last_date"):
        value = getattr(entry, name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"index row has no usable {name}")
    return WeatherSupport(
        supported=True, status=Status.COMPLETE, source="snapshot", freshness="snapshot",
        location_id=entry.id, snapshot_hash=entry.snapshot_hash,
        first_date=entry.first_date, last_date=entry.last_date,
    )  # fmt: skip


def resolve_location(
    lat: Any,
    lon: Any,
    *,
    region: str | None = None,
    fetch_history: bool = False,  # accepted for old callers; nothing is fetched
    index: LocationIndex | None = None,
) -> LocationResult:
    """Resolve a point. Never raises for bad input: the status says what is wrong.

    ``index`` is the weather snapshot index (default: the committed one)."""
    try:
        la, lo = float(lat), float(lon)
        if isinstance(lat, bool) or isinstance(lon, bool):
            raise ValueError
    except (TypeError, ValueError):
        return LocationResult(
            status=Status.INVALID_INPUT, reason="latitude and longitude must be numbers"
        )
    if not (math.isfinite(la) and math.isfinite(lo) and -90 <= la <= 90 and -180 <= lo <= 180):
        return LocationResult(
            status=Status.INVALID_INPUT,
            reason="latitude must be within [-90, 90] and longitude within [-180, 180]",
        )
    in_nc = in_nc_bounds(la, lo)
    bounds = Bounds(in_nc=in_nc)
    if not in_nc:
        return LocationResult(
            status=Status.UNSUPPORTED,
            code="unsupported_location",
            reason="the point is outside North Carolina; guidance and history cover NC only",
            latitude=la,
            longitude=lo,
            bounds=bounds,
        )

    cell = derive_grid_cell(la, lo)
    cid = cell_id(cell)
    notes: list[str] = []

    # ---- weather: only what the committed snapshot index serves
    try:
        entry = (index if index is not None else get_index()).by_cell(cid)
    except Exception:  # noqa: BLE001 - a missing or malformed index is "no weather", not a 500
        entry = None
        notes.append("the weather snapshot index could not be read")
    at_reference = entry is not None and entry.id == "union"
    weather: WeatherSupport | None = None
    if entry is not None:
        try:
            weather = _support_from_entry(entry)
        except (ValueError, TypeError, AttributeError):  # pydantic ValidationError is a ValueError
            weather = None
            notes.append("the weather snapshot index row for this grid cell is malformed")
    if weather is None:
        weather = WeatherSupport(
            supported=False, status=Status.UNAVAILABLE, source="none", freshness="unavailable",
            reason="no committed weather snapshot covers this grid cell"
            if entry is None
            else "the snapshot index row for this grid cell is malformed",
        )  # fmt: skip

    # ---- guidance region
    tag = normalize_field_region(region)
    scope = region_scope(region)
    statewide = (region or "").strip().lower() in {
        "nc",
        "north carolina",
        "north carolina statewide",
    }
    if scope == "nc" and tag is None and region and region.strip() and not statewide:
        guidance = GuidanceSupport(
            supported=False, status=Status.UNKNOWN, region=None, basis="provided",
            reason=f"region '{region}' is not in the region mapping table; guidance is unknown",
        )  # fmt: skip
    elif scope in ("outside", "unrecognized"):
        guidance = GuidanceSupport(
            supported=False, status=Status.UNKNOWN, region=None, basis="provided",
            reason=(
                f"region '{region}' is outside North Carolina"
                if scope == "outside"
                else f"region '{region}' is not one of the supported NC regions"
            ),
        )  # fmt: skip
    elif tag is not None:
        guidance = GuidanceSupport(
            supported=True, status=Status.COMPLETE, region=tag, basis="provided"
        )
    elif at_reference:
        guidance = GuidanceSupport(
            supported=True, status=Status.COMPLETE, region="piedmont", basis="reference_point",
            reason="Union County reference point (Piedmont)",
        )  # fmt: skip
    else:
        approx = approximate_region(la, lo)
        if approx is None:
            guidance = GuidanceSupport(
                supported=False, status=Status.UNKNOWN, region=None, basis="none",
                reason="the point is too close to a region boundary to infer a region; "
                "pass region explicitly",
            )  # fmt: skip
        else:
            guidance = GuidanceSupport(
                supported=True, status=Status.PARTIAL, region=approx, basis="approximate",
                reason="region inferred approximately from coordinates; confirm it",
            )  # fmt: skip

    if not weather.supported:
        notes.append("weather history is not available for this grid cell yet")
    status = (
        Status.COMPLETE
        if weather.supported and guidance.status == Status.COMPLETE
        else Status.PARTIAL
    )
    return LocationResult(
        status=status,
        latitude=la,
        longitude=lo,
        bounds=bounds,
        grid_cell=cell,
        cell_id=cid,
        weather=weather,
        guidance=guidance,
        notes=notes,
    )


__all__ = [
    "DEFAULT_SNAPSHOT_DIR",
    "NC_BOUNDS",
    "LocationResult",
    "approximate_region",
    "cell_id",
    "in_nc_bounds",
    "resolve_location",
]
