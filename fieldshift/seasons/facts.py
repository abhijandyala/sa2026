"""Assemble the ``SeasonFacts`` the rule engine consumes from calendar + metric results."""

from __future__ import annotations

from fieldshift.contracts import (
    GrowerFacts,
    Plan,
    SeasonCalendar,
    SeasonDates,
    SeasonFacts,
    SpringFacts,
    Status,
    WetnessFacts,
)
from fieldshift.metrics.spring import SpringResult
from fieldshift.seasons.coverage import SeasonCoverage


def build_season_facts(
    plan: Plan, cal: SeasonCalendar, spring: SpringResult, coverage: SeasonCoverage
) -> SeasonFacts:
    """Missing values stay ``None`` with a status; they are never coerced to 0."""
    seq = [plan.previous_crop_id]
    if plan.winter.crop_id:
        seq.append(plan.winter.crop_id)
    seq.append(plan.next_crop_id)
    status_map: dict[str, Status] = coverage.status_map()
    return SeasonFacts(
        year=cal.year,
        plan_id=plan.plan_id,
        crop_sequence=seq,
        region=plan.region,
        production_system=plan.production_system,
        dates=SeasonDates(
            harvest=cal.prev_harvest,
            seed=cal.cover.seed if cal.cover else None,
            terminate=cal.cover.terminate if cal.cover else None,
            plant=cal.plant,
            spring_start=cal.spring_start,
            spring_end=cal.spring_end,
        ),
        termination_gap_days=cal.termination_gap_days,
        spring=SpringFacts(
            total_mm=spring.total_mm,
            rank=spring.rank,
            percentile=spring.percentile,
            is_dry=spring.is_dry,
            status=spring.status,
        ),
        wetness=WetnessFacts(
            gwettop=spring.wetness.gwettop,
            gwetroot=spring.wetness.gwetroot,
            status=spring.wetness.status,
        ),
        grower=GrowerFacts(
            low_moisture_concern=plan.grower.low_moisture_concern,
            residue_report=plan.grower.residue_report,
            observations=list(plan.grower.observations),
        ),
        coverage=status_map,
    )
