"""Chronology validation for a plan. Returns typed issues; never an exception trace.

Order inside one season, anchored on the previous harvest ``H`` and next planting ``P``::

    H <= seed < terminate <= P          (cover)
    H <= grain_plant < grain_harvest <= P   (winter grain)

``L = days from H forward to P`` around the 365-day cycle is the winter length. A date whose
forward offset from ``H`` is >= ``L`` (cover/seed) lies outside the winter window; whether
that is "before harvest" or "after planting" is decided by which side it is nearer.
"""

from __future__ import annotations

from fieldshift.contracts import FieldIssue, InvalidPlanError, Plan
from fieldshift.seasons.dates import CYCLE_DAYS, cycle_offset


def winter_length_days(plan: Plan) -> int:
    """Forward days from previous harvest to next planting (the MM-DD winter length)."""
    return cycle_offset(plan.prev_harvest, plan.next_plant)


def _side(offset: int, length: int) -> str:
    """For an offset outside [0, length]: nearer to 'before harvest' or 'after planting'."""
    after_planting = offset - length
    before_harvest = CYCLE_DAYS - offset
    return "after_planting" if after_planting <= before_harvest else "before_harvest"


def validate_plan(plan: Plan) -> list[FieldIssue]:
    issues: list[FieldIssue] = []
    length = winter_length_days(plan)
    if length == 0:
        issues.append(
            FieldIssue(
                field="next_plant",
                code="window_not_positive",
                message="next_plant must be later in the year than prev_harvest "
                "(the winter window would be empty)",
            )
        )
        return issues

    def off(md: str) -> int:
        return cycle_offset(plan.prev_harvest, md)

    w = plan.winter
    if w.kind == "cover":
        assert w.seed is not None and w.terminate is not None
        seed_off, term_off = off(w.seed), off(w.terminate)
        if seed_off >= length:
            side = _side(seed_off, length)
            issues.append(
                FieldIssue(
                    field="winter.seed",
                    code="seed_before_harvest" if side == "before_harvest" else "seed_after_planting",
                    message=(
                        "seeding comes before the previous harvest"
                        if side == "before_harvest"
                        else "seeding comes on or after the next planting"
                    ),
                )
            )
        if term_off > length:
            side = _side(term_off, length)
            issues.append(
                FieldIssue(
                    field="winter.terminate",
                    code="terminate_after_planting"
                    if side == "after_planting"
                    else "terminate_before_harvest",
                    message=(
                        "termination comes after the next planting"
                        if side == "after_planting"
                        else "termination comes before the previous harvest"
                    ),
                )
            )
        elif seed_off < length and term_off <= seed_off:
            issues.append(
                FieldIssue(
                    field="winter.terminate",
                    code="terminate_not_after_seed",
                    message="termination must be after seeding (the cover interval would be empty)",
                )
            )
    elif w.kind == "winter_grain":
        assert w.plant is not None and w.harvest is not None
        plant_off, harvest_off = off(w.plant), off(w.harvest)
        if plant_off >= length:
            issues.append(
                FieldIssue(
                    field="winter.plant",
                    code="grain_plant_outside_winter_window",
                    message="winter grain must be planted after the previous harvest "
                    "and before the next planting",
                )
            )
        if harvest_off > length or harvest_off <= plant_off:
            issues.append(
                FieldIssue(
                    field="winter.harvest",
                    code="grain_harvest_not_between_plant_and_next_planting",
                    message="winter grain harvest must be after its planting and not after "
                    "the next planting",
                )
            )
    return issues


def ensure_valid(plan: Plan) -> None:
    issues = validate_plan(plan)
    if issues:
        raise InvalidPlanError(issues)
