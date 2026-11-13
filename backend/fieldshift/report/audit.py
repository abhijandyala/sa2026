"""Audit trail: every number a report shows resolves to an entry saying where it came from.

A report number is an object ``{"value": 12, "unit": "days", "audit_id": "a1b2c3d4e5"}``. The id
points at an entry in the report's ``audit.entries``:

    {value, unit, derivation, source_ref, inputs, label}

``derivation`` says what kind of number it is:

* ``nasa``        a weather value taken or aggregated from the NASA POWER snapshot,
* ``usda``        a soil-survey value from USDA Soil Data Access,
* ``extension``   a number published by a catalog source (NC State Extension, SARE, NCDA&CS, ...),
* ``grower``      a value the grower entered (dates, concerns, observations),
* ``calculation`` computed here from other audited numbers (counts, shares, differences),
* ``assumed``     a demo default that is not grower-entered (sample plan dates).

Identifiers that look like numbers (years) are shown as strings, never as quantities. Entries with
identical content share one id, so the audit is deterministic.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel

DERIVATIONS = ("nasa", "usda", "extension", "grower", "calculation", "assumed")
UNCLASSIFIED = "unclassified"
_VALUE_KEYS = frozenset({"value", "unit", "audit_id"})


class AuditError(ValueError):
    pass


class AuditEntry(BaseModel):
    audit_id: str
    value: float | int
    unit: str | None
    derivation: str
    source_ref: dict[str, Any]
    inputs: dict[str, Any]
    label: str | None = None


def source_ref(kind: str, ref: str | None = None, **extra: Any) -> dict[str, Any]:
    """A uniform pointer to where a number comes from (snapshot, catalog rule, plan input, ...)."""
    return {"kind": kind, "ref": ref, **{k: v for k, v in extra.items() if v is not None}}


class AuditBook:
    """Collects entries while a report is built."""

    def __init__(self) -> None:
        self._entries: dict[str, AuditEntry] = {}

    def num(
        self,
        value: float | int | None,
        unit: str | None,
        derivation: str,
        ref: dict[str, Any],
        inputs: dict[str, Any] | None = None,
        label: str | None = None,
    ) -> dict[str, Any] | None:
        """Audited number, or ``None`` for a missing value (a missing value is not a number)."""
        if value is None:
            return None
        if derivation not in (*DERIVATIONS, UNCLASSIFIED):
            raise AuditError(f"unknown derivation '{derivation}'")
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
        ):
            raise AuditError(f"not a finite number: {value!r}")
        body = {
            "value": value, "unit": unit, "derivation": derivation, "source_ref": ref,
            "inputs": inputs or {}, "label": label,
        }  # fmt: skip
        blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        aid = "a" + hashlib.sha256(blob.encode()).hexdigest()[:10]
        if aid not in self._entries:
            self._entries[aid] = AuditEntry(audit_id=aid, **body)
        return {"value": value, "unit": unit, "audit_id": aid}

    @property
    def entries(self) -> dict[str, AuditEntry]:
        return dict(sorted(self._entries.items()))

    def as_dict(self) -> dict[str, Any]:
        entries = self.entries
        return {
            "entries": {k: v.model_dump(mode="json") for k, v in entries.items()},
            "count": len(entries),
            "unclassified": sum(1 for e in entries.values() if e.derivation == UNCLASSIFIED),
            "derivations": sorted({e.derivation for e in entries.values()}),
        }


def is_audited_number(obj: Any) -> bool:
    return isinstance(obj, dict) and set(obj) == _VALUE_KEYS


def bare_numbers(tree: Any, path: str = "") -> Iterator[tuple[str, float | int]]:
    """Yield ``(path, value)`` for every numeric leaf that is NOT an audited number."""
    if is_audited_number(tree):
        return
    if isinstance(tree, bool) or tree is None or isinstance(tree, str):
        return
    if isinstance(tree, int | float):
        yield path, tree
    elif isinstance(tree, dict):
        for k, v in tree.items():
            yield from bare_numbers(v, f"{path}.{k}" if path else str(k))
    elif isinstance(tree, list | tuple):
        for i, v in enumerate(tree):
            yield from bare_numbers(v, f"{path}[{i}]")


def audited_numbers(tree: Any, path: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    if is_audited_number(tree):
        yield path, tree
    elif isinstance(tree, dict):
        for k, v in tree.items():
            yield from audited_numbers(v, f"{path}.{k}" if path else str(k))
    elif isinstance(tree, list | tuple):
        for i, v in enumerate(tree):
            yield from audited_numbers(v, f"{path}[{i}]")


def finalize(tree: Any, book: AuditBook, path: str = "") -> Any:
    """Make the tree fully audited: year-like integers become strings, any other bare number
    becomes an ``unclassified`` audit entry (tests assert there are none)."""
    if is_audited_number(tree) or tree is None or isinstance(tree, str | bool):
        return tree
    if isinstance(tree, int | float):
        last = path.rsplit(".", 1)[-1].split("[")[0]
        if isinstance(tree, int) and ("year" in last or "years" in path.rsplit(".", 1)[-1]):
            return str(tree)
        return book.num(tree, None, UNCLASSIFIED, source_ref("unclassified", path))
    if isinstance(tree, dict):
        return {k: finalize(v, book, f"{path}.{k}" if path else str(k)) for k, v in tree.items()}
    if isinstance(tree, list | tuple):
        return [finalize(v, book, f"{path}[{i}]") for i, v in enumerate(tree)]
    return tree


def verify(note: dict[str, Any]) -> list[str]:
    """Problems with a finished report; empty means every number resolves to an audit entry."""
    problems: list[str] = []
    audit = note.get("audit", {})
    entries = audit.get("entries", {})
    body = {k: v for k, v in note.items() if k != "audit"}
    for path, n in bare_numbers(body):
        problems.append(f"bare number at {path}: {n!r}")
    for path, n in audited_numbers(body):
        e = entries.get(n["audit_id"])
        if e is None:
            problems.append(f"{path}: audit_id {n['audit_id']} has no entry")
        elif e["value"] != n["value"] or e["unit"] != n["unit"]:
            problems.append(f"{path}: value/unit differ from audit entry {n['audit_id']}")
        elif e["derivation"] == UNCLASSIFIED:
            problems.append(f"{path}: number has no classified derivation")
    return problems
