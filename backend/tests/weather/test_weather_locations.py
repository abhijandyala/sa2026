"""The committed per-location snapshots, the index, and the point -> snapshot lookup (offline)."""

import json

import pytest

from fieldshift.field.location import cell_id as field_cell_id
from fieldshift.weather.locations import (
    INDEX_PATH,
    PLACES,
    SNAPSHOT_ROOT,
    build_index_rows,
    build_locations,
    cell_id_for,
    get_index,
    load_entry_snapshot,
    lookup,
    read_index,
    verify_index,
)
from fieldshift.weather.snapshot import SnapshotError, verify_snapshot
from fieldshift.weather.sources import SNAPSHOT_END, SNAPSHOT_START, derive_grid_cell

IDS = ["union", "iredell", "rowan", "johnston", "wayne", "duplin", "pitt", "robeson"]
UNION_HASH = "5ce131cfcd1f07d3738ecb9afaec6c3ef6a4764b6a3528bdd2b64debe7ba5f4e"


def test_the_eight_places_match_the_place_picker_points():
    assert [p.id for p in PLACES] == IDS
    pts = {p.id: (p.latitude, p.longitude) for p in PLACES}
    assert pts == {
        "union": (34.98, -80.55), "iredell": (35.81, -80.87), "rowan": (35.64, -80.53),
        "johnston": (35.52, -78.37), "wayne": (35.36, -77.99), "duplin": (34.94, -77.93),
        "pitt": (35.59, -77.37), "robeson": (34.64, -79.10),
    }  # fmt: skip


def test_region_labels_follow_the_card():
    regions = {p.id: p.region for p in PLACES}
    assert {k for k, v in regions.items() if v == "piedmont"} == {"union", "iredell", "rowan"}
    assert {k for k, v in regions.items() if v == "coastal_plain"} == {
        "johnston", "wayne", "duplin", "pitt", "robeson"
    }  # fmt: skip


def test_index_verifies_and_every_snapshot_directory_verifies():
    assert verify_index() == {"ok": True, "places": 8, "snapshots": 7}


@pytest.mark.parametrize("directory", sorted({e.snapshot_dir for e in get_index().entries}))
def test_each_snapshot_verifies_from_its_raw_bytes(directory):
    res = verify_snapshot(SNAPSHOT_ROOT / directory)
    assert res["ok"]
    snap = load_entry_snapshot(directory)
    m = snap.manifest
    assert m["coverage"]["first_date"] == SNAPSHOT_START and m["coverage"]["last_date"] == SNAPSHOT_END
    assert m["coverage"]["n_days"] == 16252 and m["coverage"]["days_with_any_missing"] == 0
    assert m["source"]["time_standard"] == "LST" and m["source"]["community"] == "AG"
    assert m["schema_version"] == 1 and len(snap.daily) == 16252


def test_union_snapshot_is_untouched():
    assert get_index().by_id("union").snapshot_hash == UNION_HASH
    assert load_entry_snapshot("union_county").snapshot_hash == UNION_HASH


def test_index_lists_id_name_point_cell_and_hash():
    doc = json.loads(INDEX_PATH.read_text())
    assert [r["id"] for r in doc["locations"]] == IDS
    for r in doc["locations"]:
        assert set(r) >= {"id", "name", "point", "grid_cell", "cell_id", "snapshot_hash", "region"}
        assert r["grid_cell"]["lat_step_deg"] == 0.5 and r["grid_cell"]["lon_step_deg"] == 0.625
        assert len(r["snapshot_hash"]) == 64


def test_every_cell_is_stored_once_and_johnston_and_wayne_share_one():
    rows = {r["id"]: r for r in build_index_rows()}
    assert rows["wayne"]["snapshot_dir"] == "johnston"
    assert rows["wayne"]["shares_snapshot_with"] == "johnston"
    assert rows["wayne"]["snapshot_hash"] == rows["johnston"]["snapshot_hash"]
    assert rows["wayne"]["cell_id"] == rows["johnston"]["cell_id"]
    cells = [r["cell_id"] for r in rows.values()]
    dirs = {r["snapshot_dir"] for r in rows.values()}
    assert len(set(cells)) == len(dirs) == 7  # seven cells, seven directories
    assert not (SNAPSHOT_ROOT / "wayne").exists()
    # every other place has its own cell, so its own hash
    assert len({r["snapshot_hash"] for r in rows.values()}) == 7
    check = json.loads(INDEX_PATH.read_text())["cell_checks"]["wayne"]
    assert check["compared_with"] == "johnston" and check["identical_daily_values"] is True


def test_lookup_by_id_alias_point_and_cell():
    idx = get_index()
    assert idx.by_id("union_county_sample").id == "union"
    assert idx.by_id("union_county_nc").id == "union"
    assert idx.by_id("nope") is None
    for p in PLACES:
        e = lookup(latitude=p.latitude, longitude=p.longitude)
        assert e is not None and e.cell_id == cell_id_for(p.latitude, p.longitude)
        assert e.snapshot_hash == idx.by_id(p.id).snapshot_hash
    assert lookup(latitude=35.36, longitude=-77.99).id == "johnston"  # Wayne's point: shared cell
    assert lookup(location_id="wayne", latitude=0.0, longitude=0.0).id == "wayne"  # id wins
    assert lookup() is None


def test_a_cell_without_a_snapshot_is_not_served_by_a_neighbour():
    assert lookup(latitude=35.78, longitude=-78.64) is None  # Raleigh
    assert lookup(latitude=36.1, longitude=-79.8) is None  # Greensboro area
    assert lookup(latitude=40.7, longitude=-74.0) is None


def test_cell_id_matches_field_location_cell_id():
    for lat, lon in [(34.98, -80.55), (35.52, -78.37), (35.78, -78.64), (34.64, -79.10)]:
        assert cell_id_for(lat, lon) == field_cell_id(derive_grid_cell(lat, lon))


def test_each_index_cell_is_the_manifest_cell_and_contains_its_point():
    for e in get_index().entries:
        c = e.grid_cell
        assert abs(e.latitude - c["center_latitude"]) <= 0.25 + 1e-9
        assert abs(e.longitude - c["center_longitude"]) <= 0.3125 + 1e-9


def test_verify_index_rejects_a_tampered_hash(tmp_path):
    root = tmp_path / "snapshots"
    root.mkdir()
    doc = json.loads(INDEX_PATH.read_text())
    doc["locations"][1]["snapshot_hash"] = "0" * 64
    (root / "index.json").write_text(json.dumps(doc))
    with pytest.raises(Exception):  # noqa: B017 - missing dirs or hash mismatch: both are failures
        verify_index(root)


def test_read_index_reports_a_missing_file(tmp_path):
    from fieldshift.weather.locations import IndexError_

    with pytest.raises(IndexError_):
        read_index(tmp_path / "missing.json")


# --- the builder (fake fetch; no network) ---------------------------------------------------------


class _Fetch:
    """Serves the committed raw bytes as if POWER had returned them."""

    def __init__(self, same: bool = True):
        from fieldshift.weather.power_client import RawFetch

        self.calls: list[tuple[float, float]] = []
        raw = (SNAPSHOT_ROOT / "pitt" / "raw" / "power_daily.json").read_bytes()
        other = (SNAPSHOT_ROOT / "duplin" / "raw" / "power_daily.json").read_bytes()
        self._same, self._raw, self._other, self._cls = same, raw, other, RawFetch

    def __call__(self, lat, lon, start, end, **_):
        self.calls.append((lat, lon))
        body = self._raw if (self._same or len(self.calls) % 2) else self._other
        return self._cls(body=body, url="u", params={}, status_code=200,
                         retrieved_at="2026-01-01T00:00:00Z", elapsed_s=0.0)  # fmt: skip


def test_build_locations_stores_each_cell_once_and_checks_the_shared_one(tmp_path):
    fetch = _Fetch()
    doc = build_locations(fetch=fetch, root=tmp_path, log=lambda *_: None)
    # Union has no directory here, so it is fetched too: 7 cells + the shared Wayne point = 8 calls
    assert len(fetch.calls) == 8
    assert (tmp_path / "johnston" / "manifest.json").exists() and not (tmp_path / "wayne").exists()
    assert doc["cell_checks"]["wayne"]["identical_daily_values"] is True
    assert [r["id"] for r in doc["locations"]] == IDS
    again = _Fetch()
    build_locations(fetch=again, root=tmp_path, log=lambda *_: None)
    assert again.calls == []  # nothing missing, nothing refetched


def test_build_locations_refuses_to_share_a_cell_whose_values_differ(tmp_path):
    class Alternating(_Fetch):
        def __call__(self, lat, lon, start, end, **_):
            self.calls.append((lat, lon))
            body = self._other if (lat, lon) == (35.36, -77.99) else self._raw
            return self._cls(body=body, url="u", params={}, status_code=200,
                             retrieved_at="t", elapsed_s=0.0)  # fmt: skip

    with pytest.raises(SnapshotError, match="different daily values"):
        build_locations(fetch=Alternating(), root=tmp_path, log=lambda *_: None)
