"""Pick the weather snapshot a request is answered from (owner: Agent A).

A request names a place by ``location_id`` (an id from ``data/snapshots/index.json``) or by a
latitude/longitude. The result is one of:

* ``ok``           the place's snapshot is used; its own frozen thresholds follow from it;
* ``unsupported``  the point is outside North Carolina (``unsupported_location``, as before);
* ``no_snapshot``  the point is in North Carolina but its POWER grid cell has no committed
                   snapshot (``no_weather_snapshot``, status ``unavailable``);
* ``invalid``      an unknown ``location_id``, a non-finite point, or an id and a point that
                   disagree (HTTP 400 ``invalid_input``).

A request with no place uses the Union County default, exactly as before. Locations are never
mixed: one request, one snapshot, one ``ThresholdSet``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

from fieldshift.compare.context import Context, context_for, get_context
from fieldshift.compare.models import WeatherLocation
from fieldshift.contracts import Status
from fieldshift.weather.locations import LocationEntry, cell_id_for, get_index

NO_SNAPSHOT = "no_weather_snapshot"
UNSUPPORTED = "unsupported_location"

Kind = Literal["ok", "unsupported", "no_snapshot", "invalid"]


@dataclass(frozen=True)
class Choice:
    kind: Kind
    ctx: Context | None = None
    entry: LocationEntry | None = None
    requested: dict[str, Any] | None = None  # {location_id, latitude, longitude} as given
    code: str | None = None
    reason: str | None = None  # "<code>: <detail>" for statuses; plain message for invalid
    issues: list[dict[str, str]] = field(default_factory=list)
    cell_id: str | None = None

    @property
    def ok(self) -> bool:
        return self.kind == "ok"


def _issue(field_: str, code: str, message: str) -> dict[str, str]:
    return {"field": field_, "code": code, "message": message}


def choose(
    location_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> Choice:
    """Resolve a place. Never raises; the result says what to return."""
    requested = {"location_id": location_id, "latitude": latitude, "longitude": longitude}
    index = get_index()
    have_point = latitude is not None and longitude is not None
    if (latitude is None) != (longitude is None):
        return Choice(
            "invalid", requested=requested,
            issues=[_issue("location", "incomplete_point", "give both latitude and longitude")],
        )  # fmt: skip
    if have_point:
        assert latitude is not None and longitude is not None
        if not (math.isfinite(latitude) and math.isfinite(longitude)
                and -90 <= latitude <= 90 and -180 <= longitude <= 180):  # fmt: skip
            return Choice("invalid", requested=requested, issues=[_issue(
                "location", "invalid_point",
                "latitude must be within [-90, 90] and longitude within [-180, 180]")])  # fmt: skip
    from fieldshift.field.location import in_nc_bounds

    entry_by_id = None
    if location_id:
        entry_by_id = index.by_id(location_id)
        if entry_by_id is None:
            known = ", ".join(e.id for e in index.entries)
            return Choice("invalid", requested=requested, issues=[_issue(
                "location_id", "unknown_location",
                f"unknown location '{location_id}'; known locations: {known}")])  # fmt: skip
    if have_point:
        assert latitude is not None and longitude is not None
        cid = cell_id_for(latitude, longitude)
        if not in_nc_bounds(latitude, longitude):  # also when an id is given
            return Choice(
                "unsupported", requested=requested, code=UNSUPPORTED, cell_id=cid,
                reason=f"{UNSUPPORTED}: the point is outside North Carolina; guidance and "
                "history cover NC only",
            )  # fmt: skip
        if entry_by_id is not None and cid != entry_by_id.cell_id:
            return Choice("invalid", requested=requested, issues=[_issue(
                "location", "location_conflict",
                f"the point is not in {entry_by_id.name}'s grid cell; give location_id or a "
                "point, not both")])  # fmt: skip
    if entry_by_id is not None:
        return Choice("ok", ctx=context_for(entry_by_id), entry=entry_by_id,
                      requested=requested, cell_id=entry_by_id.cell_id)  # fmt: skip
    if not have_point:
        return Choice("ok", ctx=get_context(), entry=None, requested=requested)
    assert latitude is not None and longitude is not None
    entry = index.by_cell(cid)
    if entry is None:
        return Choice(
            "no_snapshot", requested=requested, code=NO_SNAPSHOT, cell_id=cid,
            reason=f"{NO_SNAPSHOT}: no committed weather snapshot for grid cell {cid}",
        )  # fmt: skip
    return Choice("ok", ctx=context_for(entry), entry=entry, requested=requested, cell_id=cid)


def thresholds_sentence(entry: LocationEntry | None, ctx: Context) -> str:
    place = entry or ctx.place
    name = place.name if place else "this location"
    cov = ctx.manifest["coverage"]
    return (
        f"Dry-spring cutoffs come from {name}'s own {cov['first_date'][:4]}-"
        f"{cov['last_date'][:4]} weather baseline (snapshot {ctx.snapshot_hash[:12]}); heavy rain "
        "is the fixed 76.2 mm daily value. Thresholds are never shared across locations."
    )


def weather_location(choice: Choice, reason_text: str | None = None) -> WeatherLocation:
    """The block a response carries for this choice."""
    req = choice.requested or {}
    requested_point = (
        {"latitude": req["latitude"], "longitude": req["longitude"]}
        if req.get("latitude") is not None and req.get("longitude") is not None
        else None
    )
    if choice.ok:
        assert choice.ctx is not None
        e = choice.entry or choice.ctx.place
        assert e is not None
        return WeatherLocation(
            status=Status.COMPLETE,
            id=e.id,
            name=e.name,
            region=e.region,
            region_basis="county table: the place's region as listed in the snapshot index",
            point={"latitude": e.latitude, "longitude": e.longitude},
            requested_point=requested_point,
            grid_cell={k: e.grid_cell[k] for k in ("center_latitude", "center_longitude")},
            cell_id=e.cell_id,
            snapshot_hash=choice.ctx.snapshot_hash,
            first_date=e.first_date,
            last_date=e.last_date,
            shares_snapshot_with=e.shares_snapshot_with,
            thresholds_from=thresholds_sentence(e, choice.ctx),
        )
    status = Status.UNSUPPORTED if choice.kind == "unsupported" else Status.UNAVAILABLE
    return WeatherLocation(
        status=status,
        code=choice.code,
        reason=choice.reason,
        reason_text=reason_text,
        requested_point=requested_point,
        cell_id=choice.cell_id,
        thresholds_from=(
            "No plan was evaluated for this place. The thresholds shown only keep the response "
            "shape; they are Union County's and apply to nothing here."
        ),
    )


REGION_NAMES = {"piedmont": "the Piedmont", "coastal_plain": "the Coastal Plain"}


def add_region_notes(results: list[Any], entry: LocationEntry, samples: dict[str, Any]) -> None:
    """Label plans whose assumptions are for a different region than the place.

    The sample plans' dates are Piedmont-based assumptions. They are kept, but at a place in
    another region the plan says so (``dates_assumed_for_region`` and ``region_note``). A plan whose
    own ``region`` maps to another region than the place is told that its guidance follows the
    plan's region. Nothing here changes a plan or its rule applicability (that is
    ``fieldshift/field/regions.py``, owned by B).
    """
    from fieldshift.field.regions import normalize_field_region

    place_region = REGION_NAMES.get(entry.region, entry.region)
    for r in results:
        notes: list[str] = []
        sample = samples.get(r.plan_id)
        if (
            entry.region != "piedmont"
            and r.dates_assumed
            and sample is not None
            and sample.plan == r.plan
        ):
            r.dates_assumed_for_region = "piedmont"
            notes.append(
                f"These dates were assumed for the Piedmont; {entry.name} is in {place_region}, "
                "so check them against local timing."
            )
        tag = normalize_field_region(r.plan.region) if r.plan is not None else None
        if tag is not None and tag != entry.region:
            notes.append(
                f"This plan's region is {r.plan.region}, so that region's guidance applies; "
                f"{entry.name} is in {place_region}."
            )
        r.region_note = " ".join(notes) or None
