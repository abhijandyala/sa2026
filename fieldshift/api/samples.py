"""Sample plans and rotations for the Union County reference location (``data/samples``)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from fieldshift.contracts import Plan, Rotation

SAMPLES_PATH = Path(__file__).resolve().parents[2] / "data" / "samples" / "union_plans.json"


@dataclass(frozen=True)
class SamplePlan:
    plan_id: str
    plan: Plan | None
    meta: dict[str, Any]  # rotation_id, leg, dates_assumed, editable, unavailable, label


@dataclass(frozen=True)
class Samples:
    plans: dict[str, SamplePlan]
    rotations: dict[str, Rotation]


@lru_cache(maxsize=1)
def load_samples() -> Samples:
    doc = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))
    plans: dict[str, SamplePlan] = {}
    for s in doc["samples"]:
        plan = Plan.model_validate(s["plan"]) if s.get("plan") else None
        meta = {k: s.get(k) for k in ("rotation_id", "leg", "dates_assumed", "editable",
                                      "unavailable", "label", "note")}
        plans[s["plan_id"]] = SamplePlan(s["plan_id"], plan, meta)
    rotations = {r["rotation_id"]: Rotation.model_validate(r) for r in doc["rotations"]}
    return Samples(plans=plans, rotations=rotations)
