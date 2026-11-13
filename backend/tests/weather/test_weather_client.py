"""Phase 1 client tests: mocked transport only, no network."""

import httpx
import pytest

from fieldshift.weather.power_client import (
    OFFLINE_ENV,
    OfflineError,
    PowerFetchError,
    build_params,
    fetch_daily,
)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_params_use_ag_community_and_compact_dates():
    p = build_params(34.98, -80.55, "1981-01-01", "2025-06-30")
    assert p["community"] == "AG" and p["start"] == "19810101" and p["end"] == "20250630"
    assert p["latitude"] == "34.98" and p["longitude"] == "-80.55"
    assert "PRECTOTCORR" in p["parameters"] and "GWETROOT" in p["parameters"]


def test_returns_raw_bytes_untouched_with_query_url():
    body = b'{"keep": "exact bytes",  "spacing":   1}'
    fetch = fetch_daily(
        35.0, -80.5, "2024-01-01", "2024-01-02",
        client=_client(lambda r: httpx.Response(200, content=body)),
    )
    assert fetch.body == body
    assert "power.larc.nasa.gov" in fetch.url and "start=20240101" in fetch.url
    assert fetch.retrieved_at.endswith("Z")


def test_retries_5xx_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, content=b"{}")

    sleeps = []
    fetch = fetch_daily(35, -80, "2024-01-01", "2024-01-02", client=_client(handler),
                        sleep=sleeps.append)
    assert fetch.status_code == 200 and len(calls) == 3 and sleeps == [2.0, 4.0]


def test_retries_transport_errors_then_gives_up():
    def handler(request):
        raise httpx.ConnectTimeout("boom")

    with pytest.raises(PowerFetchError, match="after 3 attempts"):
        fetch_daily(35, -80, "2024-01-01", "2024-01-02", client=_client(handler),
                    retries=2, sleep=lambda s: None)


def test_422_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(422, json={"messages": ["start date out of range"]})

    with pytest.raises(PowerFetchError, match="422"):
        fetch_daily(35, -80, "1980-01-01", "1981-01-02", client=_client(handler),
                    sleep=lambda s: None)
    assert len(calls) == 1


def test_offline_mode_blocks_fetch(monkeypatch):
    monkeypatch.setenv(OFFLINE_ENV, "1")
    with pytest.raises(OfflineError):
        fetch_daily(35, -80, "2024-01-01", "2024-01-02")
