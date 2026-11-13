"""Typed response models for the Phase 9 endpoints (calendar, backup, field note).

They give the OpenAPI contract field-level schemas for the front end. Every number a report shows
is an :class:`AuditedNumber` (``null`` when the value is missing; a real ``0`` is ``{"value": 0}``).
Models allow extra keys so a newly added informational field never breaks a response; fields the
front end relies on are declared.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fieldshift.compare.models import Meta
from fieldshift.contracts import Status
from fieldshift.planner.backup import BackupPlan
from fieldshift.planner.calendar import ActionCalendar


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")


class AuditedNumber(BaseModel):
    """A number plus the id of its audit entry (``audit.entries[audit_id]``)."""

    model_config = ConfigDict(extra="forbid")
    value: float | int
    unit: str | None = None
    audit_id: str


Num = AuditedNumber | None


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audit_id: str
    value: float | int
    unit: str | None = None
    derivation: Literal[
        "nasa", "usda", "extension", "grower", "calculation", "assumed", "unclassified"
    ]
    source_ref: dict[str, Any]
    inputs: dict[str, Any]
    label: str | None = None


class AuditBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entries: dict[str, AuditEntryOut] = Field(default_factory=dict)
    count: int
    unclassified: int
    derivations: list[str]


class SourceOut(_Open):
    title: str | None = None
    url: str | None = None
    locator: str | None = None
    verified_date: str | None = None
    snapshot_hash: str | None = None


class ReferenceOut(_Open):
    """A published number carried by a rule; never the grower's target."""

    kind: str
    operator: str | None = None
    unit: str | None = None
    value_min: Num = None
    value_max: Num = None
    is_grower_target: Literal[False] = False
    source_url: str | None = None
    label: str


class RuleLineOut(_Open):
    rule_id: str
    status: Status
    verdict: str | None = None
    flagged: bool = False
    condition_met: bool | None = None
    suitability: str | None = None
    reason: str
    missing_inputs: list[str] = Field(default_factory=list)
    reference: ReferenceOut | None = None
    source: SourceOut | None = None


class EvidenceOut(_Open):
    rule_id: str
    status: Status
    verdict: str | None = None
    reason: str
    missing_inputs: list[str] = Field(default_factory=list)
    reference: ReferenceOut | None = None
    source: SourceOut | None = None


class ActionOut(_Open):
    action_id: str
    kind: Literal["harvest", "seed", "terminate", "plant", "window", "check"]
    date: str
    end_date: str | None = None
    label: str
    zone: str | None = None
    trigger: str
    status: Status
    flagged: bool
    evidence: list[EvidenceOut] = Field(default_factory=list)


class SpringSnapshot(_Open):
    total_mm: Num = None
    rank: Num = None
    of: Num = None
    cutoff_mm: Num = None
    is_dry: bool | None = None
    status: str


class WetnessSnapshot(_Open):
    gwettop_window_mean: Num = None
    gwetroot_window_mean: Num = None
    label: str
    status: str


class WinterSnapshot(_Open):
    rain_outside_cover_mm: Num = None
    heavy_rain_days_outside_cover: Num = None


class ScenarioOut(_Open):
    status: str | None = None
    year: str | None = None
    replay: str | None = None
    spring: SpringSnapshot | None = None
    wetness: WetnessSnapshot | None = None
    winter: WinterSnapshot | None = None
    decisions_that_could_change: list[dict[str, Any]] | None = None
    decisions_note: str | None = None
    drainage_access_checks: dict[str, Any] | None = None


class ScenariosOut(_Open):
    status: str
    reason: str | None = None
    typical: ScenarioOut | None = None
    dry: ScenarioOut | None = None
    wet: ScenarioOut | None = None


class CalendarSection(_Open):
    status: Status
    year: str | None = None
    actions: list[ActionOut] = Field(default_factory=list)
    scenarios: ScenariosOut | None = None
    notes: list[str] = Field(default_factory=list)


class NotePlanCalendar(_Open):
    winter_days: Num = None
    living_cover_days_planned: Num = None
    days_without_planned_cover: Num = None
    termination_gap_days: Num = None
    establishment: str | None = None
    cover_label: str | None = None


class WheatDates(_Open):
    previous_harvest: str
    wheat_plant: str
    wheat_harvest: str
    soybean_plant: str
    wheat_season_days: Num = None
    harvest_to_plant_days: Num = None
    winter_days: Num = None


class NotePlan(_Open):
    plan_id: str
    label: str | None = None
    previous_crop: str | None = None
    prev_harvest: str | None = None
    winter: dict[str, Any] | None = None
    next_crop: str | None = None
    next_plant: str | None = None
    region: str | None = None
    production_system: str | None = None
    dates_basis: Literal["grower", "assumed"] | None = None
    grower_inputs: dict[str, Any] | None = None
    planting_year: str | None = None
    calendar: NotePlanCalendar | None = None
    dates: WheatDates | None = None  # winter-wheat plans
    catalog_state: dict[str, Any] | None = None


class WinterSection(_Open):
    status: Status
    label: str | None = None
    seasons: Num = None
    eligible_seasons: Num = None
    per_season_median: dict[str, Num] | None = None
    seasons_with_heavy_rain_outside_cover: Num = None
    segments: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    residue_context: list[dict[str, Any]] = Field(default_factory=list)


class SpringSection(_Open):
    status: Status
    window_days: Num = None
    dry_cutoff_mm: Num = None
    eligible_seasons: Num = None
    dry_seasons: Num = None
    dry_years: list[str] = Field(default_factory=list)
    median_total_mm: Num = None
    excluded_years: list[dict[str, Any]] = Field(default_factory=list)
    # winter-wheat plans: the window and baseline this plan's numbers use
    label: str | None = None
    baseline: str | None = None
    baseline_note: str | None = None
    window: dict[str, Any] | None = None


class SkippedYearOut(_Open):
    year: str
    status: str | None = None
    reason: str | None = None


class SpringCheckOut(_Open):
    check_id: str
    label: str
    fires_when: str
    optional: bool
    rule_ids: list[str]
    count: Num = None
    denominator: Num = None
    pct: Num = None
    qualifying_years: list[str] = Field(default_factory=list)
    skipped_years: list[SkippedYearOut] = Field(default_factory=list)
    source: SourceOut | None = None


class EraStatsOut(_Open):
    start: str
    end: str
    seasons: Num = None
    evaluable: Num = None
    events: Num = None
    pct: Num = None
    not_evaluable: list[dict[str, str]] = Field(default_factory=list)


class EraBlockOut(_Open):
    status: Status
    result: str
    caveat: str
    diff_pp: Num = None
    similarity_band_pp: Num = None
    min_evaluable_per_era: Num = None
    basis: str
    threshold_set_id: str
    thresholds: dict[str, Num] = Field(default_factory=dict)
    excluded_from_eras: list[str] = Field(default_factory=list)
    earlier: EraStatsOut
    recent: EraStatsOut


class ThresholdOut(_Open):
    name: str
    method: str
    status: Status
    unit: str | None = None
    value: Num = None
    reference_span: str | None = None
    note: str | None = None
    published: bool
    title: str | None = None
    url: str | None = None
    locator: str | None = None
    verified_date: str | None = None


class UnresolvedOut(_Open):
    rule_id: str
    status: str
    flagged: bool = False
    due: str | None = None
    what: str | None = None
    reason: str | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    reference: ReferenceOut | None = None
    source: SourceOut | None = None


class CountPair(_Open):
    default: Num = None
    alternative: Num = None
    default_denominator: Num = None
    alternative_denominator: Num = None
    same_denominator: bool | None = None


class DifferenceOut(_Open):
    label: str
    living_cover_days_planned: Num = None
    termination_gap_days: Num = None
    rain_mm_outside_cover_median: Num = None
    heavy_rain_days_outside_cover_median: Num = None
    spring_check_counts: dict[str, CountPair] = Field(default_factory=dict)
    note: str | None = None


class AlternativeOut(_Open):
    kind: Literal["fixed_alternative"]
    status: Status
    plan: NotePlan
    fallback_source: str | None = None
    divergence: dict[str, Any] | None = None
    switch_condition: dict[str, Any] | None = None
    decision_deadline: str | None = None
    next_check_date: str | None = None
    timing: str | None = None
    backtest: dict[str, Any] | None = None
    assumptions: list[str] = Field(default_factory=list)
    winter: WinterSection | None = None
    spring_checks: list[SpringCheckOut] = Field(default_factory=list)
    difference_vs_default: DifferenceOut | None = None  # same-calendar alternatives
    comparison_label: str | None = None  # "different-calendar" for winter-grain comparisons
    raw_totals: dict[str, Any] | None = None  # different-calendar: raw 30-day totals only


class AdviserField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_id: str
    label: str
    value: str | None = None


class AdviserNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instructions: str
    fields: list[AdviserField]


class MaturityGroupOut(_Open):
    input: Num = None
    status: str
    missing: list[str] = Field(default_factory=list)
    planting_context: dict[str, Any] | None = None
    checks: list[RuleLineOut] = Field(default_factory=list)


class SoybeanWindowOut(_Open):
    moved_to_after_wheat_harvest: bool
    earliest_planting_date: str
    planting_date: str
    days_after_wheat_harvest: Num = None
    basis: str
    catalog_context: RuleLineOut | None = None
    delay_caution: RuleLineOut | None = None
    notes: list[str] = Field(default_factory=list)


class InapplicableOut(_Open):
    rule_id: str
    status: Literal["inapplicable"]
    reason: str
    source: SourceOut | None = None


class CrossCalendarOut(_Open):
    """Full-season soybean vs double-crop: ``different-calendar``, raw totals only."""

    label: str
    status: str
    note: str
    reason: str | None = None
    full_season: dict[str, Any] | None = None
    double_crop: dict[str, Any] | None = None
    median_total_mm_difference: Num = None
    difference_label: str | None = None


class FieldNote(_Open):
    """``GET/POST .../note``. A plan that cannot be evaluated returns a status and no numbers."""

    meta: Meta
    note_version: str
    status: Status
    path: str | None = None  # "winter_wheat_double_crop" for wheat plans
    reason: str | None = None
    detail: str | None = None
    issues: list[dict[str, Any]] = Field(default_factory=list)
    plan: NotePlan
    winter: WinterSection | None = None
    spring: SpringSection | None = None
    spring_checks: list[SpringCheckOut] = Field(default_factory=list)
    eras: dict[str, EraBlockOut] = Field(default_factory=dict)
    thresholds: list[ThresholdOut] = Field(default_factory=list)
    calendar: CalendarSection | None = None
    unresolved_checks: list[UnresolvedOut] = Field(default_factory=list)
    alternatives: list[AlternativeOut] = Field(default_factory=list)
    sources: list[SourceOut] = Field(default_factory=list)
    adviser_note: AdviserNote
    limits: list[str] = Field(default_factory=list)
    audit: AuditBlock
    # winter-wheat plans
    soybean_planting_window: SoybeanWindowOut | None = None
    maturity_group: MaturityGroupOut | None = None
    inapplicable_checks: list[InapplicableOut] = Field(default_factory=list)
    cross_calendar: CrossCalendarOut | None = None
    wetness: dict[str, Any] | None = None


# --------------------------------------------------------------------------- calendar / backup


class PlanEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    before: Any = None
    after: Any = None


class CalendarChange(_Open):
    action_id: str
    change: Literal["added", "removed", "changed"]
    why: list[str] = Field(default_factory=list)
    date: str | None = None
    label: str | None = None
    status: str | None = None
    date_before: str | None = None
    date_after: str | None = None
    days_moved: int | None = None
    status_before: str | None = None
    status_after: str | None = None
    flagged_before: bool | None = None
    flagged_after: bool | None = None
    label_after: str | None = None


class GapPair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before: int | None = None
    after: int | None = None


class CalendarDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status
    plan_edits: list[PlanEdit]
    changes: list[CalendarChange]
    termination_gap_days: GapPair
    unchanged: bool


# ---- calendar scenarios (the plain numbers the calendar endpoint returns; the note audits them)


class RawSpring(_Open):
    total_mm: float | None = None
    rank: int | None = None
    of: int | None = None
    is_dry: bool | None = None
    cutoff_mm: float | None = None
    status: str


class RawWetness(_Open):
    gwettop_window_mean: float | None = None
    gwetroot_window_mean: float | None = None
    label: Literal["modeled"]
    status: str


class RawWinter(_Open):
    rain_outside_cover_mm: float | None = None
    heavy_rain_days_outside_cover: int | None = None


class DecisionOut(_Open):
    rule_id: str
    date: str | None = None
    question: str
    reason: str
    source: SourceOut | None = None


class DrainageItem(_Open):
    zone: str
    name: str
    due: str
    check: str
    why: str
    status: Status


class DrainageChecks(_Open):
    status: str
    basis: str | None = None
    reason: str | None = None
    heavy_rain_days_outside_cover: int | None = None
    items: list[DrainageItem] = Field(default_factory=list)


class RawScenario(_Open):
    year: int
    spring: RawSpring
    wetness: RawWetness
    winter: RawWinter
    replay: str
    decisions_that_could_change: list[DecisionOut] | None = None
    decisions_note: str | None = None
    drainage_access_checks: DrainageChecks | None = None


class RawScenarios(_Open):
    status: str | None = None  # absent ({}) when scenarios were not requested
    reason: str | None = None
    typical: RawScenario | None = None
    dry: RawScenario | None = None
    wet: RawScenario | None = None


class ActionCalendarOut(ActionCalendar):
    """``ActionCalendar`` with typed scenarios."""

    scenarios: RawScenarios | None = None  # type: ignore[assignment]  # null = not requested

    @field_validator("scenarios", mode="before")
    @classmethod
    def _empty_means_not_requested(cls, v: Any) -> Any:
        return None if v == {} else v


# ---- backup comparison


class SpringCheckBrief(_Open):
    check_id: str
    count: int
    denominator: int
    pct: float | None = None


class PlanBrief(_Open):
    """One plan's numbers in a same-calendar fixed-plan comparison."""

    plan_id: str
    status: str
    reason: str | None = None
    calendar_year: int | None = None
    living_cover_days_planned: int | None = None
    days_without_planned_cover: int | None = None
    termination_gap_days: int | None = None
    rain_mm_outside_cover_median: float | None = None
    heavy_rain_days_outside_cover_median: float | None = None
    spring_checks: list[SpringCheckBrief] = Field(default_factory=list)
    flagged_other_checks: list[str] = Field(default_factory=list)


class CrossBrief(_Open):
    """One plan's own-window raw totals in a different-calendar comparison."""

    plan_id: str
    winter_kind: str
    calendar_year: int
    next_plant: str
    plant_date: str
    window: dict[str, Any]
    median_total_mm: float | None = None
    eligible_seasons: int | None = None


class CountDiff(_Open):
    default: int
    default_denominator: int
    fallback: int
    fallback_denominator: int
    same_denominator: bool


class FallbackDiff(_Open):
    living_cover_days_planned: float | None = None
    termination_gap_days: float | None = None
    rain_mm_outside_cover_median: float | None = None
    heavy_rain_days_outside_cover_median: float | None = None
    spring_check_counts: dict[str, CountDiff] | None = None
    median_total_mm: float | None = None  # different-calendar comparisons: raw totals only


class BackupComparison(_Open):
    basis: Literal["fixed_plans", "different_calendar"]
    label: str | None = None
    threshold_set_id: str | None = None
    shared_eligible_years: dict[str, Any] | None = None
    default: PlanBrief | CrossBrief
    fallback: PlanBrief | CrossBrief
    fallback_minus_default: FallbackDiff
    note: str


class BackupPlanOut(BackupPlan):
    """``BackupPlan`` with a typed comparison."""

    comparison: BackupComparison | None = None  # type: ignore[assignment]


class CalendarResponse(BaseModel):
    """``POST /v1/plans/calendar``: dated actions, scenarios, and (with ``previous_plan``) a diff."""

    model_config = ConfigDict(extra="forbid")
    meta: Meta
    calendar: ActionCalendarOut
    diff: CalendarDiff | None = None


class BackupResponse(BaseModel):
    """``POST /v1/plans/backup``: default + fallback, switch condition, dates, fixed-plan comparison."""

    model_config = ConfigDict(extra="forbid")
    meta: Meta
    backup: BackupPlanOut
