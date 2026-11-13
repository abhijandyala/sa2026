import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from fieldshift.field import soil as soil_mod
from fieldshift.field.soil import awc_to_depth, get_soil, parse_sda_table

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sda" / "union_county_response.json"
NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)


@pytest.fixture
def table():
    return json.loads(FIXTURE.read_text())["Table"]


def client_returning(payload, status=200, calls=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(json.loads(request.content))
        return httpx.Response(status, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def failing_client(exc):
    def handler(request):
        raise exc

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parse_dominant_component_texture_drainage_and_survey(table):
    r = parse_sda_table(table)
    assert r.status == "complete"
    assert r.mukey == "2440251" and r.survey_area == "NC179"
    assert r.survey_version == "9/3/2026 1:43:46 PM"
    d = r.dominant_component
    assert (d.name, d.percent, d.drainage_class, d.hydrologic_group) == (
        "Tarrus", 60.0, "Well drained", "B",
    )  # fmt: skip
    assert r.surface_texture == "Gravelly silt loam"
    assert [c.name for c in r.other_components] == ["Urban land"]
    assert [h.name for h in r.horizons] == ["Ap", "Bt", "Cr"]


def test_awc_by_depth_has_units_and_keeps_a_published_zero(table):
    r = parse_sda_table(table)
    ap, bt, cr = r.horizons
    assert ap.awc_in == pytest.approx(0.14 * 18 / 2.54, abs=1e-3)
    assert cr.awc_cm_per_cm == 0 and cr.awc_in == 0  # bedrock: a real zero, not missing
    assert r.awc.depth_in == 24 and r.awc.status == "complete"
    assert r.awc.value_in == pytest.approx((0.14 * 18 + 0.10 * (24 * 2.54 - 18)) / 2.54, abs=1e-3)


def test_missing_awc_makes_the_total_partial_not_zero():
    from fieldshift.field.soil import SoilHorizon

    hz = [
        SoilHorizon(name="A", top_cm=0, bottom_cm=30, texture=None, texture_code=None,
                    awc_cm_per_cm=0.12, awc_in=1.4),
        SoilHorizon(name="B", top_cm=30, bottom_cm=100, texture=None, texture_code=None,
                    awc_cm_per_cm=None, awc_in=None),
    ]  # fmt: skip
    s = awc_to_depth(hz)
    assert s.status == "partial" and s.value_in == pytest.approx(0.12 * 30 / 2.54, abs=1e-3)
    assert awc_to_depth([hz[1]]).status == "unavailable" and awc_to_depth([hz[1]]).value_in is None


def test_empty_table_is_unavailable():
    assert parse_sda_table([["mukey"]]).status == "unavailable"
    assert parse_sda_table([]).status == "unavailable"


def test_fetch_success_builds_query_and_provenance(table, tmp_path):
    calls = []
    r = get_soil(
        34.98, -80.55, client=client_returning({"Table": table}, calls=calls),
        cache_dir=tmp_path, now=NOW,
    )  # fmt: skip
    assert r.status == "complete" and r.provenance.freshness == "fresh"
    assert (
        r.provenance.fetched_at == "2026-11-12T12:00:00Z" and len(r.provenance.query_sha256) == 64
    )
    assert "point (-80.550000 34.980000)" in calls[0]["query"]  # SDA wants "lon lat"
    assert calls[0]["format"] == "JSON+COLUMNNAME"


def test_timeout_is_unavailable_with_a_reason(tmp_path):
    r = get_soil(
        34.98, -80.55, client=failing_client(httpx.ReadTimeout("slow")), cache_dir=tmp_path, now=NOW
    )
    assert r.status == "unavailable" and "ReadTimeout" in r.reason and r.provenance is None


def test_http_error_and_bad_body_are_unavailable(tmp_path):
    assert (
        get_soil(
            34.98, -80.55, client=client_returning({}, status=500), cache_dir=tmp_path, now=NOW
        ).status
        == "unavailable"
    )
    bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<xml/>")))
    r = get_soil(34.98, -80.55, client=bad, cache_dir=tmp_path, now=NOW)
    assert r.status == "unavailable"


def test_empty_sda_body_means_no_survey_data(tmp_path):
    r = get_soil(34.98, -80.55, client=client_returning({}), cache_dir=tmp_path, now=NOW)
    assert r.status == "unavailable" and "no soil survey data" in r.reason


def test_cache_is_used_for_30_days_then_refreshed(table, tmp_path):
    calls = []
    get_soil(
        34.98,
        -80.55,
        client=client_returning({"Table": table}, calls=calls),
        cache_dir=tmp_path,
        now=NOW,
    )
    inside = get_soil(
        34.98, -80.55, client=failing_client(httpx.ConnectError("down")), cache_dir=tmp_path,
        now=NOW + timedelta(days=29),
    )  # fmt: skip
    assert inside.status == "complete" and inside.provenance.freshness.startswith("cached(")
    assert len(calls) == 1
    expired = get_soil(
        34.98, -80.55, client=client_returning({"Table": table}, calls=calls), cache_dir=tmp_path,
        now=NOW + timedelta(days=31),
    )  # fmt: skip
    assert expired.provenance.freshness == "fresh" and len(calls) == 2


def test_failed_refresh_falls_back_to_a_stale_cached_copy(table, tmp_path):
    get_soil(34.98, -80.55, client=client_returning({"Table": table}), cache_dir=tmp_path, now=NOW)
    r = get_soil(
        34.98, -80.55, client=failing_client(httpx.ReadTimeout("slow")), cache_dir=tmp_path,
        now=NOW + timedelta(days=60),
    )  # fmt: skip
    assert r.status == "complete" and r.provenance.stale and "stale" in r.provenance.freshness
    assert any("ReadTimeout" in n for n in r.notes)


def test_offline_never_opens_a_connection(tmp_path):
    r = get_soil(
        34.98,
        -80.55,
        client=failing_client(AssertionError("network used")),
        cache_dir=tmp_path,
        offline=True,
        now=NOW,
    )
    assert r.status == "unavailable" and "offline" in r.reason


def test_module_constants():
    assert soil_mod.SDA_CACHE_DAYS == 30
