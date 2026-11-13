"""Map one plan onto every historical planting year.

Window conventions (all documented here, tested in ``tests/seasons``):

* Previous harvest falls in ``Y-1`` when its MM-DD is later than the next-planting MM-DD,
  otherwise in ``Y``.
* Winter window: ``[prev_harvest, next_plant)``. Harvest day included, planting day excluded.
* Living-cover interval: ``[seed, terminate)``, labelled ``planned``; establishment uncertain.
  The termination day is not cover.
* Spring window: ``[next_plant - 30 d, next_plant - 1 d]``; for May 12 that is Apr 12 - May 11.
* Termination gap: ``next_plant - terminate`` in days.
"""

from __future__ import annotations

from datetime import date, timedelta

from fieldshift.contracts import (
    CoverInterval,
    FieldIssue,
    GrainInterval,
    InvalidPlanError,
    Plan,
    SeasonCalendar,
)
from fieldshift.seasons.dates import resolve_md, split_md
from fieldshift.seasons.validate import ensure_valid

SPRING_WINDOW_DAYS = 30


def _after(anchor: date, md: str) -> date:
    """First occurrence of ``md`` on or after ``anchor`` (Feb 29 -> Feb 28 in non-leap years)."""
    candidate = resolve_md(anchor.year, md)
    return candidate if candidate >= anchor else resolve_md(anchor.year + 1, md)


def build_calendar(plan: Plan, year: int) -> SeasonCalendar:
    """Resolve ``plan`` for planting year ``year``. Raises :class:`InvalidPlanError`."""
    ensure_valid(plan)
    plant = resolve_md(year, plan.next_plant)
    harvest_year = year - 1 if split_md(plan.prev_harvest) > split_md(plan.next_plant) else year
    harvest = resolve_md(harvest_year, plan.prev_harvest)
    if not harvest < plant:  # only reachable via Feb 29 -> Feb 28 collapsing two dates
        raise InvalidPlanError(
            [FieldIssue(field="prev_harvest", code="window_not_positive",
                        message=f"in {year} the winter window [{harvest}, {plant}) is empty")]
        )

    cover: CoverInterval | None = None
    grain: GrainInterval | None = None
    gap: int | None = None
    w = plan.winter
    if w.kind == "cover":
        assert w.crop_id and w.seed and w.terminate
        seed = _after(harvest, w.seed)
        terminate = _after(seed, w.terminate)
        _require_ordered(year, seed < terminate <= plant, "winter.terminate",
                         f"in {year} seed {seed}, terminate {terminate}, plant {plant} are not in order")
        cover = CoverInterval(crop_id=w.crop_id, seed=seed, terminate=terminate,
                              days=(terminate - seed).days)
        gap = (plant - terminate).days
    elif w.kind == "winter_grain":
        assert w.crop_id and w.plant and w.harvest
        g_plant = _after(harvest, w.plant)
        g_harvest = _after(g_plant, w.harvest)
        _require_ordered(year, g_plant < g_harvest <= plant, "winter.harvest",
                         f"in {year} grain plant {g_plant}, harvest {g_harvest}, "
                         f"next plant {plant} are not in order")
        grain = GrainInterval(crop_id=w.crop_id, plant=g_plant, harvest=g_harvest,
                              days=(g_harvest - g_plant).days)

    return SeasonCalendar(
        plan_id=plan.plan_id,
        year=year,
        prev_harvest=harvest,
        plant=plant,
        winter_days=(plant - harvest).days,
        spring_start=plant - timedelta(days=SPRING_WINDOW_DAYS),
        spring_end=plant - timedelta(days=1),
        spring_days=SPRING_WINDOW_DAYS,
        cover=cover,
        grain=grain,
        termination_gap_days=gap,
    )


def _require_ordered(year: int, ok: bool, field: str, message: str) -> None:
    if not ok:
        raise InvalidPlanError([FieldIssue(field=field, code="chronology", message=message)])


def build_calendars(plan: Plan, years: range | list[int]) -> dict[int, SeasonCalendar]:
    """One calendar per planting year. Validates the plan once; raises before any year is built."""
    ensure_valid(plan)
    return {y: build_calendar(plan, y) for y in years}
