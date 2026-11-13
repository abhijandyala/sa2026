"""Phase 6 API tests. Plans are sample/fixture plans with ASSUMED dates; weather is the real
Union County snapshot. The network is blocked for every test in this module."""

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fieldshift.api.app import create_app

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/snapshots/union_county/raw/power_daily.json"
PLANS = ROOT / "data/samples/union_plans.json"


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("FIELDSHIFT_OFFLINE", "1")

    def refuse(*a, **k):
        raise AssertionError("network access attempted")

    mp.setattr(socket.socket, "connect", refuse)
    yield TestClient(create_app())
    mp.undo()


def sample_plan(plan_id: str) -> dict:
    doc = json.loads(PLANS.read_text())
    return next(s["plan"] for s in doc["samples"] if s["plan_id"] == plan_id)


def rye_plan(terminate: str, plan_id: str = "corn_soy__rye") -> dict:
    p = sample_plan("corn_soy__rye")
    p["plan_id"] = plan_id
    p["winter"]["terminate"] = terminate
    return p


def post(client, path, body):
    return client.post(path, json=body)


def stable(resp_json: dict) -> str:
    """Response without the per-request metadata, serialized deterministically."""
    body = {k: v for k, v in resp_json.items() if k != "meta"}
    return json.dumps(body, sort_keys=True)


# --- compare ------------------------------------------------------------------------------------


def test_compare_presets_returns_shared_thresholds_meta_and_hashes(client):
    r = post(client, "/v1/plans/compare", {"rotation_ids": ["current_practice", "winter_cover"]})
    assert r.status_code == 200
    body = r.json()
    assert set(body["meta"]) == {"plan_version", "catalog_version", "snapshot_hash", "request_id"}
    assert body["meta"]["snapshot_hash"] and body["result_id"] and body["input_hash"]
    ids = [p["plan_id"] for p in body["plans"]]
    assert ids == ["corn_soy__no_cover", "soy_corn__no_cover", "corn_soy__rye", "soy_corn__rye"]
    t = body["thresholds"]
    hr = t["heavy_rain"]
    assert hr["value"] == 76.2 and hr["parameters"]["assumed"] is False
    assert hr["source"]["rule_id"] == "fc_v2_ref_very_heavy_rain" and hr["source"]["url"]
    assert "Local Solar Time" in hr["note"] and "soil loss" in hr["note"]
    assert "05-12" in t["dry_spring"] and "04-15" in t["dry_spring"]
    assert body["shared_eligible_years"]["spring"] == list(range(1981, 2026))
    assert body["shared_eligible_years"]["winter"] == list(range(1982, 2026))  # 44 winters
    assert body["eras"]["excluded_from_eras"] == [2001, 2002, 2003, 2004, 2005]


def test_rye_plan_numbers_match_the_handbook_shape(client):
    body = post(client, "/v1/plans/compare", {"plan_ids": ["corn_soy__rye"]}).json()
    (plan,) = body["plans"]
    assert plan["calendar"]["termination_gap_days"] == 12
    assert plan["calendar"]["spring_window"] == {"start": "04-12", "end": "05-11"}
    assert plan["spring"]["eligible_seasons"] == 45 and plan["spring"]["dry_seasons"] == 9
    (check,) = [c for c in plan["spring_checks"] if c["check_id"] == "rye_soy_short_gap_moisture"]
    assert check["rule_ids"] == ["cr_tt_03"]
    assert (check["count"], check["denominator"], check["pct"]) == (9, 45, 20.0)
    assert check["qualifying_years"] == plan["spring"]["dry_years"]
    era = plan["eras"]["rye_soy_short_gap_moisture"]
    assert era["earlier"]["evaluable"] == era["recent"]["evaluable"] == 20
    assert era["earlier"]["threshold_value"] == era["recent"]["threshold_value"] == 64.18
    assert "not a trend, cause, or forecast" in era["caveat"]


def test_each_plan_uses_its_own_denominators_and_legs_are_not_summed(client):
    body = post(client, "/v1/plans/compare", {"rotation_ids": ["winter_cover"]}).json()
    leg1, leg2 = body["plans"]
    assert (leg1["plan_id"], leg2["plan_id"]) == ("corn_soy__rye", "soy_corn__rye")
    assert leg1["spring"]["window_days"] == leg2["spring"]["window_days"] == 30
    assert leg1["calendar"]["spring_window"] != leg2["calendar"]["spring_window"]
    assert leg1["spring"]["cutoff_mm"] != leg2["spring"]["cutoff_mm"]
    assert "rotation_total" not in body


def test_wheat_double_crop_is_unavailable_catalog_missing_and_others_still_work(client):
    body = post(client, "/v1/plans/compare", {"rotation_ids": ["add_grain_crop"]}).json()
    wheat, other = body["plans"]
    assert (wheat["plan_id"], wheat["status"], wheat["reason"]) == (
        "corn_soy__wheat_dc", "unavailable", "catalog_missing")
    assert other["status"] == "complete"


def test_clover_plan_flags_sb_rc_02_cc_rc_02_and_cc_soil_02_manual_check(client):
    body = post(client, "/v1/plans/compare", {"plan_ids": ["corn_soy__clover"]}).json()
    lines = {c["rule_id"]: c for c in body["plans"][0]["other_checks"]}
    assert lines["sb_rc_02"]["flagged"] and lines["cc_rc_02"]["flagged"]
    assert lines["cc_soil_02"]["status"] == "manual_check"


def test_choosing_a_replay_year_never_changes_the_aggregate_or_era_results(client):
    req = {"rotation_ids": ["current_practice", "winter_cover"]}
    first = post(client, "/v1/plans/compare", req).json()
    for year in (1981, 1999, 2008, 2025):
        assert client.get(f"/v1/seasons/{year}/replay?plan=corn_soy__rye").status_code == 200
    second = post(client, "/v1/plans/compare", req).json()
    assert stable(first) == stable(second)  # byte-identical apart from per-request meta
    assert first["result_id"] == second["result_id"]
    assert first["meta"]["request_id"] != second["meta"]["request_id"]


def test_editing_the_termination_date_keeps_spring_results_and_clears_the_check(client):
    body = post(client, "/v1/plans/compare",
                {"plans": [rye_plan("04-30", "gap12"), rye_plan("04-23", "gap19")]}).json()
    a, b = body["plans"]
    assert (a["calendar"]["termination_gap_days"], b["calendar"]["termination_gap_days"]) == (12, 19)
    assert a["spring"] == b["spring"]  # window, cutoff, dry years identical
    assert a["spring_checks"][0]["count"] == 9 and b["spring_checks"][0]["count"] == 0
    assert a["seasons"][5]["spring_total_mm"] == b["seasons"][5]["spring_total_mm"]


def test_cross_plan_eras_are_computed_on_shared_years_and_labelled(client):
    body = post(client, "/v1/plans/compare", {"plan_ids": ["corn_soy__no_cover", "corn_soy__rye"]}).json()
    for plan in body["plans"]:
        shared = plan["eras_shared_years"]["winter_heavy_rain_outside_cover"]
        assert shared["basis"] == "shared_evaluable_seasons"
        assert shared["thresholds"] == plan["eras"]["winter_heavy_rain_outside_cover"]["thresholds"]


def test_compare_ignores_soil_failure(client, monkeypatch):
    import fieldshift.field.soil as soil

    def boom(*a, **k):
        raise RuntimeError("SDA timed out")

    monkeypatch.setattr(soil, "get_soil", boom)
    r = post(client, "/v1/plans/compare", {"plan_ids": ["corn_soy__rye"]})
    assert r.status_code == 200
    assert r.json()["soil"]["status"] == "unavailable"
    assert r.json()["plans"][0]["status"] == "complete"


def test_offline_default_soil_is_unavailable_not_an_error(client):
    body = post(client, "/v1/plans/compare", {"plan_ids": ["corn_soy__rye"]}).json()
    assert body["soil"]["status"] == "unavailable"


# --- invalid input -----------------------------------------------------------------------------------


def test_chronology_error_is_a_typed_400_naming_the_field(client):
    bad = rye_plan("05-20")  # terminates after planting
    r = post(client, "/v1/plans/compare", {"plans": [bad]})
    assert r.status_code == 400
    body = r.json()
    assert body["status"] == "invalid_input" and body["request_id"]
    assert body["issues"][0]["field"] == "plans.corn_soy__rye.winter.terminate"
    assert body["issues"][0]["code"] == "terminate_after_planting"


@pytest.mark.parametrize(
    ("path", "body", "field"),
    [
        ("/v1/plans/compare", {"plan_ids": ["nope"]}, "plan_ids.0"),
        ("/v1/plans/compare", {"rotation_ids": ["nope"]}, "rotation_ids.0"),
        ("/v1/plans/compare", {}, "plans"),
        ("/v1/plans/compare", {"unknown_field": 1, "plan_ids": ["corn_soy__rye"]}, "unknown_field"),
        ("/v1/plans/sensitivity", {}, "plan"),
    ],
)
def test_bad_requests_are_typed_400s(client, path, body, field):
    r = post(client, path, body)
    assert r.status_code == 400
    assert r.json()["status"] == "invalid_input"
    assert any(i["field"] == field for i in r.json()["issues"])


def test_too_many_plans_and_bad_year_and_unknown_plan(client):
    many = [rye_plan("04-30", f"p{i}") for i in range(9)]
    assert post(client, "/v1/plans/compare", {"plans": many}).json()["issues"][0]["code"] == "too_many_plans"
    assert client.get("/v1/seasons/1980/replay").json()["issues"][0]["field"] == "year"
    assert client.get("/v1/seasons/2008/replay?plan=zzz").status_code == 400
    assert client.get("/v1/seasons/2008/replay?plan=corn_soy__wheat_dc").status_code == 400


# --- replay --------------------------------------------------------------------------------------------


def test_replay_has_exact_season_days_checks_and_missing_labels(client):
    r = client.get("/v1/seasons/2008/replay?plan=corn_soy__rye")
    body = r.json()
    assert r.status_code == 200 and body["year"] == 2008
    days = body["daily"]
    assert days[0]["date"] == "2007-09-20" and days[-1]["date"] == "2008-05-11"
    assert len(days) == 235  # [prev_harvest, plant): harvest day in, planting day out
    segs = {d["segment"] for d in days}
    assert segs == {"before_establishment", "living_cover", "after_termination"}
    by_date = {d["date"]: d for d in days}
    assert by_date["2007-09-30"]["segment"] == "before_establishment"
    assert by_date["2007-10-01"]["cover_status"] == "planned_living_cover"
    assert by_date["2008-04-29"]["segment"] == "living_cover"
    assert by_date["2008-04-30"]["segment"] == "after_termination"  # termination day not cover
    assert by_date["2008-04-30"]["cover_status"] == "terminated"
    assert sum(d["in_spring_window"] for d in days) == 30
    assert body["spring"]["is_dry"] is True and body["spring"]["rank"] == 8
    assert [c["check_id"] for c in body["checks_triggered"]] == ["rye_soy_short_gap_moisture"]
    assert body["wetness"]["label"] == "modeled"
    assert all(d["precip_mm"] is not None for d in days)  # real zeros stay 0.0, never None


def test_replay_1981_marks_pre_record_days_missing_with_reason(client):
    body = client.get("/v1/seasons/1981/replay?plan=corn_soy__rye").json()
    first = body["daily"][0]
    assert first["precip_mm"] is None and first["missing_reasons"]["precip_mm"] == "outside_record"
    assert body["coverage"]["winter"] == "partial" and body["coverage"]["spring"] == "complete"
    assert body["winter"]["total_rain_mm"] is None


def test_post_replay_accepts_an_edited_plan(client):
    r = post(client, "/v1/seasons/2008/replay", {"plan": rye_plan("04-23")})
    assert r.status_code == 200
    assert r.json()["checks_triggered"] == []  # 19-day gap clears
    assert r.json()["spring"]["total_mm"] == 64.09  # spring unchanged


# --- sensitivity -----------------------------------------------------------------------------------------


def test_sensitivity_curve_is_flat_on_both_sides_of_14_days_and_step_equals_dry_years(client):
    body = post(client, "/v1/plans/sensitivity", {"plan_id": "corn_soy__rye"}).json()
    pts = body["points"]
    dry = len(body["dry_years"])
    assert dry == 9 and body["check_id"] == "rye_soy_short_gap_moisture"
    below = {p["checks_count"] for p in pts if p["gap_days"] < 14}
    above = {p["checks_count"] for p in pts if p["gap_days"] >= 14}
    assert below == {dry} and above == {0}
    by_gap = {p["gap_days"]: p for p in pts}
    assert by_gap[13]["checks_count"] - by_gap[14]["checks_count"] == dry
    assert by_gap[12]["terminate"] == "04-30" and by_gap[0]["terminate"] == "05-12"
    assert all(p["denominator"] == 45 for p in pts)
    assert pts[0]["gap_days"] > pts[-1]["gap_days"] == 0
    # later termination = more living cover days and less rain outside cover
    assert pts[-1]["living_cover_days_planned"] > pts[0]["living_cover_days_planned"]
    assert pts[-1]["rain_outside_cover_mm_median"] <= pts[0]["rain_outside_cover_mm_median"]


def test_sensitivity_with_grower_concern_fires_every_evaluable_season_below_14_days(client):
    p = sample_plan("corn_soy__rye")
    p["grower"]["low_moisture_concern"] = True
    pts = post(client, "/v1/plans/sensitivity", {"plan": p}).json()["points"]
    assert {x["checks_count"] for x in pts if x["gap_days"] < 14} == {45}
    assert {x["checks_count"] for x in pts if x["gap_days"] >= 14} == {0}


def test_sensitivity_winter_numbers_equal_compute_winter(client):
    from fieldshift.compare.context import get_context
    from fieldshift.compare.engine import threshold_set_for
    from fieldshift.contracts import Plan
    from fieldshift.metrics.winter import compute_winter
    from fieldshift.seasons.align import build_calendar

    body = post(client, "/v1/plans/sensitivity", {"plan_id": "corn_soy__rye"}).json()
    ctx = get_context()
    base = Plan.model_validate(sample_plan("corn_soy__rye"))
    ts = threshold_set_for(ctx, [base.next_plant])
    import statistics

    for point in body["points"][::40]:
        p2 = base.model_copy(update={"winter": base.winter.model_copy(
            update={"terminate": point["terminate"]})})
        rains = []
        for y in range(1982, 2026):
            w = compute_winter(p2, build_calendar(p2, y), ctx.series, ts, ctx.snapshot_hash)
            rains.append(w.rain_outside_cover_mm)
        assert round(statistics.median(rains), 3) == point["rain_outside_cover_mm_median"]


def test_sensitivity_needs_a_cover_plan(client):
    r = post(client, "/v1/plans/sensitivity", {"plan_id": "corn_soy__no_cover"})
    assert r.status_code == 400 and r.json()["issues"][0]["code"] == "not_a_cover_plan"


# --- years --------------------------------------------------------------------------------------------------


def test_years_lists_all_45_with_statuses_and_shortcuts(client):
    body = client.get("/v1/years").json()
    yrs = body["years"]
    assert [y["year"] for y in yrs] == list(range(1981, 2026))
    assert yrs[0]["winter"] == "partial" and yrs[0]["spring"] == "complete"
    assert "1981-01-01" in yrs[0]["reason"]
    assert sum(y["winter"] == "complete" for y in yrs) == 44
    sc = body["shortcuts"]
    assert set(sc) == {"typical", "dry", "wet"} and len({sc["dry"], sc["wet"]}) == 2
    assert body["eras"]["earlier"] == {"start": 1981, "end": 2000}
    assert body["meta"]["request_id"]


def test_rotations_endpoint_lists_the_three_presets(client):
    env = client.get("/v1/rotations").json()
    assert set(env["meta"]) == {"plan_version", "catalog_version", "snapshot_hash", "request_id"}
    r = env["rotations"]
    assert [x["rotation_id"] for x in r] == ["current_practice", "winter_cover", "add_grain_crop"]
    assert r[1]["legs"] == ["corn_soy__rye", "soy_corn__rye"]


def test_health_carries_meta_and_reads_only_the_snapshot(client):
    body = client.get("/health").json()
    assert body["offline"] is True and set(body["meta"]) >= {"snapshot_hash", "request_id"}


# --- reproducibility from raw/ alone ---------------------------------------------------------------------


@pytest.mark.parametrize(("plan_id", "year"), [("corn_soy__rye", 2008), ("corn_soy__no_cover", 1999),
                                               ("soy_corn__rye", 2015)])
def test_a_replay_is_reproducible_by_a_standalone_script_from_raw_only(client, plan_id, year):
    api = client.get(f"/v1/seasons/{year}/replay?plan={plan_id}").json()
    out = subprocess.run(
        [sys.executable, "-I", str(ROOT / "scripts/reproduce_replay.py"), "--raw", str(RAW),
         "--plans", str(PLANS), "--plan", plan_id, "--year", str(year)],
        capture_output=True, text=True, check=True,
    )
    ref = json.loads(out.stdout)
    assert ref["spring_total_mm"] == api["spring"]["total_mm"]
    assert ref["spring_rank"] == api["spring"]["rank"]
    assert ref["spring_is_dry"] == api["spring"]["is_dry"]
    assert ref["spring_dry_cutoff_mm"] == api["spring"]["cutoff_mm"]
    assert ref["heavy_rain_threshold_mm"] == api["thresholds"]["heavy_rain"]["value"]
    assert ref["rain_outside_cover_mm"] == api["winter"]["rain_outside_cover_mm"]
    assert ref["heavy_rain_days_outside_cover"] == api["winter"]["heavy_rain_days_outside_cover"]
    assert ref["n_eligible_springs"] == api["spring"]["of"]


# --- review fixes ------------------------------------------------------------------------------------------------


def test_replay_payload_rows_wetness_and_checks_reproduce_from_raw(client):
    for plan_id, year in [("corn_soy__rye", 2008), ("corn_soy__rye", 1981), ("soy_corn__rye", 2015)]:
        api = client.get(f"/v1/seasons/{year}/replay?plan={plan_id}").json()
        out = subprocess.run(
            [sys.executable, "-I", str(ROOT / "scripts/reproduce_replay.py"), "--raw", str(RAW),
             "--plans", str(PLANS), "--plan", plan_id, "--year", str(year)],
            capture_output=True, text=True, check=True,
        )
        ref = json.loads(out.stdout)
        assert len(ref["daily"]) == len(api["daily"])
        for a, b in zip(api["daily"], ref["daily"], strict=True):
            assert a["date"] == b["date"] and a["segment"] == b["segment"]
            for k in ("precip_mm", "tmax_c", "tmin_c", "gwettop", "gwetroot"):
                assert a[k] == b[k], (plan_id, year, a["date"], k)
        assert api["wetness"]["gwettop_window_mean"] == ref["gwettop_window_mean"]
        assert api["wetness"]["gwetroot_window_mean"] == ref["gwetroot_window_mean"]
        fired = any(c["rule_ids"] == ["cr_tt_03"] for c in api["checks_triggered"])
        assert fired == bool(ref["cr_tt_03_flagged"])


def test_shared_era_results_keep_each_plans_own_threshold(client):
    body = post(client, "/v1/plans/compare", {"plan_ids": ["corn_soy__rye", "soy_corn__rye"]}).json()
    corn, soy = body["plans"]
    for plan in (corn, soy):
        shared = plan["eras_shared_years"]["dry_spring"]
        own = plan["eras"]["dry_spring"]
        assert shared["thresholds"] == own["thresholds"]
        assert shared["earlier"]["threshold_value"] == plan["spring"]["cutoff_mm"]
    assert corn["spring"]["cutoff_mm"] != soy["spring"]["cutoff_mm"]


def test_shared_full_season_years_are_reported(client):
    body = post(client, "/v1/plans/compare", {"plan_ids": ["corn_soy__rye", "corn_soy__no_cover"]}).json()
    assert body["shared_eligible_years"]["full_season"] == list(range(1982, 2026))


def test_replay_returns_every_flagged_check_for_a_plan_with_problems(client):
    ids = {c["rule_ids"][0] for c in
           client.get("/v1/seasons/2008/replay?plan=corn_soy__clover").json()["checks_triggered"]}
    assert {"sb_rc_02", "cc_rc_02"} <= ids


def test_sensitivity_rule_validation_and_check_id_alias(client):
    bad = post(client, "/v1/plans/sensitivity", {"plan_id": "corn_soy__rye", "rule_id": "zz_zz_99"})
    assert bad.status_code == 400 and bad.json()["issues"][0]["field"] == "rule_id"
    alias = post(client, "/v1/plans/sensitivity",
                 {"plan_id": "corn_soy__rye", "rule_id": "rye_soy_short_gap_moisture"}).json()
    assert alias["rule_ids"] == ["cr_tt_03"] and alias["status"] == "complete"
    other = post(client, "/v1/plans/sensitivity", {"plan_id": "corn_soy__rye", "rule_id": "cc_pw_01"})
    assert other.json()["status"] == "inapplicable"


def test_sensitivity_flags_gaps_that_cross_feb_29(client):
    p = sample_plan("corn_soy__rye")
    p.update(prev_harvest="10-15", next_plant="03-10")
    p["winter"].update(seed="10-20", terminate="02-25")
    pts = post(client, "/v1/plans/sensitivity", {"plan": p}).json()["points"]
    before_leap_day = [x for x in pts if x["terminate"] < "03-01" and x["terminate"] > "01-31"]
    assert before_leap_day and all(x["gap_days_in_leap_years"] == x["gap_days"] + 1
                                   for x in before_leap_day)
    after_leap_day = [x for x in pts if "03-01" <= x["terminate"] <= "03-10"]
    assert after_leap_day and all(x["gap_days_in_leap_years"] is None for x in after_leap_day)


# --- review r2 fixes ----------------------------------------------------------------------------------------


def test_a_point_outside_the_union_cell_is_unsupported_not_union_county_data(client):
    for lat, lon in [(0.0, 0.0), (35.78, -78.64), (40.7, -74.0)]:  # null island, Raleigh, NYC
        body = post(client, "/v1/plans/compare", {
            "plan_ids": ["corn_soy__rye"], "location": {"latitude": lat, "longitude": lon}}).json()
        plan = body["plans"][0]
        assert plan["status"] == "unsupported" and "unsupported_location" in plan["reason"]
        assert plan["spring"] is None and plan["eras"] == {}
        assert body["location"] is not None


def test_a_point_inside_the_union_cell_resolves_to_the_snapshot(client):
    body = post(client, "/v1/plans/compare", {
        "plan_ids": ["corn_soy__rye"], "location": {"latitude": 34.99, "longitude": -80.54}}).json()
    assert body["plans"][0]["status"] == "complete"
    assert body["location"]["weather"]["source"] == "snapshot"


def test_replay_and_sensitivity_report_unsupported_crops_like_compare(client):
    p = sample_plan("corn_soy__rye")
    p["next_crop_id"] = "dragon_fruit"
    cmp_status = post(client, "/v1/plans/compare", {"plans": [p]}).json()["plans"][0]["status"]
    rep = post(client, "/v1/seasons/2008/replay", {"plan": p})
    sens = post(client, "/v1/plans/sensitivity", {"plan": p})
    assert cmp_status == "unsupported"
    for r in (rep, sens):
        assert r.status_code == 200 and r.json()["status"] == "unsupported"
        assert any("dragon_fruit" in u for u in r.json()["unsupported"]) and "daily" not in r.json()


def test_sensitivity_keeps_manual_check_status_for_applicable_rules(client):
    r = post(client, "/v1/plans/sensitivity",
             {"plan_id": "corn_soy__clover", "rule_id": "cc_soil_02"}).json()
    assert r["status"] == "manual_check"
    assert post(client, "/v1/plans/sensitivity",
                {"plan_id": "corn_soy__rye", "rule_id": "cc_pw_01"}).json()["status"] == "inapplicable"


def test_rotation_membership_comes_from_the_requested_rotations(client):
    body = post(client, "/v1/plans/compare", {"rotation_ids": ["add_grain_crop"]}).json()
    wheat, shared_leg = body["plans"]
    assert wheat["rotation_ids"] == ["add_grain_crop"]
    assert shared_leg["plan_id"] == "soy_corn__no_cover" and shared_leg["rotation_ids"] == ["add_grain_crop"]
    both = post(client, "/v1/plans/compare", {"rotation_ids": ["current_practice", "add_grain_crop"]}).json()
    leg = next(p for p in both["plans"] if p["plan_id"] == "soy_corn__no_cover")
    assert leg["rotation_ids"] == ["current_practice", "add_grain_crop"]
    alone = post(client, "/v1/plans/compare", {"plan_ids": ["soy_corn__no_cover"]}).json()["plans"][0]
    assert alone["rotation_ids"] == ["current_practice", "add_grain_crop"]
