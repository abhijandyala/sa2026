"""Field zones: terrain summaries, plausible water-collection zones, ponding prompts, `verify` flags.

``data/samples/zones.json`` holds SAMPLE zones (synthetic geometry, real USGS 3DEP elevation and USDA
drainage). Each zone records its terrain source, survey date, resolution and drainage.

Documented assumptions (constants below, chosen here because the catalog has no zone rules):

* A zone is a **plausible collection zone** when its drainage class is poor, or when its mean
  elevation is at or below the field's mean zone elevation AND its mean slope is at most
  ``COLLECTION_SLOPE_PCT``. This only decides where an inspection prompt is warranted; it is not a
  flood or drainage prediction.
* A ponding report is tied to heavy rain when a heavy-rain day falls within ``PONDING_RAIN_WINDOW_DAYS``
  days up to and including the report date. The heavy-rain days come from the winter metrics
  (the shared ``ThresholdSet``); this module never defines "heavy".
* Regrading or a drainage change reported **after the terrain survey date** flags that zone's
  findings ``verify`` (status ``manual_check``).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from fieldshift.contracts import Status

DEFAULT_ZONES_PATH = Path(__file__).resolve().parents[2] / "data" / "samples" / "zones.json"
COLLECTION_SLOPE_PCT = 2.0
PONDING_RAIN_WINDOW_DAYS = 3
POOR_DRAINAGE = ("poorly drained", "very poorly drained", "somewhat poorly drained")


class Range(BaseModel):
    min: float | None = None
    mean: float | None = None
    max: float | None = None


class ZoneTerrain(BaseModel):
    source: str
    elevation_m: Range
    slope_pct: Range
    points: int
    point_spacing_m: float
    resolution_m: list[float]
    acquisition_dates: list[str]
    terrain_date: str | None  # earliest acquisition: the date of the terrain survey
    retrieved_on: str
    derivation: str = "usgs"


class ZoneDrainage(BaseModel):
    cls: str | None = Field(None, alias="class")
    source: str
    component: str | None = None
    survey_version: str | None = None
    status: str
    derivation: str = "usda"

    model_config = ConfigDict(populate_by_name=True)


class Zone(BaseModel):
    zone_id: str
    name: str
    center: dict[str, float]
    size_m: float
    terrain: ZoneTerrain
    drainage: ZoneDrainage


class ZoneSet(BaseModel):
    label: str
    field_id: str
    zones: list[Zone]

    def zone(self, zone_id: str) -> Zone | None:
        return next((z for z in self.zones if z.zone_id == zone_id), None)


def load_zones(path: Path | str = DEFAULT_ZONES_PATH) -> ZoneSet:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ZoneSet(label=data["_label"], field_id=data["field_id"], zones=data["zones"])


def _field_mean_elevation(zs: ZoneSet) -> float | None:
    means = [z.terrain.elevation_m.mean for z in zs.zones if z.terrain.elevation_m.mean is not None]
    return sum(means) / len(means) if means else None


def collection_assessment(zone: Zone, zs: ZoneSet) -> tuple[bool | None, str]:
    """``(plausible_collection_zone, reason)``; ``None`` when the zone data cannot say."""
    drainage = (zone.drainage.cls or "").lower()
    if drainage in POOR_DRAINAGE:
        return True, f"drainage class is '{zone.drainage.cls}'"
    mean_elev = zone.terrain.elevation_m.mean
    slope = zone.terrain.slope_pct.mean
    field_mean = _field_mean_elevation(zs)
    if mean_elev is None or slope is None or field_mean is None:
        return None, "elevation or slope is missing for this zone"
    if mean_elev <= field_mean and slope <= COLLECTION_SLOPE_PCT:
        return True, (
            f"mean elevation {mean_elev:g} m is at or below the field mean {field_mean:.2f} m and "
            f"mean slope {slope:g}% is at most {COLLECTION_SLOPE_PCT:g}%"
        )
    return False, (
        f"mean elevation {mean_elev:g} m vs field mean {field_mean:.2f} m, mean slope {slope:g}%: "
        "water is not expected to collect"
    )


class PondingReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    zone_id: str
    reported_on: date
    note: str | None = None
    derivation: Literal["grower"] = "grower"


class ChangeReport(BaseModel):
    """Grower-reported regrading or drainage change. ``zone_id=None`` means the whole field."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["regrading", "drainage_change"]
    reported_on: date
    zone_id: str | None = None
    derivation: Literal["grower"] = "grower"


class Prompt(BaseModel):
    zone_id: str
    kind: Literal["inspect", "verify_location", "note"]
    status: Status  # manual_check: a person has to look
    reason: str
    reported_on: date
    heavy_rain_days: list[date] = Field(default_factory=list)


class ZoneFinding(BaseModel):
    zone_id: str
    name: str
    plausible_collection_zone: bool | None
    collection_reason: str
    verify: bool
    verify_reason: str | None = None
    terrain_date: str | None
    terrain_source: str
    resolution_m: list[float]
    drainage_class: str | None


class ZoneAnalysis(BaseModel):
    label: str
    status: Status
    findings: list[ZoneFinding]
    prompts: list[Prompt]


def analyze_zones(
    zs: ZoneSet,
    *,
    ponding: list[PondingReport] | None = None,
    heavy_rain_days: list[date] | None = None,
    changes: list[ChangeReport] | None = None,
) -> ZoneAnalysis:
    heavy = sorted(set(heavy_rain_days or []))
    findings: list[ZoneFinding] = []
    for z in zs.zones:
        plausible, why = collection_assessment(z, zs)
        verify, v_reason = False, None
        survey = date.fromisoformat(z.terrain.terrain_date) if z.terrain.terrain_date else None
        for c in changes or []:
            if c.zone_id not in (None, z.zone_id):
                continue
            if survey is None or c.reported_on > survey:
                verify = True
                v_reason = (
                    f"{c.kind.replace('_', ' ')} reported on {c.reported_on}"
                    + (
                        f", after the terrain survey ({survey})"
                        if survey
                        else "; terrain date unknown"
                    )
                    + ": terrain and drainage findings for this zone may be out of date"
                )
        findings.append(
            ZoneFinding(
                zone_id=z.zone_id, name=z.name, plausible_collection_zone=plausible,
                collection_reason=why, verify=verify, verify_reason=v_reason,
                terrain_date=z.terrain.terrain_date, terrain_source=z.terrain.source,
                resolution_m=z.terrain.resolution_m, drainage_class=z.drainage.cls,
            )
        )  # fmt: skip
    by_id = {f.zone_id: f for f in findings}

    prompts: list[Prompt] = []
    for rep in ponding or []:
        f = by_id.get(rep.zone_id)
        if f is None:
            prompts.append(
                Prompt(zone_id=rep.zone_id, kind="note", status=Status.MANUAL_CHECK,
                       reason=f"ponding was reported in unknown zone '{rep.zone_id}'",
                       reported_on=rep.reported_on)
            )  # fmt: skip
            continue
        window = [
            d for d in heavy
            if rep.reported_on - timedelta(days=PONDING_RAIN_WINDOW_DAYS) <= d <= rep.reported_on
        ]  # fmt: skip
        if f.plausible_collection_zone and window:
            prompts.append(
                Prompt(zone_id=rep.zone_id, kind="inspect", status=Status.MANUAL_CHECK,
                       reason="ponding reported after heavy rain in a zone where water plausibly "
                       f"collects ({f.collection_reason}): inspect drainage and field access",
                       reported_on=rep.reported_on, heavy_rain_days=window)
            )  # fmt: skip
        elif f.plausible_collection_zone is False:
            prompts.append(
                Prompt(zone_id=rep.zone_id, kind="verify_location", status=Status.MANUAL_CHECK,
                       reason="ponding was reported in a zone where water is not expected to "
                       "collect: check the report location, terrain and drainage",
                       reported_on=rep.reported_on, heavy_rain_days=window)
            )  # fmt: skip
        else:
            prompts.append(
                Prompt(zone_id=rep.zone_id, kind="note", status=Status.MANUAL_CHECK,
                       reason="ponding reported with no heavy-rain day in the "
                       f"{PONDING_RAIN_WINDOW_DAYS} days before it"
                       if f.plausible_collection_zone
                       else "ponding reported; zone terrain could not be assessed",
                       reported_on=rep.reported_on, heavy_rain_days=window)
            )  # fmt: skip
    return ZoneAnalysis(
        label=zs.label,
        status=Status.COMPLETE if zs.zones else Status.UNAVAILABLE,
        findings=findings,
        prompts=prompts,
    )


def zones_as_dict(zs: ZoneSet) -> dict[str, Any]:
    return zs.model_dump(mode="json", by_alias=True)
