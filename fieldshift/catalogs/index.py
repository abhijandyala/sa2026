"""Lookup index over a loaded :class:`Catalog` (usable rows only)."""

from __future__ import annotations

from collections import defaultdict

from fieldshift.catalogs.loader import Catalog
from fieldshift.catalogs.models import Crop, CropRule, Fertilizer


def _norm(s: str | None) -> str | None:
    return s.strip().lower() if s else None


class CatalogIndex:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.crops: dict[str, Crop] = {c.crop_id: c for c in catalog.crops}
        self.rules: dict[str, CropRule] = {r.rule_id: r for r in catalog.rules}
        self.fertilizers: dict[str, Fertilizer] = {f.fertilizer_id: f for f in catalog.fertilizers}
        self._by_crop: dict[str, list[CropRule]] = defaultdict(list)
        self._by_type: dict[str, list[CropRule]] = defaultdict(list)
        self._by_prev: dict[str, list[CropRule]] = defaultdict(list)
        self._by_next: dict[str, list[CropRule]] = defaultdict(list)
        self._by_region: dict[str, list[CropRule]] = defaultdict(list)
        self._by_system: dict[str, list[CropRule]] = defaultdict(list)
        for r in catalog.rules:  # catalog order is preserved in every bucket
            self._by_crop[r.crop_id].append(r)
            if r.rule_type:
                self._by_type[r.rule_type].append(r)
            if r.previous_crop_id:
                self._by_prev[r.previous_crop_id].append(r)
            if r.next_crop_id:
                self._by_next[r.next_crop_id].append(r)
            if reg := _norm(r.region):
                self._by_region[reg].append(r)
            if sys_ := _norm(r.production_system):
                self._by_system[sys_].append(r)

    @property
    def version(self) -> str:
        return self.catalog.version

    def crop(self, crop_id: str) -> Crop | None:
        return self.crops.get(crop_id)

    def rule(self, rule_id: str) -> CropRule | None:
        return self.rules.get(rule_id)

    def rules_for_crop(self, crop_id: str) -> list[CropRule]:
        return list(self._by_crop.get(crop_id, []))

    def rules_by_type(self, rule_type: str) -> list[CropRule]:
        return list(self._by_type.get(rule_type, []))

    def rules_with_previous_crop(self, crop_id: str) -> list[CropRule]:
        return list(self._by_prev.get(crop_id, []))

    def rules_with_next_crop(self, crop_id: str) -> list[CropRule]:
        return list(self._by_next.get(crop_id, []))

    def rules_for_region(self, region: str) -> list[CropRule]:
        """Exact (case-insensitive) match on the rule's ``region`` text."""
        return list(self._by_region.get(_norm(region) or "", []))

    def rules_for_production_system(self, system: str) -> list[CropRule]:
        return list(self._by_system.get(_norm(system) or "", []))

    def regions(self) -> list[str]:
        """Distinct region strings exactly as written in the catalog."""
        return sorted({r.region for r in self.catalog.rules if r.region})

    def rules_matching(
        self,
        *,
        crop_id: str | None = None,
        rule_type: str | None = None,
        previous_crop_id: str | None = None,
        next_crop_id: str | None = None,
        production_system: str | None = None,
    ) -> list[CropRule]:
        """AND-filter over indexed fields; ``None`` means "do not filter on this"."""
        out = []
        for r in self.catalog.rules:
            if crop_id is not None and r.crop_id != crop_id:
                continue
            if rule_type is not None and r.rule_type != rule_type:
                continue
            if previous_crop_id is not None and r.previous_crop_id != previous_crop_id:
                continue
            if next_crop_id is not None and r.next_crop_id != next_crop_id:
                continue
            if production_system is not None and _norm(r.production_system) != _norm(
                production_system
            ):
                continue
            out.append(r)
        return out

    def cash_crops(self) -> list[Crop]:
        return [c for c in self.catalog.crops if c.crop_role == "cash_crop"]

    def cover_crops(self) -> list[Crop]:
        return [c for c in self.catalog.crops if c.crop_role == "cover_crop"]
