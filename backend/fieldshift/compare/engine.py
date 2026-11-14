"""Plan comparison engine (Phase 6): runs a plan over all 45 planting years.

Pure functions over a :class:`Context`; no HTTP and no network. Every plan in one comparison
shares the same frozen :class:`ThresholdSet` and the same weather rows, so differences between
plans can only come from the plans themselves.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from typing import Any

from fieldshift.compare.context import Context
from fieldshift.compare.eras import (
    EARLIER,
    EXCLUDED_FROM_ERAS,
    RECENT,
    Indicator,
    check_indicator,
    compare_eras,
    dry_spring_indicator,
    restrict_to_years,
    shared_years,
    winter_heavy_rain_indicator,
)
from fieldshift.compare.models import (
    CalendarSummary,
    CheckSummaryOut,
    PlanComparison,
    RuleLine,
    SeasonRow,
    SharedYears,
    SpringShortcuts,
    SpringSummary,
    ThresholdsView,
    WinterSummary,
)
from fieldshift.contracts import (
    InvalidPlanError,
    Plan,
    SeasonCalendar,
    SeasonFacts,
    Status,
    ThresholdSet,
)
from fieldshift.metrics.rules import GATES, SeasonEvaluation, evaluate_season, summarize_checks
from fieldshift.metrics.spring import (
    SPRING_DRY_PREFIX,
    SpringReference,
    SpringResult,
    compute_spring,
    spring_reference,
)
from fieldshift.metrics.thresholds import HEAVY_RAIN_NAME, build_threshold_set
from fieldshift.metrics.winter import ALL_SEGMENTS, WinterExposure, compute_winter
from fieldshift.planner.checker import check_plan
from fieldshift.seasons.align import build_calendar
from fieldshift.seasons.coverage import SeasonCoverage, season_coverage
from fieldshift.seasons.facts import build_season_facts

YEARS = list(range(1981, 2026))
REFERENCE_YEAR = 2025  # calendar summaries and weather-free checks use the last planting year
MAX_PLANS = 8

CHECK_META: dict[str, tuple[str, str, str]] = {
    "cr_tt_03": (
        "rye_soy_short_gap_moisture",
        "Would have prompted a field-moisture check",
        "gap < 14 days AND (dry replay OR grower low-moisture concern)",
    ),
    "cr_tt_04": (
        "rye_soy_pest_spillover_window",
        "Pest-spillover termination window (only if grower reports the concern)",
        "grower reports insect pest spillover concern",
    ),
}


# --------------------------------------------------------------------------- shared caches

_THRESHOLD_CACHE: dict[tuple[str, tuple[str, ...]], ThresholdSet] = {}
_REFERENCE_CACHE: dict[tuple[str, str], SpringReference] = {}


def threshold_set_for(ctx: Context, plant_mds: list[str]) -> ThresholdSet:
    """The one frozen ThresholdSet for a request (cached; immutable, so safe to share)."""
    key = (ctx.snapshot_hash, tuple(sorted(set(plant_mds))))
    if key not in _THRESHOLD_CACHE:
        _THRESHOLD_CACHE[key] = build_threshold_set(ctx.series, ctx.snapshot_hash, list(key[1]))
    return _THRESHOLD_CACHE[key]


def reference_for(ctx: Context, plant_md: str) -> SpringReference:
    key = (ctx.snapshot_hash, plant_md)
    if key not in _REFERENCE_CACHE:
        _REFERENCE_CACHE[key] = spring_reference(ctx.series, plant_md)
    return _REFERENCE_CACHE[key]


def thresholds_view(ts: ThresholdSet, ctx: Context | None = None) -> ThresholdsView:
    """The frozen thresholds. With ``ctx`` they also say which location's baseline they came from."""
    place = ctx.place if ctx is not None else None
    cov = ctx.manifest["coverage"] if ctx is not None else None
    return ThresholdsView(
        threshold_set_id=ts.threshold_set_id,
        heavy_rain=ts.get(HEAVY_RAIN_NAME),
        dry_spring={
            n.removeprefix(SPRING_DRY_PREFIX): t
            for n, t in ts.thresholds.items()
            if n.startswith(SPRING_DRY_PREFIX)
        },
        location_id=place.id if place else None,
        location_name=place.name if place else None,
        baseline=f"{cov['first_date']}..{cov['last_date']} daily record of this location's snapshot"
        if cov
        else None,
    )


def canonical_hash(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


# --------------------------------------------------------------------------- per-season bundle


@dataclass(frozen=True)
class SeasonBundle:
    year: int
    cal: SeasonCalendar
    coverage: SeasonCoverage
    winter: WinterExposure
    spring: SpringResult
    facts: SeasonFacts
    evaluation: SeasonEvaluation


def season_bundle(
    plan: Plan, year: int, ctx: Context, ts: ThresholdSet, ref: SpringReference
) -> SeasonBundle:
    cal = build_calendar(plan, year)
    cov = season_coverage(cal, ctx.series)
    winter = compute_winter(plan, cal, ctx.series, ts, ctx.snapshot_hash)
    spring = compute_spring(plan, cal, ctx.series, ts, ctx.snapshot_hash, ref)
    facts = build_season_facts(plan, cal, spring, cov)
    return SeasonBundle(year, cal, cov, winter, spring, facts, evaluate_season(facts, ctx.index))


def season_bundles(
    plan: Plan, ctx: Context, ts: ThresholdSet, years: list[int] | None = None
) -> list[SeasonBundle]:
    ref = reference_for(ctx, plan.next_plant)
    return [season_bundle(plan, y, ctx, ts, ref) for y in (years or YEARS)]


# --------------------------------------------------------------------------- one plan


def _median(values: list[float], digits: int = 3) -> float | None:
    return round(float(statistics.median(values)), digits) if values else None


def _source(src: Any) -> dict[str, Any] | None:
    return None if src is None else src.model_dump(mode="json")


def _calendar_summary(plan: Plan) -> CalendarSummary:
    cal = build_calendar(plan, REFERENCE_YEAR)
    living = cal.cover or cal.grain  # a cover crop, or growing winter wheat
    cover_days = living.days if living else 0
    return CalendarSummary(
        reference_year=REFERENCE_YEAR,
        winter_days=cal.winter_days,
        living_cover_days_planned=cover_days,
        days_without_planned_cover=cal.winter_days - cover_days,
        termination_gap_days=cal.termination_gap_days,
        establishment="uncertain" if living else "inapplicable",
        living_cover_kind=("cover_crop" if cal.cover else "winter_grain" if cal.grain else None),
        spring_window={
            "start": cal.spring_start.strftime("%m-%d"),
            "end": cal.spring_end.strftime("%m-%d"),
        },
    )


def _check_out(index_rules: dict[str, Any], s: Any) -> CheckSummaryOut:
    cid, label, fires = CHECK_META.get(
        s.rule_id,
        (s.rule_id, f"Rule {s.rule_id} would have flagged this season", "see rule guidance"),
    )
    rule = index_rules.get(s.rule_id)
    if s.rule_id not in CHECK_META and rule is not None:
        fires = rule.applies_when or rule.guidance or fires
    return CheckSummaryOut(
        check_id=cid,
        rule_ids=[s.rule_id],
        label=label,
        fires_when=fires,
        optional=s.optional,
        count=s.count,
        denominator=s.denominator,
        pct=round(100 * s.count / s.denominator, 1) if s.denominator else None,
        qualifying_years=s.qualifying_years,
        clear_years=s.clear_years,
        skipped_years=[k.model_dump(mode="json") for k in s.skipped_years],
        source=_source(s.source),
    )


def _rule_lines(res: Any, exclude: set[str]) -> tuple[list[RuleLine], list, list]:
    lines = [
        RuleLine(
            rule_id=r.rule_id,
            status=r.status,
            verdict=str(r.verdict) if r.verdict else None,
            flagged=r.flagged,
            reason=r.reason,
            text=r.text,
            print=r.print,
            conflict=r.conflict,
            conflicts_with=list(r.conflicts_with),
            source=_source(r.source),
            reference=r.reference,
        )
        for r in res.rules
        if r.status != Status.INAPPLICABLE and r.rule_id not in exclude
    ]
    lines.sort(key=lambda x: (not x.flagged, x.rule_id))
    return (
        lines,
        [c.rule_ids for c in res.conflicts],
        [n.model_dump(mode="json") for n in res.path_notes],
    )


def _summaries(
    plan: Plan,
    winters: dict[int, WinterExposure],
    springs: dict[int, SpringResult],
    ts: ThresholdSet,
    dry_name: str,
) -> tuple[WinterSummary, SpringSummary]:
    """Winter and spring summaries over the plan's OWN windows (shared by every plan kind)."""
    eligible_w = [w for w in winters.values() if w.eligible]
    eligible_s = [s for s in springs.values() if s.eligible]
    dry_years = [s.year for s in springs.values() if s.is_dry]
    heavy_known = [w for w in eligible_w if w.heavy_rain_days_outside_cover is not None]
    w_status = (
        Status.UNAVAILABLE
        if not eligible_w
        else Status.COMPLETE
        if len(eligible_w) == len(winters)
        else Status.PARTIAL
    )
    w_reasons = sorted({r for w in winters.values() if not w.eligible for r in w.reasons})
    winter_summary = WinterSummary(
        status=w_status,
        seasons=len(winters),
        eligible_seasons=len(eligible_w),
        per_season_median={
            "rain_mm_outside_cover": _median([w.rain_outside_cover_mm for w in eligible_w]),  # type: ignore[misc]
            "heavy_rain_days_outside_cover": _median(
                [float(w.heavy_rain_days_outside_cover) for w in heavy_known],
                1,  # type: ignore[arg-type]
            ),
        },
        seasons_with_heavy_rain_outside_cover=(
            sum(1 for w in heavy_known if w.heavy_rain_days_outside_cover) if heavy_known else None
        ),
        segments=(
            list(ALL_SEGMENTS)
            if plan.winter.kind in ("cover", "winter_grain")
            else ["no_planned_cover"]
        ),
        reasons=[
            f"{len(winters) - len(eligible_w)} season(s) not complete: " + ", ".join(w_reasons)
        ]
        if w_reasons
        else [],
    )
    cutoff = ts.get(dry_name)
    spring_summary = SpringSummary(
        status=Status.COMPLETE if cutoff.status == Status.COMPLETE else cutoff.status,
        window_days=30,
        cutoff_mm=cutoff.value,
        eligible_seasons=len(eligible_s),
        dry_seasons=len(dry_years) if cutoff.value is not None else None,
        dry_years=dry_years,
        excluded_years=list(cutoff.parameters.get("excluded_years", ()))
        and [{"year": y} for y in cutoff.parameters["excluded_years"]],
        median_total_mm=_median([s.total_mm for s in eligible_s]),  # type: ignore[misc]
    )
    return winter_summary, spring_summary


def _season_rows(bundles: list[SeasonBundle]) -> list[SeasonRow]:
    return [
        SeasonRow(
            year=b.year,
            winter_status=b.winter.status,
            spring_status=b.spring.status,
            full_season_status=b.coverage.metrics["full_season"].status,
            spring_total_mm=b.spring.total_mm,
            spring_rank=b.spring.rank,
            spring_is_dry=b.spring.is_dry,
            rain_outside_cover_mm=b.winter.rain_outside_cover_mm,
            heavy_rain_days_outside_cover=b.winter.heavy_rain_days_outside_cover,
            termination_gap_days=b.cal.termination_gap_days,
            flagged_rule_ids=[
                c.rule_id for c in b.evaluation.checks if c.flagged and c.rule_id in GATES
            ],
            # modeled soil wetness over the spring window; same window and label as the replay
            gwetroot_window_mean=b.spring.wetness.gwetroot,
            gwettop_window_mean=b.spring.wetness.gwettop,
            wetness_status=b.spring.wetness.status,
        )
        for b in bundles
    ]


def spring_shortcuts(ref: SpringReference) -> SpringShortcuts:
    """Typical / dry / wet planting years for one planting date: the same definition as
    ``GET /v1/years``. Dry = lowest 30-day total, wet = highest, typical = closest to the median
    (ties go to the lower year, except wet which takes the higher)."""
    totals = ref.totals
    ordered = sorted(totals, key=lambda y: (totals[y], y))
    median_total = sorted(totals.values())[len(totals) // 2] if totals else None
    typical = (
        min(totals, key=lambda y: (abs(totals[y] - median_total), y))  # type: ignore[operator]
        if totals
        else None
    )
    return SpringShortcuts(
        typical=typical,
        dry=ordered[0] if ordered else None,
        wet=ordered[-1] if ordered else None,
    )


def _analyze_wheat(
    plan: Plan, ctx: Context, ts: ThresholdSet, full_season_plan: Plan | None, maturity_group: Any
) -> PlanComparison:
    """Winter wheat -> double-crop soybean through B's wheat path (Phase 12).

    Catalog v1 has no wheat rows, so the path itself answers ``unavailable: catalog_missing``.
    With catalog v2 the result is ``partial``: the grower's dates, the maturity-group checks and
    the manual_check rows. The plan is never part of the shared-year or era comparisons (its
    baseline is its own planting window), and the full-season comparison inside ``double_crop``
    is labelled ``different-calendar`` with raw totals only.
    """
    from fieldshift.planner.wheat_path import evaluate_wheat_double_crop

    result = evaluate_wheat_double_crop(
        plan,
        ctx,
        maturity_group=maturity_group,
        year=REFERENCE_YEAR,
        full_season_plan=full_season_plan,
    )
    if (
        result["status"] == str(Status.INVALID_INPUT)
        and full_season_plan is not None
        and all(i["field"].startswith("compare_to_plan") for i in result["issues"])
    ):  # an unusable neighbouring plan must not sink this plan; say why there is no comparison
        why = "; ".join(i["message"] for i in result["issues"])
        result = evaluate_wheat_double_crop(
            plan, ctx, maturity_group=maturity_group, year=REFERENCE_YEAR
        )
        if result["status"] in (str(Status.COMPLETE), str(Status.PARTIAL)):
            result["cross_calendar"] = {
                "label": "different-calendar",
                "status": str(Status.UNAVAILABLE),
                "reason": f"the full-season soybean plan could not be used: {why}",
            }
    status = Status(result["status"])
    if status in (Status.COMPLETE, Status.PARTIAL):
        pc = PlanComparison(
            plan_id=plan.plan_id,
            label=plan.label,
            status=status,
            reason=(result.get("catalog_state") or {}).get("reason"),
            plan=plan,
            double_crop=result,
        )
        _wheat_winter_and_spring(pc, plan, ctx, ts, result)
        return pc
    reason = result.get("reason") or "; ".join(
        f"{i['field']}: {i['message']}" for i in result.get("issues", [])
    )
    return PlanComparison(
        plan_id=plan.plan_id,
        label=plan.label,
        status=status,
        reason=reason or None,
        plan=plan,
    )


def _wheat_winter_and_spring(
    pc: PlanComparison, plan: Plan, ctx: Context, ts: ThresholdSet, result: dict[str, Any]
) -> None:
    """Fill the winter, spring, seasons and eras of a winter-wheat plan over its OWN windows.

    Winter: growing wheat (wheat plant to wheat harvest) counts as living cover; the window runs
    from the previous harvest to the soybean planting date; heavy rain uses the same frozen
    ThresholdSet threshold as every other plan. Spring stays on its own-window baseline. The plan
    is still kept out of every cross-plan (shared-year) comparison: nothing here is added to or
    ranked against another plan.
    """
    bundles = season_bundles(plan, ctx, ts)
    springs = {b.year: b.spring for b in bundles}
    winters = {b.year: b.winter for b in bundles}
    dry_name = f"{SPRING_DRY_PREFIX}{plan.next_plant}"
    winter_summary, spring_summary = _summaries(plan, winters, springs, ts, dry_name)
    shortcuts = spring_shortcuts(reference_for(ctx, plan.next_plant))
    spring_summary = spring_summary.model_copy(update={"shortcuts": shortcuts})
    winter_ind = winter_heavy_rain_indicator(winters)
    eras = {
        "dry_spring": compare_eras(
            "dry_spring", dry_spring_indicator(springs), ts, threshold_names=[dry_name]
        ),
        "winter_heavy_rain_outside_cover": compare_eras(
            "winter_heavy_rain_outside_cover",
            winter_ind,
            ts,
            threshold_names=[HEAVY_RAIN_NAME],
        ),
    }
    result = pc.double_crop  # PlanComparison holds its own copy of the dict; edit that one
    assert result is not None
    pc.calendar = _calendar_summary(plan)
    pc.winter, pc.spring, pc.eras = winter_summary, spring_summary, eras
    pc.seasons = _season_rows(bundles)
    pc.residue_context = [
        r.model_dump(mode="json") for r in winters[REFERENCE_YEAR].residue_context
    ]
    result["spring"]["shortcuts"] = shortcuts.model_dump(mode="json")
    result["winter_exposure"] = {
        "status": str(winter_summary.status),
        "label": "own_window",
        "window": {
            "from": "previous harvest",
            "to": "soybean planting date (exclusive)",
            "days": pc.calendar.winter_days,
            "living_cover": "growing wheat, wheat planting to wheat harvest (planned)",
        },
        "heavy_rain_threshold": ts.get(HEAVY_RAIN_NAME).model_dump(mode="json"),
        "eligible_seasons": winter_summary.eligible_seasons,
        "per_season_median": winter_summary.per_season_median,
        "seasons_with_heavy_rain_outside_cover": winter_summary.seasons_with_heavy_rain_outside_cover,
        "segments": winter_summary.segments,
        "era": eras["winter_heavy_rain_outside_cover"].model_dump(mode="json"),
        "note": (
            "Rain on days with no planned living cover: before wheat is planted and after it is "
            "harvested. Rainfall depth only, never erosion or soil loss. Computed over this "
            "plan's own window with the same frozen heavy-rain threshold as every other plan."
        ),
    }


def analyze_plan(
    plan: Plan,
    ctx: Context,
    ts: ThresholdSet,
    *,
    full_season_plan: Plan | None = None,
    maturity_group: Any = None,
) -> tuple[PlanComparison, dict[str, Indicator]]:
    """Run one plan over every planting year. Returns the result and its per-year indicators."""
    if plan.winter.kind == "winter_grain":
        return _analyze_wheat(plan, ctx, ts, full_season_plan, maturity_group), {}
    checked = check_plan(plan, ctx.index, year=REFERENCE_YEAR)
    if checked.status == Status.UNSUPPORTED:
        return PlanComparison(
            plan_id=plan.plan_id,
            label=plan.label,
            status=Status.UNSUPPORTED,
            reason="; ".join(checked.unsupported) or "unsupported",
            plan=plan,
        ), {}
    bundles = season_bundles(plan, ctx, ts)
    springs = {b.year: b.spring for b in bundles}
    winters = {b.year: b.winter for b in bundles}
    evals = [b.evaluation for b in bundles]
    rules = {r.rule_id: r for r in ctx.index.catalog.rules}

    summaries = summarize_checks(evals)
    spring_checks = [s for s in summaries if s.rule_id in GATES and (not s.optional or s.count > 0)]
    dry_name = f"{SPRING_DRY_PREFIX}{plan.next_plant}"
    indicators: dict[str, Indicator] = {
        "dry_spring": dry_spring_indicator(springs),
        "winter_heavy_rain_outside_cover": winter_heavy_rain_indicator(winters),
    }
    eras = {
        "dry_spring": compare_eras(
            "dry_spring", indicators["dry_spring"], ts, threshold_names=[dry_name]
        ),
        "winter_heavy_rain_outside_cover": compare_eras(
            "winter_heavy_rain_outside_cover",
            indicators["winter_heavy_rain_outside_cover"],
            ts,
            threshold_names=[HEAVY_RAIN_NAME],
        ),
    }
    outs = []
    for s in spring_checks:
        out = _check_out(rules, s)
        outs.append(out)
        ind = check_indicator(evals, s.rule_id)
        indicators[out.check_id] = ind
        eras[out.check_id] = compare_eras(out.check_id, ind, ts, threshold_names=[dry_name])

    winter_summary, spring_summary = _summaries(plan, winters, springs, ts, dry_name)
    shortcuts = spring_shortcuts(reference_for(ctx, plan.next_plant))
    spring_summary = spring_summary.model_copy(update={"shortcuts": shortcuts})
    lines, conflicts, notes = _rule_lines(checked, {s.rule_id for s in spring_checks})
    rows = _season_rows(bundles)
    ref_winter = winters[REFERENCE_YEAR]
    return PlanComparison(
        plan_id=plan.plan_id,
        label=plan.label,
        status=Status.COMPLETE,
        plan=plan,
        calendar=_calendar_summary(plan),
        winter=winter_summary,
        spring=spring_summary,
        spring_checks=outs,
        other_checks=lines,
        conflicts=conflicts,
        path_notes=notes,
        eras=eras,
        seasons=rows,
        residue_context=[r.model_dump(mode="json") for r in ref_winter.residue_context],
    ), indicators


# --------------------------------------------------------------------------- several plans


def _full_season_for(plans: list[Plan], default: Plan | None) -> Plan | None:
    """The first full-season soybean plan in the request, else ``default``."""
    for p in plans:
        if p.next_crop_id == "soybean" and p.winter.kind != "winter_grain":
            return p
    return default


def compare_plans(
    plans: list[Plan],
    ctx: Context,
    *,
    meta_by_plan: dict[str, dict[str, Any]] | None = None,
    maturity_group: Any = None,
    full_season_default: Plan | None = None,
) -> tuple[list[PlanComparison], ThresholdSet, SharedYears]:
    """Analyze every plan against ONE frozen ThresholdSet and the same weather rows.

    A winter-wheat double-crop plan is shown next to the request's first full-season soybean plan
    (or ``full_season_default``) as ``different-calendar``, raw totals only.
    """
    if len(plans) > MAX_PLANS:
        raise ValueError(f"at most {MAX_PLANS} plans per comparison")
    for p in plans:
        _validate(p)
    mds = [p.next_plant for p in plans]
    ts = threshold_set_for(ctx, mds)
    full = _full_season_for(plans, full_season_default)
    analyses = [
        analyze_plan(p, ctx, ts, full_season_plan=full, maturity_group=maturity_group)
        for p in plans
    ]
    results = [a for a, _ in analyses]
    meta_by_plan = meta_by_plan or {}
    live = [
        (r, ind)
        for r, (_, ind) in zip(results, analyses, strict=True)
        if r.status == Status.COMPLETE
    ]
    if len(live) > 1:
        names = set.intersection(*(set(ind) for _, ind in live))
        for name in sorted(names):
            years = shared_years({r.plan_id: ind[name] for r, ind in live})
            for r, ind in live:  # each plan keeps ITS OWN frozen threshold (windows differ)
                r.eras_shared_years[name] = compare_eras(
                    name,
                    restrict_to_years(ind[name], years),
                    ts,
                    threshold_names=_threshold_names_for(name, r, ts),
                    basis="shared_evaluable_seasons",
                )
    for r in results:
        m = meta_by_plan.get(r.plan_id, {})
        r.rotation_id, r.leg = m.get("rotation_id"), m.get("leg")
        r.dates_assumed, r.editable = m.get("dates_assumed"), list(m.get("editable") or [])
        r.dates_basis = m.get("dates_basis") or ("assumed" if m.get("dates_assumed") else None)
        if m.get("unavailable") and r.status == Status.UNAVAILABLE:
            r.reason = m["unavailable"].get("reason", r.reason)
    shared = _shared_years([r for r in results if r.status == Status.COMPLETE])
    return results, ts, shared


def _threshold_names_for(name: str, plan_result: PlanComparison, ts: ThresholdSet) -> list[str]:
    if name == "winter_heavy_rain_outside_cover":
        return [HEAVY_RAIN_NAME]
    if plan_result.plan is None:
        return []
    return [f"{SPRING_DRY_PREFIX}{plan_result.plan.next_plant}"]


def _validate(plan: Plan) -> None:
    build_calendar(plan, REFERENCE_YEAR)  # raises InvalidPlanError with typed issues


def _shared_years(results: list[PlanComparison]) -> SharedYears:
    def years(attr: str, ok: Status = Status.COMPLETE) -> list[int]:
        sets = [{s.year for s in r.seasons if getattr(s, attr) == ok} for r in results]
        return sorted(set.intersection(*sets)) if sets else []

    return SharedYears(
        spring=years("spring_status"),
        winter=years("winter_status"),
        full_season=years("full_season_status"),
        note="Years where every compared plan has a complete result; use these when comparing "
        "plans so no plan is judged on years another could not be evaluated.",
    )


def eras_block() -> dict[str, Any]:
    return {
        "earlier": {"start": EARLIER[0], "end": EARLIER[1]},
        "recent": {"start": RECENT[0], "end": RECENT[1]},
        "excluded_from_eras": list(EXCLUDED_FROM_ERAS),
    }


__all__ = [
    "InvalidPlanError",
    "MAX_PLANS",
    "REFERENCE_YEAR",
    "YEARS",
    "SeasonBundle",
    "analyze_plan",
    "canonical_hash",
    "compare_plans",
    "eras_block",
    "reference_for",
    "season_bundle",
    "season_bundles",
    "threshold_set_for",
    "thresholds_view",
]
