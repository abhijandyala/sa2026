"""Grower observations and soil tests, kept as evidence separate from weather and soil survey data.

Each record carries its observation date and (optionally) a zone. Evidence is never merged into the
USDA soil survey or the weather history: it is passed alongside them with ``derivation: "grower"``
so every number shows where it came from. The API is stateless, so evidence is supplied per request.
Evidence is never written to logs.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Grower soil-test fields that map onto rule-engine inputs (see ``metrics.rules.NUMERIC_INPUTS``).
_SOIL_TEST_INPUTS = {"soil_ph": "soil_ph"}
# Grower observations that map onto rule-engine inputs.
_OBSERVATION_INPUTS = {
    "soil_temp_f": "soil_temp_f",
    "water_table_depth_in": "water_table_depth_in",
}
# Accepted units per mapped observation, as functions into the input's own unit. A unit that is
# not listed is rejected rather than silently read in the input's unit.
_UNIT_TO_INPUT = {
    "soil_temp_f": {
        None: lambda v: v, "f": lambda v: v, "degf": lambda v: v, "\u00b0f": lambda v: v,
        "c": lambda v: v * 9 / 5 + 32, "degc": lambda v: v * 9 / 5 + 32,
        "\u00b0c": lambda v: v * 9 / 5 + 32,
    },
    "water_table_depth_in": {
        None: lambda v: v, "in": lambda v: v, "inch": lambda v: v, "inches": lambda v: v,
        "cm": lambda v: v / 2.54, "m": lambda v: v * 39.37007874, "ft": lambda v: v * 12,
    },
}  # fmt: skip


def _unit_key(unit: str | None) -> str | None:
    return unit.strip().lower() if unit and unit.strip() else None


class _Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observed_on: date
    zone_id: str | None = None
    note: str | None = None
    derivation: Literal["grower"] = "grower"


class GrowerObservation(_Evidence):
    """A field observation: ponding, seedbed moisture, soil temperature, regrading, ..."""

    kind: str = Field(min_length=1)
    value: float | str | bool | None = None
    unit: str | None = None

    @field_validator("value")
    @classmethod
    def _finite(cls, v: Any) -> Any:
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError("value must be finite")
        return v

    @model_validator(mode="after")
    def _unit_is_usable(self) -> GrowerObservation:
        table = _UNIT_TO_INPUT.get(self.kind)
        if table is not None and _unit_key(self.unit) not in table:
            raise ValueError(
                f"unit '{self.unit}' is not supported for {self.kind}; use one of "
                f"{sorted(k for k in table if k)}"
            )
        return self


class SoilTest(_Evidence):
    """One soil-test result from a lab report. ``None`` means "not reported"; 0 is a real value."""

    lab: str | None = None
    soil_ph: float | None = None
    p_index: float | None = None
    k_index: float | None = None
    organic_matter_pct: float | None = None

    @field_validator("soil_ph", "p_index", "k_index", "organic_matter_pct")
    @classmethod
    def _finite(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("value must be finite")
        return v


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observations: list[GrowerObservation] = Field(default_factory=list)
    soil_tests: list[SoilTest] = Field(default_factory=list)

    def latest_inputs(self, *, zone_id: str | None = None) -> dict[str, dict[str, Any]]:
        """Most recent value per rule-engine input, each with its date, zone and derivation.

        If ``zone_id`` is given, only evidence for that zone (or with no zone) is used.
        """
        found: dict[str, dict[str, Any]] = {}

        def consider(name: str, value: Any, ev: _Evidence) -> None:
            if value is None or isinstance(value, (str, bool)):
                return
            if zone_id is not None and ev.zone_id not in (None, zone_id):
                return
            cur = found.get(name)
            if cur is None or ev.observed_on > cur["observed_on"]:
                found[name] = {
                    "value": value,
                    "observed_on": ev.observed_on,
                    "zone_id": ev.zone_id,
                    "derivation": ev.derivation,
                }

        for t in self.soil_tests:
            for attr, name in _SOIL_TEST_INPUTS.items():
                consider(name, getattr(t, attr), t)
        for o in self.observations:
            if o.kind in _OBSERVATION_INPUTS and isinstance(o.value, int | float):
                convert = _UNIT_TO_INPUT[o.kind][_unit_key(o.unit)]
                consider(_OBSERVATION_INPUTS[o.kind], convert(float(o.value)), o)
        return found

    def as_rule_inputs(self, *, zone_id: str | None = None) -> dict[str, float]:
        return {k: v["value"] for k, v in self.latest_inputs(zone_id=zone_id).items()}
