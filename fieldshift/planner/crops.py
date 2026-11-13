"""``GET /v1/crops``: supported crops, their roles, and which evaluation paths are available."""

from __future__ import annotations

from pydantic import BaseModel, Field

from fieldshift.catalogs.index import CatalogIndex
from fieldshift.contracts import Status

#: Rule types a crop needs before each path can be fully evaluated.
REQUIRED_RULE_TYPES: dict[str, dict[str, tuple[str, ...]]] = {
    "cash_crop": {"as_next_crop": ("planting_window",)},
    "cover_crop": {
        "as_winter_cover": ("planting_window", "termination_timing"),
    },
}


class PathAvailability(BaseModel):
    path: str
    status: Status  # complete | partial
    missing_rule_types: list[str] = Field(default_factory=list)
    note: str | None = None


class CropInfo(BaseModel):
    crop_id: str
    common_name: str | None
    scientific_name: str | None
    crop_role: str | None
    summary: str | None
    source_url: str | None
    rule_count: int
    rule_types: dict[str, int]
    paths: list[PathAvailability]


class CropsResponse(BaseModel):
    catalog_version: str
    crops: list[CropInfo]


def list_crops(index: CatalogIndex) -> CropsResponse:
    crops: list[CropInfo] = []
    for crop in index.catalog.crops:
        rules = index.rules_for_crop(crop.crop_id)
        types: dict[str, int] = {}
        for r in rules:
            types[r.rule_type or "unspecified"] = types.get(r.rule_type or "unspecified", 0) + 1
        paths: list[PathAvailability] = []
        for path, required in REQUIRED_RULE_TYPES.get(crop.crop_role or "", {}).items():
            missing = [t for t in required if t not in types]
            paths.append(
                PathAvailability(
                    path=path,
                    status=Status.PARTIAL if missing else Status.COMPLETE,
                    missing_rule_types=missing,
                    note=(
                        "catalog_missing: only rotation rules exist; planting and harvest rows "
                        "are not in the catalog yet"
                        if missing
                        else None
                    ),
                )
            )
        if crop.crop_id == "winter_wheat":
            paths.append(
                PathAvailability(
                    path="winter_grain_double_crop",
                    status=Status.UNAVAILABLE,
                    missing_rule_types=["planting_window", "growth_duration"],
                    note="catalog_missing: wheat planting/harvest and double-crop soybean window",
                )
            )
        crops.append(
            CropInfo(
                crop_id=crop.crop_id,
                common_name=crop.common_name,
                scientific_name=crop.scientific_name,
                crop_role=crop.crop_role,
                summary=crop.summary,
                source_url=crop.source_url,
                rule_count=len(rules),
                rule_types=dict(sorted(types.items())),
                paths=paths,
            )
        )
    return CropsResponse(catalog_version=index.version, crops=crops)
