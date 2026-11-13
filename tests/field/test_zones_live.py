import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from fieldshift.contracts import Status
from fieldshift.field.live import LiveCache, county_fips, get_live, parse_usdm_csv
from fieldshift.field.zones import (
    ChangeReport,
    PondingReport,
    analyze_zones,
    collection_assessment,
    load_zones,
)

NOW = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)

# ------------------------------------------------------------------ zones (sample zones.json)


@pytest.fixture(scope="module")
def zs():
    return load_zones()


def test_sample_zones_record_terrain_source_date_resolution_and_drainage(zs):
    assert "SAMPLE" in zs.label and len(zs.zones) == 4
    for z in zs.zones:
        t = z.terrain
        assert "3DEP" in t.source and t.terrain_date and t.resolution_m and t.points == 9
        assert t.elevation_m.min <= t.elevation_m.mean <= t.elevation_m.max
        assert z.drainage.cls and z.drainage.derivation == "usda" and t.derivation == "usgs"


def test_collection_zones_come_from_elevation_slope_and_drainage(zs):
    flags = {z.zone_id: collection_assessment(z, zs)[0] for z in zs.zones}
    assert flags == {"zone_nw": False, "zone_ne": True, "zone_sw": False, "zone_se": False}
    poor = zs.model_copy(deep=True)
    poor.zones[0].drainage.cls = "Poorly drained"
    assert collection_assessment(poor.zones[0], poor) == (
        True,
        "drainage class is 'Poorly drained'",
    )
    missing = zs.model_copy(deep=True)
    missing.zones[1].terrain.slope_pct.mean = None
    assert collection_assessment(missing.zones[1], missing)[0] is None


def test_ponding_after_heavy_rain_in_a_collection_zone_prompts_inspection(zs):
    rep = PondingReport(zone_id="zone_ne", reported_on="2025-03-10")
    a = analyze_zones(zs, ponding=[rep], heavy_rain_days=[date(2025, 3, 8), date(2025, 1, 1)])
    (p,) = a.prompts
    assert (p.kind, p.status, p.heavy_rain_days) == ("inspect", "manual_check", [date(2025, 3, 8)])
    assert "inspect" in p.reason


def test_heavy_rain_window_is_three_days_inclusive_of_the_report_day(zs):
    rep = PondingReport(zone_id="zone_ne", reported_on="2025-03-10")
    on_day = analyze_zones(zs, ponding=[rep], heavy_rain_days=[date(2025, 3, 10)]).prompts[0]
    edge = analyze_zones(zs, ponding=[rep], heavy_rain_days=[date(2025, 3, 7)]).prompts[0]
    outside = analyze_zones(zs, ponding=[rep], heavy_rain_days=[date(2025, 3, 6)]).prompts[0]
    after = analyze_zones(zs, ponding=[rep], heavy_rain_days=[date(2025, 3, 11)]).prompts[0]
    assert on_day.kind == "inspect" and edge.kind == "inspect"
    assert outside.kind == "note" and after.kind == "note"  # no heavy rain in the window


def test_ponding_in_a_zone_that_should_not_collect_asks_to_verify_the_report(zs):
    rep = PondingReport(zone_id="zone_sw", reported_on="2025-03-10")
    (p,) = analyze_zones(zs, ponding=[rep], heavy_rain_days=[date(2025, 3, 9)]).prompts
    assert p.kind == "verify_location"
    (u,) = analyze_zones(
        zs, ponding=[PondingReport(zone_id="nope", reported_on="2025-03-10")]
    ).prompts
    assert u.kind == "note" and "unknown zone" in u.reason


def test_regrading_after_the_terrain_survey_flags_verify(zs):
    survey = date.fromisoformat(zs.zones[0].terrain.terrain_date)
    after = ChangeReport(kind="regrading", reported_on=survey + timedelta(days=400))
    a = analyze_zones(zs, changes=[after])
    assert (
        all(f.verify for f in a.findings)
        and "after the terrain survey" in a.findings[0].verify_reason
    )
    before = ChangeReport(kind="drainage_change", reported_on=survey - timedelta(days=1))
    assert not any(f.verify for f in analyze_zones(zs, changes=[before]).findings)
    one = analyze_zones(
        zs,
        changes=[
            ChangeReport(
                kind="regrading", reported_on=survey + timedelta(days=9), zone_id="zone_se"
            )
        ],
    )
    assert [f.zone_id for f in one.findings if f.verify] == ["zone_se"]


def test_zone_evidence_models_reject_unknown_fields():
    with pytest.raises(ValueError):
        PondingReport(zone_id="z", reported_on="2025-01-01", mystery=1)
    with pytest.raises(ValueError):
        ChangeReport(kind="flood", reported_on="2025-01-01")


# ------------------------------------------------------------------ live

POINTS = {
    "properties": {
        "forecast": "https://api.weather.gov/gridpoints/GSP/131,55/forecast",
        "county": "https://api.weather.gov/zones/county/NCC179",
        "gridId": "GSP", "gridX": 131, "gridY": 55,
    }
}  # fmt: skip
FORECAST = {
    "properties": {
        "periods": [
            {"name": "Tonight", "startTime": "2026-11-12T22:00:00-05:00", "endTime": "2026-11-13T06:00:00-05:00",
             "temperature": 41, "temperatureUnit": "F", "probabilityOfPrecipitation": {"value": 0},
             "shortForecast": "Clear"},
            {"name": "Friday", "startTime": "x", "endTime": "y", "temperature": 60, "temperatureUnit": "F",
             "probabilityOfPrecipitation": {"value": None}, "shortForecast": "Sunny"},
        ]
    }
}  # fmt: skip
ALERTS = {
    "features": [
        {
            "properties": {
                "event": "Frost Advisory",
                "severity": "Minor",
                "headline": "Frost",
                "onset": "a",
                "ends": "b",
            }
        }
    ]
}
USDM = (
    "MapDate,FIPS,County,State,None,D0,D1,D2,D3,D4,ValidStart,ValidEnd,StatisticFormatID\n"
    "20261110,37179,Union County,NC,0.00,100.00,32.31,0.00,0.00,0.00,2026-11-10,2026-11-16,1\n"
    "20261103,37179,Union County,NC,0.00,100.00,32.35,0.00,0.00,0.00,2026-11-03,2026-11-09,1\n"
)


def make_client(calls, *, down=()):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        assert request.headers["user-agent"] == "fieldshift-backend"
        for tag in down:
            if tag in url:
                raise httpx.ConnectError("down")
        if "/points/" in url:
            return httpx.Response(200, json=POINTS)
        if url.endswith("/forecast"):
            return httpx.Response(200, json=FORECAST)
        if "alerts/active" in url:
            return httpx.Response(200, json=ALERTS)
        if "usdmdataservices" in url:
            return httpx.Response(200, text=USDM)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_live_block_has_forecast_alerts_drought_with_fetch_time_and_validity():
    calls = []
    b = get_live(
        34.98, -80.55, client=make_client(calls), now=NOW, cache=LiveCache(), offline=False
    )
    assert b.status == Status.COMPLETE and b.county_fips == "37179"
    assert (
        b.forecast.fetched_at == "2026-11-12T15:00:00Z"
        and b.forecast.valid_until == "2026-11-12T15:15:00Z"
    )
    assert (
        b.alerts.valid_until == "2026-11-12T15:05:00Z"
        and b.drought.valid_until == "2026-11-12T21:00:00Z"
    )
    assert b.forecast.freshness == "fresh"
    periods = b.forecast.data["periods"]
    assert periods[0]["precip_probability_pct"] == 0  # a real 0 stays 0
    assert periods[1]["precip_probability_pct"] is None  # blank stays None
    assert "no rainfall depth" in b.forecast.data["note"]
    assert b.alerts.data[0]["event"] == "Frost Advisory"
    assert b.drought.data["highest_category"] == "D1" and b.drought.data["map_date"] == "20261110"
    assert "never used in historical" in b.note


def test_each_source_fails_independently():
    b = get_live(
        34.98,
        -80.55,
        client=make_client([], down=("alerts/active",)),
        now=NOW,
        cache=LiveCache(),
        offline=False,
    )
    assert b.status == Status.PARTIAL
    assert (
        b.alerts.status == Status.UNAVAILABLE
        and b.alerts.freshness == "unavailable"
        and "ConnectError" in b.alerts.reason
    )
    assert b.forecast.status == Status.COMPLETE and b.drought.status == Status.COMPLETE


def test_nws_down_means_unavailable_and_nothing_raises():
    b = get_live(
        34.98,
        -80.55,
        client=make_client([], down=("api.weather.gov",)),
        now=NOW,
        cache=LiveCache(),
        offline=False,
    )
    assert b.status == Status.UNAVAILABLE
    assert all(p.status == Status.UNAVAILABLE for p in (b.forecast, b.alerts, b.drought))
    assert b.county_fips is None and "county" in b.drought.reason


def test_cache_ttl_forecast_15m_alerts_5m_drought_6h():
    calls, cache = [], LiveCache()
    client = make_client(calls)
    get_live(34.98, -80.55, client=client, now=NOW, cache=cache, offline=False)
    n = len(calls)
    again = get_live(
        34.98, -80.55, client=client, now=NOW + timedelta(minutes=4), cache=cache, offline=False
    )
    assert len(calls) == n and again.forecast.freshness.startswith("cached(")
    later = get_live(
        34.98, -80.55, client=client, now=NOW + timedelta(minutes=10), cache=cache, offline=False
    )
    assert later.alerts.freshness == "fresh" and later.forecast.freshness.startswith("cached(")
    assert later.drought.freshness.startswith("cached(")
    much_later = get_live(
        34.98, -80.55, client=client, now=NOW + timedelta(hours=7), cache=cache, offline=False
    )
    assert much_later.drought.freshness == "fresh"


def test_offline_makes_no_requests():
    calls = []
    b = get_live(34.98, -80.55, client=make_client(calls), now=NOW, cache=LiveCache(), offline=True)
    assert calls == [] and b.status == Status.UNAVAILABLE and "offline" in b.forecast.reason


def test_county_fips_and_usdm_parser():
    assert county_fips(POINTS["properties"]) == "37179"
    assert county_fips({"county": "https://api.weather.gov/zones/county/SCC045"}) is None
    assert county_fips({}) is None
    assert parse_usdm_csv(USDM)["percent_area_at_or_worse"]["D1"] == 32.31
    none_row = USDM.replace("100.00,32.31", "0.00,0.00")
    assert parse_usdm_csv(none_row)["highest_category"] == "None"
    for bad in ("", "a,b\n1,2", USDM.replace("100.00", "n/a", 1)):
        with pytest.raises(ValueError):
            parse_usdm_csv(bad)


def test_live_never_feeds_history_modules():
    import fieldshift.metrics.rules as rules

    assert "fieldshift.field.live" not in open(rules.__file__).read()


def test_malformed_provider_bodies_are_unavailable_not_errors():
    def handler(request):
        url = str(request.url)
        if "/points/" in url:
            return httpx.Response(200, json=POINTS)
        return httpx.Response(200, text="<html>oops</html>")

    c = httpx.Client(transport=httpx.MockTransport(handler))
    b = get_live(34.98, -80.55, client=c, now=NOW, cache=LiveCache(), offline=False)
    assert b.status == Status.UNAVAILABLE


def test_json_zone_file_round_trips():
    from fieldshift.field.zones import zones_as_dict

    d = zones_as_dict(load_zones())
    assert d["zones"][0]["drainage"]["class"] and json.dumps(d)
