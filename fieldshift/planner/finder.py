"""\"Help me find a plan\": enumerate the winter options the catalog supports for a cash-crop pair.

Options are generated from catalog rules only: seeding dates come from a crop's preferred seeding
window, and termination dates from the day-gaps in its termination-timing rules. Each option is
checked with the same checker as a hand-written plan. **Priorities only reorder the options**; the
facts of every option (flags, cover days, gaps) are identical whatever the ranking.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from fieldshift.catalogs.index import CatalogIndex
from fieldshift.catalogs.models import CropRule
from fieldshift.contracts import Plan, Status, WinterManagement
from fieldshift.field.regions import region_match
from fieldshift.metrics.rules import RuleCheck
from fieldshift.planner.checker import CheckResult, check_plan, default_planting_year

Priority = Literal["soil_protection", "planting_window", "limited_water"]
PRIORITIES: tuple[Priority, ...] = ("soil_protection", "planting_window", "limited_water")
DEFAULT_PRIORITIES = PRIORITIES
#: Rules about soil-moisture depletion by a living cover (the "limited water" priority).
MOISTURE_RULES = frozenset({"cr_tt_01", "cr_tt_03"})
#: Termination gap used when the catalog gives no day-gap rule for a cover crop.
FALLBACK_GAP_DAYS = 14


class Option(BaseModel):
    option_id: str
    label: str
    winter: WinterManagement
    status: Status
    cover_days: int | None  # living-cover days, [seed, terminate)
    gap_days: int | None  # termination-to-planting gap
    flagged_rule_ids: list[str] = Field(default_factory=list)
    window_flag_ids: list[str] = Field(default_factory=list)
    moisture_flag_ids: list[str] = Field(default_factory=list)
    chronology_conflicts: list[str] = Field(default_factory=list)
    manual_check_ids: list[str] = Field(default_factory=list)
    unknown_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    rank: int | None = None


class Excluded(BaseModel):
    option_id: str
    status: Status
    reason: str


class FindResult(BaseModel):
    status: Status
    year: int
    priorities: list[Priority]
    options: list[Option] = Field(default_factory=list)
    excluded: list[Excluded] = Field(default_factory=list)
    check: CheckResult | None = None  # set when the base pair itself is invalid or unsupported


def _md(d: date) -> str:
    return f"{d.month:02d}-{d.day:02d}"


def _region_ok(rule: CropRule, region: str | None) -> bool:
    return region_match(rule.region, region)[0] != "no_match"


def _seed_window(index: CatalogIndex, crop_id: str, region: str | None) -> CropRule | None:
    for r in index.rules_for_crop(crop_id):
        if (
            r.rule_type == "planting_window"
            and r.management_action == "seed"
            and r.suitability == "preferred"
            and r.window_start_mm_dd
            and r.window_end_mm_dd
            and _region_ok(r, region)
        ):
            return r
    return None


def _gaps(index: CatalogIndex, crop_id: str, next_crop: str, region: str | None) -> list[int]:
    gaps: set[int] = set()
    for r in index.rules_for_crop(crop_id):
        if (
            r.rule_type == "termination_timing"
            and r.condition_key == "days_between_termination_and_planting"
            and r.next_crop_id in (None, next_crop)
            and _region_ok(r, region)
        ):
            for v in (r.value_min, r.value_max):
                if v is not None and v > 0:
                    gaps.add(int(v))
    return sorted(gaps) or [FALLBACK_GAP_DAYS]


def _summarise(option_id: str, label: str, winter: WinterManagement, res: CheckResult) -> Option:
    cal = res.calendar
    rules: list[RuleCheck] = res.rules
    flagged = [r for r in rules if r.flagged]
    return Option(
        option_id=option_id,
        label=label,
        winter=winter,
        status=res.status,
        cover_days=cal.cover.days if cal and cal.cover else None,
        gap_days=cal.termination_gap_days if cal else None,
        flagged_rule_ids=[r.rule_id for r in flagged],
        window_flag_ids=[
            r.rule_id for r in flagged if r.rule_type == "planting_window" or r.chronology_conflict
        ],
        moisture_flag_ids=[r.rule_id for r in flagged if r.rule_id in MOISTURE_RULES],
        chronology_conflicts=res.chronology_conflicts,
        manual_check_ids=[r.rule_id for r in rules if r.status == "manual_check"],
        unknown_ids=[r.rule_id for r in rules if r.status == "unknown"],
    )


def _sort_key(o: Option, priorities: list[Priority]) -> tuple:
    parts: list[tuple] = []
    for p in priorities:
        if p == "soil_protection":
            parts.append((-(o.cover_days or 0),))
        elif p == "planting_window":
            parts.append((len(o.window_flag_ids),))
        else:  # limited_water: fewest moisture flags, then the earlier termination (larger gap)
            parts.append((len(o.moisture_flag_ids), -(o.gap_days or 0)))
    return (*parts, len(o.flagged_rule_ids), o.option_id)


def find_plans(
    base: Plan,
    index: CatalogIndex,
    *,
    priorities: list[Priority] | None = None,
    year: int | None = None,
    inputs: dict | None = None,
) -> FindResult:
    """Enumerate and rank winter options for ``base``'s cash-crop pair. ``base.winter`` is ignored."""
    year = year or default_planting_year()
    prios = list(priorities) if priorities else list(DEFAULT_PRIORITIES)
    bare = base.model_copy(update={"winter": WinterManagement(kind="none")})
    base_check = check_plan(bare, index, year=year, inputs=inputs)
    if base_check.status != Status.COMPLETE:
        return FindResult(status=base_check.status, year=year, priorities=prios, check=base_check)
    harvest = base_check.calendar.prev_harvest  # type: ignore[union-attr]
    plant = base_check.calendar.plant  # type: ignore[union-attr]

    options: list[Option] = [
        _summarise("none", "No winter cover (bare / residue only)", bare.winter, base_check)
    ]
    excluded: list[Excluded] = []

    for crop in index.cover_crops():
        win = _seed_window(index, crop.crop_id, base.region)
        notes: list[str] = []
        seed = harvest
        if win is None:
            notes.append(
                f"catalog has no preferred seeding window for {crop.crop_id}; seeding at harvest"
            )
        else:
            start = date(
                harvest.year, int(win.window_start_mm_dd[:2]), int(win.window_start_mm_dd[3:])
            )
            end = date(harvest.year, int(win.window_end_mm_dd[:2]), int(win.window_end_mm_dd[3:]))
            if harvest > end:
                notes.append(
                    f"harvest {harvest} is after the preferred seeding window end ({win.window_end_mm_dd}); "
                    "no in-window seeding date follows harvest"
                )
            else:
                seed = max(harvest, start)
        for gap in _gaps(index, crop.crop_id, base.next_crop_id, base.region):
            terminate = plant - timedelta(days=gap)
            oid = f"{crop.crop_id}_gap{gap}"
            label = f"{crop.common_name}, terminated {gap} days before planting"
            if not seed < terminate:
                excluded.append(
                    Excluded(
                        option_id=oid,
                        status=Status.INVALID_INPUT,
                        reason=f"seeding {seed} would not be before termination {terminate}",
                    )
                )
                continue
            winter = WinterManagement(
                kind="cover", crop_id=crop.crop_id, seed=_md(seed), terminate=_md(terminate)
            )
            res = check_plan(
                bare.model_copy(update={"winter": winter}), index, year=year, inputs=inputs
            )
            if res.status != Status.COMPLETE:
                reason = "; ".join(res.unsupported or [i.message for i in res.issues])
                excluded.append(Excluded(option_id=oid, status=res.status, reason=reason))
                continue
            opt = _summarise(oid, label, winter, res)
            opt.notes = notes
            options.append(opt)

    excluded.append(
        Excluded(
            option_id="winter_wheat_double_crop",
            status=Status.UNAVAILABLE,
            reason="catalog_missing: winter wheat planting/harvest rows and the double-crop "
            "soybean window are not in the catalog yet",
        )
    )

    for rank, opt in enumerate(sorted(options, key=lambda o: _sort_key(o, prios)), start=1):
        opt.rank = rank
    options.sort(key=lambda o: o.rank or 0)
    return FindResult(
        status=Status.COMPLETE, year=year, priorities=prios, options=options, excluded=excluded
    )
