import json
import shutil

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fieldshift.field import routes as field_routes
from fieldshift.field.evidence import EvidenceBundle, GrowerObservation, SoilTest
from fieldshift.field.location import approximate_region, in_nc_bounds, resolve_location
from fieldshift.field.routes import router
from fieldshift.field.soil import unavailable
from fieldshift.weather.power_client import RawFetch
from fieldshift.weather.snapshot import DEFAULT_SNAPSHOT_DIR

UNION = (34.98, -80.55)
RAW = DEFAULT_SNAPSHOT_DIR / "raw"


def no_network(*a, **k):
    raise AssertionError("network must not be used")


# ------------------------------------------------------------------ resolve


def test_union_sample_resolves_offline_from_the_snapshot(tmp_path):
    r = resolve_location(*UNION, cache_dir=tmp_path, fetch=no_network, offline=True)
    assert r.status == "complete"
    assert (
        r.weather.supported and r.weather.source == "snapshot" and r.weather.freshness == "snapshot"
    )
    assert r.weather.snapshot_hash and r.weather.first_date == "1981-01-01"
    assert r.guidance.supported and r.guidance.region == "piedmont"
    assert r.grid_cell["center_latitude"] == 35.0 and r.cell_id == "cell_+35.000_-80.625"


def test_point_outside_nc_is_unsupported_location():
    for lat, lon in ((40.7, -74.0), (33.0, -80.0), (35.0, -90.0)):
        r = resolve_location(lat, lon)
        assert r.status == "unsupported" and r.code == "unsupported_location" and not r.bounds.in_nc
        assert r.weather is None
    assert in_nc_bounds(35.78, -78.64)


@pytest.mark.parametrize(
    "lat,lon", [(None, -80), ("x", 1), (95, -80), (35, 200), (float("nan"), -80), (True, -80)]
)
def test_bad_coordinates_are_invalid_input(lat, lon):
    r = resolve_location(lat, lon)
    assert r.status == "invalid_input" and r.code is None


def test_other_cell_without_cache_is_weather_unsupported_but_guidance_can_be_known(tmp_path):
    r = resolve_location(35.8, -82.6, cache_dir=tmp_path, fetch=no_network)  # western NC
    assert r.status == "partial"
    assert not r.weather.supported and r.weather.status == "unavailable"
    assert "fetch_history" in r.weather.reason
    assert (
        r.guidance.supported
        and r.guidance.region == "mountains"
        and r.guidance.basis == "approximate"
    )
    assert r.guidance.status == "partial"  # inferred, not confirmed


def test_fetch_history_goes_through_phase_1_pipeline_at_the_cell_centre_then_caches(tmp_path):
    calls = []
    raw_bytes = (
        (RAW / "power_daily_response.json").read_bytes()
        if (RAW / "power_daily_response.json").exists()
        else None
    )
    if raw_bytes is None:  # use whatever the snapshot's raw file is called
        raw_bytes = next(
            p for p in RAW.iterdir() if p.suffix == ".json" and "fetch" not in p.name
        ).read_bytes()

    def fake_fetch(lat, lon, start, end):
        calls.append((lat, lon, start, end))
        return RawFetch(body=raw_bytes, url="https://example.test", params={}, status_code=200,
                        retrieved_at="2026-11-12T00:00:00Z", elapsed_s=0.0)  # fmt: skip

    field_point = (35.4321, -79.1234)
    r = resolve_location(
        *field_point, cache_dir=tmp_path, fetch=fake_fetch, fetch_history=True, offline=False
    )
    assert r.weather.supported and r.weather.source == "fetched" and r.weather.freshness == "fresh"
    ((lat, lon, start, end),) = calls
    assert (lat, lon) != field_point  # the exact field point is never sent to POWER
    assert (lat, lon) == (r.grid_cell["center_latitude"], r.grid_cell["center_longitude"])
    assert start == "1981-01-01"
    again = resolve_location(*field_point, cache_dir=tmp_path, fetch=no_network, offline=False)
    assert again.weather.source == "cache" and again.weather.freshness.startswith("cached(")
    # a second point in the same cell reuses the cached history
    same_cell = resolve_location(35.40, -79.20, cache_dir=tmp_path, fetch=no_network, offline=False)
    assert same_cell.cell_id == r.cell_id and same_cell.weather.source == "cache"


def test_fetch_failure_and_offline_leave_weather_unavailable(tmp_path):
    def boom(*a, **k):
        raise RuntimeError("POWER down")

    r = resolve_location(
        35.4, -79.2, cache_dir=tmp_path, fetch=boom, fetch_history=True, offline=False
    )
    assert not r.weather.supported and "POWER down" in r.weather.reason
    off = resolve_location(
        35.4, -79.2, cache_dir=tmp_path, fetch=no_network, fetch_history=True, offline=True
    )
    assert not off.weather.supported and "offline" in off.weather.reason


def test_corrupt_cache_is_ignored_not_trusted(tmp_path):
    d = tmp_path / "cell_+35.500_-79.375"
    d.mkdir()
    (d / "manifest.json").write_text("{}")
    r = resolve_location(35.4, -79.2, cache_dir=tmp_path, fetch=no_network, offline=True)
    assert not r.weather.supported


def test_region_handling(tmp_path):
    kw = dict(cache_dir=tmp_path, fetch=no_network, offline=True)
    assert resolve_location(35.8, -82.6, region="NC Piedmont", **kw).guidance.region == "piedmont"
    assert resolve_location(35.8, -82.6, region="NC Piedmont", **kw).guidance.basis == "provided"
    bad = resolve_location(35.8, -82.6, region="Iowa", **kw)
    assert not bad.guidance.supported and bad.guidance.status == "unknown"
    assert (
        resolve_location(35.8, -82.6, region="North Carolina", **kw).guidance.basis == "approximate"
    )
    boundary = resolve_location(35.8, -78.65, **kw)  # right on the Fall Line
    assert boundary.guidance.status == "unknown" and boundary.guidance.region is None


@pytest.mark.parametrize(
    "lat,lon,tag",
    [(35.2, -81.0, "piedmont"), (35.5, -82.6, "mountains"), (35.0, -77.5, "coastal_plain"),
     (35.8, -78.65, None), (35.6, -81.6, None)],
)  # fmt: skip
def test_approximate_region(lat, lon, tag):
    assert approximate_region(lat, lon) == tag


# ------------------------------------------------------------------ evidence


def test_evidence_keeps_date_zone_and_derivation_and_prefers_the_latest():
    b = EvidenceBundle(
        soil_tests=[
            SoilTest(observed_on="2024-03-01", zone_id="north", soil_ph=5.4),
            SoilTest(observed_on="2025-03-01", zone_id="north", soil_ph=5.9),
            SoilTest(observed_on="2025-04-01", zone_id="south", soil_ph=0.0),
        ],
        observations=[GrowerObservation(kind="soil_temp_f", value=48.0, observed_on="2025-04-02")],
    )
    latest = b.latest_inputs(zone_id="north")
    assert latest["soil_ph"]["value"] == 5.9 and latest["soil_ph"]["zone_id"] == "north"
    assert latest["soil_ph"]["derivation"] == "grower"
    assert b.as_rule_inputs(zone_id="south")["soil_ph"] == 0.0  # a real zero stays zero
    assert b.as_rule_inputs()["soil_temp_f"] == 48.0
    assert b.as_rule_inputs(zone_id="north")["soil_temp_f"] == 48.0  # zone-less applies everywhere


def test_evidence_requires_a_date_and_finite_numbers():
    with pytest.raises(ValueError):
        SoilTest(soil_ph=6.0)  # no observed_on
    with pytest.raises(ValueError):
        SoilTest(observed_on="2025-01-01", soil_ph=float("nan"))
    with pytest.raises(ValueError):
        GrowerObservation(observed_on="2025-01-01", kind="ponding", surprise=1)


# ------------------------------------------------------------------ review fixes (phase-8-B)


@pytest.mark.parametrize(
    "lat,lon,inside",
    [(35.23, -80.84, True), (35.60, -82.55, True), (35.78, -78.64, True), (34.23, -77.94, True),
     (36.20, -81.67, True), (34.98, -80.55, True), (35.07, -77.04, True),
     (35.89, -82.83, True), (35.09, -84.03, True), (35.43, -83.45, True), (35.49, -82.99, True),
     (36.31, -82.35, False), (35.71, -83.51, False),
     (34.00, -81.03, False), (32.78, -79.93, False), (34.85, -82.40, False), (35.96, -83.92, False),
     (36.85, -75.98, False), (37.54, -77.44, False), (33.50, -79.00, False), (34.70, -84.00, False)],
)  # fmt: skip
def test_neighbouring_state_cities_are_outside_nc(lat, lon, inside):
    assert in_nc_bounds(lat, lon) is inside
    r = resolve_location(lat, lon)
    assert (r.status != "unsupported") is inside
    if not inside:
        assert r.code == "unsupported_location"


def test_explicit_unmapped_region_text_is_unknown_guidance(tmp_path):
    kw = dict(cache_dir=tmp_path, fetch=no_network, offline=True)
    for text in ("Atlantis NC", "Wake County NC", "somewhere"):
        g = resolve_location(35.8, -82.6, region=text, **kw).guidance
        assert (g.supported, g.status, g.region) == (False, "unknown", None), text
    assert resolve_location(35.8, -82.6, region="NC", **kw).guidance.region == "mountains"
    assert resolve_location(35.8, -82.6, region="VA Piedmont", **kw).guidance.supported is False


# ------------------------------------------------------------------ routes


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_resolve_route(client):
    ok = client.post("/v1/locations/resolve", json={"lat": UNION[0], "lon": UNION[1]})
    assert ok.status_code == 200
    j = ok.json()
    assert set(j["meta"]) == {"plan_version", "catalog_version", "snapshot_hash", "request_id"}
    assert j["location"]["weather"]["source"] == "snapshot"
    out = client.post("/v1/locations/resolve", json={"lat": 40.7, "lon": -74.0})
    assert out.status_code == 200 and out.json()["location"]["code"] == "unsupported_location"


@pytest.mark.parametrize(
    "payload,field",
    [({"lat": "x", "lon": 1}, "lat"), ({"lat": 35, "lon": None}, "lon"), ({"lat": 95, "lon": 0}, "lat"),
     ({"lat": 35, "lon": -80, "region": 5}, "region"),
     ({"lat": 35, "lon": -80, "region": {"a": 1}}, "region"),
     ({"lat": 35, "lon": -80, "fetch_history": "false"}, "fetch_history"),
     ({"lat": True, "lon": -80}, "lat"), ({"lat": 10**400, "lon": -80}, "lat")],
)  # fmt: skip
def test_resolve_route_validates_types(client, payload, field):
    r = client.post("/v1/locations/resolve", json=payload)
    assert r.status_code == 400 and r.json()["issues"][0]["field"] == field
    assert "request_id" in r.json()


def test_resolve_route_malformed_json(client):
    r = client.post(
        "/v1/locations/resolve", content=b"{oops", headers={"content-type": "application/json"}
    )
    assert r.status_code == 400 and r.json()["issues"][0]["code"] == "invalid_json"


def test_soil_route_survives_an_sda_failure(client, monkeypatch):
    monkeypatch.setattr(field_routes, "get_soil", lambda lat, lon: unavailable("SDA timed out"))
    r = client.get("/v1/soil", params={"lat": UNION[0], "lon": UNION[1]})
    assert r.status_code == 200
    assert r.json()["soil"]["status"] == "unavailable" and "timed out" in r.json()["soil"]["reason"]
    out = client.get("/v1/soil", params={"lat": 40.7, "lon": -74.0})
    assert out.json()["status"] == "unsupported" and out.json()["code"] == "unsupported_location"
    bad = client.get("/v1/soil", params={"lat": "abc", "lon": "1"})
    assert bad.status_code == 400 and bad.json()["issues"][0]["field"] == "lat"


def test_soil_route_follows_offline_mode_without_touching_the_network(
    client, monkeypatch, tmp_path
):
    from fieldshift.field import soil as soil_mod

    monkeypatch.setenv("FIELDSHIFT_OFFLINE", "1")
    monkeypatch.setattr(soil_mod, "DEFAULT_CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        soil_mod.httpx, "Client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network"))
    )
    real = soil_mod.get_soil
    monkeypatch.setattr(
        field_routes, "get_soil", lambda lat, lon: real(lat, lon, cache_dir=tmp_path)
    )
    r = client.get("/v1/soil", params={"lat": UNION[0], "lon": UNION[1]})
    assert r.status_code == 200 and r.json()["soil"]["status"] == "unavailable"
    assert "offline" in r.json()["soil"]["reason"]


def test_malformed_weather_cache_manifest_is_unavailable_not_a_500(tmp_path):
    cid = "cell_+35.500_-79.375"
    d = tmp_path / cid
    d.mkdir()
    # a valid parquet next to a manifest that parses but lacks required keys
    snap_dir = DEFAULT_SNAPSHOT_DIR
    shutil.copy(snap_dir / "daily.parquet", d / "daily.parquet")
    good = json.loads((snap_dir / "manifest.json").read_text())
    for broken in ({}, {**good, "coverage": {}}, {**good, "retrieval": "oops"}):
        (d / "manifest.json").write_text(json.dumps(broken))
        r = resolve_location(35.4, -79.2, cache_dir=tmp_path, fetch=no_network, offline=True)
        assert r.status in ("partial", "complete") and r.weather is not None


def test_evidence_units_are_converted_or_rejected():
    b = EvidenceBundle(
        observations=[
            GrowerObservation(kind="soil_temp_f", value=10.0, unit="C", observed_on="2025-04-01"),
            GrowerObservation(
                kind="water_table_depth_in", value=91.44, unit="cm", observed_on="2025-04-01"
            ),
        ]
    )
    got = b.as_rule_inputs()
    assert got["soil_temp_f"] == pytest.approx(50.0) and got[
        "water_table_depth_in"
    ] == pytest.approx(36.0)
    with pytest.raises(ValueError, match="not supported"):
        GrowerObservation(
            kind="water_table_depth_in", value=10, unit="furlongs", observed_on="2025-04-01"
        )
    with pytest.raises(ValueError, match="not supported"):
        GrowerObservation(kind="soil_temp_f", value=50, unit="cm", observed_on="2025-04-01")
    plain = EvidenceBundle(
        observations=[GrowerObservation(kind="soil_temp_f", value=50, observed_on="2025-04-01")]
    )
    assert plain.as_rule_inputs()["soil_temp_f"] == 50  # no unit = the input's own unit


def test_missing_query_parameters_are_typed_400s_with_metadata():
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    for path in ("/v1/soil", "/v1/live"):
        r = c.get(path)
        assert r.status_code == 400 and r.json()["status"] == "invalid_input"
        assert {i["field"] for i in r.json()["issues"]} == {
            "lat",
            "lon",
        } and "request_id" in r.json()
        only = c.get(path, params={"lat": "35"})
        assert [i["field"] for i in only.json()["issues"]] == ["lon"]
