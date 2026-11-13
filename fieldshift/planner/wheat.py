"""Winter wheat double-crop path (Phase 12): what the catalog can and cannot evaluate.

Catalog v2 has wheat and double-crop soybean rows, but no numeric Piedmont calendar windows: the
wheat planting window is relative to a regional map, harvest timing is context only, and the
double-crop soybean window is prose. So the wheat harvest and soybean planting dates are entered by
the grower, and the qualitative or map-based rows are shown as ``manual_check``.
"""

from __future__ import annotations

from fieldshift.catalogs.index import CatalogIndex
from fieldshift.contracts import Status

WHEAT = "winter_wheat"


def wheat_catalog_state(index: CatalogIndex, crop_id: str = WHEAT) -> tuple[Status, str | None]:
    """``(unavailable | partial | complete, reason)`` for the wheat double-crop path."""
    rules = index.rules_for_crop(crop_id)
    types = {r.rule_type for r in rules}
    if "planting_window" not in types:
        return Status.UNAVAILABLE, (
            f"catalog_missing: no planting_window rows for {crop_id} or for double-crop soybean; "
            "only rotation rules are evaluated"
        )
    if not any(r.window_start_mm_dd and r.window_end_mm_dd for r in rules):
        return Status.PARTIAL, (
            "the catalog has no numeric Piedmont calendar windows for winter wheat or double-crop "
            "soybean; the wheat harvest and soybean planting dates are entered by the grower, "
            "the maturity-group rows are checked, and qualitative or map-based rows are manual_check"
        )
    return Status.COMPLETE, None
