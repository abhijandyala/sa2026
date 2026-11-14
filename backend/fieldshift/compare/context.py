"""Process-wide read-only context: a weather snapshot, its series and the catalog index.

``get_context()`` is the Union County default. ``context_for(entry)`` is the context of any place
in ``data/snapshots/index.json``; each is loaded once. One context is one location: thresholds,
eras and shared-year sets are built from its snapshot only, never across locations.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from fieldshift.catalogs.index import CatalogIndex
from fieldshift.report.meta import get_index
from fieldshift.weather.locations import LocationEntry, load_entry_snapshot
from fieldshift.weather.locations import get_index as get_location_index
from fieldshift.weather.series import DailySeries
from fieldshift.weather.snapshot import load_snapshot

DEFAULT_LOCATION_ID = "union"


@dataclass(frozen=True)
class Context:
    series: DailySeries
    snapshot_hash: str
    manifest: dict[str, Any]
    index: CatalogIndex
    location: LocationEntry | None = None  # None: the Union County default, no lookup made

    @property
    def location_id(self) -> str:
        """``union_county_sample`` for the default context (unchanged), else the place id."""
        if self.location is None or self.location.id == DEFAULT_LOCATION_ID:
            return "union_county_sample"
        return self.location.id

    @property
    def place(self) -> LocationEntry | None:
        """The index row this context serves (the default context serves Union County)."""
        return self.location or get_location_index().by_id(DEFAULT_LOCATION_ID)


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


@lru_cache(maxsize=16)
def _context_for_dir(snapshot_dir: str) -> Context:
    snap = load_entry_snapshot(snapshot_dir)
    return Context(
        series=DailySeries(snap.daily),
        snapshot_hash=snap.snapshot_hash,
        manifest=snap.manifest,
        index=get_index(),
    )


def context_for(entry: LocationEntry) -> Context:
    """The context of one indexed place. Places that share a cell share the loaded snapshot."""
    ctx = _context_for_dir(entry.snapshot_dir)
    if ctx.snapshot_hash != entry.snapshot_hash:
        raise RuntimeError(f"{entry.id}: index hash differs from the loaded snapshot")
    return Context(series=ctx.series, snapshot_hash=ctx.snapshot_hash, manifest=ctx.manifest,
                   index=ctx.index, location=entry)  # fmt: skip
