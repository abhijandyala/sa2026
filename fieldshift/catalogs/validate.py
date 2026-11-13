"""Strict, per-row validation of the three Perplexity catalogs.

Every check returns :class:`ValidationIssue` records pointing at the exact file,
spreadsheet row and field. Validation never raises on bad data and never edits
rows: the loader decides which rows stay usable (rows with any ``error`` are
dropped, rows with only ``warning`` issues are kept).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import date

from fieldshift.catalogs.models import Crop, CropRule, Fertilizer, ValidationIssue

CROPS_FILE = "crops.csv"
RULES_FILE = "crop_rules.csv"
FERTILIZERS_FILE = "fertilizers.csv"

CROPS_HEADER = [
    "crop_id", "common_name", "scientific_name", "crop_role", "summary",
    "source_title", "source_url", "source_locator", "verified_date",
]  # fmt: skip
RULES_HEADER = [
    "rule_id", "crop_id", "region", "rule_type", "growth_stage", "management_action",
    "cultivar_or_maturity_group", "production_system", "previous_crop_id", "next_crop_id",
    "window_start_mm_dd", "window_end_mm_dd", "condition_key", "operator", "value_min",
    "value_max", "value_text", "unit", "exposure_duration", "exposure_unit", "suitability",
    "applies_when", "guidance", "source_title", "source_url", "source_locator", "verified_date",
]  # fmt: skip
FERTILIZERS_HEADER = [
    "fertilizer_id", "product_name", "manufacturer", "grade", "n_pct", "p2o5_pct", "k2o_pct",
    "source_title", "source_url", "source_locator", "verified_date",
]  # fmt: skip

EXPECTED_HEADERS: dict[str, list[str]] = {
    CROPS_FILE: CROPS_HEADER,
    RULES_FILE: RULES_HEADER,
    FERTILIZERS_FILE: FERTILIZERS_HEADER,
}

CROP_ROLES = frozenset({"cash_crop", "cover_crop"})
RULE_TYPES = frozenset(
    {
        "planting_window",
        "weather_tolerance",
        "growth_duration",
        "water_demand",
        "light_requirement",
        "soil_suitability",
        "nutrient_guidance",
        "rotation_compatibility",
        "rotation_trait",
        "termination_timing",
    }
)
OPERATORS = frozenset({"gte", "gt", "lte", "lt", "eq", "between"})
SINGLE_BOUND_OPERATORS = frozenset({"gte", "gt", "lte", "lt", "eq"})
SUITABILITIES = frozenset({"preferred", "acceptable", "caution", "avoid"})
UNITS = frozenset(
    {
        "degF",
        "in",
        "GDD_F",
        "days",
        "weeks",
        "hours",
        "pH",
        "lb_N_per_acre",
        "bu_per_acre",
        "in_per_day",
        "in_per_ft",
        "maturity_group",
    }
)

_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_MMDD_RE = re.compile(r"^(\d{2})-(\d{2})$")
_NUM = r"\d+(?:\.\d+)?"
_GRADE_RE = re.compile(rf"^({_NUM})-({_NUM})-({_NUM})((?:-{_NUM}[A-Za-z]+)*)$")
_PCT_TOLERANCE = 1e-6


def parse_mm_dd(value: str) -> tuple[int, int] | None:
    """Parse ``MM-DD`` into ``(month, day)``. ``02-29`` is accepted (leap-year anchored)."""
    m = _MMDD_RE.match(value)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    try:
        date(2000, month, day)  # 2000 is a leap year, so 02-29 is valid
    except ValueError:
        return None
    return month, day


def check_header(file: str, header: Sequence[str]) -> tuple[list[ValidationIssue], bool]:
    """Compare a CSV header to the contract. Returns ``(issues, rows_are_loadable)``."""
    expected = EXPECTED_HEADERS[file]
    issues: list[ValidationIssue] = []
    got = [h.strip() for h in header]
    missing = [c for c in expected if c not in got]
    extra = [c for c in got if c not in expected]
    for col in missing:
        issues.append(
            ValidationIssue(file, 1, "header", "error", f"missing column '{col}'", "header_missing")
        )
    for col in extra:
        issues.append(
            ValidationIssue(
                file, 1, "header", "warning", f"unexpected column '{col}' ignored", "header_extra"
            )
        )
    if not missing and not extra and got != expected:
        issues.append(
            ValidationIssue(
                file, 1, "header", "warning", "columns are in a different order than the contract",
                "header_order",
            )
        )  # fmt: skip
    return issues, not missing


# --------------------------------------------------------------------------- helpers


def _issue(file: str, row: int, field: str, severity: str, message: str, code: str):
    return ValidationIssue(file, row, field, severity, message, code)  # type: ignore[arg-type]


def _check_id(file: str, row: int, field: str, value: str | None) -> list[ValidationIssue]:
    if not value:
        return [_issue(file, row, field, "error", f"{field} is required", "id_missing")]
    if not _ID_RE.match(value):
        return [
            _issue(file, row, field, "error", f"'{value}' is not lowercase snake_case", "id_format")
        ]
    return []


def _check_unique(file: str, rows: Iterable[tuple[int, str]], field: str) -> list[ValidationIssue]:
    seen: dict[str, int] = {}
    out: list[ValidationIssue] = []
    for row, value in rows:
        if value in seen:
            out.append(
                _issue(
                    file, row, field, "error",
                    f"duplicate {field} '{value}' (first seen on row {seen[value]})", "id_duplicate",
                )
            )  # fmt: skip
        else:
            seen[value] = row
    return out


def _check_source(file: str, row: int, rec) -> list[ValidationIssue]:
    out: list[ValidationIssue] = []
    if not rec.source_url:
        out.append(
            _issue(file, row, "source_url", "error", "source_url is required", "source_missing")
        )
    elif not re.match(r"^https?://\S+$", rec.source_url):
        out.append(
            _issue(
                file,
                row,
                "source_url",
                "error",
                "source_url is not an http(s) URL",
                "source_bad_url",
            )
        )
    if not rec.source_locator:
        out.append(
            _issue(
                file, row, "source_locator", "error", "source_locator is required", "source_missing"
            )
        )
    if rec.verified_date is None:
        out.append(
            _issue(
                file, row, "verified_date", "warning",
                "verified_date is blank; the source was not date-verified", "verified_blank",
            )
        )  # fmt: skip
    return out


# --------------------------------------------------------------------------- crops


def validate_crops(rows: Sequence[tuple[int, Crop]]) -> list[ValidationIssue]:
    f = CROPS_FILE
    out: list[ValidationIssue] = []
    for row, c in rows:
        out += _check_id(f, row, "crop_id", c.crop_id)
        if not c.common_name:
            out.append(
                _issue(f, row, "common_name", "error", "common_name is required", "required")
            )
        if c.crop_role not in CROP_ROLES:
            out.append(
                _issue(
                    f, row, "crop_role", "error",
                    f"crop_role '{c.crop_role}' is not one of {sorted(CROP_ROLES)}", "crop_role",
                )
            )  # fmt: skip
        out += _check_source(f, row, c)
    out += _check_unique(f, [(r, c.crop_id) for r, c in rows], "crop_id")
    return out


# --------------------------------------------------------------------------- rules


def validate_rules(
    rows: Sequence[tuple[int, CropRule]], crop_ids: set[str]
) -> list[ValidationIssue]:
    f = RULES_FILE
    out: list[ValidationIssue] = []
    for row, r in rows:
        out += _check_id(f, row, "rule_id", r.rule_id)
        out += _check_id(f, row, "crop_id", r.crop_id)
        for fld in ("crop_id", "previous_crop_id", "next_crop_id"):
            ref = getattr(r, fld)
            if ref and ref not in crop_ids:
                out.append(
                    _issue(
                        f,
                        row,
                        fld,
                        "error",
                        f"{fld} '{ref}' does not exist in crops.csv",
                        "dangling_ref",
                    )
                )

        if r.rule_type not in RULE_TYPES:
            out.append(
                _issue(
                    f,
                    row,
                    "rule_type",
                    "error",
                    f"rule_type '{r.rule_type}' is not allowed",
                    "rule_type",
                )
            )
        if r.suitability is not None and r.suitability not in SUITABILITIES:
            out.append(
                _issue(
                    f,
                    row,
                    "suitability",
                    "error",
                    f"suitability '{r.suitability}' is not allowed",
                    "suitability",
                )
            )
        out += _check_operator(f, row, r)
        out += _check_windows(f, row, r)

        for fld in ("unit", "exposure_unit"):
            u = getattr(r, fld)
            if u is not None and u not in UNITS:
                out.append(_issue(f, row, fld, "error", f"unknown unit '{u}'", "unit_unknown"))
        has_value = r.value_min is not None or r.value_max is not None
        if has_value and r.unit is None:
            out.append(
                _issue(f, row, "unit", "warning", "numeric value has no unit", "unit_missing")
            )
        if r.exposure_duration is not None and r.exposure_unit is None:
            out.append(
                _issue(
                    f,
                    row,
                    "exposure_unit",
                    "warning",
                    "numeric exposure_duration has no unit",
                    "unit_missing",
                )
            )
        out += _check_source(f, row, r)
    out += _check_unique(f, [(r, x.rule_id) for r, x in rows], "rule_id")
    return out


def _check_operator(file: str, row: int, r: CropRule) -> list[ValidationIssue]:
    out: list[ValidationIssue] = []
    op = r.operator
    if op is None:
        if r.value_min is not None or r.value_max is not None:
            out.append(
                _issue(
                    file,
                    row,
                    "operator",
                    "warning",
                    "numeric value present but operator is blank",
                    "operator_missing",
                )
            )
        return out
    if op not in OPERATORS:
        return [
            _issue(file, row, "operator", "error", f"operator '{op}' is not allowed", "operator")
        ]
    if op == "between":
        if r.value_min is None:
            out.append(
                _issue(
                    file, row, "value_min", "error", "'between' needs value_min", "bound_missing"
                )
            )
        if r.value_max is None:
            out.append(
                _issue(
                    file, row, "value_max", "error", "'between' needs value_max", "bound_missing"
                )
            )
        if r.value_min is not None and r.value_max is not None and r.value_min > r.value_max:
            out.append(
                _issue(
                    file, row, "value_max", "error",
                    f"'between' bounds are reversed (min {r.value_min} > max {r.value_max})",
                    "between_reversed",
                )
            )  # fmt: skip
    else:
        if r.value_min is None:
            out.append(
                _issue(file, row, "value_min", "error", f"'{op}' needs value_min", "bound_missing")
            )
        if r.value_max is not None:
            out.append(
                _issue(
                    file,
                    row,
                    "value_max",
                    "error",
                    f"single-bound operator '{op}' must not have value_max",
                    "bound_extra",
                )
            )
    return out


def _check_windows(file: str, row: int, r: CropRule) -> list[ValidationIssue]:
    out: list[ValidationIssue] = []
    for fld in ("window_start_mm_dd", "window_end_mm_dd"):
        v = getattr(r, fld)
        if v is not None and parse_mm_dd(v) is None:
            out.append(
                _issue(file, row, fld, "error", f"'{v}' is not a valid MM-DD date", "date_format")
            )
    if (r.window_start_mm_dd is None) != (r.window_end_mm_dd is None):
        missing = "window_end_mm_dd" if r.window_end_mm_dd is None else "window_start_mm_dd"
        out.append(
            _issue(
                file,
                row,
                missing,
                "warning",
                "only one end of the date window is given",
                "window_open",
            )
        )
    return out


# --------------------------------------------------------------------------- fertilizers


def validate_fertilizers(rows: Sequence[tuple[int, Fertilizer]]) -> list[ValidationIssue]:
    f = FERTILIZERS_FILE
    out: list[ValidationIssue] = []
    for row, x in rows:
        out += _check_id(f, row, "fertilizer_id", x.fertilizer_id)
        if not x.product_name:
            out.append(
                _issue(f, row, "product_name", "error", "product_name is required", "required")
            )
        pcts = {"n_pct": x.n_pct, "p2o5_pct": x.p2o5_pct, "k2o_pct": x.k2o_pct}
        for fld, v in pcts.items():
            if v is None:
                out.append(_issue(f, row, fld, "error", f"{fld} is required", "required"))
            elif not 0 <= v <= 100:
                out.append(_issue(f, row, fld, "error", f"{fld} {v} is outside 0-100", "pct_range"))
        out += _check_grade(f, row, x, pcts)
        out += _check_source(f, row, x)
    out += _check_unique(f, [(r, x.fertilizer_id) for r, x in rows], "fertilizer_id")
    return out


def _check_grade(file: str, row: int, x: Fertilizer, pcts: dict[str, float | None]):
    if not x.grade:
        return [_issue(file, row, "grade", "error", "grade is required", "required")]
    m = _GRADE_RE.match(x.grade)
    if not m:
        return [
            _issue(
                file,
                row,
                "grade",
                "error",
                f"grade '{x.grade}' is not N-P-K (optionally with S/Zn suffixes)",
                "grade_format",
            )
        ]
    out = []
    for (fld, v), part in zip(pcts.items(), m.groups()[:3], strict=True):
        if v is not None and abs(float(part) - v) > _PCT_TOLERANCE:
            out.append(
                _issue(
                    file,
                    row,
                    "grade",
                    "error",
                    f"grade '{x.grade}' says {fld} = {part} but the column is {v}",
                    "grade_mismatch",
                )
            )
    return out
