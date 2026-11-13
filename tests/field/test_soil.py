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


# ------------------------------------------------------------------ review fixes (phase-8-B)


@pytest.mark.parametrize(
    "bad",
    [
        "not a table",
        [["mukey"], [1]],  # missing columns
        [["a"], "row"],
        [[], []],
        {"Table": []},
    ],
)
def test_malformed_tables_are_unavailable_not_exceptions(bad):
    assert parse_sda_table(bad).status == "unavailable"


def test_wrong_row_width_and_bad_values_are_unavailable(table):
    short = [table[0], table[1][:5]]
    assert parse_sda_table(short).status == "unavailable"
    bad_pct = [list(r) for r in table]
    bad_pct[1][7] = "lots"  # comppct_r is not a number: treated as missing, not a crash
    assert parse_sda_table(bad_pct).status in ("complete", "partial")


def test_malformed_body_from_sda_is_unavailable(tmp_path):
    for payload in ({"Table": "oops"}, {"Table": [["mukey"], ["1"]]}, {"Table": [["x"]] * 3}):
        r = get_soil(34.98, -80.55, client=client_returning(payload), cache_dir=tmp_path, now=NOW)
        assert r.status == "unavailable"


def test_corrupt_cache_is_ignored_and_refetched(table, tmp_path):
    from fieldshift.field.soil import _cache_path, build_query

    p = _cache_path(tmp_path, build_query(34.98, -80.55))
    for junk in ("{not json", json.dumps({"fetched_at": "2026-11-12T12:00:00Z", "table": "oops"}),
                 json.dumps({"fetched_at": 5, "table": []}), json.dumps([1, 2])):  # fmt: skip
        p.write_text(junk)
        r = get_soil(
            34.98, -80.55, client=client_returning({"Table": table}), cache_dir=tmp_path, now=NOW
        )
        assert r.status == "complete" and r.provenance.freshness == "fresh"


def test_expired_cache_is_never_reported_as_current(table, tmp_path):
    get_soil(34.98, -80.55, client=client_returning({"Table": table}), cache_dir=tmp_path, now=NOW)
    later = NOW + timedelta(days=60)
    r = get_soil(
        34.98,
        -80.55,
        client=failing_client(httpx.ReadTimeout("slow")),
        cache_dir=tmp_path,
        now=later,
    )
    assert r.status == "unavailable" and "30-day limit" in r.reason
    assert (
        r.stale_copy is not None
        and r.stale_copy.status == "complete"
        and r.stale_copy.provenance.stale
    )
    off = get_soil(
        34.98,
        -80.55,
        client=failing_client(AssertionError("net")),
        cache_dir=tmp_path,
        now=later,
        offline=True,
    )
    assert off.status == "unavailable" and off.stale_copy is not None


def test_offline_follows_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELDSHIFT_OFFLINE", "1")
    r = get_soil(
        34.98, -80.55, client=failing_client(AssertionError("net")), cache_dir=tmp_path, now=NOW
    )
    assert r.status == "unavailable" and "offline" in r.reason


def test_published_zero_percent_outranks_a_missing_percentage(table):
    rows = [list(r) for r in table]
    hdr = rows[0]
    ip = hdr.index("comppct_r")
    for r in rows[1:]:
        if r[hdr.index("compname")] == "Tarrus":
            r[ip] = None  # missing
        else:
            r[ip] = "0"  # published zero
    assert parse_sda_table(rows).dominant_component.name == "Urban land"
