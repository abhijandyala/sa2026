"""Per-location weather: every endpoint answers from the snapshot of the place it is asked about.

Offline: the committed snapshots are the only weather. Union County's output must not change.
"""

import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fieldshift.api.app import create_app
from fieldshift.weather.locations import get_index
from tests.api.union_golden_requests import run

GOLDEN = json.loads((Path(__file__).parent / "golden_union.json").read_text())
PLACES = ["union", "iredell", "rowan", "johnston", "wayne", "duplin", "pitt", "robeson"]
COASTAL = ["johnston", "wayne", "duplin", "pitt", "robeson"]
UNION_HASH = "5ce131cfcd1f07d3738ecb9afaec6c3ef6a4764b6a3528bdd2b64debe7ba5f4e"
RALEIGH = {"latitude": 35.78, "longitude": -78.64}  # in NC; its grid cell has no snapshot


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("FIELDSHIFT_OFFLINE", "1")

    def refuse(*a, **k):
        raise AssertionError("network access attempted")

    mp.setattr(socket.socket, "connect", refuse)
    yield TestClient(create_app())
    mp.undo()


def compare(client, location_id=None, plan_ids=("corn_soy__rye", "corn_soy__no_cover"), **extra):
    body = {"plan_ids": list(plan_ids), "include_soil": False, **extra}
    if location_id:
        body["location_id"] = location_id
    r = client.post("/v1/plans/compare", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_union_output_is_unchanged(client):
    """Every Union request hashes to what it did at d7d3367, apart from the keys added since."""
    assert run(client) == GOLDEN


@pytest.mark.parametrize("place", PLACES)
def test_compare_is_complete_and_carries_that_places_hash(client, place):
    entry = get_index().by_id(place)
    body = compare(client, place)
    assert body["meta"]["snapshot_hash"] == entry.snapshot_hash
    assert body["weather_location"]["snapshot_hash"] == entry.snapshot_hash
    assert body["weather_location"]["id"] == place and body["weather_location"]["status"] == "complete"
    assert body["data_sources"]["weather"]["snapshot_hash"] == entry.snapshot_hash
    assert body["request_echo"]["location_id"] == place
    assert [p["status"] for p in body["plans"]] == ["complete", "complete"]
    for p in body["plans"]:
        assert p["spring"]["status"] == "complete" and p["winter"] is not None
        assert p["eras"] and p["seasons"]


def test_a_point_in_a_served_cell_uses_that_snapshot(client):
    by_point = compare(client, location={"latitude": 35.52, "longitude": -78.37})
    by_id = compare(client, "johnston")
    assert by_point["meta"]["snapshot_hash"] == by_id["meta"]["snapshot_hash"]
    assert by_point["weather_location"]["id"] == "johnston"
    assert by_point["location"]["weather"]["source"] == "snapshot"
    # Wayne's point is in Johnston's cell: the same stored history
    wayne = compare(client, location={"latitude": 35.36, "longitude": -77.99})
    assert wayne["meta"]["snapshot_hash"] == by_id["meta"]["snapshot_hash"]


def test_johnston_and_wayne_share_one_snapshot_and_one_set_of_results(client):
    j, w = compare(client, "johnston"), compare(client, "wayne")
    assert j["meta"]["snapshot_hash"] == w["meta"]["snapshot_hash"]
    assert j["weather_location"]["shares_snapshot_with"] is None
    assert w["weather_location"]["shares_snapshot_with"] == "johnston"
    assert j["thresholds"]["dry_spring"] == w["thresholds"]["dry_spring"]
    assert j["plans"][0]["spring"] == w["plans"][0]["spring"]


def test_each_place_has_its_own_frozen_thresholds(client):
    seen: dict[str, tuple] = {}
    for place in ["union", "iredell", "rowan", "johnston", "duplin", "pitt", "robeson"]:
        t = compare(client, place)["thresholds"]
        assert t["location_id"] == place and t["location_name"].endswith("County")
        assert t["heavy_rain"]["value"] == 76.2 and t["heavy_rain"]["parameters"]["assumed"] is False
        assert "1981-01-01..2025-06-30" in t["baseline"]
        dry = tuple((k, v["value"]) for k, v in sorted(t["dry_spring"].items()))
        seen[place] = (t["threshold_set_id"], dry)
    assert len({v[0] for v in seen.values()}) == 7  # a threshold set per place
    assert len({v[1] for v in seen.values()}) == 7  # from each place's own baseline


def test_dry_cutoff_is_the_bottom_fifth_of_that_places_own_baseline(client):
    """Recompute the cutoff for Pitt from its own snapshot: it must equal the one reported."""
    import pandas as pd

    from fieldshift.weather.locations import load_entry_snapshot

    t = compare(client, "pitt", plan_ids=("corn_soy__rye",))["thresholds"]
    daily = load_entry_snapshot("pitt").daily
    md_start = pd.Timestamp("2001-05-12") - pd.Timedelta(days=30)  # 30 days before planting
    totals = []
    for y in range(1981, 2026):
        start = pd.Timestamp(year=y, month=md_start.month, day=md_start.day)
        w = daily[(daily["date"] >= start) & (daily["date"] <= start + pd.Timedelta(days=29))]
        totals.append(round(float(w["precip_mm"].sum()), 2))
    cutoff = sorted(totals)[8]  # k = 9 of 45
    assert t["dry_spring"]["05-12"]["value"] == pytest.approx(cutoff, abs=0.011)
    assert t["dry_spring"]["05-12"]["parameters"]["k"] == 9


def test_places_never_share_a_threshold_set_or_a_shared_year_set(client):
    a, b = compare(client, "iredell"), compare(client, "robeson")
    assert a["thresholds"]["threshold_set_id"] != b["thresholds"]["threshold_set_id"]
    assert a["result_id"] != b["result_id"]
    assert a["meta"]["snapshot_hash"] != b["meta"]["snapshot_hash"]
    # a repeat call after another place is still that place's own result
    assert compare(client, "iredell")["thresholds"] == a["thresholds"]


def test_results_differ_between_places_and_union_is_still_union(client):
    union, default = compare(client, "union"), compare(client)
    assert union["plans"][0]["spring"] == default["plans"][0]["spring"]
    assert union["meta"]["snapshot_hash"] == UNION_HASH == default["meta"]["snapshot_hash"]
    assert default["request_echo"]["location_id"] == "union_county_sample"
    assert default["weather_location"]["id"] == "union"
    assert compare(client, "pitt")["plans"][0]["spring"]["median_total_mm"] != \
        union["plans"][0]["spring"]["median_total_mm"]  # fmt: skip


def test_the_response_says_which_location_the_thresholds_come_from(client):
    for place in ("duplin", "iredell"):
        wl = compare(client, place)["weather_location"]
        name = get_index().by_id(place).name
        assert name in wl["thresholds_from"] and "never shared across locations" in wl["thresholds_from"]


# --- places with no weather ---------------------------------------------------------------------


def test_nc_cell_without_a_snapshot_is_unavailable_with_code_and_text(client):
    body = compare(client, location=RALEIGH)
    assert body["meta"]["snapshot_hash"] is None  # no snapshot was used
    wl = body["weather_location"]
    assert wl["status"] == "unavailable" and wl["code"] == "no_weather_snapshot"
    assert wl["reason_text"] and wl["snapshot_hash"] is None and wl["id"] is None
    for p in body["plans"]:
        assert p["status"] == "unavailable" and p["reason"].startswith("no_weather_snapshot")
        assert p["reason_text"] == wl["reason_text"] and p["spring"] is None and p["eras"] == {}
    assert body["data_sources"]["weather"]["freshness"] == "unavailable"
    assert body["shared_eligible_years"]["spring"] == []
    assert "unsupported_location" not in json.dumps(body["plans"])


def test_outside_nc_stays_unsupported_location(client):
    body = compare(client, location={"latitude": 40.7, "longitude": -74.0})
    assert body["weather_location"]["status"] == "unsupported"
    assert body["weather_location"]["code"] == "unsupported_location"
    assert all(p["status"] == "unsupported" and "unsupported_location" in p["reason"]
               for p in body["plans"])  # fmt: skip
    assert body["meta"]["snapshot_hash"] is None


@pytest.mark.parametrize("req", [
    ("get", "/v1/years?latitude=35.78&longitude=-78.64"),
    ("get", "/v1/seasons/2008/replay?latitude=35.78&longitude=-78.64"),
    ("post", "/v1/plans/sensitivity", {"plan_id": "corn_soy__rye", "location": RALEIGH}),
    ("post", "/v1/plans/calendar", {"plan_id": "corn_soy__rye", "year": 2025, "location": RALEIGH}),
    ("post", "/v1/plans/note", {"plan_id": "corn_soy__rye", "year": 2025, "location": RALEIGH}),
])  # fmt: skip
def test_every_endpoint_reports_no_weather_snapshot_the_same_way(client, req):
    method, url, *body = req
    r = client.get(url) if method == "get" else client.post(url, json=body[0])
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "unavailable" and j["code"] == "no_weather_snapshot"
    assert j["reason_text"] and j["meta"]["snapshot_hash"] is None
    assert j["weather_location"]["code"] == "no_weather_snapshot"


def test_outside_nc_on_other_endpoints_is_unsupported_location(client):
    j = client.get("/v1/years?latitude=40.7&longitude=-74.0").json()
    assert j["status"] == "unsupported" and j["code"] == "unsupported_location"


def test_unknown_location_id_and_conflicting_inputs_are_invalid_input(client):
    r = client.post("/v1/plans/compare", json={"plan_ids": ["corn_soy__rye"], "location_id": "nope"})
    assert r.status_code == 400 and r.json()["status"] == "invalid_input"
    assert r.json()["issues"][0]["code"] == "unknown_location"
    assert "pitt" in r.json()["issues"][0]["message"]
    r = client.post("/v1/plans/compare", json={
        "plan_ids": ["corn_soy__rye"], "location_id": "pitt", "location": RALEIGH})
    assert r.status_code == 400 and r.json()["issues"][0]["code"] == "location_conflict"
    r = client.get("/v1/years?location_id=nope")
    assert r.status_code == 400 and r.json()["issues"][0]["code"] == "unknown_location"
    r = client.post("/v1/plans/calendar", json={"plan_id": "corn_soy__rye", "location_id": "nope"})
    assert r.status_code == 400 and r.json()["status"] == "invalid_input"


# --- the other endpoints follow the place -----------------------------------------------------------


@pytest.mark.parametrize("place", ["iredell", "johnston", "robeson"])
def test_years_replay_and_sensitivity_use_the_places_snapshot(client, place):
    h = get_index().by_id(place).snapshot_hash
    y = client.get(f"/v1/years?location_id={place}").json()
    assert y["meta"]["snapshot_hash"] == h and y["weather_location"]["id"] == place
    assert y["location"]["id"] == place and y["shortcuts"]["dry"] != 0
    rp = client.get(f"/v1/seasons/2008/replay?location_id={place}").json()
    assert rp["meta"]["snapshot_hash"] == h and rp["thresholds"]["location_id"] == place
    se = client.post("/v1/plans/sensitivity", json={"plan_id": "corn_soy__rye",
                                                    "location_id": place}).json()  # fmt: skip
    assert se["meta"]["snapshot_hash"] == h and se["weather_location"]["id"] == place


def test_years_shortcuts_come_from_that_places_totals(client):
    union = client.get("/v1/years").json()["shortcuts"]
    pitt = client.get("/v1/years?location_id=pitt").json()["shortcuts"]
    assert union != pitt


def test_planner_report_and_field_note_routes_follow_the_place(client):
    h = get_index().by_id("pitt").snapshot_hash
    cal = client.post("/v1/plans/calendar", json={
        "plan_id": "corn_soy__rye", "year": 2025, "location_id": "pitt"})
    assert cal.status_code == 200 and cal.json()["meta"]["snapshot_hash"] == h
    note = client.post("/v1/plans/note", json={
        "plan_id": "corn_soy__rye", "alternative_id": "corn_soy__no_cover", "year": 2025,
        "as_of": "2025-09-01", "location_id": "pitt"})
    assert note.status_code == 200 and note.json()["meta"]["snapshot_hash"] == h
    get_note = client.get("/v1/plans/corn_soy__rye/note?alternative=corn_soy__no_cover"
                          "&year=2025&as_of=2025-09-01&location_id=pitt")
    assert get_note.json()["meta"]["snapshot_hash"] == h
    # the next request, with no place, is Union again (nothing leaks between requests)
    again = client.post("/v1/plans/calendar", json={"plan_id": "corn_soy__rye", "year": 2025})
    assert again.json()["meta"]["snapshot_hash"] == UNION_HASH


def test_no_place_never_leaks_into_the_following_request(client):
    client.get("/v1/years?location_id=robeson")
    assert client.get("/v1/years").json()["meta"]["snapshot_hash"] == UNION_HASH
    assert client.get("/health").json()["snapshot_hash"] == UNION_HASH


# --- region labels ------------------------------------------------------------------------------------


@pytest.mark.parametrize("place", COASTAL)
def test_sample_dates_are_labelled_assumed_for_the_piedmont_in_the_coastal_plain(client, place):
    body = compare(client, place, plan_ids=("corn_soy__rye", "corn_soy__wheat_dc"))
    for p in body["plans"]:
        assert p["dates_assumed"] is True and p["dates_assumed_for_region"] == "piedmont"
        assert "assumed for the Piedmont" in p["region_note"] and "Coastal Plain" in p["region_note"]
        assert p["plan"]["region"] == "NC Piedmont"  # kept as sent: the label does not change it
    assert body["weather_location"]["region"] == "coastal_plain"


@pytest.mark.parametrize("place", ["union", "iredell", "rowan"])
def test_no_region_label_in_the_piedmont(client, place):
    body = compare(client, place)
    assert all(p["dates_assumed_for_region"] is None and p["region_note"] is None
               for p in body["plans"])  # fmt: skip
    assert body["weather_location"]["region"] == "piedmont"


def test_an_edited_plan_with_the_samples_id_but_its_own_dates_gets_no_dates_label(client):
    plan = json.loads(Path("data/samples/union_plans.json").read_text())["samples"][2]["plan"]
    plan["winter"]["terminate"] = "04-25"
    r = client.post("/v1/plans/compare", json={"plans": [plan], "location_id": "pitt",
                                               "include_soil": False}).json()  # fmt: skip
    assert r["plans"][0]["dates_assumed_for_region"] is None


# --- health and contract ---------------------------------------------------------------------------------


def test_health_lists_every_available_location(client):
    h = client.get("/health").json()
    assert h["snapshot_hash"] == UNION_HASH and h["status"] == "complete"
    assert [x["id"] for x in h["locations"]] == PLACES
    for x in h["locations"]:
        e = get_index().by_id(x["id"])
        assert x["snapshot_hash"] == e.snapshot_hash and x["region"] == e.region
        assert x["point"] == {"latitude": e.latitude, "longitude": e.longitude}
        assert x["first_date"] == "1981-01-01" and x["last_date"] == "2025-06-30"
        assert set(x["grid_cell"]) == {"center_latitude", "center_longitude"}
    assert {x["region"] for x in h["locations"]} == {"piedmont", "coastal_plain"}


def test_a_location_id_alias_for_union_is_accepted(client):
    assert compare(client, "union_county_sample")["weather_location"]["id"] == "union"


# --- review r3 fixes ------------------------------------------------------------------------------------


def test_an_id_with_a_point_outside_nc_is_unsupported_not_evaluated(client):
    # (34.3, -79.6) is inside Robeson's grid cell but outside the NC outline
    body = compare(client, "robeson", location={"latitude": 34.3, "longitude": -79.6})
    assert body["weather_location"]["code"] == "unsupported_location"
    assert all(p["status"] == "unsupported" for p in body["plans"])
    assert body["meta"]["snapshot_hash"] is None


def test_error_responses_carry_the_resolved_snapshot_hash_or_null(client):
    pitt = get_index().by_id("pitt").snapshot_hash
    r = client.get("/v1/seasons/1980/replay?location_id=pitt")
    assert r.status_code == 400 and r.json()["snapshot_hash"] == pitt
    r = client.post("/v1/plans/sensitivity", json={"plan_id": "corn_soy__rye",
                                                   "rule_id": "nope", "location_id": "pitt"})  # fmt: skip
    assert r.status_code == 400 and r.json()["snapshot_hash"] == pitt
    r = client.post("/v1/plans/compare", json={"plan_ids": ["nope"], "location_id": "pitt"})
    assert r.status_code == 400 and r.json()["snapshot_hash"] == pitt
    # nothing resolved: nothing was used
    for r in (client.get("/v1/years?location_id=nope"),
              client.post("/v1/plans/compare", json={"plan_ids": ["corn_soy__rye"],
                                                     "location_id": "nope"}),
              client.post("/v1/plans/calendar", json={"plan_id": "corn_soy__rye",
                                                      "location_id": "nope"})):  # fmt: skip
        assert r.status_code == 400 and r.json()["snapshot_hash"] is None


@pytest.mark.parametrize("body", [
    {"plan_id": "corn_soy__rye", "year": 2025, "location": {"latitude": "bad", "longitude": "bad"}},
    {"plan_id": "corn_soy__rye", "year": 2025, "location": "pitt"},
    {"plan_id": "corn_soy__rye", "year": 2025, "location_id": 7},
    {"plan_id": "corn_soy__rye", "year": 2025, "location": {"latitude": 35.5}},
    {"plan_id": "corn_soy__rye", "year": 2025, "location": {"latitude": 135.5, "longitude": -77}},
])  # fmt: skip
def test_malformed_location_hints_are_invalid_input_not_the_union_default(client, body):
    r = client.post("/v1/plans/calendar", json=body)
    assert r.status_code == 400 and r.json()["status"] == "invalid_input", r.text
    assert r.json()["snapshot_hash"] is None


def test_malformed_query_location_is_invalid_input(client):
    r = client.post("/v1/plans/calendar?latitude=abc&longitude=1",
                    json={"plan_id": "corn_soy__rye", "year": 2025})  # fmt: skip
    assert r.status_code == 400


def test_verify_index_rejects_a_place_redirected_to_another_cells_directory(tmp_path):
    from fieldshift.weather.locations import INDEX_PATH, SNAPSHOT_ROOT, verify_index
    from fieldshift.weather.snapshot import SnapshotError

    for d in ("union_county", "iredell", "rowan", "johnston", "duplin", "pitt", "robeson"):
        (tmp_path / d).symlink_to(SNAPSHOT_ROOT / d)
    doc = json.loads(INDEX_PATH.read_text())
    (tmp_path / "index.json").write_text(json.dumps(doc))
    assert verify_index(tmp_path)["snapshots"] == 7  # the untouched copy verifies
    rows = {r["id"]: r for r in doc["locations"]}
    rows["rowan"]["snapshot_dir"] = "pitt"
    rows["rowan"]["snapshot_hash"] = rows["pitt"]["snapshot_hash"]
    (tmp_path / "index.json").write_text(json.dumps(doc))
    with pytest.raises(SnapshotError):
        verify_index(tmp_path)


def test_cell_edges_match_what_nasa_power_returned(client):
    """Expected cells written down from live POWER probes around Pitt's cell (identical values
    inside, different values outside), not from the derivation under test."""
    from fieldshift.weather.locations import cell_id_for

    pitt = "cell_+35.500_-77.500"
    inside = [(35.74, -77.37), (35.26, -77.5), (35.5, -77.78), (35.5, -77.2), (35.59, -77.37)]
    assert all(cell_id_for(la, lo) == pitt for la, lo in inside)
    assert cell_id_for(35.76, -77.37) == "cell_+36.000_-77.500"
    assert cell_id_for(35.24, -77.5) == "cell_+35.000_-77.500"
    assert cell_id_for(35.5, -77.82) == "cell_+35.500_-78.125"
    assert cell_id_for(35.5, -77.18) == "cell_+35.500_-76.875"


def test_overlapping_requests_for_different_places_keep_their_own_hashes(client):
    from concurrent.futures import ThreadPoolExecutor

    ids = ["union", "iredell", "pitt", "robeson", "johnston", "duplin"] * 2

    def go(pid):
        b = compare(client, pid, plan_ids=("corn_soy__rye",))
        y = client.get(f"/v1/years?location_id={pid}").json()
        return pid, b["meta"]["snapshot_hash"], y["meta"]["snapshot_hash"]

    with ThreadPoolExecutor(max_workers=6) as ex:
        out = list(ex.map(go, ids))
    for pid, h1, h2 in out:
        assert h1 == h2 == get_index().by_id(pid).snapshot_hash


# --- review r4 fixes -------------------------------------------------------------------------------------


def test_schema_validation_errors_carry_the_named_places_hash(client):
    pitt = get_index().by_id("pitt").snapshot_hash
    r = client.post("/v1/plans/compare", json={"plan_ids": "not-a-list", "location_id": "pitt"})
    assert r.status_code == 400 and r.json()["snapshot_hash"] == pitt
    r = client.post("/v1/plans/compare", json={"plan_ids": "x", "location_id": "nope"})
    assert r.status_code == 400 and r.json()["snapshot_hash"] is None
    r = client.post("/v1/plans/compare", json={"plan_ids": "x"})
    assert r.status_code == 400 and r.json()["snapshot_hash"] == UNION_HASH  # no place named


def test_an_empty_location_object_is_invalid_input(client):
    r = client.post("/v1/plans/calendar", json={"plan_id": "corn_soy__rye", "year": 2025,
                                                "location": {}})  # fmt: skip
    assert r.status_code == 400 and r.json()["snapshot_hash"] is None
