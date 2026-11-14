"""Crop and date checker (Phase 7).

Evaluates one crop sequence against the catalog and returns every rule with its verdict, reason,
inputs used and source. It uses the same rule engine as the historical replay
(``fieldshift.metrics.rules``), so a rule can never mean two different things.

No weather is read here: ``spring`` dryness is ``unavailable`` for a plain check, so rules gated on
a dry spring (``cr_tt_03``) only fire from a grower-reported concern, and are otherwise ``unknown``
(the compare endpoint evaluates them against the replay).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from fieldshift.catalogs.index import CatalogIndex
from fieldshift.contracts import (
    FieldIssue,
    GrowerFacts,
    InvalidPlanError,
    Plan,
    SeasonCalendar,
    SeasonDates,
    SeasonFacts,
    SpringFacts,
    Status,
)
from fieldshift.field.regions import region_scope
from fieldshift.metrics.rules import RuleCheck, SeasonEvaluation, evaluate_season
from fieldshift.planner.wheat import wheat_catalog_state
from fieldshift.seasons.align import build_calendar

#: Role each plan slot must have in the catalog.
_SLOT_ROLE = {"previous": "cash_crop", "next": "cash_crop"}
_WINTER_ROLE = {"cover": "cover_crop", "winter_grain": "cash_crop"}


def default_planting_year(today: date | None = None) -> int:
    """The next planting season: after June it is next year, otherwise this year."""
    today = today or date.today()
    return today.year + 1 if today.month >= 7 else today.year


def region_supported(region: str | None) -> bool:
    """Supported unless the region text puts the field outside North Carolina."""
    return region_scope(region) != "outside"


class PathNote(BaseModel):
    """A part of the plan the catalog cannot evaluate yet."""

    path: str
    status: Status
    reason: str  # the engine's wording
    text: str = ""  # one plain sentence for the grower


class ConflictGroup(BaseModel):
    """Catalog-declared conflicting rules. Both are shown; no winner is picked."""

    rule_ids: list[str]
    note: str
    text: str = ""  # one plain sentence for the grower


class CheckResult(BaseModel):
    status: Status  # complete | invalid_input | unsupported
    plan_id: str | None = None
    year: int | None = None
    calendar: SeasonCalendar | None = None
    issues: list[FieldIssue] = Field(default_factory=list)
    unsupported: list[str] = Field(default_factory=list)
    rules: list[RuleCheck] = Field(default_factory=list)
    conflicts: list[ConflictGroup] = Field(default_factory=list)
    chronology_conflicts: list[str] = Field(default_factory=list)
    path_notes: list[PathNote] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)

    def rule(self, rule_id: str) -> RuleCheck | None:
        return next((r for r in self.rules if r.rule_id == rule_id), None)

    @property
    def flagged_ids(self) -> list[str]:
        return [r.rule_id for r in self.rules if r.flagged]


def plan_version(plan: Plan, year: int | None = None, inputs: dict[str, Any] | None = None) -> str:
    """Stable short hash of everything that determines a check result."""
    payload = {"plan": plan.model_dump(mode="json"), "year": year, "inputs": inputs or {}}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def facts_from_calendar(plan: Plan, cal: SeasonCalendar) -> SeasonFacts:
    """Build the ``SeasonFacts`` the rule engine reads; weather metrics stay ``unavailable``."""
    w = plan.winter
    seed: date | None = None
    terminate: date | None = None
    sequence = [plan.previous_crop_id, plan.next_crop_id]
    if cal.cover is not None:
        seed, terminate = cal.cover.seed, cal.cover.terminate
        sequence.insert(1, cal.cover.crop_id)
    elif cal.grain is not None:
        seed = cal.grain.plant  # sowing date of the winter grain
        sequence.insert(1, cal.grain.crop_id)
    assert w.kind in ("none", "cover", "winter_grain")
    return SeasonFacts(
        year=cal.year,
        plan_id=plan.plan_id,
        crop_sequence=sequence,
        region=plan.region,
        production_system=plan.production_system,
        dates=SeasonDates(
            harvest=cal.prev_harvest,
            seed=seed,
            terminate=terminate,
            plant=cal.plant,
            spring_start=cal.spring_start,
            spring_end=cal.spring_end,
        ),
        termination_gap_days=cal.termination_gap_days,
        spring=SpringFacts(status=Status.UNAVAILABLE),
        grower=GrowerFacts(**plan.grower.model_dump()),
    )


def _unsupported(plan: Plan, index: CatalogIndex) -> list[str]:
    out: list[str] = []
    slots = [("previous_crop_id", plan.previous_crop_id, "cash_crop"),
             ("next_crop_id", plan.next_crop_id, "cash_crop")]  # fmt: skip
    if plan.winter.kind != "none":
        slots.append(("winter.crop_id", plan.winter.crop_id or "", _WINTER_ROLE[plan.winter.kind]))
    for field, crop_id, role in slots:
        crop = index.crop(crop_id)
        if crop is None:
            out.append(
                f"{field}: crop '{crop_id}' is not supported (not in catalog {index.version})"
            )
        elif crop.crop_role != role:
            out.append(f"{field}: '{crop_id}' is a {crop.crop_role}, but this slot needs a {role}")
    if not region_supported(plan.region):
        out.append(f"region: '{plan.region}' is outside North Carolina; guidance is NC-only")
    return out


def _path_notes(plan: Plan, index: CatalogIndex) -> list[PathNote]:
    notes: list[PathNote] = []
    if plan.winter.kind == "winter_grain":
        state, reason = wheat_catalog_state(index, plan.winter.crop_id or "")
        if state != Status.COMPLETE:
            plain = (
                "The catalog has no wheat planting rows yet, so the wheat path cannot be checked."
                if state == Status.UNAVAILABLE
                else "The catalog has no numeric Piedmont dates for wheat: enter your own wheat "
                "harvest and soybean planting dates, and check the rest with your adviser."
            )
            notes.append(
                PathNote(
                    path="winter_grain_double_crop", status=state, reason=reason or "", text=plain
                )
            )
    return notes


def _conflict_groups(rules: list[RuleCheck]) -> list[ConflictGroup]:
    seen: set[tuple[str, ...]] = set()
    out: list[ConflictGroup] = []
    for r in rules:
        if r.conflict:
            ids = tuple(sorted([r.rule_id, *r.conflicts_with]))
            if ids not in seen:
                seen.add(ids)
                out.append(
                    ConflictGroup(
                        rule_ids=list(ids),
                        note="The catalog lists these rules as conflicting; both are shown and "
                        "neither is chosen.",
                        text=f"The sources disagree here ({' and '.join(ids)}); both are shown and "
                        "neither is chosen.",
                    )
                )
    return out


def _counts(rules: list[RuleCheck]) -> dict[str, int]:
    out: dict[str, int] = {"rules": len(rules), "flagged": sum(1 for r in rules if r.flagged)}
    for r in rules:
        out[r.status] = out.get(r.status, 0) + 1
        if r.verdict:
            key = f"verdict_{r.verdict}"
            out[key] = out.get(key, 0) + 1
    return out


def check_plan(
    plan: Plan,
    index: CatalogIndex,
    *,
    year: int | None = None,
    inputs: dict[str, Any] | None = None,
) -> CheckResult:
    """Check ``plan`` for one planting ``year`` (default: the next planting season)."""
    year = year or default_planting_year()
    unsupported = _unsupported(plan, index)
    if unsupported:
        return CheckResult(
            status=Status.UNSUPPORTED, plan_id=plan.plan_id, year=year, unsupported=unsupported
        )
    try:
        cal = build_calendar(plan, year)
    except InvalidPlanError as exc:
        return CheckResult(
            status=Status.INVALID_INPUT, plan_id=plan.plan_id, year=year, issues=list(exc.issues)
        )
    facts = facts_from_calendar(plan, cal)
    ev: SeasonEvaluation = evaluate_season(facts, index, inputs=inputs)
    if ev.status != "complete":  # defensive: crops were already validated above
        return CheckResult(
            status=Status(ev.status), plan_id=plan.plan_id, year=year, unsupported=ev.errors
        )
    return CheckResult(
        status=Status.COMPLETE,
        plan_id=plan.plan_id,
        year=year,
        calendar=cal,
        rules=ev.checks,
        conflicts=_conflict_groups(ev.checks),
        chronology_conflicts=[c.rule_id for c in ev.checks if c.chronology_conflict],
        path_notes=_path_notes(plan, index),
        counts=_counts(ev.checks),
    )
