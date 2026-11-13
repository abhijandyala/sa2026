import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fieldshift.contracts import Plan, WinterManagement
from fieldshift.field import live as live_mod
from fieldshift.field import routes as field_routes
from fieldshift.field.live import LiveCache
from fieldshift.field.routes import router as field_router
from fieldshift.planner.routes import router as planner_router
from fieldshift.tools.routes import router as tools_router

META = {"plan_version", "catalog_version", "snapshot_hash", "request_id"}


@pytest.fixture
def client():
    app = FastAPI()
    for r in (field_router, planner_router, tools_router):
        app.include_router(r)
    return TestClient(app)


def post(client, path, **json):
    return client.post(path, json=json)


# ------------------------------------------------------------------ fertilizer


def test_fertilizer_route_120_lb_n_urea(client):
    r = post(
        client,
        "/v1/fertilizer/calc",
        targets={"n_lb_per_acre": 120},
        product={"fertilizer_id": "urea_46_0_0"},
        area_acres=40,
    )
    assert r.status_code == 200 and set(r.json()["meta"]) == META
    res = r.json()["result"]
    assert res["product_lb_per_acre"] == 260.9 and res["total_product_lb"] == pytest.approx(
        10434.8, abs=0.1
    )


def test_fertilizer_route_p_target_with_urea_is_a_400_naming_the_field(client):
    r = post(
        client,
        "/v1/fertilizer/calc",
        targets={"p2o5_lb_per_acre": 60},
        product={"fertilizer_id": "urea_46_0_0"},
    )
    assert r.status_code == 400
    i = r.json()["issues"][0]
    assert i["code"] == "product_supplies_none" and i["field"] == "targets.p2o5_lb_per_acre"
    assert "product supplies no P2O5" in i["message"] and "request_id" in r.json()


@pytest.mark.parametrize(
    "payload,field",
    [({"targets": [1], "product": {"grade": "46-0-0"}}, "targets"),
     ({"targets": {"n_lb_per_acre": 1}, "product": "urea"}, "product"),
     ({"targets": {"n_lb_per_acre": 1}, "product": {"grade": "46-0-0"}, "basis": 3}, "basis"),
     ({"targets": {}, "product": {"grade": "46-0-0"}}, "targets"),
     ({"targets": {"n_lb_per_acre": -4}, "product": {"grade": "46-0-0"}}, "targets.n_lb_per_acre"),
     ({"targets": {"n_lb_per_acre": 1}, "product": {"grade": "46-0-0"}, "area_acres": "big"}, "area_acres"),
     ({"targets": {"n_lb_per_acre": 1}, "product": {"grade": 46}}, "product")],
)  # fmt: skip
def test_fertilizer_route_validation(client, payload, field):
    r = client.post("/v1/fertilizer/calc", json=payload)
    assert r.status_code == 400 and r.json()["issues"][0]["field"] == field


def test_fertilizer_route_malformed_json(client):
    r = client.post(
        "/v1/fertilizer/calc", content=b"[", headers={"content-type": "application/json"}
    )
    assert r.status_code == 400 and r.json()["issues"][0]["code"] == "invalid_json"


def test_fertilizer_route_never_invents_n(client):
    r = post(
        client,
        "/v1/fertilizer/calc",
        targets={},
        product={"fertilizer_id": "urea_46_0_0"},
        crop_id="field_corn",
    )
    assert r.status_code == 400 and r.json()["issues"][0]["code"] == "no_target"


# ------------------------------------------------------------------ irrigation


def test_irrigation_route_lists_missing_inputs_as_200(client):
    r = post(client, "/v1/irrigation/check", crop_id="soybean", stage="R1-R5")
    assert r.status_code == 200
    res = r.json()["result"]
    assert res["status"] == "insufficient_data" and len(res["missing"]) >= 3
    assert res["water_balance"] is None and any(
        c["rule_id"] == "sb_wd_06" for c in res["stage_checks"]
    )


def test_irrigation_route_full_balance_and_validation(client):
    body = {"crop_id": "field_corn", "stage": "pollination", "awc_in": 4, "start_storage_in": 3,
            "weather": [{"date": "2025-07-01", "precip_mm": 0}], "irrigation": []}  # fmt: skip
    ok = client.post("/v1/irrigation/check", json=body)
    assert (
        ok.json()["result"]["status"] == "complete"
        and ok.json()["result"]["water_balance"]["end_storage_in"] == 2.75
    )
    bad = client.post("/v1/irrigation/check", json={**body, "awc_in": 0})
    assert bad.status_code == 400 and bad.json()["issues"][0]["field"] == "awc_in"
    assert client.post("/v1/irrigation/check", json={}).json()["issues"][0]["field"] == "crop_id"
    assert (
        client.post("/v1/irrigation/check", json={"crop_id": "soybean", "stage": 5}).status_code
        == 400
    )
    assert (
        client.post("/v1/irrigation/check", json={"crop_id": "quinoa"}).json()["result"]["status"]
        == "unsupported"
    )


# ------------------------------------------------------------------ zones and live


def test_zones_routes(client):
    z = client.get("/v1/zones").json()
    assert len(z["zones"]["zones"]) == 4 and set(z["meta"]) == META
    r = post(
        client,
        "/v1/zones/analyze",
        ponding=[{"zone_id": "zone_ne", "reported_on": "2025-03-10"}],
        heavy_rain_days=["2025-03-09"],
    )
    assert r.status_code == 200 and r.json()["result"]["prompts"][0]["kind"] == "inspect"
    bad = post(
        client, "/v1/zones/analyze", changes=[{"kind": "flood", "reported_on": "2025-01-01"}]
    )
    assert bad.status_code == 400 and bad.json()["status"] == "invalid_input"
    assert post(client, "/v1/zones/analyze", ponding="x").status_code == 400


def test_live_route_when_nws_is_down_history_is_unchanged(client, monkeypatch):
    def handler(request):
        raise httpx.ConnectError("down")

    down = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(
        field_routes,
        "get_live",
        lambda lat, lon: live_mod.get_live(lat, lon, client=down, cache=LiveCache(), offline=False),
    )
    plan = Plan(plan_id="p", previous_crop_id="field_corn", prev_harvest="09-20",
                winter=WinterManagement(kind="cover", crop_id="cereal_rye", seed="10-05", terminate="04-28"),
                next_crop_id="soybean", next_plant="05-12", region="NC Piedmont")  # fmt: skip
    body = {"plan": plan.model_dump(mode="json"), "year": 2025}
    before = client.post("/v1/plans/check", json=body).json()["result"]
    r = client.get("/v1/live", params={"lat": 34.98, "lon": -80.55})
    assert r.status_code == 200 and r.json()["live"]["status"] == "unavailable"
    assert r.json()["live"]["forecast"]["freshness"] == "unavailable"
    after = client.post("/v1/plans/check", json=body).json()["result"]
    assert before == after  # live data never feeds the historical checks


def test_live_route_validation_and_unsupported(client):
    assert client.get("/v1/live", params={"lat": "abc", "lon": 1}).status_code == 400
    out = client.get("/v1/live", params={"lat": 40.7, "lon": -74.0}).json()
    assert out["status"] == "unsupported" and out["code"] == "unsupported_location"


@pytest.mark.parametrize("bad", [False, 0, "", "x", {"a": 1}])
def test_zones_analyze_rejects_non_list_reports(client, bad):
    for key in ("ponding", "changes", "heavy_rain_days"):
        r = client.post("/v1/zones/analyze", json={key: bad})
        assert r.status_code == 400, (key, bad)
    assert client.post("/v1/zones/analyze", json={"ponding": None}).status_code == 200


def test_fertilizer_route_overflow_is_400(client):
    r = client.post(
        "/v1/fertilizer/calc",
        content=b'{"targets":{"n_lb_per_acre":1e400},"product":{"grade":"46-0-0"}}',
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400
    big = '{"targets":{"n_lb_per_acre":' + "9" * 400 + '},"product":{"grade":"46-0-0"}}'
    r = client.post(
        "/v1/fertilizer/calc", content=big.encode(), headers={"content-type": "application/json"}
    )
    assert r.status_code == 400 and r.json()["issues"][0]["field"] == "targets.n_lb_per_acre"


def test_zones_analyze_rejects_unknown_change_zone(client):
    r = client.post(
        "/v1/zones/analyze",
        json={"changes": [{"kind": "regrading", "reported_on": "2030-01-01", "zone_id": "nope"}]},
    )
    assert r.status_code == 400 and r.json()["issues"][0]["field"] == "changes.0.zone_id"


def test_fertilizer_route_no_target_400_still_carries_the_n_reference(client):
    r = post(
        client,
        "/v1/fertilizer/calc",
        targets={},
        product={"fertilizer_id": "urea_46_0_0"},
        crop_id="field_corn",
    )
    assert r.status_code == 400
    ref = r.json()["n_reference"]
    assert (ref["value_min"], ref["value_max"], ref["is_grower_target"]) == (120.0, 160.0, False)
    ok = post(
        client,
        "/v1/fertilizer/calc",
        targets={"n_lb_per_acre": 100},
        product={"fertilizer_id": "urea_46_0_0"},
        crop_id="field_corn",
    )
    assert ok.json()["result"]["target_vs_reference"]["position"] == "below"
