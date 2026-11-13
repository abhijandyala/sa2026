"""Phase 4a tests. Synthetic weather is a FIXTURE; the Union snapshot is real data."""

from datetime import date

import pandas as pd
import pytest

from fieldshift.contracts import Plan, Status, WinterManagement
from fieldshift.metrics.spring import (
    SPRING_DRY_PREFIX,
    compute_spring,
    dry_cutoff,
    spring_reference,
    spring_window_for,
)
from fieldshift.metrics.thresholds import build_threshold_set
from fieldshift.metrics.winter import ThresholdMismatchError
from fieldshift.seasons.align import build_calendar
from fieldshift.seasons.coverage import season_coverage
from fieldshift.seasons.facts import build_season_facts
from fieldshift.weather.series import DailySeries
from fieldshift.weather.snapshot import load_snapshot

HASH = "fixture-hash"


def plan(terminate="04-30", plant="05-12", concern=None, plan_id="p") -> Plan:
    from fieldshift.contracts import GrowerInputs

    return Plan(
        plan_id=plan_id, previous_crop_id="field_corn", prev_harvest="09-20",
        winter=WinterManagement(kind="cover", crop_id="cereal_rye", seed="10-01",
                                terminate=terminate),
        next_crop_id="soybean", next_plant=plant,
        grower=GrowerInputs(low_moisture_concern=concern),
    )


def synthetic(totals: dict[int, float], start="1981-01-01", end="2025-12-31",
              wet: float = 0.5) -> DailySeries:
    """FIXTURE: zero rain everywhere except one day (Apr 20) per year carrying that year's total."""
    days = pd.date_range(start, end, freq="D")
    precip = pd.Series(0.0, index=days)
    for y, mm in totals.items():
        ts = pd.Timestamp(y, 4, 20)
        if ts in precip.index:
            precip[ts] = mm
    return DailySeries(pd.DataFrame({"date": days, "precip_mm": precip.to_numpy(),
                                     "gwettop": wet, "gwetroot": wet + 0.1}))


YEARS = list(range(1981, 2026))
LINEAR = {y: 10.0 + i for i, y in enumerate(YEARS)}  # 1981 driest ... 2025 wettest


def run(series, p=None, year=2000, totals_mds=("05-12",)):
    p = p or plan()
    ts = build_threshold_set(series, HASH, totals_mds)
    return compute_spring(p, build_calendar(p, year), series, ts, HASH), ts


def test_window_is_30_days_apr_12_to_may_11():
    assert spring_window_for(2022, "05-12") == (date(2022, 4, 12), date(2022, 5, 11))


def test_rank_percentile_and_dry_label_with_known_totals():
    series = synthetic(LINEAR)
    first, ts = run(series, year=1981)
    ninth, _ = run(series, year=1989)
    tenth, _ = run(series, year=1990)
    assert (first.rank, first.total_mm, first.is_dry) == (1, 10.0, True)
    assert ninth.rank == 9 and ninth.percentile == 0.2 and ninth.is_dry is True
    assert tenth.rank == 10 and tenth.is_dry is False
    assert ts.get(f"{SPRING_DRY_PREFIX}05-12").value == 18.0  # 9th smallest of 45
    assert first.n_eligible == 45


def test_years_equal_to_the_cutoff_count_as_dry_even_if_that_exceeds_20_percent():
    totals = dict(LINEAR)
    totals[1990] = totals[1989]  # tie at the 9th value
    series = synthetic(totals)
    results = {y: run(series, year=y)[0] for y in (1989, 1990, 1991)}
    assert results[1989].is_dry and results[1990].is_dry and not results[1991].is_dry
    assert results[1989].rank == results[1990].rank == 9  # ties share the lowest rank


def test_cutoff_helper_uses_ceil_20_percent_and_requires_minimum_record():
    assert dry_cutoff(list(map(float, range(1, 46)))) == 9.0
    assert dry_cutoff(list(map(float, range(1, 45)))) == 9.0  # ceil(8.8) = 9
    assert dry_cutoff(list(map(float, range(1, 6)))) is None


def test_incomplete_window_is_excluded_from_rank_and_denominator_with_reason():
    series = synthetic(LINEAR, start="1981-04-20")  # 1981 window starts before the record
    ref = spring_reference(series, "05-12")
    assert ref.n_eligible == 44 and 1981 not in ref.totals
    (ex,) = ref.excluded
    assert ex.year == 1981 and ex.status == Status.PARTIAL
    assert "record_starts_after_window_start" in ex.reasons
    res, ts = run(series, year=1981)
    assert res.status == Status.PARTIAL and not res.eligible
    assert res.total_mm is None and res.rank is None and res.is_dry is None
    assert ts.get(f"{SPRING_DRY_PREFIX}05-12").parameters["excluded_years"] == (1981,)
    ordinary, _ = run(series, year=1982)
    assert ordinary.n_eligible == 44 and ordinary.rank == 1  # driest of the 44 eligible years


def test_real_zero_total_stays_zero_not_none():
    totals = dict(LINEAR)
    totals[2000] = 0.0
    res, _ = run(synthetic(totals), year=2000)
    assert res.total_mm == 0.0 and res.rank == 1 and res.is_dry is True


def test_too_few_years_gives_insufficient_data_and_no_dry_label():
    series = synthetic({y: 10.0 + y for y in range(2015, 2021)}, start="2015-01-01",
                       end="2020-12-31")
    res, ts = run(series, year=2018)
    t = ts.get(f"{SPRING_DRY_PREFIX}05-12")
    assert t.status == Status.INSUFFICIENT_DATA and t.value is None
    assert res.total_mm is not None and res.is_dry is None
    assert "dry_cutoff_unavailable" in res.reasons


def test_wetness_is_modeled_separately_and_missing_wetness_does_not_touch_precip():
    series = synthetic(LINEAR, wet=0.4)
    res, _ = run(series, year=2000)
    assert res.wetness.label == "modeled" and res.wetness.status == Status.COMPLETE
    assert res.wetness.gwettop == 0.4 and res.wetness.gwetroot == 0.5
    frame = series.frame.reset_index()
    frame.loc[frame["date"].dt.year == 2000, "gwettop"] = float("nan")
    res2, _ = run(DailySeries(frame), year=2000)
    assert res2.wetness.status == Status.UNAVAILABLE and res2.wetness.gwettop is None
    assert res2.total_mm == res.total_mm and res2.is_dry == res.is_dry  # dryness unaffected


def test_cutoff_is_fixed_across_plans_years_and_eras():
    series = synthetic(LINEAR)
    ts = build_threshold_set(series, HASH, ["05-12"])
    cutoffs = set()
    for p in (plan("04-30"), plan("04-23", plan_id="q")):
        for y in (1985, 2010, 2024):
            r = compute_spring(p, build_calendar(p, y), series, ts, HASH)
            cutoffs.add((r.cutoff_mm, r.threshold_set_id))
    assert len(cutoffs) == 1


def test_thresholds_from_another_snapshot_are_rejected():
    series = synthetic(LINEAR)
    ts = build_threshold_set(series, "other", ["05-12"])
    p = plan()
    with pytest.raises(ThresholdMismatchError):
        compute_spring(p, build_calendar(p, 2000), series, ts, HASH)


def test_missing_cutoff_for_a_planting_date_is_an_error_not_a_guess():
    series = synthetic(LINEAR)
    ts = build_threshold_set(series, HASH, ["05-12"])
    p = plan(plant="05-19")
    with pytest.raises(KeyError):
        compute_spring(p, build_calendar(p, 2000), series, ts, HASH)


# --- real Union County snapshot ------------------------------------------------------------------


@pytest.fixture(scope="module")
def union():
    snap = load_snapshot()
    series = DailySeries(snap.daily)
    return series, snap.snapshot_hash, build_threshold_set(series, snap.snapshot_hash,
                                                           ["05-12", "05-19"])


def test_real_record_has_45_eligible_springs_and_a_9th_smallest_cutoff(union):
    series, h, ts = union
    ref = spring_reference(series, "05-12")
    assert ref.n_eligible == 45 and not ref.excluded
    t = ts.get(f"{SPRING_DRY_PREFIX}05-12")
    assert t.value == sorted(ref.totals.values())[8] and t.n_reference == 45
    dry_years = [y for y, v in ref.totals.items() if v <= t.value]
    assert len(dry_years) == 9
    assert t.parameters["tie_rule"] == "total <= cutoff counts as dry"


def test_editing_planting_date_recomputes_window_total_and_rank(union):
    series, h, ts = union
    a, b = plan(plant="05-12"), plan(terminate="05-07", plant="05-19", plan_id="b")
    ra = compute_spring(a, build_calendar(a, 2010), series, ts, h)
    rb = compute_spring(b, build_calendar(b, 2010), series, ts, h)
    assert (ra.window_start, ra.window_end) == (date(2010, 4, 12), date(2010, 5, 11))
    assert (rb.window_start, rb.window_end) == (date(2010, 4, 19), date(2010, 5, 18))
    assert ra.total_mm != rb.total_mm and ra.cutoff_mm != rb.cutoff_mm
    assert ra.threshold_set_id == rb.threshold_set_id  # one frozen set holds both cutoffs


# --- Phase 4 handbook regression cases (4a + 4b rule engine) --------------------------------------


def facts_for(series, h, ts, p, year):
    cal = build_calendar(p, year)
    spring = compute_spring(p, cal, series, ts, h)
    return build_season_facts(p, cal, spring, season_coverage(cal, series)), spring


@pytest.fixture(scope="module")
def years(union):
    series, h, ts = union
    ref = spring_reference(series, "05-12")
    ordered = sorted(ref.totals, key=ref.totals.get)
    return {"driest": ordered[0], "typical": ordered[len(ordered) // 2], "wettest": ordered[-1]}


def flagged(index, facts, rule="cr_tt_03"):
    from fieldshift.metrics.rules import evaluate_season

    check = evaluate_season(facts, index, rule_ids=[rule]).check(rule)
    return check.flagged, check


def test_case1_typical_year_with_unknown_moisture_gives_no_dry_prompt(union, years, index):
    series, h, ts = union
    facts, spring = facts_for(series, h, ts, plan(terminate="04-30"), years["typical"])
    assert spring.is_dry is False and facts.grower.low_moisture_concern is None
    assert facts.termination_gap_days == 12
    assert flagged(index, facts)[0] is False


def test_case2_12_day_gap_in_dry_replay_year_prompts_moisture_check(union, years, index):
    series, h, ts = union
    facts, spring = facts_for(series, h, ts, plan(terminate="04-30"), years["driest"])
    assert spring.is_dry is True
    fired, check = flagged(index, facts)
    assert fired is True and check.status == Status.COMPLETE


def test_case3_19_day_gap_clears_check_and_leaves_spring_results_unchanged(union, years, index):
    series, h, ts = union
    y = years["driest"]
    f12, s12 = facts_for(series, h, ts, plan("04-30", plan_id="x"), y)
    f19, s19 = facts_for(series, h, ts, plan("04-23", plan_id="x"), y)
    assert (f12.termination_gap_days, f19.termination_gap_days) == (12, 19)
    assert flagged(index, f12)[0] is True and flagged(index, f19)[0] is False
    assert s12 == s19  # window, total, rank, percentile, wetness: byte-identical


def test_case4_missing_weather_with_grower_concern_still_fires_and_dryness_unavailable(index):
    snap = load_snapshot()
    daily = snap.daily.copy()
    year = 2010
    mask = (daily["date"] >= f"{year}-04-12") & (daily["date"] <= f"{year}-05-11")
    daily.loc[mask, "precip_mm"] = float("nan")
    series = DailySeries(daily)
    ts = build_threshold_set(series, "blanked", ["05-12"])
    p = plan("04-30", concern=True)
    cal = build_calendar(p, year)
    spring = compute_spring(p, cal, series, ts, "blanked")
    facts = build_season_facts(p, cal, spring, season_coverage(cal, series))
    assert spring.status == Status.UNAVAILABLE and spring.total_mm is None
    assert spring.is_dry is None and facts.spring.is_dry is None
    assert facts.dates.plant == date(2010, 5, 12) and facts.termination_gap_days == 12  # calendar valid
    fired, check = flagged(index, facts)
    assert fired is True and check.gate_active is True  # fires from the grower concern


def test_unknown_dryness_without_concern_is_not_flagged(index, union, years):
    series, h, ts = union
    facts, _ = facts_for(series, h, ts, plan("04-30"), years["typical"])
    unknown = facts.model_copy(update={"spring": facts.spring.model_copy(
        update={"is_dry": None, "status": Status.UNAVAILABLE})})
    fired, check = flagged(index, unknown)
    assert fired is False and check.gate_active is not True


# --- Phase 4a review fixes ---------------------------------------------------------------------


def test_baseline_is_fixed_to_1981_2025_even_with_a_longer_record():
    totals = dict(LINEAR)
    totals.update({2026: 1.0, 2027: 2.0})  # would be the driest if they joined the baseline
    series = synthetic(totals, end="2028-12-31")
    ref = spring_reference(series, "05-12")
    assert ref.n_eligible == 45 and 2026 not in ref.totals and 2027 not in ref.totals
    res, ts = run(series, year=2026)
    assert ts.get(f"{SPRING_DRY_PREFIX}05-12").value == 18.0  # unchanged by 2026-2027
    assert res.total_mm == 1.0 and res.rank is None and res.is_dry is None
    assert "outside_baseline_years" in res.reasons and res.classification_status != Status.COMPLETE


def test_stale_reference_for_another_planting_date_is_rejected():
    series = synthetic(LINEAR)
    ts = build_threshold_set(series, HASH, ["05-12", "05-19"])
    p = plan(plant="05-19", terminate="05-05")
    with pytest.raises(ValueError, match="spring reference is for planting date 05-12"):
        compute_spring(p, build_calendar(p, 2000), series, ts, HASH,
                       reference=spring_reference(series, "05-12"))


def test_missing_cutoff_is_reported_as_insufficient_data_in_season_facts():
    series = synthetic({y: 10.0 + y for y in range(2015, 2021)}, start="2015-01-01",
                       end="2020-12-31")
    p = plan()
    ts = build_threshold_set(series, HASH, ["05-12"])
    cal = build_calendar(p, 2018)
    spring = compute_spring(p, cal, series, ts, HASH)
    assert spring.status == Status.COMPLETE and spring.classification_status == Status.INSUFFICIENT_DATA
    facts = build_season_facts(p, cal, spring, season_coverage(cal, series))
    assert facts.spring.status == Status.INSUFFICIENT_DATA and facts.spring.is_dry is None
    assert facts.coverage["spring"] == Status.COMPLETE  # coverage kept separately


def test_planting_date_edit_changes_rank_not_just_window():
    totals = dict(LINEAR)
    series = synthetic(totals)
    frame = series.frame.reset_index()
    # 1981 is driest for the 05-12 window; a big May 15 storm lands only in the 05-19 window
    frame.loc[frame["date"] == pd.Timestamp(1981, 5, 15), "precip_mm"] = 500.0
    series = DailySeries(frame)
    ts = build_threshold_set(series, HASH, ["05-12", "05-19"])
    a, b = plan(plant="05-12"), plan(terminate="05-05", plant="05-19", plan_id="b")
    ra = compute_spring(a, build_calendar(a, 1981), series, ts, HASH)
    rb = compute_spring(b, build_calendar(b, 1981), series, ts, HASH)
    assert (ra.rank, rb.rank) == (1, 45)
    assert ra.total_mm == 10.0 and rb.total_mm == 510.0
