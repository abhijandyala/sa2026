from datetime import date, timedelta

import pytest

from fieldshift.catalogs import CatalogIndex, load_catalog
from fieldshift.tools.irrigation import check_irrigation, crop_demand, norm_stage, stage_checks


@pytest.fixture(scope="module")
def index():
    return CatalogIndex(load_catalog())


def days(n, mm=0.0, start=date(2025, 7, 1)):
    return [{"date": (start + timedelta(days=i)).isoformat(), "precip_mm": mm} for i in range(n)]


FULL = dict(
    crop_id="field_corn", stage="pollination", awc_in=4.0, start_storage_in=3.0, irrigation=[]
)


def test_norm_stage():
    assert norm_stage("R1-R5") == norm_stage("R1 to R5") == norm_stage("R1_to_R5") == "r1_to_r5"
    assert norm_stage("Pollination") == "pollination" and norm_stage(None) == ""


def test_soybean_r1_r5_and_corn_pollination_stage_checks(index):
    sb = stage_checks(index, "soybean", "R1-R5")
    ids = {c.rule_id for c in sb}
    assert "sb_wd_06" in ids and "sb_wd_01" in ids  # R1-R5 plus the general season rows
    assert all(c.status == "manual_check" for c in sb)
    assert "sb_wd_03" not in ids  # a different stage
    assert "sb_wd_04" not in ids  # numeric demand rows are crop demand, listed separately
    fc = stage_checks(index, "field_corn", "pollination")
    assert "fc_wd_03" not in {c.rule_id for c in fc}


def test_crop_demand_is_separate_and_labeled_illustrative(index):
    d = crop_demand(index, "field_corn", "pollination")
    assert (d.rule_id, d.daily_use_in_min, d.daily_use_in_max, d.unit) == (
        "fc_wd_03",
        0.25,
        0.25,
        "in_per_day",
    )
    assert d.illustrative and "not an irrigation recommendation" in d.kind
    s = crop_demand(index, "soybean", "flowering_to_pod_fill")
    assert (s.rule_id, s.daily_use_in_min, s.daily_use_in_max) == ("sb_wd_04", 0.20, 0.30)
    assert (
        crop_demand(index, "soybean", "nonsense") is None
        and crop_demand(index, "soybean", None) is None
    )


@pytest.mark.parametrize("drop", ["stage", "awc_in", "start_storage_in", "irrigation"])
def test_no_balance_unless_every_input_is_present(index, drop):
    kw = {**FULL, "weather": days(5)}
    kw.pop(drop)
    r = check_irrigation(index, **kw)
    assert (
        r.status == "insufficient_data" and r.water_balance is None and r.supplemental_need is None
    )
    assert len(r.missing) == 1 and drop.split("_")[0] in r.missing[0]
    assert r.stage_checks is not None  # guidance still comes back


def test_missing_weather_and_unknown_stage_are_listed(index):
    r = check_irrigation(index, **FULL)
    assert r.status == "insufficient_data" and "weather" in r.missing[0]
    r2 = check_irrigation(index, **{**FULL, "stage": "seedling_ish"}, weather=days(2))
    assert r2.status == "insufficient_data" and "no published daily crop water use" in r2.missing[0]


def test_water_balance_bucket_math(index):
    # corn pollination: 0.25 in/day. 4 days, 25.4 mm (1.0 in) on day 2, 0.5 in irrigation on day 3.
    w = days(4)
    w[1]["precip_mm"] = 25.4
    kw = {**FULL, "weather": w, "irrigation": [{"date": "2025-07-03", "amount_in": 0.5}]}
    r = check_irrigation(index, **kw)
    assert r.status == "complete"
    wb = r.water_balance
    # 3.0 -0.25 =2.75; +1.0-0.25 =3.5; +0.5-0.25 =3.75; -0.25 =3.5
    assert [row.storage_in for row in wb.daily] == [2.75, 3.5, 3.75, 3.5]
    assert wb.end_storage_in == 3.5 and wb.total_rain_in == 1.0 and wb.total_irrigation_in == 0.5
    assert wb.total_crop_use_in == 1.0 and wb.unmet_demand_in == 0 and wb.drainage_or_runoff_in == 0
    assert wb.days_until_empty_at_current_use == 14.0
    assert r.supplemental_need["unmet_demand_in"] == 0
    assert "not a scheduling recommendation" in r.supplemental_need["kind"]
    assert any("illustrative" in a for a in wb.assumptions) and wb.derivation == "calculation"


def test_capacity_cap_drainage_and_unmet_demand(index):
    wet = check_irrigation(index, **{**FULL, "weather": days(1, mm=127.0)})  # 5 in of rain
    wb = wet.water_balance
    assert wb.end_storage_in == 4.0
    assert wb.drainage_or_runoff_in == pytest.approx(3.0 + 5.0 - 0.25 - 4.0)
    assert wb.daily[0].drainage_or_runoff_in == pytest.approx(3.0 + 5.0 - 0.25 - 4.0)
    dry = check_irrigation(index, **{**FULL, "start_storage_in": 0.5, "weather": days(4)})
    assert dry.water_balance.unmet_demand_in == pytest.approx(0.5, abs=1e-6)
    assert (
        dry.water_balance.end_storage_in == 0
        and dry.water_balance.days_until_empty_at_current_use == 0
    )
    assert dry.supplemental_need["unmet_demand_in"] == pytest.approx(0.5, abs=1e-6)


def test_real_zero_start_storage_and_zero_rain_are_values_not_missing(index):
    r = check_irrigation(index, **{**FULL, "start_storage_in": 0, "weather": days(1, mm=0.0)})
    assert r.status == "complete" and r.water_balance.start_storage_in == 0


def test_blank_precip_is_not_zero(index):
    w = days(2)
    w[0].pop("precip_mm")
    r = check_irrigation(index, **{**FULL, "weather": w})
    assert r.status == "invalid_input" and r.issues[0].field == "weather.0.precip_mm"


@pytest.mark.parametrize(
    "patch,field",
    [({"awc_in": 0}, "awc_in"), ({"awc_in": float("nan")}, "awc_in"), ({"start_storage_in": 9}, "start_storage_in"),
     ({"start_storage_in": -1}, "start_storage_in"), ({"irrigation": "wet"}, "irrigation"),
     ({"irrigation": [{"date": "x", "amount_in": 1}]}, "irrigation.0"),
     ({"weather": [{"date": "2025-07-01", "precip_mm": -3}]}, "weather.0.precip_mm"),
     ({"weather": [{"date": "2025-07-01", "precip_mm": 1}, {"date": "2025-07-01", "precip_mm": 1}]}, "weather.1.date"),
     ({"weather": "rain"}, "weather")],
)  # fmt: skip
def test_invalid_inputs_name_the_field(index, patch, field):
    r = check_irrigation(index, **{**FULL, "weather": days(2), **patch})
    assert r.status == "invalid_input" and r.issues[0].field == field


def test_out_of_period_irrigation_is_ignored_with_a_note(index):
    r = check_irrigation(
        index,
        **{**FULL, "weather": days(2), "irrigation": [{"date": "2024-01-01", "amount_in": 1}]},
    )
    assert r.water_balance.total_irrigation_in == 0 and any(
        "outside the weather period" in n for n in r.notes
    )


def test_unsupported_crop_and_water_table_rule(index):
    assert check_irrigation(index, crop_id="quinoa").status == "unsupported"
    assert check_irrigation(index, crop_id="cereal_rye").status == "unsupported"
    r = check_irrigation(index, crop_id="soybean", stage="R1-R5", water_table_depth_in=30)
    assert r.water_table["rule_id"] == "sb_wd_07" and r.water_table["flagged"] is True
    ok = check_irrigation(index, crop_id="soybean", water_table_depth_in=40)
    assert ok.water_table["flagged"] is False
    assert (
        check_irrigation(index, crop_id="field_corn", water_table_depth_in=10).water_table is None
    )
