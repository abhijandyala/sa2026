import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fieldshift.contracts import GrowerInputs, Plan, WinterManagement
from fieldshift.planner.checker import check_plan, plan_version
from fieldshift.planner.crops import list_crops
from fieldshift.planner.finder import find_plans
from fieldshift.planner.routes import router

YEAR = 2025  # explicit so results never depend on today's date


def plan(**kw) -> Plan:
    base = dict(
        plan_id="fixture",
        previous_crop_id="field_corn",
        prev_harvest="09-20",
        winter=WinterManagement(
            kind="cover", crop_id="cereal_rye", seed="10-05", terminate="04-28"
        ),
        next_crop_id="soybean",
        next_plant="05-12",
        region="NC Piedmont",
        production_system="conventional",
    )
    base.update(kw)
    return Plan(**base)


def clover_late_corn() -> Plan:
    return plan(
        prev_harvest="10-10",
        winter=WinterManagement(
            kind="cover", crop_id="crimson_clover", seed="10-12", terminate="04-20"
        ),
    )


def test_clover_after_oct_10_corn_harvest_is_a_chronology_conflict(index):
    res = check_plan(clover_late_corn(), index, year=YEAR)
    assert res.status == "complete"
    assert "cc_rc_02" in res.chronology_conflicts
    c = res.rule("cc_rc_02")
    assert c.flagged and "after the window end" in c.reason
    assert res.rule("sb_rc_02").flagged  # legume before soybean
    assert res.rule("cc_soil_02").status == "manual_check"  # Piedmont clay


def test_organic_piedmont_corn_rule_is_inapplicable_to_conventional_plan(index):
    p = plan(previous_crop_id="soybean", next_crop_id="field_corn", next_plant="05-10")
    res = check_plan(p, index, year=YEAR)
    c = res.rule("fc_pw_03")
    assert c.status == "inapplicable" and "organic" in c.reason and "conventional" in c.reason
    organic = check_plan(p.model_copy(update={"production_system": "organic"}), index, year=YEAR)
    assert organic.rule("fc_pw_03").status == "complete"


def test_fc_pw_01_and_02_are_both_returned_and_flagged_as_conflict(index):
    p = plan(
        previous_crop_id="soybean",
        next_crop_id="field_corn",
        next_plant="04-15",
        winter=WinterManagement(kind="none"),
    )
    res = check_plan(p, index, year=YEAR, inputs={"soil_temp_f": 52})
    a, b = res.rule("fc_pw_01"), res.rule("fc_pw_02")
    assert a and b and a.conflict and b.conflict
    assert [g.rule_ids for g in res.conflicts] == [["fc_pw_01", "fc_pw_02"]]
    assert "neither is chosen" in res.conflicts[0].note


def test_unsupported_crop_is_unsupported_not_unknown(index):
    res = check_plan(plan(next_crop_id="quinoa"), index, year=YEAR)
    assert res.status == "unsupported" and res.rules == []
    assert any("quinoa" in u for u in res.unsupported)


def test_wrong_role_and_out_of_state_location_are_unsupported(index):
    res = check_plan(
        plan(
            winter=WinterManagement(
                kind="cover", crop_id="soybean", seed="10-05", terminate="04-28"
            )
        ),
        index,
        year=YEAR,
    )
    assert res.status == "unsupported" and "cover_crop" in res.unsupported[0]
    iowa = check_plan(plan(region="Iowa"), index, year=YEAR)
    assert iowa.status == "unsupported" and "outside North Carolina" in iowa.unsupported[0]
    assert check_plan(plan(region=None), index, year=YEAR).status == "complete"
    assert check_plan(plan(region="North Carolina"), index, year=YEAR).status == "complete"


def test_invalid_chronology_returns_typed_issues(index):
    bad = plan(
        winter=WinterManagement(kind="cover", crop_id="cereal_rye", seed="09-01", terminate="04-28")
    )
    res = check_plan(bad, index, year=YEAR)
    assert res.status == "invalid_input"
    assert res.issues[0].field == "winter.seed" and res.rules == []


def test_grower_concern_makes_the_rye_rule_fire_without_weather(index):
    p = plan(
        winter=WinterManagement(
            kind="cover", crop_id="cereal_rye", seed="10-05", terminate="04-30"
        ),
        grower=GrowerInputs(low_moisture_concern=True),
    )
    c = check_plan(p, index, year=YEAR).rule("cr_tt_03")  # 12-day gap
    assert c.flagged and c.status == "complete"
    no_concern = check_plan(plan(winter=p.winter), index, year=YEAR).rule("cr_tt_03")
    assert no_concern.status == "unknown"  # no weather in a plain check: do not call it clear


def test_winter_wheat_path_is_labeled_catalog_missing(index):
    p = plan(
        winter=WinterManagement(
            kind="winter_grain", crop_id="winter_wheat", plant="10-25", harvest="06-05"
        ),
        next_plant="06-20",
    )
    res = check_plan(p, index, year=YEAR)
    assert res.status == "complete"
    assert (
        res.path_notes[0].status == "unavailable" and "catalog_missing" in res.path_notes[0].reason
    )
    assert res.rule("ww_rc_01").flagged  # wheat after corn, caution


def test_check_is_deterministic_and_plan_version_is_stable(index):
    a = check_plan(plan(), index, year=YEAR).model_dump(mode="json")
    b = check_plan(plan(), index, year=YEAR).model_dump(mode="json")
    assert a == b
    assert plan_version(plan(), YEAR) == plan_version(plan(), YEAR)
    assert plan_version(plan(), YEAR) != plan_version(plan(next_plant="05-13"), YEAR)


def test_every_catalog_rule_is_accounted_for(index):
    res = check_plan(plan(), index, year=YEAR)
    assert {r.rule_id for r in res.rules} == set(index.rules)
    assert res.counts["rules"] == len(index.rules)


# ---------------------------------------------------------------- crops


def test_crops_listing_shows_roles_and_path_availability(index):
    crops = {c.crop_id: c for c in list_crops(index).crops}
    assert set(crops) == {"field_corn", "soybean", "cereal_rye", "crimson_clover", "winter_wheat"}
    assert crops["cereal_rye"].crop_role == "cover_crop"
    assert crops["field_corn"].paths[0].status == "complete"
    wheat = {p.path: p for p in crops["winter_wheat"].paths}
    assert wheat["as_next_crop"].status == "partial"
    assert wheat["winter_grain_double_crop"].status == "unavailable"


# ---------------------------------------------------------------- finder


def test_finder_enumerates_options_and_priorities_only_reorder(index):
    res_a = find_plans(plan(), index, year=YEAR, priorities=["soil_protection"])
    res_b = find_plans(plan(), index, year=YEAR, priorities=["limited_water"])
    res_c = find_plans(plan(), index, year=YEAR, priorities=["planting_window"])
    ids = {o.option_id for o in res_a.options}
    assert "none" in ids and any(i.startswith("cereal_rye_gap") for i in ids)
    assert any(i.startswith("crimson_clover_gap") for i in ids)
    assert ids == {o.option_id for o in res_b.options} == {o.option_id for o in res_c.options}

    def facts(res):
        return {o.option_id: o.model_dump(exclude={"rank"}) for o in res.options}

    assert facts(res_a) == facts(res_b) == facts(res_c)  # ranking never changes the facts
    assert [o.rank for o in res_a.options] == list(range(1, len(res_a.options) + 1))
    assert res_a.excluded[-1].option_id == "winter_wheat_double_crop"
    assert res_a.excluded[-1].status == "unavailable"


def test_finder_priorities_change_the_order(index):
    soil = find_plans(plan(), index, year=YEAR, priorities=["soil_protection"]).options
    # soil protection ranks the longest living cover first and bare ground last
    covers = [o.cover_days or 0 for o in soil]
    assert covers == sorted(covers, reverse=True) and soil[-1].option_id == "none"
    water = find_plans(plan(), index, year=YEAR, priorities=["limited_water"]).options
    assert [o.option_id for o in water] != [o.option_id for o in soil]
    assert all(not o.moisture_flag_ids for o in water[:1])


def test_finder_flags_late_corn_for_clover(index):
    p = plan(prev_harvest="10-10")
    res = find_plans(p, index, year=YEAR)
    clover = [o for o in res.options if o.option_id.startswith("crimson_clover")]
    assert clover and all("cc_rc_02" in o.chronology_conflicts for o in clover)
    assert any("no in-window seeding date" in n for o in clover for n in o.notes)


def test_finder_unsupported_pair(index):
    res = find_plans(plan(next_crop_id="quinoa"), index, year=YEAR)
    assert res.status == "unsupported" and res.options == []


# ---------------------------------------------------------------- HTTP


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def body(**kw):
    return {"plan": plan(**kw).model_dump(mode="json"), "year": YEAR}


def test_http_check_carries_metadata(client):
    r = client.post("/v1/plans/check", json=body())
    assert r.status_code == 200
    meta = r.json()["meta"]
    assert set(meta) == {"plan_version", "catalog_version", "snapshot_hash", "request_id"}
    assert meta["catalog_version"].startswith("v1:")
    assert r.json()["result"]["status"] == "complete"


def test_http_invalid_plan_is_a_400_with_field_issues(client):
    bad = body()
    bad["plan"]["next_plant"] = "13-45"
    r = client.post("/v1/plans/check", json=bad)
    assert r.status_code == 400
    j = r.json()
    assert j["status"] == "invalid_input" and j["issues"][0]["field"] == "next_plant"
    assert "request_id" in j


def test_http_chronology_error_is_a_400(client):
    b = body(
        winter=WinterManagement(kind="cover", crop_id="cereal_rye", seed="09-01", terminate="04-28")
    )
    r = client.post("/v1/plans/check", json=b)
    assert r.status_code == 400 and r.json()["issues"][0]["field"] == "winter.seed"


def test_http_unsupported_is_200_with_status(client):
    r = client.post("/v1/plans/check", json=body(next_crop_id="quinoa"))
    assert r.status_code == 200 and r.json()["result"]["status"] == "unsupported"


def test_http_crops_and_find(client):
    crops = client.get("/v1/crops").json()
    assert len(crops["crops"]) == 5 and "meta" in crops
    r = client.post("/v1/plans/find", json={**body(), "priorities": ["limited_water"]})
    assert r.status_code == 200 and r.json()["result"]["options"][0]["rank"] == 1
    bad = client.post("/v1/plans/find", json={**body(), "priorities": ["vibes"]})
    assert bad.status_code == 400 and bad.json()["issues"][0]["field"] == "priorities"
