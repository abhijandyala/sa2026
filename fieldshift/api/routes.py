"""Core API (Phase 6): compare, replay, sensitivity, years, rotations.

Every response carries ``meta = {plan_version, catalog_version, snapshot_hash, request_id}``.
Invalid input is HTTP 400 ``status: invalid_input`` with typed ``{field, code, message}`` issues.
A partial result is preserved: per-plan and per-metric statuses live in the body, not in HTTP
errors. Nothing here touches the network except the optional soil lookup, which never raises.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from fieldshift.api.samples import SamplePlan, load_samples
from fieldshift.compare import engine
from fieldshift.compare.context import Context, get_context
from fieldshift.compare.models import (
    CompareResponse,
    Meta,
    PlanComparison,
    ReplayResponse,
    RotationsResponse,
    SensitivityResponse,
    YearsResponse,
)
from fieldshift.compare.replay import replay_season
from fieldshift.compare.sensitivity import DEFAULT_RULE, sweep_termination
from fieldshift.compare.years import years_payload
from fieldshift.contracts import InvalidPlanError, Plan, Status
from fieldshift.planner.checker import plan_version
from fieldshift.report.http import invalid, issue
from fieldshift.report.meta import response_meta

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
    include_soil: bool = True


class SensitivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: Plan | None = None
    plan_id: str | None = None
    rule_id: str = DEFAULT_RULE


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: Plan


def _meta(version: str | None) -> Meta:
    return Meta.model_validate(response_meta(version))


def _issues_from_plan_error(exc: InvalidPlanError, prefix: str) -> list[dict[str, str]]:
    return [issue(f"{prefix}.{i.field}", i.code, i.message) for i in exc.issues]


def _sample(plan_id: str, field: str) -> tuple[SamplePlan | None, dict[str, str] | None]:
    sp = load_samples().plans.get(plan_id)
    if sp is None:
        known = ", ".join(sorted(load_samples().plans))
        return None, issue(field, "unknown_plan", f"unknown plan '{plan_id}'; known plans: {known}")
    return sp, None


def _unavailable(sp: SamplePlan) -> PlanComparison:
    info = sp.meta.get("unavailable") or {}
    return PlanComparison(
        plan_id=sp.plan_id, label=sp.meta.get("label"), status=Status.UNAVAILABLE,
        reason=info.get("reason", "unavailable"), rotation_id=sp.meta.get("rotation_id"),
        leg=sp.meta.get("leg"), dates_assumed=sp.meta.get("dates_assumed"),
    )


@router.post("/plans/compare", response_model=CompareResponse)
def compare(body: CompareRequest, ctx: Annotated[Context, Depends(get_context)]) -> Any:
    issues: list[dict[str, str]] = []
    wanted: dict[str, tuple[Plan | None, dict[str, Any]]] = {}  # insertion-ordered
    samples = load_samples()
    for i, rid in enumerate(body.rotation_ids):
        rot = samples.rotations.get(rid)
        if rot is None:
            issues.append(issue(f"rotation_ids.{i}", "unknown_rotation",
                                f"unknown rotation '{rid}'; known: {sorted(samples.rotations)}"))
            continue
        for leg in rot.legs:
            wanted.setdefault(leg, (samples.plans[leg].plan, samples.plans[leg].meta))
    for i, pid in enumerate(body.plan_ids):
        sp, err = _sample(pid, f"plan_ids.{i}")
        if err:
            issues.append(err)
        elif sp:
            wanted.setdefault(pid, (sp.plan, sp.meta))
    for p in body.plans:  # an edited plan replaces the sample of the same id, keeping its place
        sample = samples.plans.get(p.plan_id)
        wanted[p.plan_id] = (p, sample.meta if sample else {})
    if not wanted and not issues:
        issues.append(issue("plans", "no_plans", "give at least one of plans, plan_ids, rotation_ids"))
    if len(wanted) > engine.MAX_PLANS:
        issues.append(issue("plans", "too_many_plans",
                            f"at most {engine.MAX_PLANS} plans per comparison"))
    if issues:
        return invalid(issues)

    # validate edited / provided plans (typed chronology errors)
    for pid, (plan, _m) in wanted.items():
        if plan is not None and plan.winter.kind != "winter_grain":
            try:
                engine.build_calendar(plan, engine.REFERENCE_YEAR)
            except InvalidPlanError as exc:
                issues += _issues_from_plan_error(exc, f"plans.{pid}")
    if issues:
        return invalid(issues)

    live = [(pid, p, m) for pid, (p, m) in wanted.items() if p is not None]
    results_live, ts, shared = engine.compare_plans(
        [p for _, p, _ in live], ctx, meta_by_plan={pid: m for pid, _, m in live}
    )
    by_id = {r.plan_id: r for r in results_live}
    results: list[PlanComparison] = []
    for pid, (plan, _m) in wanted.items():
        if plan is None:
            results.append(_unavailable(load_samples().plans[pid]))
        else:
            results.append(by_id[pid])

    loc = body.location
    ref_pt = ctx.manifest["reference_point"]
    lat = loc.latitude if loc else ref_pt["requested_latitude"]
    lon = loc.longitude if loc else ref_pt["requested_longitude"]
    echo = {
        "location_id": ctx.location_id if not loc else None,
        "latitude": lat, "longitude": lon,
        "plan_ids": list(wanted),
        "rotation_ids": body.rotation_ids,
    }
    input_hash = engine.canonical_hash({
        "plans": [p.model_dump(mode="json") for _, p, _ in live], "location": [lat, lon],
        "unavailable": [pid for pid, (p, _m) in wanted.items() if p is None],
    })
    meta = _meta(input_hash[:16])
    result_id = engine.canonical_hash(
        [input_hash, ctx.snapshot_hash, meta.catalog_version, ts.threshold_set_id])[:16]
    soil = _soil(lat, lon) if body.include_soil else None
    return CompareResponse(
        meta=meta, result_id=result_id, input_hash=input_hash, request_echo=echo,
        thresholds=engine.thresholds_view(ts), shared_eligible_years=shared, plans=results,
        soil=soil, eras=engine.eras_block(),
    )


def _soil(lat: float, lon: float) -> dict[str, Any]:
    """Soil context for the point. A failure becomes ``unavailable``; the comparison still works."""
    try:
        from fieldshift.field.soil import get_soil

        return get_soil(lat, lon).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - soil must never break a comparison
        return {"status": "unavailable", "reason": f"soil_lookup_failed: {type(exc).__name__}"}


def _check_year(year: int) -> JSONResponse | None:
    if not FIRST_YEAR <= year <= LAST_YEAR:
        return invalid([issue("year", "year_out_of_range",
                              f"year must be {FIRST_YEAR}-{LAST_YEAR} (the planting years in the record)")])
    return None


def _replay(plan: Plan, year: int, ctx: Context) -> Any:
    err = _check_year(year)
    if err:
        return err
    try:
        ts = engine.threshold_set_for(ctx, [plan.next_plant])
        payload = replay_season(plan, year, ctx, ts)
    except InvalidPlanError as exc:
        return invalid(_issues_from_plan_error(exc, "plan"))
    return ReplayResponse(meta=_meta(plan_version(plan, year)), **payload)


@router.get("/seasons/{year}/replay", response_model=ReplayResponse)
def replay_get(
    year: int,
    ctx: Annotated[Context, Depends(get_context)],
    plan: Annotated[str, Query(description="sample plan id")] = "corn_soy__rye",
) -> Any:
    sp, err = _sample(plan, "plan")
    if err:
        return invalid([err])
    if sp is None or sp.plan is None:
        return invalid([issue("plan", "plan_unavailable",
                              f"plan '{plan}' is unavailable: {(sp.meta.get('unavailable') or {}).get('reason') if sp else ''}")])
    return _replay(sp.plan, year, ctx)


@router.post("/seasons/{year}/replay", response_model=ReplayResponse)
def replay_post(year: int, body: ReplayRequest, ctx: Annotated[Context, Depends(get_context)]) -> Any:
    """Replay an edited plan (same payload as the GET)."""
    return _replay(body.plan, year, ctx)


@router.post("/plans/sensitivity", response_model=SensitivityResponse)
def sensitivity(body: SensitivityRequest, ctx: Annotated[Context, Depends(get_context)]) -> Any:
    plan = body.plan
    if plan is None:
        if body.plan_id is None:
            return invalid([issue("plan", "plan_required", "give plan or plan_id")])
        sp, err = _sample(body.plan_id, "plan_id")
        if err:
            return invalid([err])
        plan = sp.plan if sp else None
        if plan is None:
            return invalid([issue("plan_id", "plan_unavailable", "that plan is unavailable")])
    rule_id = _CHECK_TO_RULE.get(body.rule_id, body.rule_id)
    if rule_id not in {r.rule_id for r in ctx.index.catalog.rules}:
        return invalid([issue("rule_id", "unknown_rule",
                              f"unknown rule or check '{body.rule_id}'")])
    try:
        ts = engine.threshold_set_for(ctx, [plan.next_plant])
        payload = sweep_termination(plan, ctx, ts, rule_id)
    except InvalidPlanError as exc:
        return invalid(_issues_from_plan_error(exc, "plan"))
    return SensitivityResponse(meta=_meta(plan_version(plan)), **payload)


@router.get("/years", response_model=YearsResponse)
def years(
    ctx: Annotated[Context, Depends(get_context)],
    plan: Annotated[str, Query(description="sample plan id that sets the windows")] = "corn_soy__rye",
) -> Any:
    sp, err = _sample(plan, "plan")
    if err:
        return invalid([err])
    if sp is None or sp.plan is None:
        return invalid([issue("plan", "plan_unavailable", "that plan is unavailable")])
    return YearsResponse(meta=_meta(plan_version(sp.plan)), **years_payload(sp.plan, ctx))


@router.get("/rotations", response_model=RotationsResponse)
def rotations() -> Any:
    """The presets: each rotation is two plan legs."""
    return RotationsResponse(meta=_meta(None), rotations=list(load_samples().rotations.values()))
