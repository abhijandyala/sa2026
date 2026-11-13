from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fieldshift.api.samples import load_samples
from fieldshift.compare.context import get_context
from fieldshift.planner.routes import router
from fieldshift.planner.wheat_path import (
    demo_plan,
    evaluate_wheat_double_crop,
    plan_from_dates,
)

YEAR = 2027


@pytest.fixture(scope="module")
def ctx():
    return get_context()


def run(ctx, plan=None, **kw):
    return evaluate_wheat_double_crop(plan or demo_plan(), ctx, year=YEAR, **kw)


def ids(lines):
    return {x["rule_id"] for x in lines}


def mg(result):
    return {c["rule_id"]: c for c in result["maturity_group"]["checks"]}


def test_demo_path_uses_grower_dates_and_moves_the_soybean_window_after_wheat_harvest(ctx):
    r = run(ctx, maturity_group=5)
    assert r["status"] == "partial" and r["catalog_state"]["status"] == "partial"
    d = r["dates"]
    assert (d["wheat_plant"], d["wheat_harvest"], d["soybean_plant"]) == (
        "2026-10-25",
        "2027-06-05",
        "2027-06-12",
    )
    assert d["harvest_to_plant_days"] == 7 and d["basis"] == "grower"
    w = r["soybean_planting_window"]
    assert w["moved_to_after_wheat_harvest"] and w["earliest_planting_date"] == "2027-06-05"
    assert w["days_after_wheat_harvest"] == 7 and "grower-entered" in w["basis"]
    assert w["catalog_context"]["kind"].startswith("context only")
    assert w["catalog_context"]["status"] == "manual_check"  # prose timing is never a calendar rule
    assert (
        w["delay_caution"]["rule_id"] == "sb_v2_pw_delay_yield"
        and not w["delay_caution"]["flagged"]
    )
    assert "SMAP" in " ".join(r["notes"])


def test_planting_on_the_harvest_day_is_noted(ctx):
    p = plan_from_dates(
        prev_harvest="09-20",
        wheat_plant="10-25",
        wheat_harvest="06-05",
        soybean_plant="06-05",
        production_system="conventional",
    )
    r = run(ctx, p, maturity_group=5)
    assert r["soybean_planting_window"]["days_after_wheat_harvest"] == 0
    assert "harvest day" in r["soybean_planting_window"]["notes"][0]


def test_maturity_group_checks_in_the_mid_june_context(ctx):
    ok = mg(run(ctx, maturity_group=5))
    assert (
        ok["sb_v2_mg_mid_june"]["verdict"] == "acceptable"
        and not ok["sb_v2_mg_mid_june"]["flagged"]
    )
    assert ok["sb_v2_mg_mid_july"]["status"] == "manual_check"  # not the July context
    assert ok["sb_rc_03"]["flagged"] is False and ok["sb_rc_03"]["condition_met"] is False
    low = run(ctx, maturity_group=3)
    c = mg(low)
    assert c["sb_rc_03"]["flagged"] and c["sb_rc_03"]["verdict"] == "caution"
    assert c["sb_v2_mg_mid_june"]["flagged"] and c["sb_v2_mg_mid_june"]["condition_met"] is False
    assert {"sb_rc_03", "sb_v2_mg_mid_june"} <= ids(low["rule_checks"]["flagged"])
    assert "sb_v2_mg_mid_june" in low["maturity_group"]["planting_context"]["rows_in_context"]


def test_maturity_group_checks_in_the_mid_july_context(ctx):
    p = plan_from_dates(
        prev_harvest="09-20",
        wheat_plant="10-25",
        wheat_harvest="07-05",
        soybean_plant="07-15",
        production_system="conventional",
    )
    c = mg(run(ctx, p, maturity_group=4))
    assert c["sb_v2_mg_mid_july"]["flagged"] and c["sb_v2_mg_mid_july"]["verdict"] == "caution"
    assert c["sb_v2_mg_mid_june"]["status"] == "manual_check"
    assert not c["sb_rc_03"]["flagged"]  # MG 4 is not below 4
    best = mg(run(ctx, p, maturity_group=6))
    assert best["sb_v2_mg_mid_july"]["verdict"] == "preferred"


def test_between_the_contexts_both_rows_are_manual_but_sb_rc_03_still_checks(ctx):
    p = plan_from_dates(
        prev_harvest="09-20",
        wheat_plant="10-25",
        wheat_harvest="06-20",
        soybean_plant="06-30",
        production_system="conventional",
    )
    r = run(ctx, p, maturity_group=3)
    c = mg(r)
    assert c["sb_v2_mg_mid_june"]["status"] == c["sb_v2_mg_mid_july"]["status"] == "manual_check"
    assert c["sb_rc_03"]["flagged"]
    assert r["maturity_group"]["planting_context"]["rows_in_context"] == []


def test_missing_maturity_group_is_unknown_not_clear(ctx):
    r = run(ctx)
    assert r["maturity_group"]["status"] == "unknown" and r["maturity_group"]["missing"] == [
        "maturity_group"
    ]
    c = mg(r)
    assert c["sb_rc_03"]["status"] == "unknown" and c["sb_v2_mg_mid_june"]["status"] == "unknown"
    assert c["sb_rc_03"]["missing_inputs"] == ["maturity_group"]


def test_a_real_zero_maturity_group_is_a_value(ctx):
    r = run(ctx, maturity_group=0)
    assert r["maturity_group"]["input"] == 0.0 and mg(r)["sb_rc_03"]["flagged"]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "x", True, 11, -1])
def test_bad_maturity_group_is_invalid_input(ctx, bad):
    r = run(ctx, maturity_group=bad)
    assert r["status"] == "invalid_input" and r["issues"][0]["field"] == "maturity_group"


def test_qualitative_and_map_based_wheat_rows_are_manual_check(ctx):
    r = run(ctx, maturity_group=5)
    manual = ids(r["rule_checks"]["manual_check"])
    assert {"ww_v2_pw_local_map", "ww_v2_gd_harvest_context", "sb_v2_pw_after_wheat_context",
            "sb_v2_seed_late", "sb_v2_spacing_late", "sb_v2_pw_delay_yield"} <= manual  # fmt: skip
    ref = next(x for x in r["rule_checks"]["manual_check"] if x["rule_id"] == "sb_v2_seed_late")[
        "reference"
    ]
    assert (ref["value_min"], ref["value_max"], ref["unit"]) == (165000.0, 175000.0, "seeds/acre")
    assert ref["is_grower_target"] is False


def test_organic_grain_rows_are_inapplicable_to_a_conventional_plan(ctx):
    r = run(ctx, maturity_group=5)
    gone = r["rule_checks"]["inapplicable_to_this_production_system"]
    assert ids(gone) == {"ww_v2_pw_freeze_reference", "ww_v2_pw_hessian_fly", "ww_v2_seed_drilled"}
    assert all("conventional" in x["reason"] for x in gone)
    assert not ids(gone) & ids(r["rule_checks"]["manual_check"])
    organic = demo_plan().model_copy(update={"production_system": "organic"})
    o = run(ctx, organic, maturity_group=5)
    assert o["rule_checks"]["inapplicable_to_this_production_system"] == []
    assert {"ww_v2_pw_freeze_reference", "ww_v2_pw_hessian_fly", "ww_v2_seed_drilled"} <= ids(
        o["rule_checks"]["manual_check"]
    )


def test_wheat_after_corn_fires_ww_rc_01_and_wheat_after_soybean_does_not(ctx):
    r = run(ctx, maturity_group=5)
    assert "ww_rc_01" in ids(r["rule_checks"]["flagged"])
    soy = plan_from_dates(
        previous_crop_id="soybean",
        prev_harvest="10-10",
        wheat_plant="10-30",
        wheat_harvest="06-05",
        soybean_plant="06-12",
        production_system="conventional",
    )
    s = run(ctx, soy, maturity_group=5)
    assert "ww_rc_01" not in ids(s["rule_checks"]["flagged"])


def test_double_crop_spring_dryness_uses_its_own_window_baseline(ctx):
    r = run(ctx, maturity_group=5)
    sp = r["spring"]
    assert (
        sp["baseline"] == "own_window_baseline"
        and "own 30-day window before 06-12" in sp["baseline_note"]
    )
    assert sp["window"]["plant_md"] == "06-12" and sp["window"]["example"]["end"].endswith("-06-11")
    full = evaluate_wheat_double_crop(
        demo_plan(),
        ctx,
        year=YEAR,
        full_season_plan=load_samples().plans["corn_soy__no_cover"].plan,
    )
    assert (
        full["cross_calendar"]["full_season"]["cutoff_mm"] != sp["cutoff_mm"]
    )  # different baselines
    assert sp["eligible_seasons"] == 45 and sp["cutoff_mm"] is not None


def test_cross_calendar_comparison_is_labeled_and_uses_raw_totals_only(ctx):
    full = load_samples().plans["corn_soy__no_cover"].plan
    r = run(ctx, maturity_group=5, full_season_plan=full)
    cc = r["cross_calendar"]
    assert cc["label"] == "different-calendar" and "NOT comparable" in cc["note"]
    assert cc["median_total_mm_difference"] == pytest.approx(
        cc["double_crop"]["median_total_mm"] - cc["full_season"]["median_total_mm"], abs=1e-3
    )
    for side in ("full_season", "double_crop"):
        assert not {"rank", "percentile", "dry_seasons", "dry_years", "era_dry_spring"} & set(
            cc[side]
        )
    assert "raw millimetres" in cc["difference_label"]
    assert "cross_calendar" not in run(ctx, maturity_group=5)


def test_cross_calendar_rejects_a_non_soybean_comparison(ctx):
    corn = load_samples().plans["soy_corn__no_cover"].plan
    r = run(ctx, maturity_group=5, full_season_plan=corn)
    assert r["status"] == "invalid_input" and r["issues"][0]["field"] == "compare_to_plan"
    assert "cross_calendar" not in r


def test_season_results_do_not_depend_on_the_weather_year(ctx):
    r = run(ctx, maturity_group=3)
    c = r["year_constant_checks"]
    assert c["constant_across_seasons"] and c["seasons_checked"] == 45
    assert "ww_rc_01" in c["flagged_rule_ids"]


def test_catalog_v1_gives_unavailable_catalog_missing(index_v1):
    r = evaluate_wheat_double_crop(demo_plan(), SimpleNamespace(index=index_v1), year=YEAR)
    assert r["status"] == "unavailable" and r["reason"] == "catalog_missing"
    assert "planting_window" in r["detail"]


def test_wrong_plan_shapes_and_chronology(ctx):
    full = load_samples().plans["corn_soy__rye"].plan
    assert run(ctx, full)["status"] == "unsupported"
    bad = plan_from_dates(
        prev_harvest="09-20", wheat_plant="09-01", wheat_harvest="06-05", soybean_plant="06-12"
    )
    r = run(ctx, bad)
    assert r["status"] == "invalid_input" and r["issues"][0]["field"].startswith("plan.winter")
    late = plan_from_dates(
        prev_harvest="09-20", wheat_plant="10-25", wheat_harvest="06-20", soybean_plant="06-10"
    )
    assert run(ctx, late)["status"] == "invalid_input"  # wheat harvest after soybean planting
    q = demo_plan().model_copy(update={"previous_crop_id": "quinoa"})
    assert run(ctx, q)["status"] == "unsupported"


# ------------------------------------------------------------------ routes


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


FLAT = {
    "prev_harvest": "09-20",
    "wheat_plant": "10-25",
    "wheat_harvest": "06-05",
    "soybean_plant": "06-12",
    "production_system": "conventional",
}


def test_template_route_is_labeled_assumed(client):
    j = client.get("/v1/plans/wheat/template").json()
    assert j["dates_basis"] == "assumed" and j["plan"]["winter"]["kind"] == "winter_grain"
    assert set(j["enter"]) == {"prev_harvest", "wheat_plant", "wheat_harvest", "soybean_plant"}


def test_wheat_route_flat_dates_with_comparison(client):
    r = client.post(
        "/v1/plans/wheat",
        json={
            **FLAT,
            "maturity_group": 5,
            "year": YEAR,
            "compare_to_plan_id": "corn_soy__no_cover",
        },
    )
    assert r.status_code == 200
    j = r.json()
    assert set(j["meta"]) == {"plan_version", "catalog_version", "snapshot_hash", "request_id"}
    assert (
        j["result"]["status"] == "partial"
        and j["result"]["cross_calendar"]["label"] == "different-calendar"
    )
    plan = client.get("/v1/plans/wheat/template").json()["plan"]
    r2 = client.post("/v1/plans/wheat", json={"plan": plan, "year": YEAR, "maturity_group": 3})
    assert r2.json()["result"]["rule_checks"]["flagged"]


@pytest.mark.parametrize(
    "payload,field",
    [
        ({}, "prev_harvest"),
        ({**FLAT, "wheat_harvest": "13-40"}, "wheat_harvest"),
        ({**FLAT, "maturity_group": "x"}, "maturity_group"),
        ({**FLAT, "maturity_group": 99}, "maturity_group"),
        ({**FLAT, "year": 0}, "year"),
        ({**FLAT, "inputs": {"soil_ph": "bad"}}, "inputs"),
        ({**FLAT, "compare_to_plan_id": "nope"}, "compare_to_plan_id"),
        ({**FLAT, "wheat_plant": "09-01"}, "plan.winter"),
        ({"plan": {"plan_id": 5}}, "plan."),
    ],
)
def test_wheat_route_validation_is_a_400_with_the_field(client, payload, field):
    r = client.post("/v1/plans/wheat", json=payload)
    assert r.status_code == 400 and r.json()["status"] == "invalid_input"
    assert r.json()["issues"][0]["field"].startswith(field) and "request_id" in r.json()


def test_a_plan_that_breaks_in_some_historical_year_is_invalid_input(ctx):
    # valid in leap 2028 (Feb 29 wheat harvest after a Feb 28 planting), impossible in other years
    p = plan_from_dates(
        prev_harvest="10-01", wheat_plant="02-28", wheat_harvest="02-29", soybean_plant="03-10"
    )
    r = evaluate_wheat_double_crop(p, ctx, year=2028)
    assert r["status"] == "invalid_input" and "planting year" in r["issues"][0]["message"]


# ------------------------------------------------------------------ review fixes (phase-12-B)


def test_an_invalid_comparison_plan_is_a_typed_error_not_a_500(client):
    base = load_samples().plans["corn_soy__rye"].plan.model_dump(mode="json")
    bad = {**base, "winter": {**base["winter"], "seed": "09-01"}}  # seeding before harvest
    r = client.post(
        "/v1/plans/wheat", json={**FLAT, "maturity_group": 5, "year": YEAR, "compare_to_plan": bad}
    )
    assert r.status_code == 400 and r.json()["issues"][0]["field"].startswith(
        "compare_to_plan.winter"
    )
    corn = load_samples().plans["soy_corn__no_cover"].plan.model_dump(mode="json")
    r2 = client.post("/v1/plans/wheat", json={**FLAT, "year": YEAR, "compare_to_plan": corn})
    assert r2.status_code == 400 and r2.json()["issues"][0]["field"] == "compare_to_plan"
    leap = {
        **base,
        "winter": {**base["winter"], "seed": "02-28", "terminate": "02-29"},
        "prev_harvest": "10-01",
        "next_plant": "03-10",
    }
    r3 = client.post("/v1/plans/wheat", json={**FLAT, "year": 2028, "compare_to_plan": leap})
    assert r3.status_code == 400 and "planting year" in r3.json()["issues"][0]["message"]


def test_maturity_group_in_inputs_is_validated_like_the_top_level_value(client, ctx):
    r = client.post(
        "/v1/plans/wheat", json={**FLAT, "year": YEAR, "inputs": {"maturity_group": 99}}
    )
    assert r.status_code == 400 and r.json()["issues"][0]["field"] == "inputs.maturity_group"
    for blank in ("", None, "  "):
        ok = client.post(
            "/v1/plans/wheat", json={**FLAT, "year": YEAR, "inputs": {"maturity_group": blank}}
        )
        mgr = ok.json()["result"]["maturity_group"]
        assert ok.status_code == 200 and mgr["status"] == "unknown" and mgr["input"] is None
    via_inputs = client.post(
        "/v1/plans/wheat", json={**FLAT, "year": YEAR, "inputs": {"maturity_group": 3}}
    ).json()
    assert via_inputs["result"]["maturity_group"]["input"] == 3.0
    assert via_inputs["result"]["rule_checks"]["flagged"]
    zero = client.post(
        "/v1/plans/wheat", json={**FLAT, "year": YEAR, "inputs": {"maturity_group": 0}}
    ).json()
    assert (
        zero["result"]["maturity_group"]["input"] == 0.0
        and zero["result"]["maturity_group"]["status"] == "complete"
    )
    both = client.post(
        "/v1/plans/wheat",
        json={**FLAT, "year": YEAR, "maturity_group": 5, "inputs": {"maturity_group": 3}},
    )
    assert both.status_code == 400 and both.json()["issues"][0]["code"] == "conflict"
    same = client.post(
        "/v1/plans/wheat",
        json={**FLAT, "year": YEAR, "maturity_group": 5, "inputs": {"maturity_group": "5"}},
    )
    assert same.status_code == 200


def test_plan_version_changes_with_the_maturity_group_and_the_comparison_plan(client):
    def version(**extra):
        return client.post("/v1/plans/wheat", json={**FLAT, "year": YEAR, **extra}).json()["meta"][
            "plan_version"
        ]

    assert version(maturity_group=3) != version(maturity_group=5)
    assert version(maturity_group=5) == version(
        inputs={"maturity_group": 5}
    )  # same effective input
    assert version(maturity_group=5) != version(
        maturity_group=5, compare_to_plan_id="corn_soy__no_cover"
    )
    assert version() == version()


def test_median_total_uses_the_true_median_for_an_even_number_of_seasons(ctx):
    import statistics

    from fieldshift.compare import engine

    p = plan_from_dates(
        prev_harvest="09-20",
        wheat_plant="10-25",
        wheat_harvest="07-05",
        soybean_plant="07-15",
        production_system="conventional",
    )
    r = run(ctx, p, maturity_group=5)
    totals = list(engine.reference_for(ctx, "07-15").totals.values())
    assert len(totals) % 2 == 0  # the record ends 06-30, so 2025 is not eligible: 44 seasons
    assert r["spring"]["median_total_mm"] == pytest.approx(statistics.median(totals), abs=1e-3)
