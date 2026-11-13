"""Load and validate the reference catalogs.

``load_catalog(dir)`` returns a :class:`Catalog` holding the *usable* rows and
every :class:`ValidationIssue`. A row with any ``error`` issue is dropped; a row
with only warnings (for example a blank ``verified_date``) is kept. One bad row
never blocks the rest.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TypeVar

from fieldshift.catalogs import validate
from fieldshift.catalogs.models import Crop, CropRule, Fertilizer, ValidationIssue

T = TypeVar("T")  # no PEP 695 syntax: the shared checkout also runs on Python 3.11

CATALOGS_ROOT = Path(__file__).resolve().parents[2] / "data" / "catalogs"
V1_CATALOG_DIR = CATALOGS_ROOT / "v1"
V2_CATALOG_DIR = CATALOGS_ROOT / "v2"
DEFAULT_CATALOG_DIR = (
    V2_CATALOG_DIR  # v2 (2026-11-13) is the working catalog; v1 stays for regressions
)

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class FileManifest:
    file: str
    sha256: str
    rows: int
    usable_rows: int
    errors: int
    warnings: int


@dataclass(frozen=True)
class CatalogManifest:
    version: str
    content_hash: str
    loaded_at: str
    files: dict[str, FileManifest]

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "content_hash": self.content_hash,
            "loaded_at": self.loaded_at,
            "files": {k: v.__dict__ for k, v in self.files.items()},
        }


@dataclass
class Catalog:
    version: str
    directory: Path
    crops: list[Crop]
    rules: list[CropRule]
    fertilizers: list[Fertilizer]
    issues: list[ValidationIssue]
    manifest: CatalogManifest
    # Spreadsheet row of each usable record, keyed by (file, id).
    row_of: dict[tuple[str, str], int] = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def issues_for(self, file: str, row: int | None = None) -> list[ValidationIssue]:
        return [i for i in self.issues if i.file == file and (row is None or i.row == row)]

    def rule_ids_with_warning(self, code: str) -> list[str]:
        """Rule ids that carry a warning with this code (e.g. ``verified_blank``)."""
        rows = {i.row for i in self.warnings if i.file == validate.RULES_FILE and i.code == code}
        return [
            r.rule_id for r in self.rules if self.row_of[(validate.RULES_FILE, r.rule_id)] in rows
        ]


# --------------------------------------------------------------------------- cell parsing


def _blank(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    return s or None


class _RowParser:
    """Converts one raw CSV row into typed values, recording type-level issues."""

    def __init__(
        self, file: str, row: int, raw: dict[str, str | None], issues: list[ValidationIssue]
    ):
        self.file, self.row, self.raw, self.issues = file, row, raw, issues

    def text(self, name: str) -> str | None:
        return _blank(self.raw.get(name))

    def number(self, name: str) -> float | None:
        s = self.text(name)
        if s is None:
            return None
        try:
            value = float(s)
            if not math.isfinite(value):
                raise ValueError(s)
            return value
        except ValueError:
            self.issues.append(
                ValidationIssue(
                    self.file, self.row, name, "error", f"'{s}' is not a number", "not_a_number"
                )
            )
            return None

    def day(self, name: str) -> date | None:
        s = self.text(name)
        if s is None:
            return None
        try:
            if not _ISO_DATE_RE.match(s):
                raise ValueError(s)
            return date.fromisoformat(s)
        except ValueError:
            self.issues.append(
                ValidationIssue(
                    self.file,
                    self.row,
                    name,
                    "error",
                    f"'{s}' is not a YYYY-MM-DD date",
                    "date_format",
                )
            )
            return None


def _parse_crop(p: _RowParser) -> Crop | None:
    cid = p.text("crop_id")
    if cid is None:
        p.issues.append(
            ValidationIssue(p.file, p.row, "crop_id", "error", "crop_id is required", "id_missing")
        )
        return None
    return Crop(
        crop_id=cid,
        **{k: p.text(k) for k in (
            "common_name", "scientific_name", "crop_role", "summary",
            "source_title", "source_url", "source_locator",
        )},
        verified_date=p.day("verified_date"),
    )  # fmt: skip


def _parse_rule(p: _RowParser) -> CropRule | None:
    rid, cid = p.text("rule_id"), p.text("crop_id")
    if rid is None or cid is None:
        for name, v in (("rule_id", rid), ("crop_id", cid)):
            if v is None:
                p.issues.append(
                    ValidationIssue(
                        p.file, p.row, name, "error", f"{name} is required", "id_missing"
                    )
                )
        return None
    text_fields = (
        "region", "rule_type", "growth_stage", "management_action", "cultivar_or_maturity_group",
        "production_system", "previous_crop_id", "next_crop_id", "window_start_mm_dd",
        "window_end_mm_dd", "condition_key", "operator", "value_text", "unit", "exposure_unit",
        "suitability", "applies_when", "guidance", "source_title", "source_url", "source_locator",
    )  # fmt: skip
    # exposure_duration: numeric when numeric; otherwise kept as qualitative text ("several").
    exp_text = p.text("exposure_duration")
    exp_num: float | None = None
    exp_qual: str | None = None
    if exp_text is not None:
        try:
            exp_num = float(exp_text)
        except ValueError:
            exp_qual = exp_text
        else:
            if not math.isfinite(exp_num):  # "nan" / "inf" are not durations
                p.issues.append(
                    ValidationIssue(
                        p.file, p.row, "exposure_duration", "error",
                        f"'{exp_text}' is not a finite number", "not_a_number",
                    )
                )  # fmt: skip
                exp_num = None
    return CropRule(
        rule_id=rid,
        crop_id=cid,
        **{k: p.text(k) for k in text_fields},
        value_min=p.number("value_min"),
        value_max=p.number("value_max"),
        exposure_duration=exp_num,
        exposure_duration_text=exp_qual,
        verified_date=p.day("verified_date"),
    )


def _parse_fertilizer(p: _RowParser) -> Fertilizer | None:
    fid = p.text("fertilizer_id")
    if fid is None:
        p.issues.append(
            ValidationIssue(
                p.file, p.row, "fertilizer_id", "error", "fertilizer_id is required", "id_missing"
            )
        )
        return None
    return Fertilizer(
        fertilizer_id=fid,
        **{k: p.text(k) for k in (
            "product_name", "manufacturer", "grade", "source_title", "source_url", "source_locator",
        )},
        n_pct=p.number("n_pct"),
        p2o5_pct=p.number("p2o5_pct"),
        k2o_pct=p.number("k2o_pct"),
        verified_date=p.day("verified_date"),
    )  # fmt: skip


# --------------------------------------------------------------------------- file reading


def _read_file(
    path: Path, file: str, parse: Callable[[_RowParser], T | None], issues: list[ValidationIssue]
) -> tuple[list[tuple[int, T]], int, str]:
    """Return ``(parsed rows, raw row count, sha256)``."""
    if not path.exists():
        issues.append(
            ValidationIssue(file, None, "file", "error", f"{file} not found", "file_missing")
        )
        return [], 0, ""
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""))
    try:
        header = next(reader)
    except StopIteration:
        issues.append(
            ValidationIssue(file, 1, "header", "error", "file is empty", "header_missing")
        )
        return [], 0, digest
    h_issues, loadable = validate.check_header(file, header)
    issues += h_issues
    if not loadable:
        return [], 0, digest
    names = [h.strip() for h in header]
    out: list[tuple[int, T]] = []
    count = 0
    for row_no, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue  # fully blank line
        count += 1
        if len(cells) != len(names):
            issues.append(
                ValidationIssue(
                    file, row_no, "row", "error",
                    f"row has {len(cells)} cells, header has {len(names)}", "row_width",
                )
            )  # fmt: skip
            continue
        rec = parse(_RowParser(file, row_no, dict(zip(names, cells, strict=True)), issues))
        if rec is not None:
            out.append((row_no, rec))
    return out, count, digest


def _usable(
    rows: list[tuple[int, T]], issues: list[ValidationIssue], file: str
) -> list[tuple[int, T]]:
    bad = {i.row for i in issues if i.file == file and i.severity == "error"}
    return [(r, x) for r, x in rows if r not in bad]


def load_catalog(directory: Path | str = DEFAULT_CATALOG_DIR) -> Catalog:
    directory = Path(directory)
    issues: list[ValidationIssue] = []

    crops, n_crops, h_crops = _read_file(
        directory / validate.CROPS_FILE, validate.CROPS_FILE, _parse_crop, issues
    )
    rules, n_rules, h_rules = _read_file(
        directory / validate.RULES_FILE, validate.RULES_FILE, _parse_rule, issues
    )
    ferts, n_ferts, h_ferts = _read_file(
        directory / validate.FERTILIZERS_FILE, validate.FERTILIZERS_FILE, _parse_fertilizer, issues
    )

    crop_issues = validate.validate_crops(crops)
    issues += crop_issues
    # Rules may only reference crops that survived validation.
    usable_crop_ids = {c.crop_id for _, c in _usable(crops, issues, validate.CROPS_FILE)}
    issues += validate.validate_rules(rules, usable_crop_ids)
    issues += validate.validate_fertilizers(ferts)

    # Stable order: by file, then row, then field.
    order = {validate.CROPS_FILE: 0, validate.RULES_FILE: 1, validate.FERTILIZERS_FILE: 2}
    issues.sort(key=lambda i: (order.get(i.file, 9), i.row or 0, i.field, i.code))

    u_crops = _usable(crops, issues, validate.CROPS_FILE)
    u_rules = _usable(rules, issues, validate.RULES_FILE)
    u_ferts = _usable(ferts, issues, validate.FERTILIZERS_FILE)

    row_of: dict[tuple[str, str], int] = {}
    for r, c in u_crops:
        row_of[(validate.CROPS_FILE, c.crop_id)] = r
    for r, x in u_rules:
        row_of[(validate.RULES_FILE, x.rule_id)] = r
    for r, f in u_ferts:
        row_of[(validate.FERTILIZERS_FILE, f.fertilizer_id)] = r

    counts = {
        f: Counter(i.severity for i in issues if i.file == f)
        for f in (validate.CROPS_FILE, validate.RULES_FILE, validate.FERTILIZERS_FILE)
    }

    def fm(file: str, digest: str, total: int, usable: int) -> FileManifest:
        return FileManifest(
            file, digest, total, usable, counts[file]["error"], counts[file]["warning"]
        )

    files = {
        validate.CROPS_FILE: fm(validate.CROPS_FILE, h_crops, n_crops, len(u_crops)),
        validate.RULES_FILE: fm(validate.RULES_FILE, h_rules, n_rules, len(u_rules)),
        validate.FERTILIZERS_FILE: fm(validate.FERTILIZERS_FILE, h_ferts, n_ferts, len(u_ferts)),
    }
    content_hash = hashlib.sha256(
        "".join(files[k].sha256 for k in sorted(files)).encode()
    ).hexdigest()
    manifest = CatalogManifest(
        version=directory.name,
        content_hash=content_hash,
        loaded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        files=files,
    )
    return Catalog(
        version=directory.name,
        directory=directory,
        crops=[c for _, c in u_crops],
        rules=[x for _, x in u_rules],
        fertilizers=[f for _, f in u_ferts],
        issues=issues,
        manifest=manifest,
        row_of=row_of,
    )
