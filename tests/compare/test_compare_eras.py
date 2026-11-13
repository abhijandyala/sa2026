"""Phase 5 tests. Indicators are synthetic FIXTURES; the real-snapshot test is labelled."""


from fieldshift.compare.eras import (
    INSUFFICIENT,
    LESS,
    MIN_EVALUABLE_PER_ERA,
    MORE,
    SIMILAR,
    YearOutcome,
    any_of,
    compare_eras,
    compare_plans_eras,
    dry_spring_indicator,
    shared_years,
    winter_heavy_rain_indicator,
)
from fieldshift.contracts import Status, Threshold, ThresholdSet

YEARS = range(1981, 2026)


def tset(value=61.2) -> ThresholdSet:
    t = Threshold(name="spring_dry_mm@05-12", method="fixture", value=value, unit="mm",
                  reference_span="1981..2025", n_reference=45)
    return ThresholdSet(snapshot_hash="h", thresholds={t.name: t})


def indicator(event_years=(), missing_years=()) -> dict[int, YearOutcome]:
    out = {}
    for y in YEARS:
        if y in missing_years:
            out[y] = YearOutcome(None, "fixture_missing")
        else:
            out[y] = YearOutcome(y in event_years)
    return out


def cmp(ind, ts=None):
    return compare_eras("dry_spring", ind, ts or tset(), threshold_names=["spring_dry_mm@05-12"])


def test_dry_windows_concentrated_in_recent_era_exact_counts_and_pp_difference():
    # 2 dry in 1981-2000 (10%), 8 dry in 2006-2025 (40%); 2001-2005 dry years are ignored
    ind = indicator(event_years={1985, 1999, 2001, 2002, 2003, 2007, 2008, 2010, 2012, 2015,
                                 2018, 2020, 2022, 2024})
    r = cmp(ind)
    assert (r.earlier.events, r.earlier.evaluable, r.earlier.pct) == (2, 20, 10.0)
    assert (r.recent.events, r.recent.evaluable, r.recent.pct) == (9, 20, 45.0)
    assert r.diff_pp == 35.0 and r.result == MORE and r.status == Status.COMPLETE
    assert r.excluded_from_eras == [2001, 2002, 2003, 2004, 2005]
    assert "not a trend, cause, or forecast" in r.caveat


def test_exact_expected_counts_when_recent_is_8_of_20():
    ind = indicator(event_years={1985, 1999, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013})
    r = cmp(ind)
    assert (r.recent.events, r.recent.pct, r.earlier.pct, r.diff_pp) == (8, 40.0, 10.0, 30.0)


def test_similar_frequency_is_labelled_similar():
    ind = indicator(event_years={1981, 1982, 1983, 1984, 2006, 2007, 2008, 2009, 2010})  # 20% / 25%
    r = cmp(ind)
    assert r.diff_pp == 5.0 and r.result == SIMILAR and "similar" in r.caveat


def test_band_edge_exactly_10_pp_is_not_similar_and_just_under_is():
    base = {1981, 1982, 1983, 1984}  # 20%
    ten = indicator(event_years=base | {2006, 2007, 2008, 2009, 2010, 2011})  # 30% -> +10
    nine_point_five = indicator(event_years=base | {2006, 2007, 2008, 2009, 2010})  # 25% -> +5
    assert cmp(ten).result == MORE and cmp(ten).diff_pp == 10.0
    assert cmp(nine_point_five).result == SIMILAR
    less = indicator(event_years={2006} | {1981, 1982, 1983, 1984})  # 5% vs 20% -> -15
    assert cmp(less).result == LESS and cmp(less).diff_pp == -15.0


def test_ten_missing_seasons_in_one_era_gives_insufficient_data():
    ind = indicator(event_years={1985, 2010}, missing_years=set(range(2006, 2016)))
    r = cmp(ind)
    assert r.recent.evaluable == 10 < MIN_EVALUABLE_PER_ERA
    assert r.status == Status.INSUFFICIENT_DATA and r.result == INSUFFICIENT
    assert r.diff_pp is None and len(r.recent.not_evaluable) == 10
    assert r.recent.not_evaluable[0].reason == "fixture_missing"


def test_exactly_15_evaluable_seasons_is_enough_and_denominator_excludes_missing():
    ind = indicator(event_years={1981, 1982, 1983}, missing_years=set(range(1981 + 15, 2001)))
    # earlier era: 1981..1995 evaluable (15), 1996..2000 missing
    r = cmp(ind)
    assert r.earlier.evaluable == 15 and r.earlier.events == 3 and r.earlier.pct == 20.0
    assert r.status == Status.COMPLETE


def test_missing_year_is_never_counted_as_no_event():
    all_missing = {y: YearOutcome(None, "x") for y in YEARS}
    r = cmp(all_missing)
    assert r.earlier.pct is None and r.earlier.evaluable == 0 and r.earlier.events == 0
    assert r.result == INSUFFICIENT


def test_cutoff_value_is_identical_in_both_eras_and_comes_from_one_threshold_set():
    ts = tset(61.2)
    r = cmp(indicator(event_years={1985, 2010}), ts)
    assert r.earlier.threshold_value == r.recent.threshold_value == 61.2
    assert r.thresholds == {"spring_dry_mm@05-12": 61.2}
    assert r.threshold_set_id == ts.threshold_set_id


def test_any_of_counts_each_season_once_and_propagates_missing():
    a = indicator(event_years={1985, 1990})
    b = indicator(event_years={1990, 1995}, missing_years={2000})
    both = any_of([a, b])
    assert [y for y, o in both.items() if o.event] == [1985, 1990, 1995]  # 1990 once
    assert both[2000].event is None and both[2000].reason == "fixture_missing"


def test_cross_plan_comparison_uses_only_years_both_plans_share_and_is_labelled():
    a = indicator(event_years={2006, 2007})
    b = indicator(event_years={2006}, missing_years={1990, 1991, 1992})
    assert shared_years({"a": a, "b": b}) == set(YEARS) - {1990, 1991, 1992}
    out = compare_plans_eras("x", {"a": a, "b": b}, tset(), threshold_names=["spring_dry_mm@05-12"])
    assert out["a"].earlier.evaluable == out["b"].earlier.evaluable == 17
    assert out["a"].basis == out["b"].basis == "shared_evaluable_seasons"
    assert out["a"].earlier.not_evaluable[0].reason == "not_evaluable_for_every_compared_plan"
    own = cmp(a)
    assert own.earlier.evaluable == 20 and own.basis == "own_evaluable_seasons"


# --- real Union snapshot (labelled: real weather, assumed heavy-rain rule) ------------------------


def test_real_snapshot_spring_and_winter_indicators_flow_into_era_comparison():
    from fieldshift.contracts import Plan, WinterManagement
    from fieldshift.metrics.spring import SPRING_DRY_PREFIX, compute_spring, spring_reference
    from fieldshift.metrics.thresholds import HEAVY_RAIN_NAME, build_threshold_set
    from fieldshift.metrics.winter import compute_winter
    from fieldshift.seasons.align import build_calendar
    from fieldshift.weather.series import DailySeries
    from fieldshift.weather.snapshot import load_snapshot

    snap = load_snapshot()
    series = DailySeries(snap.daily)
    h = snap.snapshot_hash
    ts = build_threshold_set(series, h, ["05-12"])
    p = Plan(plan_id="r", previous_crop_id="field_corn", prev_harvest="09-20",
             winter=WinterManagement(kind="cover", crop_id="cereal_rye", seed="10-01",
                                     terminate="04-30"),
             next_crop_id="soybean", next_plant="05-12")
    ref = spring_reference(series, "05-12")
    springs = {y: compute_spring(p, build_calendar(p, y), series, ts, h, ref) for y in range(1981, 2026)}
    winters = {y: compute_winter(p, build_calendar(p, y), series, ts, h) for y in range(1981, 2026)}

    dry = compare_eras("dry_spring", dry_spring_indicator(springs), ts,
                       threshold_names=[SPRING_DRY_PREFIX + "05-12"])
    cutoff = ts.get(SPRING_DRY_PREFIX + "05-12").value
    direct = {y for y, v in ref.totals.items() if v <= cutoff}
    assert dry.earlier.events == len(direct & set(range(1981, 2001)))
    assert dry.recent.events == len(direct & set(range(2006, 2026)))
    assert dry.earlier.evaluable == dry.recent.evaluable == 20
    assert dry.earlier.threshold_value == dry.recent.threshold_value == cutoff

    heavy = compare_eras("winter_heavy_rain", winter_heavy_rain_indicator(winters), ts,
                         threshold_names=[HEAVY_RAIN_NAME])
    assert heavy.earlier.evaluable == 19 and heavy.recent.evaluable == 20  # winter 1981 partial
    assert heavy.earlier.not_evaluable[0].year == 1981
    assert heavy.status == Status.COMPLETE
