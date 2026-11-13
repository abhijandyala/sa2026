"""Shared contracts: the types both agents build against (owner: Agent A).

Propose changes in ``docs/handoff.md``. Conventions (CLAUDE.md):

* a missing value is ``None`` paired with a status, never ``0``;
* a real ``0`` stays ``0``;
* status strings are exactly the :class:`Status` values;
* every threshold is computed once and frozen in a :class:`ThresholdSet`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


class Status(StrEnum):
    """The only status vocabulary. Use these exact strings."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    INAPPLICABLE = "inapplicable"
    UNSUPPORTED = "unsupported"
    INVALID_INPUT = "invalid_input"
    MANUAL_CHECK = "manual_check"
    INSUFFICIENT_DATA = "insufficient_data"


_MD_RE = re.compile(r"^(\d{2})-(\d{2})$")


def _check_month_day(value: str) -> str:
    m = _MD_RE.match(value)
    if not m:
        raise ValueError("expected MM-DD")
    month, day = int(m.group(1)), int(m.group(2))
    try:
        date(2000, month, day)  # 2000 is a leap year, so 02-29 is accepted
    except ValueError as exc:
        raise ValueError(f"{value} is not a real calendar date") from exc
    return value


MonthDay = Annotated[str, AfterValidator(_check_month_day)]
"""``MM-DD``. ``02-29`` is allowed and resolves to Feb 28 in non-leap years."""


class FrozenDict(dict):
    """A dict that rejects mutation, so frozen thresholds cannot change after creation."""

    def _blocked(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("FrozenDict is immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _blocked  # type: ignore[assignment]

    def __ior__(self, other: Any) -> Any:  # type: ignore[override]
        raise TypeError("FrozenDict is immutable")


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return FrozenDict({k: _deep_freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(v) for v in value)
    return value


FrozenMap = Annotated[dict[str, Any], AfterValidator(_deep_freeze)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- errors


class FieldIssue(_Model):
    """One typed validation problem, attached to the input field that caused it."""

    field: str
    code: str
    message: str


class InvalidPlanError(ValueError):
    """Raised for an invalid plan. Carries typed issues; status is always ``invalid_input``."""

    status = Status.INVALID_INPUT

    def __init__(self, issues: list[FieldIssue]):
        self.issues = issues
        super().__init__("; ".join(f"{i.field}: {i.message}" for i in issues))

    def as_body(self) -> dict[str, Any]:
        return {"status": self.status.value, "issues": [i.model_dump() for i in self.issues]}


# --------------------------------------------------------------------------- plan


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


class WinterManagement(_Model):
    """What occupies the field between the previous harvest and the next planting.

    * ``none``: bare/fallow (any crop residue is context only, never living cover);
    * ``cover``: a cover crop seeded then terminated;
    * ``winter_grain``: a harvested winter grain (Phase 12; double-crop path).
    """

    kind: Literal["none", "cover", "winter_grain"] = "none"
    crop_id: str | None = None
    seed: MonthDay | None = None
    terminate: MonthDay | None = None
    plant: MonthDay | None = None
    harvest: MonthDay | None = None

    @model_validator(mode="after")
    def _fields_match_kind(self) -> WinterManagement:
        needs = {
            "none": (),
            "cover": ("crop_id", "seed", "terminate"),
            "winter_grain": ("crop_id", "plant", "harvest"),
        }[self.kind]
        missing = [f for f in needs if _blank(getattr(self, f))]
        if missing:
            raise ValueError(f"winter kind '{self.kind}' requires {', '.join(missing)}")
        stray = {
            "none": ("crop_id", "seed", "terminate", "plant", "harvest"),
            "cover": ("plant", "harvest"),
            "winter_grain": ("seed", "terminate"),
        }[self.kind]
        extra = [f for f in stray if getattr(self, f) is not None]
        if extra:
            raise ValueError(f"winter kind '{self.kind}' does not use {', '.join(extra)}")
        return self


class GrowerInputs(_Model):
    """Grower-reported context. Kept separate from weather evidence and never logged."""

    low_moisture_concern: bool | None = None  # None = not reported (unknown)
    residue_report: str | None = None
    observations: list[str] = Field(default_factory=list)


class Plan(_Model):
    """One crop sequence: previous crop -> winter management -> next crop."""

    plan_id: Annotated[str, Field(min_length=1)]
    label: str | None = None
    previous_crop_id: Annotated[str, Field(min_length=1)]
    prev_harvest: MonthDay
    winter: WinterManagement = Field(default_factory=WinterManagement)
    next_crop_id: Annotated[str, Field(min_length=1)]
    next_plant: MonthDay
    region: str | None = None
    production_system: str | None = None
    grower: GrowerInputs = Field(default_factory=GrowerInputs)


class Rotation(_Model):
    """A preset: two plan legs (corn->soybean winter, soybean->corn winter). Never summed."""

    rotation_id: str
    label: str
    legs: list[str]  # plan_ids, in leg order


# --------------------------------------------------------------------------- calendar


class CoverInterval(_Model):
    """``[seed, terminate)``: terminate day is NOT planned living cover. Always planned."""

    crop_id: str
    seed: date
    terminate: date
    days: int
    label: Literal["planned"] = "planned"
    establishment: Literal["uncertain"] = "uncertain"


class GrainInterval(_Model):
    crop_id: str
    plant: date
    harvest: date
    days: int
    label: Literal["planned"] = "planned"


class SeasonCalendar(_Model):
    """One plan resolved onto one planting year ``year`` (the year of next planting)."""

    plan_id: str
    year: int
    prev_harvest: date  # first day of the winter window (inclusive)
    plant: date  # planting day: end of the winter window (exclusive)
    winter_days: int  # len([prev_harvest, plant))
    spring_start: date  # plant - 30 d (inclusive)
    spring_end: date  # plant - 1 d (inclusive)
    spring_days: int
    cover: CoverInterval | None = None
    grain: GrainInterval | None = None
    termination_gap_days: int | None = None  # plant - terminate (cover plans only)


# --------------------------------------------------------------------------- thresholds


class Threshold(_Model):
    """One frozen threshold with the method and reference span that produced it."""

    name: str
    method: str
    value: float | None
    unit: str
    parameters: FrozenMap = Field(default_factory=FrozenDict)
    reference_span: str
    n_reference: int
    status: Status = Status.COMPLETE
    note: str | None = None


class ThresholdSet(_Model):
    """All thresholds for one weather snapshot, computed once and shared by every plan and era."""

    snapshot_hash: str
    thresholds: Annotated[dict[str, Threshold], AfterValidator(_deep_freeze)]

    @property
    def threshold_set_id(self) -> str:
        blob = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def get(self, name: str) -> Threshold:
        return self.thresholds[name]


# --------------------------------------------------------------------------- results


class MetricResult(_Model):
    """A single named result. ``value`` is ``None`` whenever ``status`` is not complete."""

    name: str
    status: Status
    value: float | int | None = None
    unit: str | None = None
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- season facts


class SeasonDates(_Model):
    harvest: date
    seed: date | None = None
    terminate: date | None = None
    plant: date
    spring_start: date
    spring_end: date


class SpringFacts(_Model):
    total_mm: float | None = None
    rank: int | None = None  # 1 = driest
    percentile: float | None = None
    is_dry: bool | None = None  # None when the metric is unavailable
    status: Status = Status.UNAVAILABLE


class WetnessFacts(_Model):
    gwettop: float | None = None  # modeled window mean
    gwetroot: float | None = None  # modeled window mean
    status: Status = Status.UNAVAILABLE
    label: Literal["modeled"] = "modeled"


class GrowerFacts(_Model):
    low_moisture_concern: bool | None = None
    residue_report: str | None = None
    observations: list[str] = Field(default_factory=list)


class SeasonFacts(_Model):
    """One season for one plan: the single input the rule engine consumes."""

    year: int
    plan_id: str
    crop_sequence: list[str]  # [previous_crop_id, (winter crop_id), next_crop_id]
    region: str | None = None
    production_system: str | None = None
    dates: SeasonDates
    termination_gap_days: int | None = None
    spring: SpringFacts = Field(default_factory=SpringFacts)
    wetness: WetnessFacts = Field(default_factory=WetnessFacts)
    grower: GrowerFacts = Field(default_factory=GrowerFacts)
    coverage: dict[str, Status] = Field(default_factory=dict)  # per-metric status
