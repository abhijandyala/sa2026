"""Winter soil-protection exposure: rain that fell while no living cover was planned.

Per season, the winter window ``[prev_harvest, plant)`` is split into segments:

* ``living_cover``            ``[seed, terminate)`` (planned; establishment is uncertain)
* ``before_establishment``    ``[prev_harvest, seed)`` for a cover plan
* ``after_termination``       ``[terminate, plant)`` for a cover plan (terminate day included)
* ``no_planned_cover``        the whole window for a no-cover plan

A winter-grain plan (wheat) uses the same segments: growing wheat ``[wheat plant, wheat harvest)``
is the living-cover interval (planned; establishment is uncertain), the days before it are
``before_establishment`` and the days from the wheat harvest to the next planting are
``after_termination`` (here: after harvest). The window always runs from the previous harvest to
the next planting date, so it is that plan's own window.

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


class ThresholdMismatchError(ValueError):
    """Thresholds were frozen from a different weather snapshot than the one being used."""


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


def living_interval(cal: SeasonCalendar) -> tuple[date, date] | None:
    """``[start, end)`` of planned living cover: a cover crop's seed..terminate, or growing
    winter grain's plant..harvest. ``None`` for a plan with nothing planned."""
    if cal.cover is not None:
        return cal.cover.seed, cal.cover.terminate
    if cal.grain is not None:
        return cal.grain.plant, cal.grain.harvest
    return None


def winter_day_segments(cal: SeasonCalendar) -> pd.Series:
    """Segment label for every day of ``[prev_harvest, plant)`` (index = Timestamp)."""
    days = pd.date_range(cal.prev_harvest, cal.plant - pd.Timedelta(days=1), freq="D")
    labels = pd.Series(NO_PLANNED_COVER, index=days, dtype="object")
    interval = living_interval(cal)
    if interval is not None:
        seed, term = pd.Timestamp(interval[0]), pd.Timestamp(interval[1])
        labels[days < seed] = BEFORE_ESTABLISHMENT
        labels[(days >= seed) & (days < term)] = LIVING_COVER
        labels[days >= term] = AFTER_TERMINATION
    return labels


def _residue_context(plan: Plan, cal: SeasonCalendar) -> list[ResidueContext]:
    out: list[ResidueContext] = []
    if plan.previous_crop_id == "field_corn":
        out.append(
            ResidueContext(
                kind="corn_residue",
                note="Corn residue may remain after harvest. Context only: it is not living cover "
                "and changes no count.",
            )
        )
    if cal.cover is not None:  # winter grain leaves a harvested crop, not a terminated cover
        out.append(
            ResidueContext(
                kind="cover_residue",
                note="Terminated cover residue may remain after termination. Context only: it "
                "does not extend the living-cover interval.",
            )
        )
    if plan.grower.residue_report:
        out.append(
            ResidueContext(
                kind="grower_reported",
                note=f"Grower report: {plan.grower.residue_report}. Context only; no count changed.",
            )
        )
    return out


def compute_winter(
    plan: Plan,
    cal: SeasonCalendar,
    series: DailySeries,
    thresholds: ThresholdSet,
    snapshot_hash: str,
) -> WinterExposure:
    """Winter exposure for one season. Totals are ``None`` unless the window is complete."""
    if thresholds.snapshot_hash != snapshot_hash:
        raise ThresholdMismatchError(
            "thresholds were frozen from a different snapshot than the one in use"
        )
    heavy = thresholds.get(HEAVY_RAIN_NAME)
    cov = season_coverage(cal, series).metrics["winter"]
    labels = winter_day_segments(cal)
    rows = series.window(["precip_mm"], cal.prev_harvest, cal.plant)
    precip = rows["precip_mm"]

    status, reasons = cov.status, list(cov.reasons)
    rain_ok = status == Status.COMPLETE  # rain totals depend only on the weather window
    heavy_ok = rain_ok and heavy.value is not None
    if rain_ok and not heavy_ok:  # rain is known; only the heavy-rain count is missing
        status, reasons = Status.PARTIAL, [*reasons, "heavy_rain_threshold_unavailable"]

    seg_days = {s: int((labels == s).sum()) for s in ALL_SEGMENTS}
    segments: dict[str, SegmentTotals] = {}
    events: list[HeavyRainEvent] = []
    heavy_flag = (precip >= heavy.value) if heavy.value is not None else precip.isna() & False
    for s in ALL_SEGMENTS:
        mask = labels == s
        segments[s] = SegmentTotals(
            days=seg_days[s],
            rain_mm=round(float(precip[mask].sum()), 3) if rain_ok else None,
            heavy_rain_days=int((heavy_flag & mask).sum()) if heavy_ok else None,
        )
    if heavy_ok:
        for ts in precip.index[heavy_flag.to_numpy()]:
            events.append(
                HeavyRainEvent(
                    date=ts.date(), precip_mm=round(float(precip[ts]), 3), segment=str(labels[ts])
                )
            )
    computable = status == Status.COMPLETE

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
        total_rain_mm=round(float(precip.sum()), 3) if rain_ok else None,
        heavy_rain_days=len(events) if heavy_ok else None,
        rain_outside_cover_mm=(
            round(sum(s.rain_mm for s in outside), 3) if rain_ok else None  # type: ignore[misc]
        ),
        heavy_rain_days_outside_cover=(
            sum(s.heavy_rain_days for s in outside) if heavy_ok else None  # type: ignore[misc]
        ),
        segments=segments,
        heavy_rain_events=events,
        residue_context=_residue_context(plan, cal),
        cover_label=(cal.cover or cal.grain).label if (cal.cover or cal.grain) else None,
    )
