"""Phase 2 tests. Plans are synthetic FIXTURES; weather coverage uses the real Union snapshot."""

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from fieldshift.contracts import InvalidPlanError, Plan, Status, WinterManagement
from fieldshift.seasons.align import build_calendar, build_calendars
from fieldshift.seasons.coverage import planting_years, season_coverage
from fieldshift.weather.series import DailySeries
from fieldshift.weather.snapshot import load_snapshot


def plan(winter=None, harvest="09-25", plant="05-12", **kw) -> Plan:
    return Plan(
        plan_id=kw.pop("plan_id", "fixture"),
        previous_crop_id="field_corn",
        prev_harvest=harvest,
        winter=winter or WinterManagement(),
        next_crop_id="soybean",
        next_plant=plant,
        **kw,
    )


def rye(seed="10-15", terminate="04-30") -> WinterManagement:
    return WinterManagement(kind="cover", crop_id="cereal_rye", seed=seed, terminate=terminate)


@pytest.fixture(scope="module")
def series() -> DailySeries:
    return DailySeries(load_snapshot().daily)


# --- windows -------------------------------------------------------------------------------


def test_may_12_planting_gives_apr_12_to_may_11_spring_window():
    cal = build_calendar(plan(), 2022)
    assert (cal.spring_start, cal.spring_end, cal.spring_days) == (
        date(2022, 4, 12), date(2022, 5, 11), 30)
    assert cal.plant == date(2022, 5, 12)


def test_winter_window_includes_harvest_day_and_excludes_planting_day():
    cal = build_calendar(plan(), 2022)
    assert cal.prev_harvest == date(2021, 9, 25)
    assert cal.winter_days == (date(2022, 5, 12) - date(2021, 9, 25)).days == 229


def test_harvest_year_depends_on_mm_dd_order():
    assert build_calendar(plan(harvest="09-25", plant="05-12"), 2022).prev_harvest.year == 2021
    # harvest MM-DD earlier than planting MM-DD -> same year
    assert build_calendar(plan(harvest="03-01", plant="05-12"), 2022).prev_harvest == date(2022, 3, 1)


def test_cover_interval_is_half_open_and_labeled_planned():
    cal = build_calendar(plan(rye()), 2022)
    c = cal.cover
    assert (c.seed, c.terminate) == (date(2021, 10, 15), date(2022, 4, 30))
    assert c.days == (date(2022, 4, 30) - date(2021, 10, 15)).days  # terminate day not cover
    assert c.label == "planned" and c.establishment == "uncertain"
    assert cal.termination_gap_days == 12


def test_gap_is_plant_minus_terminate():
    assert build_calendar(plan(rye(terminate="04-23")), 2022).termination_gap_days == 19
    assert build_calendar(plan(rye(terminate="05-12")), 2022).termination_gap_days == 0
    assert build_calendar(plan(), 2022).termination_gap_days is None


def test_cover_seed_after_new_year_resolves_into_next_calendar_year():
    cal = build_calendar(plan(rye(seed="01-15", terminate="04-30")), 2022)
    assert cal.cover.seed == date(2022, 1, 15)


# --- leap days -----------------------------------------------------------------------------


def test_winter_crossing_2020_02_29_is_one_day_longer_than_one_crossing_2019_02_28():
    leap, normal = build_calendar(plan(), 2020), build_calendar(plan(), 2019)
    assert leap.winter_days == normal.winter_days + 1
    # spring window is unaffected by Feb 29 (Apr 12 - May 11)
    assert leap.spring_days == normal.spring_days == 30


def test_feb_29_resolves_to_feb_28_in_non_leap_years():
    p = plan(rye(seed="10-15", terminate="02-29"), plant="03-15")
    assert build_calendar(p, 2020).cover.terminate == date(2020, 2, 29)
    assert build_calendar(p, 2021).cover.terminate == date(2021, 2, 28)


def test_planting_on_feb_29_resolves_to_feb_28():
    p = plan(harvest="09-25", plant="02-29")
    assert build_calendar(p, 2019).plant == date(2019, 2, 28)
    assert build_calendar(p, 2020).plant == date(2020, 2, 29)


# --- chronology validation -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("kw", "field", "code"),
    [
        (dict(winter=rye(seed="09-15")), "winter.seed", "seed_before_harvest"),
        (dict(winter=rye(terminate="05-20")), "winter.terminate", "terminate_after_planting"),
        (dict(winter=rye(seed="10-15", terminate="10-15")), "winter.terminate",
         "terminate_not_after_seed"),
        (dict(winter=rye(seed="10-15", terminate="10-01")), "winter.terminate",
         "terminate_not_after_seed"),
        (dict(harvest="05-12", plant="05-12"), "next_plant", "window_not_positive"),
    ],
)
def test_invalid_chronology_returns_typed_error_with_field(kw, field, code):
    with pytest.raises(InvalidPlanError) as exc:
        build_calendar(plan(**kw), 2022)
    issue = exc.value.issues[0]
    assert (issue.field, issue.code) == (field, code)
    body = exc.value.as_body()
    assert body["status"] == "invalid_input" and body["issues"][0]["field"] == field


def test_seed_after_planting_is_reported_distinctly():
    with pytest.raises(InvalidPlanError) as exc:
        build_calendar(plan(rye(seed="05-20", terminate="05-25")), 2022)
    assert {i.code for i in exc.value.issues} >= {"seed_after_planting"}


def test_bad_mm_dd_and_missing_cover_fields_are_rejected_by_the_model():
    with pytest.raises(ValidationError):
        plan(harvest="13-01")
    with pytest.raises(ValidationError):
        plan(harvest="02-30")
    with pytest.raises(ValidationError):
        WinterManagement(kind="cover", crop_id="cereal_rye", seed="10-15")  # no terminate


def test_winter_grain_calendar_and_validation():
    wg = WinterManagement(kind="winter_grain", crop_id="winter_wheat", plant="10-25", harvest="06-10")
    # soybean after wheat harvest: next_plant after the grain harvest
    cal = build_calendar(plan(wg, plant="06-20"), 2022)
    assert cal.grain.plant == date(2021, 10, 25) and cal.grain.harvest == date(2022, 6, 10)
    with pytest.raises(InvalidPlanError):
        build_calendar(plan(wg, plant="05-12"), 2022)  # grain harvest after next planting


def test_build_calendars_validates_before_building_any_year():
    with pytest.raises(InvalidPlanError):
        build_calendars(plan(rye(seed="09-15")), [2020, 2021])


# --- coverage against the real snapshot ------------------------------------------------------


def test_record_gives_45_planting_years_1981_to_2025(series):
    years = planting_years(series)
    assert years[0] == 1981 and years[-1] == 2025 and len(years) == 45


def test_1981_spring_complete_1981_winter_partial_and_44_complete_winters(series):
    p = plan()
    cov = {y: season_coverage(build_calendar(p, y), series) for y in planting_years(series)}
    assert cov[1981].metrics["spring"].status == Status.COMPLETE
    w81 = cov[1981].metrics["winter"]
    assert w81.status == Status.PARTIAL and not w81.eligible
    assert "record_starts_after_window_start" in w81.reasons
    assert sum(c.metrics["spring"].eligible for c in cov.values()) == 45
    assert sum(c.metrics["winter"].eligible for c in cov.values()) == 44
    assert cov[2025].metrics["winter"].status == Status.COMPLETE  # record runs to 2025-06-30


def test_plant_after_record_end_is_unavailable_not_zero(series):
    cal = build_calendar(plan(plant="09-10", harvest="09-05"), 2025)  # after 2025-06-30
    cov = season_coverage(cal, series).metrics["spring"]
    assert cov.status == Status.UNAVAILABLE and cov.valid_days == 0
    assert "record_ends_before_window_end" in cov.reasons


def test_missing_wetness_makes_only_wetness_unavailable():
    days = pd.date_range("2022-03-01", "2022-05-31", freq="D")
    daily = pd.DataFrame({"date": days, "precip_mm": 1.0, "gwettop": float("nan"), "gwetroot": 0.5})
    series = DailySeries(daily)
    cov = season_coverage(build_calendar(plan(harvest="03-01"), 2022), series)
    assert cov.metrics["spring"].status == Status.COMPLETE
    assert cov.metrics["wetness"].status == Status.UNAVAILABLE
    assert cov.metrics["wetness"].reasons == ["missing_values_in_record"]
    assert cov.metrics["winter"].status == Status.COMPLETE


def test_one_missing_precip_day_makes_window_partial_not_complete():
    days = pd.date_range("2022-03-01", "2022-05-31", freq="D")
    precip = pd.Series(0.0, index=range(len(days)))  # real zeros stay valid
    precip.iloc[40] = float("nan")
    daily = pd.DataFrame({"date": days, "precip_mm": precip, "gwettop": 0.5, "gwetroot": 0.5})
    cal = build_calendar(plan(harvest="03-01"), 2022)
    cov = season_coverage(cal, DailySeries(daily))
    assert cov.metrics["winter"].status == Status.PARTIAL
    assert cov.metrics["winter"].missing_days == 1
    assert cov.metrics["winter"].eligible is False


# --- Phase 2 review fixes --------------------------------------------------------------------


def test_feb_29_harvest_with_feb_28_planting_is_valid_across_leap_and_non_leap_years():
    p = plan(harvest="02-29", plant="02-28")
    leap = build_calendar(p, 2020)  # harvest 2019-02-28 (non-leap) -> plant 2020-02-28
    assert leap.prev_harvest == date(2019, 2, 28) and leap.winter_days == 365
    normal = build_calendar(p, 2021)  # harvest 2020-02-29 -> plant 2021-02-28
    assert normal.prev_harvest == date(2020, 2, 29) and normal.winter_days == 365


def test_feb_29_collapsing_two_dates_raises_typed_error_for_that_year_only():
    p = plan(rye(seed="02-28", terminate="02-29"), harvest="09-25", plant="05-12")
    with pytest.raises(InvalidPlanError):
        build_calendar(p, 2021)  # both resolve to Feb 28: empty cover interval
    assert build_calendar(p, 2020).cover.days == 1


def test_late_planting_keeps_2025_with_unavailable_coverage(series):
    years = planting_years(series)
    assert years[-1] == 2025 and len(years) == 45
    cal = build_calendar(plan(harvest="09-05", plant="09-10"), 2025)
    assert season_coverage(cal, series).metrics["spring"].status == Status.UNAVAILABLE


def test_blank_crop_ids_are_validation_errors_not_assertion_errors():
    with pytest.raises(ValidationError):
        WinterManagement(kind="cover", crop_id="", seed="10-15", terminate="04-30")
    with pytest.raises(ValidationError):
        WinterManagement(kind="cover", crop_id="   ", seed="10-15", terminate="04-30")
    with pytest.raises(ValidationError):
        Plan(plan_id="x", previous_crop_id="", prev_harvest="09-25", next_crop_id="soybean",
             next_plant="05-12")


def test_threshold_set_is_deeply_immutable():
    from fieldshift.contracts import Threshold, ThresholdSet

    t = Threshold(name="heavy_rain_mm", method="m", value=1.0, unit="mm/day", reference_span="x",
                  n_reference=1, parameters={"months": [1, 2], "nested": {"a": 1}})
    ts = ThresholdSet(snapshot_hash="h", thresholds={"heavy_rain_mm": t})
    before = ts.threshold_set_id
    with pytest.raises(TypeError):
        ts.thresholds["x"] = t
    with pytest.raises(TypeError):
        ts.thresholds["heavy_rain_mm"].parameters["nested"]["a"] = 2
    with pytest.raises(TypeError):
        ts.thresholds["heavy_rain_mm"].parameters["extra"] = 1
    assert isinstance(ts.thresholds["heavy_rain_mm"].parameters["months"], tuple)
    assert ts.threshold_set_id == before


def test_omitted_threshold_parameters_default_is_immutable():
    from fieldshift.contracts import Threshold

    t = Threshold(name="n", method="m", value=1.0, unit="mm", reference_span="x", n_reference=1)
    with pytest.raises(TypeError):
        t.parameters["x"] = 1
