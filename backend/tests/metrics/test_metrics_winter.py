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
    ThresholdMismatchError,
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


def test_heavy_rain_threshold_is_the_published_fixed_value_frozen_once_and_shared(union):
    series, h = union
    ts = build_threshold_set(series, h)
    assert ts.threshold_set_id == build_threshold_set(series, h).threshold_set_id
    t = ts.get(HEAVY_RAIN_NAME)
    assert t.value == 76.2 and t.unit == "mm/day" and t.method == "published_fixed"
    assert t.parameters["assumed"] is False and t.parameters["inclusive"] is True
    assert t.reference_span == "1981-01-01..2025-06-30" and t.n_reference == 16252
    # same set -> same threshold regardless of plan, year or era
    a = compute_winter(plan("none"), build_calendar(plan("none"), 1990), series, ts, h)
    b = compute_winter(plan("rye"), build_calendar(plan("rye"), 2015), series, ts, h)
    assert a.heavy_rain_threshold_mm == b.heavy_rain_threshold_mm == 76.2
    assert a.threshold_set_id == b.threshold_set_id == ts.threshold_set_id


def test_threshold_records_its_catalog_source_url_and_locator(union):
    series, h = union
    t = build_threshold_set(series, h).get(HEAVY_RAIN_NAME)
    assert t.source.rule_id == "fc_v2_ref_very_heavy_rain"
    assert t.source.url.startswith("https://files.nc.gov/") and t.source.url.endswith(".pdf")
    assert "PDF p. 4" in t.source.locator and t.source.verified_date == "2026-11-13"
    assert "North Carolina Climate Science Report" in t.source.title


def test_threshold_note_states_time_convention_and_scope(union):
    series, h = union
    t = build_threshold_set(series, h).get(HEAVY_RAIN_NAME)
    assert "Local Solar Time" in t.note and "LST" in t.note and "rolling 24-hour" in t.note
    assert "not erosion, runoff or soil loss" in t.note and "Zero-count winters" in t.note
    assert t.parameters["scope"] == "rainfall depth only; not erosion or soil loss"
    assert "erosion" not in (t.parameters["comparison"] + t.parameters["daily_value_basis"])


def test_the_threshold_is_independent_of_the_record_it_is_applied_to():
    wet = weather(heavy_days=["2021-12-01"])  # 40 mm days
    dry = weather()
    a = build_threshold_set(wet, HASH).get(HEAVY_RAIN_NAME)
    b = build_threshold_set(dry, HASH).get(HEAVY_RAIN_NAME)
    assert a.value == b.value == 76.2


def test_a_day_at_exactly_76_2_mm_is_heavy_and_76_199_is_not():
    series = weather(light={"2021-11-01": 76.2, "2021-11-02": 76.199, "2021-11-03": 120.0})
    ts = build_threshold_set(series, HASH)
    w = compute_winter(plan("none"), build_calendar(plan("none"), 2022), series, ts, HASH)
    assert [e.date for e in w.heavy_rain_events] == [date(2021, 11, 1), date(2021, 11, 3)]


def test_zero_count_winters_are_valid_complete_results_with_known_rain(union):
    series, h = union
    ts = build_threshold_set(series, h)
    w = compute_winter(plan("rye"), build_calendar(plan("rye"), 2010), series, ts, h)
    assert w.status == Status.COMPLETE and w.eligible
    assert w.heavy_rain_days == 0 and w.heavy_rain_days_outside_cover == 0  # real zero, not None
    assert w.heavy_rain_events == [] and w.total_rain_mm > 0
    # most winters have none: only 6 days >= 76.2 mm fall in Sep-May over the whole record
    counts = [
        compute_winter(plan("none"), build_calendar(plan("none"), y), series, ts, h)
        for y in range(1982, 2026)
    ]
    assert sum(c.heavy_rain_days for c in counts) < 10
    assert sum(c.heavy_rain_days == 0 for c in counts) >= 36



def test_missing_reference_row_is_a_loud_error_not_a_silent_default(monkeypatch, tmp_path):
    import fieldshift.metrics.thresholds as th

    empty = tmp_path / "weather_references.csv"
    empty.write_text("rule_id,operator,unit\n")
    original = th.load_reference_row
    monkeypatch.setattr(th, "load_reference_row", lambda rid, path=empty: original(rid, path))
    with pytest.raises(th.ReferenceError):
        build_threshold_set(weather(), HASH)


def test_the_old_p95_rule_is_not_part_of_the_default_set_but_remains_an_explicit_option(union):
    from fieldshift.metrics.thresholds import HeavyRainRule

    series, h = union
    assert "p95" not in str(build_threshold_set(series, h).thresholds).lower()
    exp = build_threshold_set(series, h, heavy_rule=HeavyRainRule(method="percentile_of_wet_days"))
    t = exp.get(HEAVY_RAIN_NAME)
    assert t.parameters["assumed"] is True and 25 < t.value < 35  # labelled assumed, experiments only
    assert exp.threshold_set_id != build_threshold_set(series, h).threshold_set_id


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


# --- Phase 3 review fixes --------------------------------------------------------------------


def test_rain_totals_survive_when_no_heavy_rain_threshold_can_be_computed():
    from fieldshift.metrics.thresholds import HeavyRainRule

    days = pd.date_range("1981-01-01", "2025-06-30", freq="D")
    series = DailySeries(pd.DataFrame({"date": days, "precip_mm": 0.0, "gwettop": 0.5,
                                       "gwetroot": 0.5}))
    # an all-zero record has no wet days, so the (experimental) relative rule has no value
    ts = build_threshold_set(series, HASH, heavy_rule=HeavyRainRule(method="percentile_of_wet_days"))
    assert ts.get(HEAVY_RAIN_NAME).value is None
    p = plan("rye")
    w = compute_winter(p, build_calendar(p, 2010), series, ts, HASH)
    assert w.status == Status.PARTIAL and not w.eligible
    assert w.total_rain_mm == 0.0 and w.rain_outside_cover_mm == 0.0  # known zero, not None
    assert w.heavy_rain_days is None and w.heavy_rain_days_outside_cover is None
    assert "heavy_rain_threshold_unavailable" in w.reasons


def test_thresholds_from_another_snapshot_are_rejected():
    p = plan("rye")
    with pytest.raises(ThresholdMismatchError):
        compute_winter(p, build_calendar(p, 2022), weather(), thresholds(), "another-hash")
