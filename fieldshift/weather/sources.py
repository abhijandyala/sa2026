"""Constants describing the NASA POWER source and the Union County reference point.

Everything here was checked against the live POWER Daily API on 2026-11-12:

* ``header.api`` = POWER Daily API v2.10.3
* ``header.sources`` = ``["MERRA2", "POWER"]`` for the six parameters below
* ``header.fill_value`` = -999.0, ``header.time_standard`` = LST
* The series starts 1981-01-01 (an earlier ``start`` is rejected with HTTP 422).
* Units: PRECTOTCORR mm/day, T2M* degrees C, GWET* dimensionless 0..1.

The POWER point response echoes the *requested* coordinates, not a grid-cell centre.
The MERRA-2 native grid (0.5 deg lat x 0.625 deg lon) is therefore **derived** here and
labelled as derived in the manifest.
"""

from __future__ import annotations

from dataclasses import dataclass

POWER_DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_COMMUNITY = "AG"
POWER_TIME_STANDARD = "LST"
POWER_FILL_VALUE = -999.0

# POWER parameter -> normalized column name (order is the column order in daily.parquet).
PARAMETER_TO_COLUMN: dict[str, str] = {
    "PRECTOTCORR": "precip_mm",
    "T2M_MAX": "tmax_c",
    "T2M_MIN": "tmin_c",
    "T2M": "tmean_c",
    "GWETTOP": "gwettop",
    "GWETROOT": "gwetroot",
}
POWER_PARAMETERS: list[str] = list(PARAMETER_TO_COLUMN)
VARIABLES: list[str] = list(PARAMETER_TO_COLUMN.values())

# Columns whose physical range excludes negatives, and the dimensionless ones capped at 1.
NON_NEGATIVE_COLUMNS = {"precip_mm", "gwettop", "gwetroot"}
FRACTION_COLUMNS = {"gwettop", "gwetroot"}

# Where each parameter comes from, per POWER's parameter-metadata endpoint
# (https://power.larc.nasa.gov/api/system/manager/parameters/<NAME>).
PARAMETER_NOTES: dict[str, dict[str, str]] = {
    "PRECTOTCORR": {
        "units": "mm/day",
        "definition": "MERRA-2 bias-corrected total precipitation at the surface (POWER).",
        "provenance": "modeled reanalysis product, not a gauge",
    },
    "T2M_MAX": {"units": "C", "definition": "Daily maximum 2 m air temperature (MERRA-2)."},
    "T2M_MIN": {"units": "C", "definition": "Daily minimum 2 m air temperature (MERRA-2)."},
    "T2M": {"units": "C", "definition": "Daily mean 2 m air temperature (MERRA-2)."},
    "GWETTOP": {
        "units": "1",
        "definition": "Surface soil wetness, upper ~5 cm, 0 = dry, 1 = saturated (MERRA-2).",
        "provenance": "modeled, not observed",
    },
    "GWETROOT": {
        "units": "1",
        "definition": "Root-zone soil wetness, 0 = dry, 1 = saturated (MERRA-2).",
        "provenance": "modeled, not observed",
    },
}

# MERRA-2 native grid used by POWER for the AG community.
GRID_LAT_STEP = 0.5
GRID_LON_STEP = 0.625

# Fetch span. POWER's daily record begins 1981-01-01; the end is mid-2025 so the 2025
# spring window (Apr 12 - May 11) is complete.
SNAPSHOT_START = "1981-01-01"
SNAPSHOT_END = "2025-06-30"


@dataclass(frozen=True)
class ReferencePoint:
    id: str
    name: str
    latitude: float
    longitude: float
    basis: str


# ASSUMPTION: docs/handbooks/ is still empty, so the handbook's Union County point is not
# available. Monroe, NC (the county seat) is used until the handbook value lands.
UNION_COUNTY = ReferencePoint(
    id="union_county_nc",
    name="Union County, North Carolina (Monroe)",
    latitude=34.98,
    longitude=-80.55,
    basis="assumed: county seat of Union County, NC; replace with the handbook point when it lands",
)


def derive_grid_cell(latitude: float, longitude: float) -> dict[str, float | str]:
    """Return the MERRA-2 cell (0.5 x 0.625 deg) containing the point. Derived, not API-stated."""
    lat_center = round(-90.0 + GRID_LAT_STEP * round((latitude + 90.0) / GRID_LAT_STEP), 6)
    lon_center = round(-180.0 + GRID_LON_STEP * round((longitude + 180.0) / GRID_LON_STEP), 6)
    return {
        "center_latitude": lat_center,
        "center_longitude": lon_center,
        "lat_step_deg": GRID_LAT_STEP,
        "lon_step_deg": GRID_LON_STEP,
        "basis": "derived from the MERRA-2 native grid; POWER does not return the cell",
    }
