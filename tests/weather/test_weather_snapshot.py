"""Phase 1 snapshot tests. The Union County snapshot is real data; everything else is a fixture."""

import json
import socket

import pytest

from fieldshift.weather.coverage import coverage_report
from fieldshift.weather.normalize import normalize_power_response
from fieldshift.weather.power_client import RawFetch
from fieldshift.weather.snapshot import (
    DEFAULT_SNAPSHOT_DIR,
    SnapshotError,
    daily_to_parquet_bytes,
    load_snapshot,
    verify_snapshot,
    write_snapshot,
)
from fieldshift.weather.sources import derive_grid_cell


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket.socket, "connect", refuse)


def _fixture_fetch() -> RawFetch:
    dates = ["20240101", "20240102", "20240103", "20240105"]  # 20240104 is a gap
    precip = {"20240101": 0.0, "20240102": -999.0, "20240103": 4.2, "20240105": 1.1}
    block = {
        "PRECTOTCORR": precip,
        "T2M_MAX": {d: 12.0 for d in dates}, "T2M_MIN": {d: -2.0 for d in dates},
        "T2M": {d: 5.0 for d in dates}, "GWETTOP": {d: 0.4 for d in dates},
        "GWETROOT": {d: 0.5 for d in dates},
    }
    payload = {
        "geometry": {"coordinates": [-80.55, 34.98, 100.0]},
        "header": {"fill_value": -999.0, "time_standard": "LST", "api": {"version": "fixture"},
                   "sources": ["FIXTURE"], "title": "FIXTURE"},
        "parameters": {"PRECTOTCORR": {"units": "mm/day"}},
        "properties": {"parameter": block},
    }
    return RawFetch(body=json.dumps(payload).encode(), url="https://example.invalid/fixture",
                    params={"fixture": "1"}, status_code=200,
                    retrieved_at="2024-02-01T00:00:00Z", elapsed_s=0.0)


def test_fixture_snapshot_round_trip_and_verify(tmp_path):
    manifest = write_snapshot(_fixture_fetch(), tmp_path, start="2024-01-01", end="2024-01-05")
    assert manifest["coverage"]["n_days"] == 5
    assert manifest["coverage"]["missing_dates"]["precip_mm"] == ["2024-01-02", "2024-01-04"]
    assert verify_snapshot(tmp_path)["ok"] is True
    snap = load_snapshot(tmp_path)
    assert snap.daily["precip_mm"].tolist()[0] == 0.0  # real zero survives parquet round-trip
    assert snap.snapshot_hash == manifest["hashes"]["snapshot_hash"]


def test_tampered_raw_is_detected(tmp_path):
    write_snapshot(_fixture_fetch(), tmp_path, start="2024-01-01", end="2024-01-05")
    raw = tmp_path / "raw" / "power_daily.json"
    raw.write_bytes(raw.read_bytes() + b" ")
    with pytest.raises(SnapshotError, match="raw response hash"):
        verify_snapshot(tmp_path)


def test_missing_snapshot_raises(tmp_path):
    with pytest.raises(SnapshotError):
        load_snapshot(tmp_path / "nope")


# --- committed Union County snapshot -------------------------------------------------------


def test_committed_snapshot_loads_with_network_blocked(no_network):
    snap = load_snapshot()
    assert snap.manifest["hashes"]["snapshot_hash"] == snap.snapshot_hash
    assert len(snap.daily) == 16252


def test_committed_snapshot_reproduces_from_raw_byte_for_byte(tmp_path):
    manifest = json.loads((DEFAULT_SNAPSHOT_DIR / "manifest.json").read_text())
    raw = (DEFAULT_SNAPSHOT_DIR / "raw" / "power_daily.json").read_bytes()
    cov = manifest["coverage"]
    daily = normalize_power_response(raw, start=cov["requested_start"], end=cov["requested_end"]).daily
    assert verify_snapshot(DEFAULT_SNAPSHOT_DIR)["ok"]
    if manifest["environment"]["pyarrow_version"] == __import__("pyarrow").__version__:
        assert daily_to_parquet_bytes(daily) == (DEFAULT_SNAPSHOT_DIR / "daily.parquet").read_bytes()


def test_committed_snapshot_start_is_documented():
    snap = load_snapshot()
    report = coverage_report(snap.daily)
    assert report["first_date"] == "1981-01-01"  # POWER's earliest date
    assert report["last_date"] == "2025-06-30"
    assert report["per_variable"]["precip_mm"]["first_valid"] == "1981-01-01"
    assert any("1981-01-01" in n and "incomplete" in n for n in snap.manifest["notes"])
    assert snap.manifest["source"]["fill_value"] == -999.0
    assert snap.manifest["source"]["time_standard"] == "LST"
    assert snap.manifest["source"]["api"]["version"].startswith("v")


def test_committed_snapshot_has_real_zero_rain_days_and_no_negatives():
    daily = load_snapshot().daily
    assert (daily["precip_mm"] == 0.0).sum() > 100
    assert (daily["precip_mm"].dropna() >= 0).all()
    assert daily["gwettop"].between(0, 1).all()


def test_grid_cell_is_derived_not_api_stated():
    cell = derive_grid_cell(34.98, -80.55)
    assert cell["center_latitude"] == 35.0 and cell["center_longitude"] == -80.625
    assert "derived" in cell["basis"]


def test_time_standard_is_documented_as_local_solar_time():
    snap = load_snapshot()
    assert snap.manifest["source"]["time_standard"] == "LST"
    assert "Local Solar Time" in snap.manifest["source"]["daily_boundary"]


def test_health_endpoint_reads_only_the_snapshot(no_network, monkeypatch):
    from fastapi.testclient import TestClient

    from fieldshift.api.app import create_app
    from fieldshift.weather.power_client import OFFLINE_ENV

    monkeypatch.setenv(OFFLINE_ENV, "1")
    body = TestClient(create_app()).get("/health").json()
    assert body["offline"] is True and body["weather"]["first_date"] == "1981-01-01"
    assert body["snapshot_hash"] == load_snapshot().snapshot_hash
