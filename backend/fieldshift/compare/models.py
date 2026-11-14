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


# --------------------------------------------------------------------------- weather location


class WeatherLocation(_M):
    """Which place's weather answered the request, and where its thresholds come from."""

    status: Status  # complete | unavailable | unsupported
    code: str | None = None  # no_weather_snapshot | unsupported_location
    reason: str | None = None
    reason_text: str | None = None
    id: str | None = None
    name: str | None = None
    region: str | None = None  # piedmont | coastal_plain (the place's region, from the index)
    region_basis: str | None = None
    point: dict[str, float] | None = None  # the indexed county point
    requested_point: dict[str, float] | None = None
    grid_cell: dict[str, Any] | None = None
    cell_id: str | None = None
    snapshot_hash: str | None = None
    first_date: str | None = None
    last_date: str | None = None
    shares_snapshot_with: str | None = None
    thresholds_from: str


# --------------------------------------------------------------------------- thresholds


class ThresholdsView(_M):
    """Every frozen threshold used. Never hard-code these in a client."""

    threshold_set_id: str
    heavy_rain: Threshold
    dry_spring: dict[str, Threshold]  # keyed by planting MM-DD (the window anchor)
    # which location's weather baseline these were computed from (never shared across locations)
    location_id: str | None = None
    location_name: str | None = None
    baseline: str | None = None


# --------------------------------------------------------------------------- compare


class CalendarSummary(_M):
    reference_year: int
    winter_days: int
    living_cover_days_planned: int
    days_without_planned_cover: int
    termination_gap_days: int | None
    establishment: Literal["uncertain", "inapplicable"]
    # what the "living cover" days are: a cover crop, or growing winter wheat (planned)
    living_cover_kind: Literal["cover_crop", "winter_grain"] | None = None
    spring_window: dict[str, str]  # {"start": "04-12", "end": "05-11"} MM-DD, 30 days


class WinterSummary(_M):
    status: Status
    seasons: int
    eligible_seasons: int
    per_season_median: dict[str, float | None]
    seasons_with_heavy_rain_outside_cover: int | None
    segments: list[str]
    reasons: list[str] = Field(default_factory=list)


class SpringShortcuts(_M):
    """Typical / dry / wet planting years for THIS plan's planting date (its own 30-day window).
    Same definition as ``GET /v1/years``; they follow edited planting dates."""

    typical: int | None = None
    dry: int | None = None
    wet: int | None = None
    basis: str = "own_window_baseline"


class SpringSummary(_M):
    status: Status
    window_days: int
    cutoff_mm: float | None
    eligible_seasons: int
    dry_seasons: int | None
    dry_years: list[int]
    excluded_years: list[dict[str, Any]]
    median_total_mm: float | None
    shortcuts: SpringShortcuts | None = None


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
    reason: str  # for debugging; clients show `text`
    text: str = ""  # one plain sentence for the grower (B's rule_text); never null
    print: bool = False  # worth a printed page (B's rule_text.should_print)
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
    # Modeled soil wetness (MERRA-2 GWET*, 0-1) averaged over the spring window: the same window
    # and "modeled" label as the replay. null (never 0) when the window is not complete.
    gwetroot_window_mean: float | None = None
    gwettop_window_mean: float | None = None
    wetness_status: Status = Status.UNAVAILABLE
    wetness_label: Literal["modeled"] = "modeled"


class PlanComparison(_M):
    plan_id: str
    label: str | None
    label_generated: bool = False  # true when the label was filled in because none was sent
    status: Status
    reason: str | None = None
    reason_text: str | None = None  # a plain sentence for a reason code; the code stays in `reason`
    rotation_id: str | None = None  # first requested rotation containing this plan
    rotation_ids: list[str] = Field(default_factory=list)  # every requested rotation containing it
    leg: int | None = None
    dates_assumed: bool | None = None
    dates_basis: str | None = None  # "assumed" for the sample plans' demo dates
    # set when the sample plan's Piedmont-based demo dates are shown for another region
    dates_assumed_for_region: str | None = None
    region_note: str | None = None  # plain sentence: dates assumed for the Piedmont / region mismatch
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
    # Winter wheat -> double-crop soybean (catalog v2 only): B's wheat path result. It is never
    # folded into the shared-year or era comparisons; the full-season comparison inside it is
    # labelled ``different-calendar`` and shows raw totals only.
    double_crop: dict[str, Any] | None = None


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
    weather_location: WeatherLocation | None = None  # whose weather and thresholds were used
    data_sources: dict[
        str, Any
    ]  # per-source freshness: fresh | cached(<at>) | snapshot | unavailable
    eras: dict[str, Any]  # window definitions: earlier/recent/excluded
    coverage_note: str | None = None


class UnsupportedResponse(_M):
    """A plan the catalog/weather cannot evaluate. A result, not an HTTP error."""

    meta: Meta
    status: Status
    plan_id: str
    reason: str
    unsupported: list[str] = Field(default_factory=list)
    code: str | None = None  # no_weather_snapshot | unsupported_location when the place is the cause
    reason_text: str | None = None
    weather_location: WeatherLocation | None = None


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
    missing: list[str] = Field(
        default_factory=list
    )  # variables missing that day, with reason below
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
    weather_location: WeatherLocation | None = None


# --------------------------------------------------------------------------- sensitivity


class SensitivityPoint(_M):
    terminate: str  # MM-DD
    gap_days: int
    living_cover_days_planned: int
    rain_outside_cover_mm_median: float | None
    heavy_rain_days_outside_cover_median: float | None
    checks_count: int
    denominator: int
    # the seasons this end date would have flagged (same meaning as the comparison check's
    # qualifying_years); len == checks_count, empty when 0
    qualifying_years: list[int] = Field(default_factory=list)
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
    weather_location: WeatherLocation | None = None


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
    weather_location: WeatherLocation | None = None


# --------------------------------------------------------------------------- rotations


class RotationsResponse(_M):
    meta: Meta
    rotations: list[Rotation]
