"""Core API (Phase 6): compare, replay, sensitivity, years, rotations.

Every response carries ``meta = {plan_version, catalog_version, snapshot_hash, request_id}``.
Invalid input is HTTP 400 ``status: invalid_input`` with typed ``{field, code, message}`` issues.
A partial result is preserved: per-plan and per-metric statuses live in the body, not in HTTP
errors. Nothing here touches the network except the optional soil lookup, which never raises.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, field_validator

from fieldshift.api.samples import SamplePlan, load_samples
from fieldshift.compare import engine, text
from fieldshift.compare import locations as places
from fieldshift.compare.context import Context, get_context
from fieldshift.compare.models import (
    CompareResponse,
    Meta,
    PlanComparison,
    ReplayResponse,
    RotationsResponse,
    SensitivityResponse,
    SharedYears,
    UnsupportedResponse,
    WeatherLocation,
    YearsResponse,
)
from fieldshift.compare.replay import replay_season
from fieldshift.compare.sensitivity import DEFAULT_RULE, sweep_termination
from fieldshift.compare.years import years_payload
from fieldshift.contracts import InvalidPlanError, Plan, Status
from fieldshift.planner.calendar import plan_year_issues
from fieldshift.planner.checker import plan_version
from fieldshift.report.http import invalid, issue
from fieldshift.report.meta import response_meta
from fieldshift.weather.snapshot import set_active_snapshot_dir

router = APIRouter(prefix="/v1", tags=["core"])

_CHECK_TO_RULE = {meta[0]: rid for rid, meta in engine.CHECK_META.items()}

FIRST_YEAR, LAST_YEAR = engine.YEARS[0], engine.YEARS[-1]


class LocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class CompareRequest(BaseModel):
    """Plans to compare: edited ``plans``, sample ``plan_ids`` and/or ``rotation_ids``."""

    model_config = ConfigDict(extra="forbid")
    plans: list[Plan] = Field(default_factory=list)
    plan_ids: list[str] = Field(default_factory=list)
    rotation_ids: list[str] = Field(default_factory=list)
    location: LocationIn | None = None
    # an id from data/snapshots/index.json (the place picker's id); picks that place's snapshot
    location_id: str | None = None
    include_soil: bool = True
    # Soybean maturity group (0-10) for a winter-wheat double-crop plan; blank = not entered.
    maturity_group: (
        Annotated[StrictInt, Field(ge=0, le=10)] | Annotated[StrictFloat, Field(ge=0, le=10)] | None
    ) = None

    @field_validator("maturity_group", mode="before")
    @classmethod
    def _blank_is_not_entered(cls, v: Any) -> Any:
        """A blank string means "not entered" (unknown), never 0; a real 0 is kept."""
        return None if isinstance(v, str) and not v.strip() else v


class SensitivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: Plan | None = None
    plan_id: str | None = None
    rule_id: str = DEFAULT_RULE
    location: LocationIn | None = None
    location_id: str | None = None


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: Plan
    location: LocationIn | None = None
    location_id: str | None = None


def _meta(version: str | None, snapshot_hash: str | None | bool = True) -> Meta:
    """Response metadata. ``snapshot_hash`` is the snapshot actually used: pass the context's hash,
    or ``None`` when no snapshot was used. ``True`` keeps what the request's active snapshot says."""
    meta = response_meta(version)
    if snapshot_hash is not True:
        meta["snapshot_hash"] = snapshot_hash
    return Meta.model_validate(meta)


def _issues_from_plan_error(exc: InvalidPlanError, prefix: str) -> list[dict[str, str]]:
    return [issue(f"{prefix}.{i.field}", i.code, i.message) for i in exc.issues]


def _sample(plan_id: str, field: str) -> tuple[SamplePlan | None, dict[str, str] | None]:
    sp = load_samples().plans.get(plan_id)
    if sp is None:
        known = ", ".join(sorted(load_samples().plans))
        return None, issue(field, "unknown_plan", f"unknown plan '{plan_id}'; known plans: {known}")
    return sp, None


def _full_season_default() -> Plan | None:
    """The full-season soybean sample a double-crop plan is shown next to when the request
    has no full-season soybean plan of its own."""
    sp = load_samples().plans.get("corn_soy__no_cover")
    return sp.plan if sp else None


def _follow(choice: places.Choice) -> None:
    """Make every ``response_meta()`` in this request (including error envelopes) carry the hash of
    the snapshot the request resolved to."""
    if choice.ok and choice.entry is not None:
        set_active_snapshot_dir(choice.entry.directory)


def _invalid_for(issues: list[dict[str, str]], choice: places.Choice | None) -> JSONResponse:
    """HTTP 400. Its ``snapshot_hash`` is the resolved snapshot's, or null when the place could not
    be resolved (nothing was used)."""
    if choice is not None and choice.ok:
        return invalid(issues)  # the active snapshot is already set (see ``_follow``)
    return JSONResponse(
        status_code=400,
        content={"status": "invalid_input", "issues": issues,
                 **{**response_meta(), "snapshot_hash": None}},
    )  # fmt: skip


def _unavailable(sp: SamplePlan) -> PlanComparison:
    info = sp.meta.get("unavailable") or {}
    return PlanComparison(
        plan_id=sp.plan_id,
        label=sp.meta.get("label"),
        status=Status.UNAVAILABLE,
        reason=info.get("reason", "unavailable"),
        rotation_id=sp.meta.get("rotation_id"),
        leg=sp.meta.get("leg"),
        dates_assumed=sp.meta.get("dates_assumed"),
        dates_basis=sp.meta.get("dates_basis"),
    )


@router.post("/plans/compare", response_model=CompareResponse)
def compare(body: CompareRequest) -> Any:
    issues: list[dict[str, str]] = []
    loc = body.location
    choice = places.choose(body.location_id, loc.latitude if loc else None,
                           loc.longitude if loc else None)  # fmt: skip
    _follow(choice)
    wanted: dict[str, tuple[Plan | None, dict[str, Any]]] = {}  # insertion-ordered
    samples = load_samples()
    membership: dict[str, list[str]] = {}
    for i, rid in enumerate(body.rotation_ids):
        rot = samples.rotations.get(rid)
        if rot is None:
            issues.append(
                issue(
                    f"rotation_ids.{i}",
                    "unknown_rotation",
                    f"unknown rotation '{rid}'; known: {sorted(samples.rotations)}",
                )
            )
            continue
        for leg in rot.legs:
            wanted.setdefault(leg, (samples.plans[leg].plan, samples.plans[leg].meta))
            membership.setdefault(leg, []).append(rid)
    for i, pid in enumerate(body.plan_ids):
        sp, err = _sample(pid, f"plan_ids.{i}")
        if err:
            issues.append(err)
        elif sp:
            wanted.setdefault(pid, (sp.plan, sp.meta))
            if not body.rotation_ids:
                membership.setdefault(pid, []).extend(
                    r.rotation_id for r in samples.rotations.values() if pid in r.legs
                )
    for p in body.plans:  # an edited plan replaces the sample of the same id, keeping its place
        sample = samples.plans.get(p.plan_id)
        wanted[p.plan_id] = (p, sample.meta if sample else {})
    if not wanted and not issues:
        issues.append(
            issue("plans", "no_plans", "give at least one of plans, plan_ids, rotation_ids")
        )
    if len(wanted) > engine.MAX_PLANS:
        issues.append(
            issue("plans", "too_many_plans", f"at most {engine.MAX_PLANS} plans per comparison")
        )
    issues = choice.issues + issues if choice.kind == "invalid" else issues
    if issues:
        return _invalid_for(issues, choice)

    # validate edited / provided plans (typed chronology errors)
    for pid, (plan, _m) in wanted.items():
        if plan is not None:
            try:
                engine.build_calendar(plan, engine.REFERENCE_YEAR)
            except InvalidPlanError as exc:
                issues += _issues_from_plan_error(exc, f"plans.{pid}")
            else:
                if plan.winter.kind == "winter_grain":  # the wheat path replays every year
                    issues += [
                        issue(f"plans.{pid}.{i['field']}", i["code"], i["message"])
                        for i in plan_year_issues(plan, engine.YEARS)
                    ]
    if issues:
        return _invalid_for(issues, choice)

    ctx = choice.ctx or get_context()  # a problem place keeps the default only for the shape
    place = choice.entry
    if place is not None:  # a named place: its county point stands in for a missing point
        lat = loc.latitude if loc else place.latitude
        lon = loc.longitude if loc else place.longitude
    else:
        ref_pt = ctx.manifest["reference_point"]
        lat = loc.latitude if loc else ref_pt["requested_latitude"]
        lon = loc.longitude if loc else ref_pt["requested_longitude"]
    named = loc is not None or body.location_id is not None
    location_block = _location_block(choice, lat, lon) if named else None
    location_problem = None if choice.ok else choice.reason
    wl = places.weather_location(choice, text.reason_text(choice.reason))

    live = [(pid, p, m) for pid, (p, m) in wanted.items() if p is not None]
    if location_problem:  # no weather for this point: a result, not an error
        ts = engine.threshold_set_for(ctx, [p.next_plant for _, p, _ in live])
        shared = SharedYears(spring=[], winter=[], full_season=[], note=location_problem)
        status = Status.UNSUPPORTED if choice.kind == "unsupported" else Status.UNAVAILABLE
        by_id = {
            pid: PlanComparison(
                plan_id=pid,
                label=p.label,
                status=status,
                reason=location_problem,
                plan=p,
            )
            for pid, p, _ in live
        }
    else:
        results_live, ts, shared = engine.compare_plans(
            [p for _, p, _ in live],
            ctx,
            meta_by_plan={pid: m for pid, _, m in live},
            maturity_group=body.maturity_group,
            full_season_default=_full_season_default(),
        )
        by_id = {r.plan_id: r for r in results_live}
    results: list[PlanComparison] = []
    for pid, (plan, _m) in wanted.items():
        res = _unavailable(load_samples().plans[pid]) if plan is None else by_id[pid]
        res.rotation_ids = membership.get(pid, [])
        res.rotation_id = res.rotation_ids[0] if res.rotation_ids else None
        results.append(res)
    text.finalize(results, {pid: p for pid, (p, _m) in wanted.items()}, ctx.index)
    if choice.ok and place is not None:
        places.add_region_notes(results, place, samples.plans)

    if place is not None:
        echo_location_id: str | None = place.id
    else:
        echo_location_id = ctx.location_id if not named else None
    echo = {
        "location_id": echo_location_id,
        "latitude": lat,
        "longitude": lon,
        "plan_ids": list(wanted),
        "rotation_ids": body.rotation_ids,
    }
    hashed: dict[str, Any] = {
        "plans": [p.model_dump(mode="json") for _, p, _ in live],
        "location": [lat, lon],
        "maturity_group": body.maturity_group,  # changes the double-crop checks
        "unavailable": [pid for pid, (p, _m) in wanted.items() if p is None],
    }
    if place is not None:
        hashed["location_id"] = place.id
    input_hash = engine.canonical_hash(hashed)
    meta = _meta(input_hash[:16], ctx.snapshot_hash if choice.ok else None)
    result_id = engine.canonical_hash(
        [input_hash, ctx.snapshot_hash, meta.catalog_version, ts.threshold_set_id]
    )[:16]
    soil = _soil(lat, lon) if body.include_soil else None
    return CompareResponse(
        meta=meta,
        result_id=result_id,
        input_hash=input_hash,
        request_echo=echo,
        thresholds=engine.thresholds_view(ts, ctx if choice.ok else None),
        shared_eligible_years=shared,
        plans=results,
        soil=soil,
        location=location_block,
        weather_location=wl,
        eras=engine.eras_block(),
        data_sources=_data_sources(ctx, soil, choice),
    )


def _location_block(choice: places.Choice, lat: float, lon: float) -> dict[str, Any] | None:
    """B's point resolution (bounds, grid cell, guidance region), with ``weather`` taken from the
    committed snapshot index. The index is what serves weather, so it decides ``weather``."""
    from fieldshift.field.location import resolve_location

    res = resolve_location(lat, lon, fetch_history=False)
    block = res.model_dump(mode="json")
    e = choice.entry
    if choice.ok and e is not None and block.get("weather") is not None:
        block["weather"] = {
            "supported": True, "status": "complete", "source": "snapshot", "freshness": "snapshot",
            "reason": None, "snapshot_hash": e.snapshot_hash, "first_date": e.first_date,
            "last_date": e.last_date,
        }  # fmt: skip
        block["notes"] = [n for n in block.get("notes", []) if "weather history is not" not in n]
        guidance = block.get("guidance") or {}
        block["status"] = "complete" if guidance.get("status") == "complete" else "partial"
    return block


def _data_sources(
    ctx: Context, soil: dict[str, Any] | None, choice: places.Choice | None = None
) -> dict[str, Any]:
    """Where each input came from and how fresh it is. Weather history is always a snapshot."""
    cov = ctx.manifest["coverage"]
    soil_fresh = None
    if soil is not None:
        soil_fresh = (soil.get("provenance") or {}).get("freshness") or (
            "unavailable" if soil.get("status") == "unavailable" else None
        )
    if choice is not None and not choice.ok:
        weather: dict[str, Any] = {
            "source": "NASA POWER daily (offline snapshot)",
            "freshness": "unavailable",
            "snapshot_hash": None,
            "first_date": None,
            "last_date": None,
            "retrieved_at": None,
        }
    else:
        weather = {
            "source": "NASA POWER daily (offline snapshot)",
            "freshness": "snapshot",
            "snapshot_hash": ctx.snapshot_hash,
            "first_date": cov["first_date"],
            "last_date": cov["last_date"],
            "retrieved_at": ctx.manifest["retrieval"]["retrieved_at"],
        }
    return {
        "weather": weather,
        "soil": None
        if soil is None
        else {
            "source": "USDA NRCS Soil Data Access",
            "freshness": soil_fresh or "unavailable",
        },
        "catalog": {"source": "Perplexity catalogs v1 (verbatim)", "freshness": "snapshot"},
    }


def _soil(lat: float, lon: float) -> dict[str, Any]:
    """Soil context for the point. A failure becomes ``unavailable``; the comparison still works."""
    try:
        from fieldshift.field.soil import get_soil

        return get_soil(lat, lon).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - soil must never break a comparison
        return {"status": "unavailable", "reason": f"soil_lookup_failed: {type(exc).__name__}"}


def _check_year(year: int) -> JSONResponse | None:
    if not FIRST_YEAR <= year <= LAST_YEAR:
        return invalid(
            [
                issue(
                    "year",
                    "year_out_of_range",
                    f"year must be {FIRST_YEAR}-{LAST_YEAR} (the planting years in the record)",
                )
            ]
        )
    return None


def _unsupported(plan: Plan, ctx: Context, year: int | None = None) -> UnsupportedResponse | None:
    """Same support rule as the comparison: unknown crops are ``unsupported``, not empty results."""
    from fieldshift.planner.checker import check_plan

    try:
        res = check_plan(plan, ctx.index, year=year or engine.REFERENCE_YEAR)
    except InvalidPlanError:
        return None  # reported as typed invalid_input by the caller
    if res.status == Status.UNSUPPORTED:
        return UnsupportedResponse(
            meta=_meta(plan_version(plan, year), ctx.snapshot_hash),
            status=Status.UNSUPPORTED,
            plan_id=plan.plan_id,
            reason="; ".join(res.unsupported) or "unsupported",
            unsupported=res.unsupported,
        )
    return None


def _place(
    location_id: str | None, latitude: float | None, longitude: float | None
) -> tuple[places.Choice, Any]:
    """Resolve the place first, so every response of the request (errors included) carries the
    right ``snapshot_hash``. Returns ``(choice, invalid_response_or_None)``; a bad ``location_id``
    is ``invalid_input``."""
    choice = places.choose(location_id, latitude, longitude)
    _follow(choice)
    if choice.kind == "invalid":
        return choice, _invalid_for(choice.issues, choice)
    return choice, None


def _no_weather(choice: places.Choice, plan_id: str) -> UnsupportedResponse | None:
    """The result for a place with no usable weather: HTTP 200, ``unavailable`` (NC cell with no
    snapshot) or ``unsupported`` (outside NC), with a code and ``reason_text``. ``None`` if ok."""
    if choice.ok:
        return None
    rt = text.reason_text(choice.reason)
    return UnsupportedResponse(
        meta=_meta(None, None),
        status=Status.UNSUPPORTED if choice.kind == "unsupported" else Status.UNAVAILABLE,
        plan_id=plan_id,
        reason=choice.reason or "unavailable",
        code=choice.code,
        reason_text=rt,
        weather_location=places.weather_location(choice, rt),
    )


def _wl(choice: places.Choice) -> WeatherLocation:
    return places.weather_location(choice)


def _replay(plan: Plan, year: int, choice: places.Choice) -> Any:
    ctx = choice.ctx
    assert ctx is not None
    err = _check_year(year)
    if err:
        return err
    unsupported = _unsupported(plan, ctx, year)
    if unsupported is not None:
        return unsupported
    try:
        ts = engine.threshold_set_for(ctx, [plan.next_plant])
        payload = replay_season(plan, year, ctx, ts)
    except InvalidPlanError as exc:
        return invalid(_issues_from_plan_error(exc, "plan"))
    return ReplayResponse(
        meta=_meta(plan_version(plan, year), ctx.snapshot_hash), weather_location=_wl(choice),
        **payload,
    )


@router.get("/seasons/{year}/replay", response_model=ReplayResponse | UnsupportedResponse)
def replay_get(
    year: int,
    plan: Annotated[str, Query(description="sample plan id")] = "corn_soy__rye",
    location_id: Annotated[str | None, Query(description="place id from the snapshot index")] = None,
    latitude: Annotated[float | None, Query(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Query(ge=-180, le=180)] = None,
) -> Any:
    choice, bad = _place(location_id, latitude, longitude)
    if bad is not None:
        return bad
    sp, err = _sample(plan, "plan")
    if err:
        return _invalid_for([err], choice)
    if sp is None or sp.plan is None:
        return _invalid_for(
            [
                issue(
                    "plan",
                    "plan_unavailable",
                    f"plan '{plan}' is unavailable: {(sp.meta.get('unavailable') or {}).get('reason') if sp else ''}",
                )
            ],
            choice,
        )
    return _no_weather(choice, sp.plan.plan_id) or _replay(sp.plan, year, choice)


@router.post("/seasons/{year}/replay", response_model=ReplayResponse | UnsupportedResponse)
def replay_post(year: int, body: ReplayRequest) -> Any:
    """Replay an edited plan (same payload as the GET)."""
    loc = body.location
    choice, bad = _place(body.location_id, loc.latitude if loc else None,
                         loc.longitude if loc else None)  # fmt: skip
    if bad is not None:
        return bad
    return _no_weather(choice, body.plan.plan_id) or _replay(body.plan, year, choice)


@router.post("/plans/sensitivity", response_model=SensitivityResponse | UnsupportedResponse)
def sensitivity(body: SensitivityRequest) -> Any:
    loc = body.location
    choice, bad = _place(body.location_id, loc.latitude if loc else None,
                         loc.longitude if loc else None)  # fmt: skip
    if bad is not None:
        return bad
    plan = body.plan
    if plan is None:
        if body.plan_id is None:
            return _invalid_for([issue("plan", "plan_required", "give plan or plan_id")], choice)
        sp, err = _sample(body.plan_id, "plan_id")
        if err:
            return _invalid_for([err], choice)
        plan = sp.plan if sp else None
        if plan is None:
            return _invalid_for(
                [issue("plan_id", "plan_unavailable", "that plan is unavailable")], choice
            )
    no_weather = _no_weather(choice, plan.plan_id)
    if no_weather is not None:
        return no_weather
    assert choice.ctx is not None
    ctx = choice.ctx
    unsupported = _unsupported(plan, ctx)
    if unsupported is not None:
        return unsupported
    rule_id = _CHECK_TO_RULE.get(body.rule_id, body.rule_id)
    if rule_id not in {r.rule_id for r in ctx.index.catalog.rules}:
        return invalid(
            [issue("rule_id", "unknown_rule", f"unknown rule or check '{body.rule_id}'")]
        )
    try:
        ts = engine.threshold_set_for(ctx, [plan.next_plant])
        payload = sweep_termination(plan, ctx, ts, rule_id)
    except InvalidPlanError as exc:
        return invalid(_issues_from_plan_error(exc, "plan"))
    return SensitivityResponse(
        meta=_meta(plan_version(plan), ctx.snapshot_hash), weather_location=_wl(choice), **payload
    )


@router.get("/years", response_model=YearsResponse | UnsupportedResponse)
def years(
    plan: Annotated[
        str, Query(description="sample plan id that sets the windows")
    ] = "corn_soy__rye",
    location_id: Annotated[str | None, Query(description="place id from the snapshot index")] = None,
    latitude: Annotated[float | None, Query(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Query(ge=-180, le=180)] = None,
) -> Any:
    choice, bad = _place(location_id, latitude, longitude)
    if bad is not None:
        return bad
    sp, err = _sample(plan, "plan")
    if err:
        return _invalid_for([err], choice)
    if sp is None or sp.plan is None:
        return _invalid_for([issue("plan", "plan_unavailable", "that plan is unavailable")], choice)
    no_weather = _no_weather(choice, sp.plan.plan_id)
    if no_weather is not None:
        return no_weather
    assert choice.ctx is not None
    ctx = choice.ctx
    return YearsResponse(
        meta=_meta(plan_version(sp.plan), ctx.snapshot_hash), weather_location=_wl(choice),
        **years_payload(sp.plan, ctx),
    )


@router.get("/rotations", response_model=RotationsResponse)
def rotations() -> Any:
    """The presets: each rotation is two plan legs."""
    return RotationsResponse(meta=_meta(None), rotations=list(load_samples().rotations.values()))
