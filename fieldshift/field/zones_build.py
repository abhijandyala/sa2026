"""Build ``data/samples/zones.json``: a SAMPLE field split into zones, with real terrain summaries.

Run once with network access (``python -m fieldshift.field.zones_build``); the output is committed.
The field geometry is **synthetic** (a 2 x 2 grid of ~100 m cells beside the Union County reference
point, not a real grower's field). Elevation comes from the USGS 3DEP Elevation Point Query Service
(EPQS) on a 3 x 3 point grid per zone, and drainage from USDA Soil Data Access at the zone centre.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from fieldshift.field.soil import get_soil
from fieldshift.weather.sources import UNION_COUNTY

EPQS_URL = "https://epqs.nationalmap.gov/v1/json"
OUT = Path(__file__).resolve().parents[2] / "data" / "samples" / "zones.json"
CELL_M = 100.0
POINT_SPACING_M = 40.0  # 3 x 3 points span 80 m inside a 100 m cell
M_PER_DEG_LAT = 111_320.0

ZONE_NAMES = [
    ("zone_nw", "Northwest block", -0.5, 0.5),
    ("zone_ne", "Northeast block", 0.5, 0.5),
    ("zone_sw", "Southwest block", -0.5, -0.5),
    ("zone_se", "Southeast block", 0.5, -0.5),
]


def _elev(client: httpx.Client, lat: float, lon: float) -> tuple[float, dict]:
    r = client.get(
        EPQS_URL,
        params={
            "x": f"{lon:.6f}",
            "y": f"{lat:.6f}",
            "wkid": 4326,
            "units": "Meters",
            "includeDate": "true",
        },
    )
    r.raise_for_status()
    j = r.json()
    return float(j["value"]), j


def build() -> dict:
    lat0, lon0 = UNION_COUNTY.latitude, UNION_COUNTY.longitude
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(lat0))
    zones = []
    with httpx.Client(timeout=30, headers={"User-Agent": "fieldshift-backend"}) as client:
        for zid, name, east, north in ZONE_NAMES:
            clat = lat0 + north * CELL_M / M_PER_DEG_LAT
            clon = lon0 + east * CELL_M / m_per_deg_lon
            grid: dict[tuple[int, int], float] = {}
            dates, res = set(), set()
            for i in (-1, 0, 1):  # east offset
                for j in (-1, 0, 1):  # north offset
                    lat = clat + j * POINT_SPACING_M / M_PER_DEG_LAT
                    lon = clon + i * POINT_SPACING_M / m_per_deg_lon
                    v, meta = _elev(client, lat, lon)
                    grid[(i, j)] = v
                    dates.add(meta.get("attributes", {}).get("AcquisitionDate"))
                    res.add(meta.get("resolution"))
            vals = list(grid.values())
            slopes = []
            for (i, j), v in grid.items():  # slope to every neighbour 1 step away (rise / run)
                for di, dj in ((1, 0), (0, 1)):
                    n = grid.get((i + di, j + dj))
                    if n is not None:
                        slopes.append(abs(n - v) / POINT_SPACING_M * 100.0)
            soil = get_soil(clat, clon)
            comp = soil.dominant_component
            zones.append(
                {
                    "zone_id": zid,
                    "name": name,
                    "center": {"latitude": round(clat, 6), "longitude": round(clon, 6)},
                    "size_m": CELL_M,
                    "terrain": {
                        "source": "USGS 3DEP (Elevation Point Query Service)",
                        "elevation_m": {
                            "min": round(min(vals), 2),
                            "mean": round(sum(vals) / 9, 2),
                            "max": round(max(vals), 2),
                        },
                        "slope_pct": {
                            "mean": round(sum(slopes) / len(slopes), 2),
                            "max": round(max(slopes), 2),
                        },
                        "points": 9,
                        "point_spacing_m": POINT_SPACING_M,
                        "resolution_m": sorted(r for r in res if r is not None),
                        "acquisition_dates": sorted(d for d in dates if d),
                        "retrieved_on": datetime.now(UTC).strftime("%Y-%m-%d"),
                        "terrain_date": min(
                            (
                                datetime.strptime(d, "%m/%d/%Y").date().isoformat()
                                for d in dates
                                if d
                            ),
                            default=None,
                        ),
                        "derivation": "usgs",
                    },
                    "drainage": {
                        "class": comp.drainage_class if comp else None,
                        "source": "USDA Soil Data Access (map unit component at the zone centre)",
                        "component": comp.name if comp else None,
                        "survey_version": soil.survey_version,
                        "status": soil.status.value,
                        "derivation": "usda",
                    },
                }
            )
    return {
        "_label": "SAMPLE DATA: synthetic field geometry beside the Union County reference point; terrain and drainage are real public data",
        "field_id": "sample_field",
        "reference_point": UNION_COUNTY.id,
        "zones": zones,
    }


if __name__ == "__main__":
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    sys.stdout.write(f"wrote {OUT}\n")
