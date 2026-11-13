"""Winter soil-protection exposure: rain that fell while no living cover was planned.

Per season, the winter window ``[prev_harvest, plant)`` is split into segments:

* ``living_cover``            ``[seed, terminate)`` (planned; establishment is uncertain)
* ``before_establishment``    ``[prev_harvest, seed)`` for a cover plan
* ``after_termination``       ``[terminate, plant)`` for a cover plan (terminate day included)
* ``no_planned_cover``        the whole window for a no-cover plan

"Outside cover" = every segment except ``living_cover``. Residue context (corn residue,
cover residue, grower-reported) is recorded separately and never changes any count.
Paired plans read the same weather rows; the output carries the snapshot hash so a client
can verify that.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from fieldshift.contracts import Plan, SeasonCalendar, Status, ThresholdSet
from fieldshift.metrics.thresholds import HEAVY_RAIN_NAME
from fieldshift.seasons.coverage import season_coverage
from fieldshift.weather.series import DailySeries

LIVING_COVER = "living_cover"
BEFORE_ESTABLISHMENT = "before_establishment"
AFTER_TERMINATION = "after_termination"
NO_PLANNED_COVER = "no_planned_cover"
OUTSIDE_SEGMENTS = (BEFORE_ESTABLISHMENT, AFTER_TERMINATION, NO_PLANNED_COVER)
ALL_SEGMENTS = (LIVING_COVER, *OUTSIDE_SEGMENTS)


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SegmentTotals(_M):
    days: int
    rain_mm: float | None
    heavy_rain_days: int | None


class HeavyRainEvent(_M):
    date: date
    precip_mm: float
    segment: str


class ResidueContext(_M):
    kind: str  # corn_residue | cover_residue | grower_reported
    note: str
    changes_living_cover_indicator: bool = False


class WinterExposure(_M):
    plan_id: str
    year: int
    status: Status
    eligible: bool
    reasons: list[str] = Field(default_factory=list)
    snapshot_hash: str
    threshold_set_id: str
    heavy_rain_threshold_mm: float | None
    window_start: date
    window_end_exclusive: date
    window_days: int
    living_cover_days: int
    days_outside_cover: int
    total_rain_mm: float | None
    heavy_rain_days: int | None
    rain_outside_cover_mm: float | None
    heavy_rain_days_outside_cover: int | None
    segments: dict[str, SegmentTotals]
    heavy_rain_events: list[HeavyRainEvent]
    residue_context: list[ResidueContext]
    cover_label: str | None = None  # "planned" for cover plans; establishment uncertain


def winter_day_segments(cal: SeasonCalendar) -> pd.Series:
    """Segment label for every day of ``[prev_harvest, plant)`` (index = Timestamp)."""
    days = pd.date_range(cal.prev_harvest, cal.plant - pd.Timedelta(days=1), freq="D")
    labels = pd.Series(NO_PLANNED_COVER, index=days, dtype="object")
    if cal.cover is not None:
        seed, term = pd.Timestamp(cal.cover.seed), pd.Timestamp(cal.cover.terminate)
        labels[days < seed] = BEFORE_ESTABLISHMENT
        labels[(days >= seed) & (days < term)] = LIVING_COVER
        labels[days >= term] = AFTER_TERMINATION
    return labels


def _residue_context(plan: Plan, cal: SeasonCalendar) -> list[ResidueContext]:
    out: list[ResidueContext] = []
    if plan.previous_crop_id == "field_corn":
        out.append(ResidueContext(
            kind="corn_residue",
            note="Corn residue may remain after harvest. Context only: it is not living cover "
            "and changes no count.",
        ))
    if cal.cover is not None:
        out.append(ResidueContext(
            kind="cover_residue",
            note="Terminated cover residue may remain after termination. Context only: it "
            "does not extend the living-cover interval.",
        ))
    if plan.grower.residue_report:
        out.append(ResidueContext(
            kind="grower_reported",
            note=f"Grower report: {plan.grower.residue_report}. Context only; no count changed.",
        ))
    return out


def compute_winter(
    plan: Plan,
    cal: SeasonCalendar,
    series: DailySeries,
    thresholds: ThresholdSet,
    snapshot_hash: str,
) -> WinterExposure:
    """Winter exposure for one season. Totals are ``None`` unless the window is complete."""
    heavy = thresholds.get(HEAVY_RAIN_NAME)
    cov = season_coverage(cal, series).metrics["winter"]
    labels = winter_day_segments(cal)
    rows = series.window(["precip_mm"], cal.prev_harvest, cal.plant)
    precip = rows["precip_mm"]

    status, reasons = cov.status, list(cov.reasons)
    if plan.winter.kind == "winter_grain":  # Phase 12 path
        status, reasons = Status.UNSUPPORTED, ["winter_grain_path_not_enabled"]
    elif heavy.value is None:
        status, reasons = Status.UNAVAILABLE, [*reasons, "heavy_rain_threshold_unavailable"]
    computable = status == Status.COMPLETE

    seg_days = {s: int((labels == s).sum()) for s in ALL_SEGMENTS}
    segments: dict[str, SegmentTotals] = {}
    events: list[HeavyRainEvent] = []
    heavy_flag = (precip >= heavy.value) if heavy.value is not None else precip.isna()
    for s in ALL_SEGMENTS:
        mask = labels == s
        if not computable:
            segments[s] = SegmentTotals(days=seg_days[s], rain_mm=None, heavy_rain_days=None)
            continue
        segments[s] = SegmentTotals(
            days=seg_days[s],
            rain_mm=round(float(precip[mask].sum()), 3),
            heavy_rain_days=int((heavy_flag & mask).sum()),
        )
    if computable:
        for ts in precip.index[heavy_flag.to_numpy()]:
            events.append(HeavyRainEvent(
                date=ts.date(), precip_mm=round(float(precip[ts]), 3), segment=str(labels[ts])))

    outside = [segments[s] for s in OUTSIDE_SEGMENTS]
    outside_days = sum(seg_days[s] for s in OUTSIDE_SEGMENTS)
    return WinterExposure(
        plan_id=plan.plan_id,
        year=cal.year,
        status=status,
        eligible=computable,
        reasons=reasons,
        snapshot_hash=snapshot_hash,
        threshold_set_id=thresholds.threshold_set_id,
        heavy_rain_threshold_mm=heavy.value,
        window_start=cal.prev_harvest,
        window_end_exclusive=cal.plant,
        window_days=cal.winter_days,
        living_cover_days=seg_days[LIVING_COVER],
        days_outside_cover=outside_days,
        total_rain_mm=round(float(precip.sum()), 3) if computable else None,
        heavy_rain_days=len(events) if computable else None,
        rain_outside_cover_mm=(
            round(sum(s.rain_mm for s in outside), 3) if computable else None  # type: ignore[misc]
        ),
        heavy_rain_days_outside_cover=(
            sum(s.heavy_rain_days for s in outside) if computable else None  # type: ignore[misc]
        ),
        segments=segments,
        heavy_rain_events=events,
        residue_context=_residue_context(plan, cal),
        cover_label=cal.cover.label if cal.cover else None,
    )
