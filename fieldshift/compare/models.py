"""Typed result models for plan comparison, replay, sensitivity and years (Phase 6).

These become the response bodies of the API (``fieldshift/api``), so they are the contract
the frontend reads. Labels and values always ship together; nothing is left for the client
to re-derive. Missing values are ``None`` with a status, never 0.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from fieldshift.compare.eras import EraComparison
from fieldshift.contracts import Plan, Rotation, Status, Threshold


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Meta(_M):
    plan_version: str | None
    catalog_version: str | None
    snapshot_hash: str | None
    request_id: str


# --------------------------------------------------------------------------- thresholds


class ThresholdsView(_M):
    """Every frozen threshold used. Never hard-code these in a client."""

    threshold_set_id: str
    heavy_rain: Threshold
    dry_spring: dict[str, Threshold]  # keyed by planting MM-DD (the window anchor)


# --------------------------------------------------------------------------- compare


class CalendarSummary(_M):
    reference_year: int
    winter_days: int
    living_cover_days_planned: int
    days_without_planned_cover: int
    termination_gap_days: int | None
    establishment: Literal["uncertain", "inapplicable"]
    spring_window: dict[str, str]  # {"start": "04-12", "end": "05-11"} MM-DD, 30 days


class WinterSummary(_M):
    status: Status
    seasons: int
    eligible_seasons: int
    per_season_median: dict[str, float | None]
    seasons_with_heavy_rain_outside_cover: int | None
    segments: list[str]
    reasons: list[str] = Field(default_factory=list)


class SpringSummary(_M):
    status: Status
    window_days: int
    cutoff_mm: float | None
    eligible_seasons: int
    dry_seasons: int | None
    dry_years: list[int]
    excluded_years: list[dict[str, Any]]
    median_total_mm: float | None


class CheckSummaryOut(_M):
    check_id: str
    rule_ids: list[str]
    label: str
    fires_when: str
    optional: bool
    count: int
    denominator: int
    pct: float | None
    qualifying_years: list[int]
    clear_years: list[int]
    skipped_years: list[dict[str, Any]]
    source: dict[str, Any] | None


class RuleLine(_M):
    rule_id: str
    status: Status
    verdict: str | None
    flagged: bool
    reason: str
    conflict: bool = False
    conflicts_with: list[str] = Field(default_factory=list)
    source: dict[str, Any] | None = None
    reference: dict[str, Any] | None = None  # sourced published number; never a grower target


class SeasonRow(_M):
    year: int
    winter_status: Status
    spring_status: Status
    full_season_status: Status
    spring_total_mm: float | None
    spring_rank: int | None
    spring_is_dry: bool | None
    rain_outside_cover_mm: float | None
    heavy_rain_days_outside_cover: int | None
    termination_gap_days: int | None
    flagged_rule_ids: list[str]


class PlanComparison(_M):
    plan_id: str
    label: str | None
    status: Status
    reason: str | None = None
    rotation_id: str | None = None  # first requested rotation containing this plan
    rotation_ids: list[str] = Field(default_factory=list)  # every requested rotation containing it
    leg: int | None = None
    dates_assumed: bool | None = None
    editable: list[str] = Field(default_factory=list)
    plan: Plan | None = None
    calendar: CalendarSummary | None = None
    winter: WinterSummary | None = None
    spring: SpringSummary | None = None
    spring_checks: list[CheckSummaryOut] = Field(default_factory=list)
    other_checks: list[RuleLine] = Field(default_factory=list)
    conflicts: list[list[str]] = Field(default_factory=list)
    path_notes: list[dict[str, Any]] = Field(default_factory=list)
    eras: dict[str, EraComparison] = Field(default_factory=dict)
    eras_shared_years: dict[str, EraComparison] = Field(default_factory=dict)
    seasons: list[SeasonRow] = Field(default_factory=list)
    residue_context: list[dict[str, Any]] = Field(default_factory=list)


class SharedYears(_M):
    spring: list[int]
    winter: list[int]
    full_season: list[int]
    note: str


class CompareResponse(_M):
    meta: Meta
    result_id: str
    input_hash: str
    request_echo: dict[str, Any]
    thresholds: ThresholdsView
    shared_eligible_years: SharedYears
    plans: list[PlanComparison]
    soil: dict[str, Any] | None = None
    location: dict[str, Any] | None = None  # resolve result when a point was requested
    data_sources: dict[str, Any]  # per-source freshness: fresh | cached(<at>) | snapshot | unavailable
    eras: dict[str, Any]  # window definitions: earlier/recent/excluded
    coverage_note: str | None = None


class UnsupportedResponse(_M):
    """A plan the catalog/weather cannot evaluate. A result, not an HTTP error."""

    meta: Meta
    status: Status
    plan_id: str
    reason: str
    unsupported: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- replay


class ReplayDay(_M):
    date: date
    precip_mm: float | None
    tmax_c: float | None
    tmin_c: float | None
    gwettop: float | None
    gwetroot: float | None
    cover_status: Literal["planned_living_cover", "terminated", "no_planned_cover"]
    segment: str
    in_spring_window: bool
    heavy_rain: bool | None
    missing: list[str] = Field(default_factory=list)  # variables missing that day, with reason below
    missing_reasons: dict[str, str] = Field(default_factory=dict)


class KeyRainDay(_M):
    date: date
    precip_mm: float
    segment: str
    heavy: bool | None


class TriggeredCheck(_M):
    check_id: str
    rule_ids: list[str]
    reason: str
    inputs_used: dict[str, Any]
    source: dict[str, Any] | None


class ReplayResponse(_M):
    meta: Meta
    year: int
    plan_id: str
    dates: dict[str, Any]
    coverage: dict[str, Status]
    spring: dict[str, Any]
    wetness: dict[str, Any]
    winter: dict[str, Any]
    thresholds: ThresholdsView
    checks_triggered: list[TriggeredCheck]
    key_rain_days: list[KeyRainDay]
    daily: list[ReplayDay]


# --------------------------------------------------------------------------- sensitivity


class SensitivityPoint(_M):
    terminate: str  # MM-DD
    gap_days: int
    living_cover_days_planned: int
    rain_outside_cover_mm_median: float | None
    heavy_rain_days_outside_cover_median: float | None
    checks_count: int
    denominator: int
    gap_days_in_leap_years: int | None = None  # set when a Feb 29 crossing changes the gap


class SensitivityResponse(_M):
    meta: Meta
    status: Status  # complete | inapplicable | manual_check | unknown
    base_plan_id: str
    varied: Literal["terminate"]
    fixed: dict[str, Any]
    check_id: str
    rule_ids: list[str]
    denominator: int
    dry_years: list[int]
    reference_year: int
    points: list[SensitivityPoint]
    thresholds: ThresholdsView
    note: str


# --------------------------------------------------------------------------- years


class YearRow(_M):
    year: int
    spring: Status
    winter: Status
    full_season: Status
    reason: str | None


class YearsResponse(_M):
    meta: Meta
    location: dict[str, Any]
    plan_basis: dict[str, str]
    years: list[YearRow]
    shortcuts: dict[str, int | None]
    eras: dict[str, Any]


# --------------------------------------------------------------------------- rotations


class RotationsResponse(_M):
    meta: Meta
    rotations: list[Rotation]
