"""Irrigation tools (Phase 11): stage checks, crop demand, and a water balance only when complete.

Three things are kept apart on purpose:

* **Stage checks** come from the catalog's water-demand rules (``*_wd_*``), for example soybean
  R1-R5 (``sb_wd_06``) or corn pollination (``fc_wd_03``). They are guidance, not calculations.
* **Crop demand** is the published daily crop water use for a stage (``fc_wd_02/03``,
  ``sb_wd_02-05``, inches/day). It describes the crop, not a recommendation to irrigate.
* **Supplemental need** is only reported from a numeric water balance, and that balance is run
  only when the crop stage, weather, soil AWC, recent irrigation and a starting moisture value are
  ALL present. Otherwise ``insufficient_data`` lists exactly what is missing. The catalog has no
  management-allowed-depletion threshold, so none is invented: the output is the unmet demand over
  the period, not a scheduling instruction.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from fieldshift.catalogs.index import CatalogIndex
from fieldshift.catalogs.models import CropRule
from fieldshift.contracts import FieldIssue, Status

MM_PER_INCH = 25.4
GENERAL_STAGES = frozenset({"season", "critical stages"})


def norm_stage(s: str | None) -> str:
    """``"R1-R5"`` / ``"R1 to R5"`` / ``"R1_to_R5"`` -> ``"r1_to_r5"``."""
    t = (s or "").strip().lower()
    t = re.sub(r"\s*(-|–|to)\s*", "_to_", t)
    return re.sub(r"[\s_]+", "_", t)


class StageCheck(BaseModel):
    rule_id: str
    stage: str | None
    status: Status  # manual_check: guidance a person applies
    suitability: str | None
    guidance: str | None
    condition: str | None
    source_url: str | None
    verified_date: str | None


class CropDemand(BaseModel):
    rule_id: str
    stage: str | None
    daily_use_in_min: float | None
    daily_use_in_max: float | None
    unit: str = "in_per_day"
    illustrative: bool
    note: str | None
    source_url: str | None
    kind: str = "crop_demand (not an irrigation recommendation)"


class DailyRow(BaseModel):
    date: date
    rain_in: float
    irrigation_in: float
    crop_use_in: float
    storage_in: float  # end-of-day available water in the root zone
    unmet_demand_in: float
    drainage_or_runoff_in: float


class WaterBalance(BaseModel):
    awc_in: float
    start_storage_in: float
    end_storage_in: float
    days: int
    total_rain_in: float
    total_irrigation_in: float
    total_crop_use_in: float
    unmet_demand_in: float
    drainage_or_runoff_in: float
    days_until_empty_at_current_use: float | None
    daily: list[DailyRow]
    assumptions: list[str]
    derivation: str = "calculation"


class IrrigationResult(BaseModel):
    status: Status  # complete | insufficient_data | invalid_input | unsupported
    issues: list[FieldIssue] = Field(default_factory=list)
    crop_id: str
    stage: str | None
    stage_checks: list[StageCheck] = Field(default_factory=list)
    crop_demand: CropDemand | None = None
    missing: list[str] = Field(default_factory=list)
    water_balance: WaterBalance | None = None
    supplemental_need: dict[str, Any] | None = None
    water_table: dict[str, Any] | None = None
    notes: list[str] = Field(default_factory=list)


def _bad(crop_id: str, stage: str | None, field: str, code: str, msg: str) -> IrrigationResult:
    return IrrigationResult(
        status=Status.INVALID_INPUT, crop_id=crop_id, stage=stage,
        issues=[FieldIssue(field=field, code=code, message=msg)],
    )  # fmt: skip


def _wd_rules(index: CatalogIndex, crop_id: str) -> list[CropRule]:
    return [r for r in index.rules_for_crop(crop_id) if "_wd_" in r.rule_id]


def _stage_matches(rule: CropRule, stage: str) -> bool:
    rs = norm_stage(rule.growth_stage)
    return bool(rs) and (rs == stage or stage in rs.split("_and_") or rs in GENERAL_STAGES)


def stage_checks(index: CatalogIndex, crop_id: str, stage: str | None) -> list[StageCheck]:
    out = []
    want = norm_stage(stage)
    for r in _wd_rules(index, crop_id):
        if r.condition_key == "daily_crop_water_use":
            continue  # that is crop demand, reported separately
        if want and not _stage_matches(r, want):
            continue
        out.append(
            StageCheck(
                rule_id=r.rule_id, stage=r.growth_stage, status=Status.MANUAL_CHECK,
                suitability=r.suitability, guidance=r.guidance,
                condition=r.applies_when or r.value_text, source_url=r.source_url,
                verified_date=r.verified_date.isoformat() if r.verified_date else None,
            )
        )  # fmt: skip
    return out


def crop_demand(index: CatalogIndex, crop_id: str, stage: str | None) -> CropDemand | None:
    want = norm_stage(stage)
    if not want:
        return None
    for r in _wd_rules(index, crop_id):
        if r.condition_key != "daily_crop_water_use" or norm_stage(r.growth_stage) != want:
            continue
        lo = r.value_min
        hi = r.value_max if r.operator == "between" else r.value_min
        return CropDemand(
            rule_id=r.rule_id, stage=r.growth_stage, daily_use_in_min=lo, daily_use_in_max=hi,
            illustrative="illustrative" in (r.applies_when or "").lower(),
            note=r.applies_when or r.value_text, source_url=r.source_url,
        )  # fmt: skip
    return None


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def _day(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        return None


def _parse_weather(rows: Any) -> tuple[list[tuple[date, float]] | None, FieldIssue | None]:
    if not isinstance(rows, list):
        return None, FieldIssue(
            field="weather", code="invalid_type", message="weather must be a list"
        )
    out: dict[date, float] = {}
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            return None, FieldIssue(
                field=f"weather.{i}", code="invalid_type", message="expected an object"
            )
        d = _day(r.get("date"))
        if d is None:
            return None, FieldIssue(
                field=f"weather.{i}.date", code="invalid_date", message="date must be YYYY-MM-DD"
            )
        if d in out:
            return None, FieldIssue(
                field=f"weather.{i}.date", code="duplicate_date", message=f"{d} appears twice"
            )
        if "precip_in" in r and r["precip_in"] is not None:
            p = _num(r["precip_in"])
        elif "precip_mm" in r and r["precip_mm"] is not None:
            p = _num(r["precip_mm"])
            p = None if p is None else p / MM_PER_INCH
        else:
            return None, FieldIssue(
                field=f"weather.{i}.precip_mm",
                code="missing_value",
                message="a day has no precipitation value; blanks are not treated as 0",
            )
        if p is None or p < 0:
            return None, FieldIssue(
                field=f"weather.{i}.precip_mm",
                code="invalid_value",
                message="precipitation must be a finite number >= 0",
            )
        out[d] = p
    return sorted(out.items()), None


def water_table_check(index: CatalogIndex, crop_id: str, depth_in: Any) -> dict[str, Any] | None:
    rule = index.rule("sb_wd_07") if crop_id == "soybean" else None
    if rule is None or rule.value_min is None:
        return None
    depth = _num(depth_in)
    if depth is None:
        return None
    hit = depth <= rule.value_min
    return {
        "rule_id": rule.rule_id,
        "water_table_depth_in": depth,
        "threshold_in": rule.value_min,
        "status": "complete",
        "flagged": hit,
        "guidance": rule.guidance,
        "note": "applies to irrigated soybean; also check the rainfall forecast first",
        "source_url": rule.source_url,
    }


def check_irrigation(
    index: CatalogIndex,
    *,
    crop_id: str,
    stage: str | None = None,
    awc_in: Any = None,
    start_storage_in: Any = None,
    weather: Any = None,
    irrigation: Any = None,
    water_table_depth_in: Any = None,
) -> IrrigationResult:
    if index.crop(crop_id) is None or not _wd_rules(index, crop_id):
        return IrrigationResult(
            status=Status.UNSUPPORTED, crop_id=crop_id, stage=stage,
            notes=[f"no water-demand rules for '{crop_id}' in the catalog"],
        )  # fmt: skip
    res = IrrigationResult(status=Status.INSUFFICIENT_DATA, crop_id=crop_id, stage=stage)
    res.stage_checks = stage_checks(index, crop_id, stage)
    demand = crop_demand(index, crop_id, stage)
    res.crop_demand = demand
    res.water_table = water_table_check(index, crop_id, water_table_depth_in)
    if demand is not None and demand.illustrative:
        res.notes.append(
            f"{demand.rule_id} is an illustrative published example for this stage, not a "
            "measured value for this field"
        )

    # ---- is a numeric balance possible? every input must be present
    missing: list[str] = []
    if not stage:
        missing.append("stage")
    elif demand is None:
        missing.append("stage (no published daily crop water use for this stage in the catalog)")
    awc = _num(awc_in)
    if awc_in is None:
        missing.append("awc_in (soil available water capacity to rooting depth, inches)")
    elif awc is None or awc <= 0:
        return _bad(crop_id, stage, "awc_in", "invalid_value", "awc_in must be a finite number > 0")
    start = _num(start_storage_in)
    if start_storage_in is None:
        missing.append("start_storage_in (available water at the start, inches)")
    elif start is None or start < 0 or (awc is not None and start > awc):
        return _bad(
            crop_id,
            stage,
            "start_storage_in",
            "invalid_value",
            "start_storage_in must be between 0 and awc_in",
        )
    days: list[tuple[date, float]] = []
    if weather is None or weather == []:
        missing.append("weather (daily precipitation for the period)")
    else:
        parsed, issue = _parse_weather(weather)
        if issue is not None:
            return IrrigationResult(
                status=Status.INVALID_INPUT, crop_id=crop_id, stage=stage, issues=[issue]
            )
        days = parsed or []
    irr: dict[date, float] = {}
    if irrigation is None:
        missing.append("irrigation (recent irrigation amounts; an empty list means none)")
    elif not isinstance(irrigation, list):
        return _bad(crop_id, stage, "irrigation", "invalid_type", "irrigation must be a list")
    else:
        for i, r in enumerate(irrigation):
            d = _day(r.get("date")) if isinstance(r, dict) else None
            a = _num(r.get("amount_in")) if isinstance(r, dict) else None
            if d is None or a is None or a < 0:
                return _bad(
                    crop_id,
                    stage,
                    f"irrigation.{i}",
                    "invalid_value",
                    "each entry needs a date and amount_in >= 0",
                )
            irr[d] = irr.get(d, 0.0) + a
    if missing:
        res.missing = missing
        res.notes.append("No numeric water balance is given until every input is present.")
        return res
    assert demand is not None and awc is not None and start is not None

    use = ((demand.daily_use_in_min or 0.0) + (demand.daily_use_in_max or 0.0)) / 2
    in_range = {d for d, _ in days}
    stray = sorted(d for d in irr if d not in in_range)
    if stray:
        res.notes.append(
            f"irrigation on {', '.join(map(str, stray))} is outside the weather period and was not used"
        )
    storage = start
    rows: list[DailyRow] = []
    tot_rain = tot_irr = tot_use = tot_unmet = tot_drain = 0.0
    for d, rain in days:
        add = irr.get(d, 0.0)
        storage += rain + add - use
        unmet = drain = 0.0
        if storage > awc:
            drain, storage = storage - awc, awc
        elif storage < 0:
            unmet, storage = -storage, 0.0
        tot_rain += rain
        tot_irr += add
        tot_use += use
        tot_unmet += unmet
        tot_drain += drain
        rows.append(
            DailyRow(date=d, rain_in=round(rain, 4), irrigation_in=round(add, 4), crop_use_in=round(use, 4),
                     storage_in=round(storage, 4), unmet_demand_in=round(unmet, 4),
                     drainage_or_runoff_in=round(drain, 4))
        )  # fmt: skip
    res.status = Status.COMPLETE
    res.water_balance = WaterBalance(
        awc_in=awc, start_storage_in=start, end_storage_in=round(storage, 4), days=len(rows),
        total_rain_in=round(tot_rain, 4), total_irrigation_in=round(tot_irr, 4),
        total_crop_use_in=round(tot_use, 4), unmet_demand_in=round(tot_unmet, 4),
        drainage_or_runoff_in=round(tot_drain, 4),
        days_until_empty_at_current_use=round(storage / use, 2) if use > 0 else None,
        daily=rows,
        assumptions=[
            f"daily crop use = {use:g} in/day for the whole period ({demand.rule_id}"
            + (", an illustrative published value" if demand.illustrative else "")
            + "); the stage is held constant",
            "bucket model: storage cannot exceed AWC; any excess is drainage or runoff (not separated)",
            "rain is counted in full; no runoff or interception loss is modeled",
        ],
    )  # fmt: skip
    res.supplemental_need = {
        "unmet_demand_in": round(tot_unmet, 4),
        "kind": "unmet crop demand over the period; not a scheduling recommendation",
        "note": "the catalog has no management-allowed-depletion threshold, so none is applied",
        "derivation": "calculation",
    }
    return res
