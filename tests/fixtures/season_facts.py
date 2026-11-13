"""SYNTHETIC FIXTURES (not real weather or grower data): SeasonFacts-shaped dicts.

Shape follows the ``SeasonFacts`` contract in CLAUDE.md §2. Missing values are ``None`` with a
status, never 0.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from typing import Any


def season_facts(
    *,
    year: int = 2010,
    sequence: tuple[str, ...] = ("field_corn", "cereal_rye", "soybean"),
    region: str = "NC Piedmont",
    production_system: Any = "no-till",
    plant: date | None = None,
    gap_days: int | None = 12,
    harvest: date | None = None,
    seed: date | None = None,
    spring_status: str = "complete",
    is_dry: bool | None = False,
    concern: bool | None = None,
    observations: Any = None,
    plan_id: str = "fixture_plan",
) -> dict[str, Any]:
    plant = plant or date(year, 5, 12)
    terminate = plant - timedelta(days=gap_days) if gap_days is not None else None
    return {
        "year": year,
        "plan_id": plan_id,
        "crop_sequence": list(sequence),
        "region": region,
        "production_system": production_system,
        "dates": {
            "harvest": harvest or date(year - 1, 9, 20),
            "seed": seed or date(year - 1, 10, 5),
            "terminate": terminate,
            "plant": plant,
            "spring_window": (plant - timedelta(days=30), plant - timedelta(days=1)),
        },
        "termination_gap_days": gap_days,
        "spring": {
            "total_mm": 55.0 if spring_status == "complete" else None,
            "rank": 9 if spring_status == "complete" else None,
            "percentile": 0.2 if spring_status == "complete" else None,
            "is_dry": is_dry if spring_status == "complete" else None,
            "status": spring_status,
        },
        "wetness": {"gwettop": None, "gwetroot": None, "status": "unavailable"},
        "grower": {
            "low_moisture_concern": concern,
            "residue_report": None,
            "observations": observations if observations is not None else {},
        },
        "coverage": {"spring": spring_status},
    }


def frozen_copy(facts: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(facts)
