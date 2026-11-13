"""Phase 3 tests. Weather here is a synthetic FIXTURE except where the Union snapshot is named."""

from datetime import date

import pandas as pd
import pytest

from fieldshift.contracts import (
    GrowerInputs,
    Plan,
    Status,
    Threshold,
    ThresholdSet,
    WinterManagement,
)
from fieldshift.metrics.thresholds import HEAVY_RAIN_NAME, build_threshold_set, heavy_rain_threshold
from fieldshift.metrics.winter import (
    AFTER_TERMINATION,
    BEFORE_ESTABLISHMENT,
    LIVING_COVER,
    NO_PLANNED_COVER,
    compute_winter,
)
from fieldshift.seasons.align import build_calendar
from fieldshift.weather.series import DailySeries
from fieldshift.weather.snapshot import load_snapshot

HASH = "fixture-hash"


def thresholds(value: float = 25.0) -> ThresholdSet:
    t = Threshold(
        name=HEAVY_RAIN_NAME,
        method="fixed_mm",
        value=value,
        unit="mm/day",
        reference_span="fixture",
        n_reference=0,
    )
    return ThresholdSet(snapshot_hash=HASH, thresholds={HEAVY_RAIN_NAME: t})


def weather(heavy_days=(), light=None, start="2021-08-01", end="2022-06-30") -> DailySeries:
    days = pd.date_range(start, end, freq="D")
    precip = pd.Series(0.0, index=days)
    for d in heavy_days:
        precip[pd.Timestamp(d)] = 40.0
    for d, v in (light or {}).items():
        precip[pd.Timestamp(d)] = v
    return DailySeries(
        pd.DataFrame(
            {"date": days, "precip_mm": precip.to_numpy(), "gwettop": 0.5, "gwetroot": 0.5}
        )
    )


def plan(kind="rye", residue=None, prev="field_corn") -> Plan:
    winter = (
        WinterManagement(kind="cover", crop_id="cereal_rye", seed="10-15", terminate="04-30")
        if kind == "rye"
        else WinterManagement()
    )
    return Plan(
        plan_id=kind,
        previous_crop_id=prev,
        prev_harvest="09-25",
        winter=winter,
        next_crop_id="soybean",
        next_plant="05-12",
        grower=GrowerInputs(residue_report=residue),
    )


def run(p: Plan, series: DailySeries, value=25.0):
    cal = build_calendar(p, 2022)
    return compute_winter(p, cal, series, thresholds(value), HASH)


def test_heavy_day_before_seeding_is_before_establishment():
    w = run(plan(), weather(heavy_days=["2021-10-14"]))
    (event,) = w.heavy_rain_events
    assert event.segment == BEFORE_ESTABLISHMENT and event.date == date(2021, 10, 14)


def test_heavy_day_on_termination_day_is_after_termination_not_cover():
    w = run(plan(), weather(heavy_days=["2022-04-30"]))
    (event,) = w.heavy_rain_events
    assert event.segment == AFTER_TERMINATION
    assert w.segments[LIVING_COVER].heavy_rain_days == 0
    assert w.segments[AFTER_TERMINATION].heavy_rain_days == 1


def test_seed_day_is_cover_and_day_before_termination_is_cover():
    w = run(plan(), weather(heavy_days=["2021-10-15", "2022-04-29"]))
    assert [e.segment for e in w.heavy_rain_events] == [LIVING_COVER, LIVING_COVER]
    assert w.heavy_rain_days_outside_cover == 0


def test_segment_day_counts_partition_the_half_open_winter_window():
    w = run(plan(), weather())
    s = w.segments
    assert s[BEFORE_ESTABLISHMENT].days == (date(2021, 10, 15) - date(2021, 9, 25)).days == 20
    assert s[LIVING_COVER].days == (date(2022, 4, 30) - date(2021, 10, 15)).days
    assert s[AFTER_TERMINATION].days == (date(2022, 5, 12) - date(2022, 4, 30)).days == 12
    assert sum(x.days for x in s.values()) == w.window_days == 229
    assert w.living_cover_days + w.days_outside_cover == w.window_days
    assert w.cover_label == "planned"


def test_harvest_day_is_in_window_and_planting_day_is_not():
    # heavy rain on harvest day counts; on planting day it does not
    w = run(plan(), weather(heavy_days=["2021-09-25", "2022-05-12"]))
    assert [e.date for e in w.heavy_rain_events] == [date(2021, 9, 25)]


def test_no_cover_vs_rye_same_rain_and_event_dates_only_segments_differ():
    series = weather(
        heavy_days=["2021-10-14", "2021-12-01", "2022-04-30"], light={"2022-01-10": 3.5}
    )
    none, rye = run(plan("none"), series), run(plan("rye"), series)
    assert none.total_rain_mm == rye.total_rain_mm == 3.5 + 3 * 40.0
    assert [e.date for e in none.heavy_rain_events] == [e.date for e in rye.heavy_rain_events]
    assert {e.segment for e in none.heavy_rain_events} == {NO_PLANNED_COVER}
    assert [e.segment for e in rye.heavy_rain_events] == [
        BEFORE_ESTABLISHMENT,
        LIVING_COVER,
        AFTER_TERMINATION,
    ]
    assert none.living_cover_days == 0 and none.days_outside_cover == none.window_days
    assert none.heavy_rain_days_outside_cover == 3 and rye.heavy_rain_days_outside_cover == 2
    assert none.snapshot_hash == rye.snapshot_hash == HASH


def test_grower_residue_report_is_visible_and_changes_no_count():
    series = weather(heavy_days=["2021-10-14", "2021-12-01"])
    base = run(plan("none"), series)
    with_residue = run(plan("none", residue="heavy corn stalk residue"), series)
    kinds = [r.kind for r in with_residue.residue_context]
    assert "grower_reported" in kinds and "corn_residue" in kinds
    assert all(not r.changes_living_cover_indicator for r in with_residue.residue_context)
    for field in (
        "living_cover_days",
        "days_outside_cover",
        "total_rain_mm",
        "heavy_rain_days",
        "heavy_rain_days_outside_cover",
        "segments",
    ):
        assert getattr(with_residue, field) == getattr(base, field)
    assert with_residue.living_cover_days == 0


def test_threshold_is_inclusive_and_real_zero_totals_stay_zero():
    series = weather(light={"2021-11-01": 25.0, "2021-11-02": 24.999})
    w = run(plan("none"), series, value=25.0)
    assert [e.date for e in w.heavy_rain_events] == [date(2021, 11, 1)]
    dry = run(plan("none"), weather())
    assert dry.total_rain_mm == 0.0 and dry.heavy_rain_days == 0 and dry.status == Status.COMPLETE


def test_incomplete_window_has_no_totals_and_is_not_eligible():
    series = weather(start="2021-12-01")  # record starts after the winter window start
    w = run(plan(), series)
    assert w.status == Status.PARTIAL and not w.eligible
    assert w.total_rain_mm is None and w.heavy_rain_days is None
    assert w.segments[LIVING_COVER].rain_mm is None
    assert "record_starts_after_window_start" in w.reasons


def test_winter_grain_is_unsupported_until_phase_12():
    p = Plan(
        plan_id="wheat",
        previous_crop_id="field_corn",
        prev_harvest="09-25",
        winter=WinterManagement(
            kind="winter_grain", crop_id="winter_wheat", plant="10-25", harvest="06-10"
        ),
        next_crop_id="soybean",
        next_plant="06-20",
    )
    cal = build_calendar(p, 2022)
    w = compute_winter(p, cal, weather(), thresholds(), HASH)
    assert w.status == Status.UNSUPPORTED and w.total_rain_mm is None


# --- thresholds on the real snapshot -----------------------------------------------------------


@pytest.fixture(scope="module")
def union():
    snap = load_snapshot()
    return DailySeries(snap.daily), snap.snapshot_hash


def test_heavy_rain_threshold_is_frozen_once_and_shared_across_plans(union):
    series, h = union
    ts = build_threshold_set(series, h)
    again = build_threshold_set(series, h)
    assert ts.threshold_set_id == again.threshold_set_id
    t = ts.get(HEAVY_RAIN_NAME)
    assert t.method == "percentile_of_wet_days" and t.parameters["assumed"] is True
    assert t.reference_span == "1981-01-01..2025-06-30" and t.n_reference > 1000
    assert 25 < t.value < 35
    # same set -> same threshold regardless of plan, year or era
    a = compute_winter(plan("none"), build_calendar(plan("none"), 1990), series, ts, h)
    b = compute_winter(plan("rye"), build_calendar(plan("rye"), 2015), series, ts, h)
    assert a.heavy_rain_threshold_mm == b.heavy_rain_threshold_mm == t.value
    assert a.threshold_set_id == b.threshold_set_id == ts.threshold_set_id


def test_threshold_set_id_changes_when_threshold_changes(union):
    series, h = union
    assert heavy_rain_threshold(series).value is not None
    assert thresholds(25.0).threshold_set_id != thresholds(26.0).threshold_set_id


def test_real_season_totals_are_consistent(union):
    series, h = union
    ts = build_threshold_set(series, h)
    w = compute_winter(plan("rye"), build_calendar(plan("rye"), 2010), series, ts, h)
    assert w.status == Status.COMPLETE and w.eligible
    assert w.total_rain_mm == pytest.approx(sum(s.rain_mm for s in w.segments.values()), abs=1e-2)
    assert w.heavy_rain_days == len(w.heavy_rain_events)
    assert all(e.precip_mm >= ts.get(HEAVY_RAIN_NAME).value for e in w.heavy_rain_events)
