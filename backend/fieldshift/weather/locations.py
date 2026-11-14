"""The places that have a committed weather snapshot, and the lookup from a point to one.

``data/snapshots/index.json`` lists every place: id, name, point, POWER grid cell, snapshot hash.
Each *grid cell* is stored once. Two places in the same cell (Johnston and Wayne) point at one
snapshot directory, so they always carry the same ``snapshot_hash``.

The lookup is by grid cell, not by distance: a point is served only when it falls in the MERRA-2
cell (0.5 x 0.625 degrees) of a committed snapshot. A cell with no snapshot is "no snapshot",
never a neighbouring cell's weather.

The index is built by ``python -m fieldshift.weather build-locations`` (network, once) and
verified offline by :func:`verify_index`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from fieldshift.weather.snapshot import MANIFEST_NAME, REPO_ROOT, Snapshot, load_snapshot
from fieldshift.weather.sources import derive_grid_cell

SNAPSHOT_ROOT = REPO_ROOT / "data" / "snapshots"
INDEX_PATH = SNAPSHOT_ROOT / "index.json"
INDEX_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Place:
    """A county-centre point from the web place picker (``web/src/content/locations.ts``)."""

    id: str
    name: str
    latitude: float
    longitude: float
    region: str  # the region the place is in: piedmont | coastal_plain (rule applicability is B's)
    # directory under data/snapshots/ that holds its history if it has a cell of its own; a place
    # that shares a cell (Wayne) is served from the earlier place's directory (see index.json)
    snapshot_dir: str
    reference_id: str  # ReferencePoint.id written into the manifest


#: The eight places. Union County keeps the original ``union_county`` directory. The order is the
#: build order, so a place that shares a cell with an earlier one becomes an alias of it.
PLACES: tuple[Place, ...] = (
    Place("union", "Union County", 34.98, -80.55, "piedmont", "union_county", "union_county_nc"),
    Place("iredell", "Iredell County", 35.81, -80.87, "piedmont", "iredell", "iredell_county_nc"),
    Place("rowan", "Rowan County", 35.64, -80.53, "piedmont", "rowan", "rowan_county_nc"),
    Place("johnston", "Johnston County", 35.52, -78.37, "coastal_plain", "johnston",
          "johnston_county_nc"),
    Place("wayne", "Wayne County", 35.36, -77.99, "coastal_plain", "wayne", "wayne_county_nc"),
    Place("duplin", "Duplin County", 34.94, -77.93, "coastal_plain", "duplin", "duplin_county_nc"),
    Place("pitt", "Pitt County", 35.59, -77.37, "coastal_plain", "pitt", "pitt_county_nc"),
    Place("robeson", "Robeson County", 34.64, -79.10, "coastal_plain", "robeson",
          "robeson_county_nc"),
)  # fmt: skip

#: Ids a caller may use for Union County besides ``union`` (the older sample ids).
ALIASES: dict[str, str] = {"union_county": "union", "union_county_nc": "union",
                           "union_county_sample": "union"}  # fmt: skip

COUNTY_BASIS = (
    "approximate county centre used by the web place picker (web/src/content/locations.ts); "
    "a county point, not a farm"
)


def cell_id_for(latitude: float, longitude: float) -> str:
    """Same id format as ``fieldshift.field.location.cell_id`` (kept equal by a test)."""
    cell = derive_grid_cell(latitude, longitude)
    return f"cell_{cell['center_latitude']:+.3f}_{cell['center_longitude']:+.3f}"


@dataclass(frozen=True)
class LocationEntry:
    """One index row: a place, its grid cell, and the snapshot that serves it."""

    id: str
    name: str
    latitude: float
    longitude: float
    region: str
    cell_id: str
    grid_cell: dict[str, Any]
    snapshot_dir: str
    snapshot_hash: str
    first_date: str
    last_date: str
    shares_snapshot_with: str | None  # the place whose directory holds this cell, if not itself

    @property
    def directory(self) -> Path:
        return SNAPSHOT_ROOT / self.snapshot_dir

    def as_public(self) -> dict[str, Any]:
        """The compact block responses carry (``/health`` and ``weather_location``)."""
        return {
            "id": self.id,
            "name": self.name,
            "point": {"latitude": self.latitude, "longitude": self.longitude},
            "region": self.region,
            "grid_cell": {k: self.grid_cell[k] for k in ("center_latitude", "center_longitude")},
            "cell_id": self.cell_id,
            "snapshot_hash": self.snapshot_hash,
            "first_date": self.first_date,
            "last_date": self.last_date,
        }


class IndexError_(RuntimeError):  # noqa: N818 - avoid shadowing the builtin IndexError
    """``index.json`` is missing or malformed."""


@dataclass(frozen=True)
class LocationIndex:
    entries: tuple[LocationEntry, ...]

    def by_id(self, location_id: str) -> LocationEntry | None:
        key = ALIASES.get(location_id, location_id)
        return next((e for e in self.entries if e.id == key), None)

    def by_cell(self, cell_id: str) -> LocationEntry | None:
        """The place that serves this grid cell. When two places share a cell the first listed
        (the one whose directory holds it) answers, so the hash is the same either way."""
        return next((e for e in self.entries if e.cell_id == cell_id), None)

    def by_point(self, latitude: float, longitude: float) -> LocationEntry | None:
        return self.by_cell(cell_id_for(latitude, longitude))


def _entry(row: dict[str, Any]) -> LocationEntry:
    return LocationEntry(
        id=row["id"], name=row["name"], latitude=row["point"]["latitude"],
        longitude=row["point"]["longitude"], region=row["region"], cell_id=row["cell_id"],
        grid_cell=row["grid_cell"], snapshot_dir=row["snapshot_dir"],
        snapshot_hash=row["snapshot_hash"], first_date=row["first_date"],
        last_date=row["last_date"], shares_snapshot_with=row.get("shares_snapshot_with"),
    )  # fmt: skip


def read_index(path: Path | str = INDEX_PATH) -> LocationIndex:
    p = Path(path)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return LocationIndex(tuple(_entry(r) for r in doc["locations"]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise IndexError_(f"snapshot index {p} is missing or malformed: {exc}") from exc


@lru_cache(maxsize=1)
def get_index() -> LocationIndex:
    """The committed index, read once per process."""
    return read_index()


@lru_cache(maxsize=16)
def load_entry_snapshot(snapshot_dir: str) -> Snapshot:
    """The snapshot in ``data/snapshots/<snapshot_dir>/``, loaded once and hash-checked."""
    return load_snapshot(SNAPSHOT_ROOT / snapshot_dir)


def lookup(
    *, location_id: str | None = None, latitude: float | None = None, longitude: float | None = None
) -> LocationEntry | None:
    """The place serving an id or a point. An id wins when both are given."""
    idx = get_index()
    if location_id:
        return idx.by_id(location_id)
    if latitude is not None and longitude is not None:
        return idx.by_point(latitude, longitude)
    return None


def build_index_rows(root: Path = SNAPSHOT_ROOT) -> list[dict[str, Any]]:
    """Index rows from the manifests on disk. A place in the same cell as an earlier place
    points at that place's directory (it must not have one of its own)."""
    rows: list[dict[str, Any]] = []
    owner_of_cell: dict[str, Place] = {}
    for place in PLACES:
        cid = cell_id_for(place.latitude, place.longitude)
        owner = owner_of_cell.setdefault(cid, place)
        manifest_path = root / owner.snapshot_dir / MANIFEST_NAME
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cell = manifest["grid"]["derived_cell"]
        if cell_id_for(cell["center_latitude"], cell["center_longitude"]) != cid:
            raise ValueError(f"{owner.snapshot_dir}: manifest cell does not match {cid}")
        cov = manifest["coverage"]
        rows.append(
            {
                "id": place.id,
                "name": place.name,
                "point": {"latitude": place.latitude, "longitude": place.longitude},
                "region": place.region,
                "cell_id": cid,
                "grid_cell": cell,
                "snapshot_dir": owner.snapshot_dir,
                "snapshot_hash": manifest["hashes"]["snapshot_hash"],
                "first_date": cov["first_date"],
                "last_date": cov["last_date"],
                "shares_snapshot_with": None if owner is place else owner.id,
            }
        )
    return rows


def write_index(
    root: Path = SNAPSHOT_ROOT, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "note": (
            "One snapshot per POWER grid cell. A place that shares a cell points at the directory "
            "that holds it. Lookup is by grid cell. County points are approximate county centres, "
            "not farms. Regenerate with `python -m fieldshift.weather build-locations`."
        ),
        "locations": build_index_rows(root),
    }
    if extra:
        doc.update(extra)
    (root / "index.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n",
                                     encoding="utf-8")
    return doc


def verify_index(root: Path = SNAPSHOT_ROOT) -> dict[str, Any]:
    """Offline check: every place is listed once, its cell matches its point, each snapshot
    directory verifies against its manifest, and the index hashes equal the manifests'."""
    from fieldshift.weather.snapshot import SnapshotError, verify_snapshot

    idx = read_index(root / "index.json")
    if [e.id for e in idx.entries] != [p.id for p in PLACES]:
        raise SnapshotError("index.json does not list exactly the known places, in order")
    seen: dict[str, str] = {}
    for e in idx.entries:
        place = next(p for p in PLACES if p.id == e.id)
        if (e.latitude, e.longitude) != (place.latitude, place.longitude):
            raise SnapshotError(f"{e.id}: index point differs from the place table")
        if e.cell_id != cell_id_for(e.latitude, e.longitude):
            raise SnapshotError(f"{e.id}: index cell does not match its point")
        prior = seen.setdefault(e.cell_id, e.snapshot_hash)
        if prior != e.snapshot_hash:
            raise SnapshotError(f"{e.id}: two hashes for one grid cell")
    dir_of_cell: dict[str, str] = {}
    cell_of_dir: dict[str, str] = {}
    for e in idx.entries:
        if dir_of_cell.setdefault(e.cell_id, e.snapshot_dir) != e.snapshot_dir:
            raise SnapshotError(f"{e.id}: one grid cell, two snapshot directories")
        if cell_of_dir.setdefault(e.snapshot_dir, e.cell_id) != e.cell_id:
            raise SnapshotError(f"{e.id}: {e.snapshot_dir}/ is listed for two grid cells")
    checked: dict[str, str] = {}
    for e in idx.entries:
        if e.snapshot_dir in checked:
            continue
        res = verify_snapshot(root / e.snapshot_dir)
        if res["snapshot_hash"] != e.snapshot_hash:
            raise SnapshotError(f"{e.id}: index hash differs from {e.snapshot_dir}/manifest.json")
        manifest = json.loads((root / e.snapshot_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
        cell = manifest["grid"]["derived_cell"]
        if cell_id_for(cell["center_latitude"], cell["center_longitude"]) != e.cell_id:
            raise SnapshotError(f"{e.id}: {e.snapshot_dir}/ holds a different grid cell")
        checked[e.snapshot_dir] = res["snapshot_hash"]
    return {"ok": True, "places": len(idx.entries), "snapshots": len(checked)}


# --------------------------------------------------------------------------- building (network)


def reference_point(place: Place) -> Any:
    from fieldshift.weather.sources import ReferencePoint

    if place.id == "union":
        from fieldshift.weather.sources import UNION_COUNTY

        return UNION_COUNTY
    return ReferencePoint(
        id=place.reference_id,
        name=f"{place.name}, North Carolina (county centre)",
        latitude=place.latitude,
        longitude=place.longitude,
        basis=COUNTY_BASIS,
    )


def build_locations(
    *,
    fetch: Any | None = None,
    root: Path = SNAPSHOT_ROOT,
    force: bool = False,
    log: Any = print,
) -> dict[str, Any]:
    """Fetch and write one snapshot per grid cell, then write ``index.json``.

    Needs the network (``FIELDSHIFT_OFFLINE`` unset); only missing directories are fetched unless
    ``force``. A place in a cell that an earlier place already holds is not stored again: its own
    point is fetched once and compared with the stored history, and the comparison is recorded in
    the index. If the two differ the build stops, because sharing would be wrong.
    """
    from fieldshift.weather.normalize import normalize_power_response
    from fieldshift.weather.power_client import fetch_daily
    from fieldshift.weather.snapshot import (
        SnapshotError,
        daily_canonical_csv,
        sha256_bytes,
        write_snapshot,
    )
    from fieldshift.weather.sources import SNAPSHOT_END, SNAPSHOT_START

    do_fetch = fetch or fetch_daily
    previous: dict[str, Any] = {}
    if (root / "index.json").exists():
        previous = json.loads((root / "index.json").read_text(encoding="utf-8")).get(
            "cell_checks", {}
        )
    checks: dict[str, Any] = dict(previous)
    owner_of_cell: dict[str, Place] = {}
    for place in PLACES:
        cid = cell_id_for(place.latitude, place.longitude)
        owner = owner_of_cell.setdefault(cid, place)
        if owner is place:
            if (root / place.snapshot_dir / MANIFEST_NAME).exists() and not force:
                log(f"{place.id}: snapshot exists in {place.snapshot_dir}/ (skipped)")
                continue
            log(f"{place.id}: fetching POWER daily for {place.latitude}, {place.longitude} ...")
            raw = do_fetch(place.latitude, place.longitude, SNAPSHOT_START, SNAPSHOT_END)
            write_snapshot(raw, root / place.snapshot_dir, point=reference_point(place),
                           start=SNAPSHOT_START, end=SNAPSHOT_END)  # fmt: skip
            continue
        if place.id in checks and not force:
            log(f"{place.id}: shares {cid} with {owner.id} (already compared)")
            continue
        log(f"{place.id}: shares {cid} with {owner.id}; fetching its own point to compare ...")
        raw = do_fetch(place.latitude, place.longitude, SNAPSHOT_START, SNAPSHOT_END)
        theirs = normalize_power_response(raw.body, start=SNAPSHOT_START, end=SNAPSHOT_END)
        stored = json.loads((root / owner.snapshot_dir / MANIFEST_NAME).read_text("utf-8"))
        same = (
            sha256_bytes(daily_canonical_csv(theirs.daily))
            == stored["hashes"]["daily_canonical_csv_sha256"]
        )
        if not same:
            raise SnapshotError(
                f"{place.id} and {owner.id} are in {cid} but POWER returned different daily "
                "values; give them separate snapshot directories"
            )
        checks[place.id] = {
            "compared_with": owner.id,
            "identical_daily_values": True,
            "retrieved_at": raw.retrieved_at,
        }
    return write_index(root, {"cell_checks": checks})
