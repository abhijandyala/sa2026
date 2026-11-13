"""Phase 1 normalization tests. All inputs are synthetic FIXTURES, not real weather."""

import json

import numpy as np
import pandas as pd

from fieldshift.weather.normalize import (
    REASON_ABSENT,
    REASON_FILL,
    REASON_NAN,
    REASON_NEGATIVE,
    REASON_OUT_OF_RANGE,
    normalize_daily,
    normalize_power_response,
    parse_power_json,
)


def _payload(rows: dict[str, dict[str, float | None]]) -> dict:
    """rows: parameter -> {YYYYMMDD: value}. Synthetic fixture shaped like a POWER response."""
    return {
        "header": {"fill_value": -999.0, "time_standard": "LST"},
        "properties": {"parameter": rows},
    }


def _flat(date_to_precip: dict[str, float | None]) -> dict:
    dates = list(date_to_precip)
    return _payload(
        {
            "PRECTOTCORR": date_to_precip,
            "T2M_MAX": {d: 20.0 for d in dates},
            "T2M_MIN": {d: 10.0 for d in dates},
            "T2M": {d: 15.0 for d in dates},
            "GWETTOP": {d: 0.5 for d in dates},
            "GWETROOT": {d: 0.6 for d in dates},
        }
    )


def test_fill_value_is_missing_with_reason():
    result = normalize_power_response(_flat({"20240101": 1.0, "20240102": -999.0, "20240103": 2.0}))
    day = result.daily.set_index("date").loc["2024-01-02"]
    assert np.isnan(day["precip_mm"])
    assert day["precip_mm_reason"] == REASON_FILL
    assert result.log.missing_by_reason["precip_mm"] == {REASON_FILL: 1}


def test_negative_precip_is_missing_but_negative_temperature_is_kept():
    payload = _flat({"20240101": -0.5, "20240102": 0.3})
    payload["properties"]["parameter"]["T2M_MIN"]["20240101"] = -12.0
    daily = normalize_power_response(payload).daily.set_index("date")
    assert np.isnan(daily.loc["2024-01-01", "precip_mm"])
    assert daily.loc["2024-01-01", "precip_mm_reason"] == REASON_NEGATIVE
    assert daily.loc["2024-01-01", "tmin_c"] == -12.0
    assert daily.loc["2024-01-01", "tmin_c_reason"] is None


def test_real_zero_is_kept_and_has_no_reason():
    daily = normalize_power_response(_flat({"20240101": 0.0, "20240102": 0.0})).daily
    assert daily["precip_mm"].tolist() == [0.0, 0.0]
    assert daily["precip_mm_reason"].isna().all()


def test_gap_becomes_explicit_all_missing_row():
    result = normalize_power_response(_flat({"20240101": 1.0, "20240104": 2.0}))
    daily = result.daily.set_index("date")
    assert len(daily) == 4
    for gap in ("2024-01-02", "2024-01-03"):
        assert daily.loc[gap, ["precip_mm", "tmax_c", "gwetroot"]].isna().all()
        assert daily.loc[gap, "precip_mm_reason"] == REASON_ABSENT
    assert result.log.missing_by_reason["tmax_c"] == {REASON_ABSENT: 2}


def test_requested_span_is_reindexed_even_when_source_is_short():
    daily = normalize_power_response(
        _flat({"20240102": 1.0}), start="2024-01-01", end="2024-01-03"
    ).daily
    assert daily["date"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-01", "2024-01-02", "2024-01-03"]
    assert daily["precip_mm_reason"].tolist() == [REASON_ABSENT, None, REASON_ABSENT]


def test_duplicate_dates_are_deduplicated_first_wins_and_logged():
    records = pd.DataFrame(
        {
            "date": ["20240101", "20240102", "20240102", "20240103", "20240103"],
            "precip_mm": [1.0, 2.0, 2.0, 3.0, 9.0],
            "tmax_c": 20.0, "tmin_c": 10.0, "tmean_c": 15.0, "gwettop": 0.5, "gwetroot": 0.6,
        }
    )
    result = normalize_daily(records)
    assert result.daily["precip_mm"].tolist() == [1.0, 2.0, 3.0]
    dups = {d["date"]: d for d in result.log.duplicates}
    assert dups["2024-01-02"]["conflicting_values"] is False
    assert dups["2024-01-03"]["conflicting_values"] is True
    assert dups["2024-01-03"]["kept"] == "first"


def test_null_nan_and_out_of_range_wetness():
    payload = _flat({"20240101": None, "20240102": 1.0})
    payload["properties"]["parameter"]["GWETTOP"]["20240102"] = 1.4
    payload["properties"]["parameter"]["GWETROOT"]["20240102"] = -0.1
    daily = normalize_power_response(payload).daily.set_index("date")
    assert daily.loc["2024-01-01", "precip_mm_reason"] == REASON_NAN
    assert daily.loc["2024-01-02", "gwettop_reason"] == REASON_OUT_OF_RANGE
    assert daily.loc["2024-01-02", "gwetroot_reason"] == REASON_NEGATIVE


def test_invalid_dates_are_dropped_and_logged():
    records = pd.DataFrame(
        {"date": ["20240101", "not-a-date"], "precip_mm": [1.0, 2.0], "tmax_c": 1.0,
         "tmin_c": 0.0, "tmean_c": 0.5, "gwettop": 0.5, "gwetroot": 0.5}
    )
    result = normalize_daily(records)
    assert len(result.daily) == 1
    assert result.log.invalid_dates == ["not-a-date"]


def test_parse_accepts_bytes_and_missing_parameter_column():
    payload = _payload({"PRECTOTCORR": {"20240101": 1.5}})
    wide = parse_power_json(json.dumps(payload).encode())
    assert wide["precip_mm"].tolist() == [1.5]
    assert wide["gwettop"].isna().all()
