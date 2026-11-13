"""Process-wide read-only context: the weather snapshot, its series and the catalog index."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from fieldshift.catalogs.index import CatalogIndex
from fieldshift.report.meta import get_index
from fieldshift.weather.series import DailySeries
from fieldshift.weather.snapshot import load_snapshot


@dataclass(frozen=True)
class Context:
    series: DailySeries
    snapshot_hash: str
    manifest: dict[str, Any]
    index: CatalogIndex

    @property
    def location_id(self) -> str:
        return "union_county_sample"


@lru_cache(maxsize=1)
def get_context() -> Context:
    """Load once. Reads only ``data/snapshots/`` and the catalogs; never the network."""
    snap = load_snapshot()
    return Context(
        series=DailySeries(snap.daily),
        snapshot_hash=snap.snapshot_hash,
        manifest=snap.manifest,
        index=get_index(),
    )
