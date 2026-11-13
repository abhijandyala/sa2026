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

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Grower soil-test fields that map onto rule-engine inputs (see ``metrics.rules.NUMERIC_INPUTS``).
_SOIL_TEST_INPUTS = {"soil_ph": "soil_ph"}
# Grower observations that map onto rule-engine inputs.
_OBSERVATION_INPUTS = {
    "soil_temp_f": "soil_temp_f",
    "water_table_depth_in": "water_table_depth_in",
}


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
            if o.kind in _OBSERVATION_INPUTS:
                consider(_OBSERVATION_INPUTS[o.kind], o.value, o)
        return found

    def as_rule_inputs(self, *, zone_id: str | None = None) -> dict[str, float]:
        return {k: v["value"] for k, v in self.latest_inputs(zone_id=zone_id).items()}
