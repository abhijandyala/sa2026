"""Typed catalog models and the validation-issue record.

Blank CSV cells become ``None``; a genuine ``0`` stays a number. Nothing here
coerces one into the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class ValidationIssue:
    """One problem found in a catalog file.

    ``row`` is the spreadsheet row number: the header is row 1, the first data
    row is row 2. ``row`` is ``None`` and ``field`` is ``"header"`` for header
    problems.
    """

    file: str
    row: int | None
    field: str
    severity: Severity
    message: str
    code: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "file": self.file,
            "row": self.row,
            "field": self.field,
            "severity": self.severity,
            "message": self.message,
            "code": self.code,
        }


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Crop(_Frozen):
    crop_id: str
    common_name: str | None = None
    scientific_name: str | None = None
    crop_role: str | None = None
    summary: str | None = None
    source_title: str | None = None
    source_url: str | None = None
    source_locator: str | None = None
    verified_date: date | None = None


class CropRule(_Frozen):
    rule_id: str
    crop_id: str
    region: str | None = None
    rule_type: str | None = None
    growth_stage: str | None = None
    management_action: str | None = None
    cultivar_or_maturity_group: str | None = None
    production_system: str | None = None
    previous_crop_id: str | None = None
    next_crop_id: str | None = None
    window_start_mm_dd: str | None = None
    window_end_mm_dd: str | None = None
    condition_key: str | None = None
    operator: str | None = None
    value_min: float | None = None
    value_max: float | None = None
    value_text: str | None = None
    unit: str | None = None
    # ``exposure_duration`` is numeric when the source gave a number. A word such
    # as "several" (sb_wt_02) is kept verbatim in ``exposure_duration_text`` and
    # is never coerced to a number.
    exposure_duration: float | None = None
    exposure_duration_text: str | None = None
    exposure_unit: str | None = None
    suitability: str | None = None
    applies_when: str | None = None
    guidance: str | None = None
    source_title: str | None = None
    source_url: str | None = None
    source_locator: str | None = None
    verified_date: date | None = None


class Fertilizer(_Frozen):
    fertilizer_id: str
    product_name: str | None = None
    manufacturer: str | None = None
    grade: str | None = None
    n_pct: float | None = None
    p2o5_pct: float | None = None
    k2o_pct: float | None = None
    source_title: str | None = None
    source_url: str | None = None
    source_locator: str | None = None
    verified_date: date | None = None
