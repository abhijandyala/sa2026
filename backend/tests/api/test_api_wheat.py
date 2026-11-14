"""Phase 6 follow-up: winter-wheat double-crop in the comparison (catalog v2) and the v1 fallback.

The wheat plan's dates are the sample's ASSUMED demo dates; weather is the real Union County
snapshot. The network is blocked for every test here.
"""

import dataclasses
import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fieldshift.api.app import create_app
from fieldshift.catalogs import V1_CATALOG_DIR, CatalogIndex, load_catalog
from fieldshift.compare import engine
from fieldshift.compare.context import get_context
from fieldshift.contracts import Plan
from fieldshift.planner.wheat_path import demo_plan

ROOT = Path(__file__).resolve().parents[2]
PLANS = ROOT / "data/samples/union_plans.json"
WHEAT = "corn_soy__wheat_dc"


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("FIELDSHIFT_OFFLINE", "1")

    def refuse(*a, **k):
        raise AssertionError("network access attempted")

    mp.setattr(socket.socket, "connect", refuse)
    yield TestClient(create_app())
    mp.undo()


def sample(plan_id: str) -> dict:
    doc = json.loads(PLANS.read_text())
    return next(s["plan"] for s in doc["samples"] if s["plan_id"] == plan_id)


def _all_keys(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _all_keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _all_keys(v)}
    return set()


def compare(client, body: dict):
    return client.post("/v1/plans/compare", json=body)


def wheat_of(body: dict) -> dict:
    return next(p for p in body["plans"] if p["plan_id"] == WHEAT)


def test_sample_wheat_plan_is_the_template_demo_dates_labelled_assumed(client):
    assert sample(WHEAT) == demo_plan().model_dump(mode="json")
    tmpl = client.get("/v1/plans/wheat/template").json()
    assert tmpl["plan"] == sample(WHEAT) and tmpl["dates_basis"] == "assumed"
    doc = json.loads(PLANS.read_text())
    entry = next(s for s in doc["samples"] if s["plan_id"] == WHEAT)
    assert entry["dates_basis"] == "assumed" and entry["dates_assumed"] is True
    assert "unavailable" not in entry


def test_add_grain_crop_returns_partial_not_unavailable(client):
    r = compare(client, {"rotation_ids": ["add_grain_crop"]})
    assert r.status_code == 200
    wheat, other = r.json()["plans"]
    assert wheat["plan_id"] == WHEAT and wheat["status"] == "partial"
    assert wheat["dates_basis"] == "assumed" and wheat["dates_assumed"] is True
    assert wheat["rotation_ids"] == ["add_grain_crop"]
    assert wheat["double_crop"]["status"] == "partial"
    assert wheat["double_crop"]["path"] == "winter_wheat_double_crop"
    assert other["plan_id"] == "soy_corn__no_cover" and other["status"] == "complete"
    assert other["double_crop"] is None and other["dates_basis"] == "assumed"


def test_double_crop_sits_next_to_full_season_only_as_different_calendar_raw_totals(client):
    body = compare(client, {"rotation_ids": ["add_grain_crop"]}).json()
    cross = wheat_of(body)["double_crop"]["cross_calendar"]
    assert cross["label"] == "different-calendar" and cross["status"] == "complete"
    assert cross["full_season"]["plan_id"] == "corn_soy__no_cover"  # the sample default
    assert cross["double_crop"]["plan_id"] == WHEAT
    # raw totals only: no rank, percentile, dry label or era result across the two calendars
    keys = _all_keys(cross)
    for forbidden in (
        "percentile",
        "rank",
        "is_dry",
        "dry_years",
        "dry_seasons",
        "eras",
        "era_dry_spring",
    ):
        assert forbidden not in keys
    fs, dc = cross["full_season"], cross["double_crop"]
    assert cross["median_total_mm_difference"] == round(
        dc["median_total_mm"] - fs["median_total_mm"], 3
    )
    assert fs["window"]["plant_md"] == "05-12" and dc["window"]["plant_md"] == "06-12"


def test_maturity_group_checks_and_manual_check_rows_stay_visible(client):
    dc = wheat_of(compare(client, {"rotation_ids": ["add_grain_crop"]}).json())["double_crop"]
    assert dc["maturity_group"]["status"] == "unknown" and dc["maturity_group"]["missing"] == [
        "maturity_group"
    ]
    ids = {c["rule_id"] for c in dc["maturity_group"]["checks"]}
    assert ids == {"sb_v2_mg_mid_june", "sb_v2_mg_mid_july", "sb_rc_03"}
    manual = dc["rule_checks"]["manual_check"]
    assert manual and all(m["status"] == "manual_check" for m in manual)
    withmg = wheat_of(
        compare(client, {"rotation_ids": ["add_grain_crop"], "maturity_group": 3}).json()
    )
    mg = withmg["double_crop"]["maturity_group"]
    assert mg["input"] == 3 and mg["status"] == "complete"
    flagged = {c["rule_id"] for c in mg["checks"] if c["flagged"]}
    assert "sb_rc_03" in flagged  # MG below 4 is a caution (B's rule; used as is)


@pytest.mark.parametrize("bad", [11, -1, True, "3", float("inf")])
def test_bad_maturity_group_is_a_typed_400(client, bad):
    r = client.post(
        "/v1/plans/compare",
        content=json.dumps({"rotation_ids": ["add_grain_crop"], "maturity_group": bad}),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400 and r.json()["status"] == "invalid_input"
    assert any(i["field"].startswith("maturity_group") for i in r.json()["issues"])


def test_wheat_is_never_added_to_other_plans_or_folded_into_shared_years(client):
    others = {"plan_ids": ["corn_soy__no_cover", "corn_soy__rye"]}
    alone = compare(client, others).json()
    both = compare(client, {**others, "plan_ids": [*others["plan_ids"], WHEAT]}).json()
    assert both["shared_eligible_years"] == alone["shared_eligible_years"]
    wheat = wheat_of(both)
    assert wheat["eras_shared_years"] == {}  # never in a cross-plan era comparison
    assert wheat["spring"]["shortcuts"]["basis"] == "own_window_baseline"
    for p in both["plans"]:
        if p["plan_id"] != WHEAT:  # the other plans' results are unchanged by the wheat plan
            twin = next(q for q in alone["plans"] if q["plan_id"] == p["plan_id"])
            # identical apart from the threshold-set id (the set also holds the wheat window's cutoff)
            strip = lambda eras: {k: {**v, "threshold_set_id": None} for k, v in eras.items()}  # noqa: E731
            assert strip(p["eras_shared_years"]) == strip(twin["eras_shared_years"])
    assert not any(k in both for k in ("rotation_total", "combined", "total"))


def test_the_request_s_own_full_season_soybean_plan_is_preferred_to_the_default(client):
    mine = sample("corn_soy__no_cover")
    mine["plan_id"], mine["next_plant"] = "my_full_season", "05-20"
    body = compare(client, {"plans": [mine], "plan_ids": [WHEAT]}).json()
    cross = wheat_of(body)["double_crop"]["cross_calendar"]
    assert cross["full_season"]["plan_id"] == "my_full_season"
    assert cross["full_season"]["window"]["plant_md"] == "05-20"
    alone = compare(client, {"plan_ids": [WHEAT]}).json()  # no neighbour: sample default
    assert (
        wheat_of(alone)["double_crop"]["cross_calendar"]["full_season"]["plan_id"]
        == "corn_soy__no_cover"
    )


def test_wheat_dry_cutoff_is_the_frozen_threshold_in_the_response(client):
    body = compare(client, {"plan_ids": [WHEAT, "corn_soy__no_cover"]}).json()
    dc = wheat_of(body)["double_crop"]
    frozen = body["thresholds"]["dry_spring"]["06-12"]
    assert dc["spring"]["cutoff_mm"] == frozen["value"]
    assert dc["spring"]["baseline"] == "own_window_baseline"


def test_an_unusable_neighbour_plan_does_not_sink_the_wheat_plan(client):
    bad = sample("corn_soy__no_cover")
    bad["plan_id"], bad["previous_crop_id"] = "dragon", "dragon_fruit"
    body = compare(client, {"plans": [bad], "plan_ids": [WHEAT]}).json()
    dragon = next(p for p in body["plans"] if p["plan_id"] == "dragon")
    assert dragon["status"] == "unsupported"
    wheat = wheat_of(body)
    assert wheat["status"] == "partial"
    cross = wheat["double_crop"]["cross_calendar"]
    assert cross["status"] == "unavailable" and "dragon_fruit" in cross["reason"]


def test_bad_wheat_chronology_is_a_typed_400_with_the_plan_prefix(client):
    p = sample(WHEAT)
    p["winter"]["harvest"] = "06-20"  # harvested after the soybean planting date
    r = compare(client, {"plans": [p]})
    assert r.status_code == 400 and r.json()["status"] == "invalid_input"
    assert all(i["field"].startswith(f"plans.{WHEAT}.") for i in r.json()["issues"])


def test_wheat_plan_with_a_feb_29_date_is_rejected_for_the_years_it_breaks(client):
    p = sample(WHEAT)
    p["prev_harvest"], p["winter"]["plant"], p["winter"]["harvest"] = "02-27", "02-28", "02-29"
    r = compare(client, {"plans": [p]})
    assert r.status_code == 400 and r.json()["status"] == "invalid_input"


def test_catalog_v1_keeps_unavailable_catalog_missing_and_other_plans_still_work():
    v1 = dataclasses.replace(get_context(), index=CatalogIndex(load_catalog(V1_CATALOG_DIR)))
    plans = [demo_plan(), Plan.model_validate(sample("corn_soy__no_cover"))]
    results, ts, shared = engine.compare_plans(plans, v1, maturity_group=4)
    wheat, other = results
    assert (wheat.status, wheat.reason) == ("unavailable", "catalog_missing")
    assert wheat.double_crop is None and wheat.spring is None
    assert other.status == "complete"
    assert len(shared.spring) == 45 and shared.winter == shared.spring[1:]  # winter 1981 is partial


def test_replay_of_the_wheat_sample_works_and_sensitivity_says_not_a_cover_plan(client):
    assert client.get(f"/v1/seasons/2008/replay?plan={WHEAT}").status_code == 200
    r = client.post("/v1/plans/sensitivity", json={"plan_id": WHEAT, "rule_id": "cr_tt_03"})
    assert r.status_code == 400
    assert r.json()["issues"][0]["code"] == "not_a_cover_plan"


def test_maturity_group_zero_is_a_real_value_and_null_means_not_entered(client):
    zero = wheat_of(
        compare(client, {"rotation_ids": ["add_grain_crop"], "maturity_group": 0}).json()
    )
    assert zero["double_crop"]["maturity_group"]["input"] == 0
    assert zero["double_crop"]["maturity_group"]["status"] == "complete"
    blank = wheat_of(
        compare(client, {"rotation_ids": ["add_grain_crop"], "maturity_group": None}).json()
    )
    assert blank["double_crop"]["maturity_group"]["input"] is None
    assert blank["double_crop"]["maturity_group"]["status"] == "unknown"


def test_blank_maturity_group_means_not_entered_not_a_400(client):
    for blank in ("", "   "):
        w = wheat_of(
            compare(client, {"rotation_ids": ["add_grain_crop"], "maturity_group": blank}).json()
        )
        assert w["double_crop"]["maturity_group"]["status"] == "unknown"


def test_maturity_group_changes_the_input_hash_and_plan_version(client):
    def head(mg):
        b = compare(client, {"rotation_ids": ["add_grain_crop"], "maturity_group": mg}).json()
        return b["input_hash"], b["meta"]["plan_version"], b["result_id"]

    seen = {mg: head(mg) for mg in (None, 0, 3, 5)}
    assert len(set(seen.values())) == 4
    assert head(None) == head("")  # blank is the same request as not entering it


def test_openapi_bounds_use_real_json_schema_keywords():
    schema = json.loads((ROOT / "docs/api/openapi.json").read_text())
    mg = schema["components"]["schemas"]["CompareRequest"]["properties"]["maturity_group"]
    branches = [b for b in mg["anyOf"] if b.get("type") in ("integer", "number")]
    assert len(branches) == 2
    for b in branches:
        assert b["minimum"] == 0 and b["maximum"] == 10
    assert not any({"ge", "le"} & set(b) for b in mg["anyOf"])


def test_wheat_winter_exposure_is_computed_over_its_own_window_with_the_frozen_threshold(client):
    body = compare(client, {"plan_ids": [WHEAT, "corn_soy__rye"]}).json()
    w = wheat_of(body)
    rye = next(p for p in body["plans"] if p["plan_id"] == "corn_soy__rye")
    # winter 1981 starts before the record: 44 of 45 seasons evaluable, same as the rye plan
    assert w["winter"]["status"] == rye["winter"]["status"] == "partial"
    assert w["winter"]["eligible_seasons"] == 44
    assert w["winter"]["segments"] == [
        "living_cover",
        "before_establishment",
        "after_termination",
        "no_planned_cover",
    ]
    assert w["calendar"]["living_cover_kind"] == "winter_grain"
    assert w["calendar"]["living_cover_days_planned"] == 223  # wheat 10-25 .. 06-05 (2025)
    assert w["calendar"]["winter_days"] == 265  # 2024-09-20 .. 2025-06-12 (exclusive)
    rows = {r["year"]: r for r in w["seasons"]}
    assert len(rows) == 45
    first, last = rows[1981], rows[2025]
    assert first["winter_status"] == "partial" and first["rain_outside_cover_mm"] is None  # not 0
    assert last["rain_outside_cover_mm"] is not None and last["heavy_rain_days_outside_cover"] >= 0
    assert (
        w["eras"]["winter_heavy_rain_outside_cover"]["indicator"]
        == "winter_heavy_rain_outside_cover"
    )
    eras = w["eras"]["winter_heavy_rain_outside_cover"]
    assert eras["threshold_set_id"] == body["thresholds"]["threshold_set_id"]
    # the block inside double_crop agrees with the plan-level numbers
    we = w["double_crop"]["winter_exposure"]
    assert we["status"] == "partial" and we["label"] == "own_window"
    assert we["heavy_rain_threshold"]["value"] == body["thresholds"]["heavy_rain"]["value"] == 76.2
    assert we["per_season_median"] == w["winter"]["per_season_median"]
    # spring stays on its own planting window
    assert w["spring"]["cutoff_mm"] == body["thresholds"]["dry_spring"]["06-12"]["value"]
    assert w["double_crop"]["spring"]["cutoff_mm"] == w["spring"]["cutoff_mm"]


def test_wheat_winter_numbers_match_a_direct_compute_winter(client):
    from fieldshift.compare.context import get_context
    from fieldshift.compare.engine import threshold_set_for
    from fieldshift.metrics.winter import compute_winter
    from fieldshift.seasons.align import build_calendar

    ctx = get_context()
    plan = Plan.model_validate(sample(WHEAT))
    ts = threshold_set_for(ctx, [plan.next_plant])
    rows = {
        r["year"]: r for r in wheat_of(compare(client, {"plan_ids": [WHEAT]}).json())["seasons"]
    }
    for y in (1990, 2008, 2020):
        direct = compute_winter(plan, build_calendar(plan, y), ctx.series, ts, ctx.snapshot_hash)
        assert rows[y]["rain_outside_cover_mm"] == direct.rain_outside_cover_mm
        assert rows[y]["heavy_rain_days_outside_cover"] == direct.heavy_rain_days_outside_cover


def test_wheat_does_not_change_the_other_plans_or_the_shared_winter_years(client):
    alone = compare(client, {"plan_ids": ["corn_soy__no_cover", "corn_soy__rye"]}).json()
    both = compare(client, {"plan_ids": ["corn_soy__no_cover", "corn_soy__rye", WHEAT]}).json()
    assert both["shared_eligible_years"]["winter"] == alone["shared_eligible_years"]["winter"]
    for pid in ("corn_soy__no_cover", "corn_soy__rye"):
        a = next(p for p in alone["plans"] if p["plan_id"] == pid)
        b = next(p for p in both["plans"] if p["plan_id"] == pid)
        assert a["winter"] == b["winter"] and a["seasons"] == b["seasons"]
