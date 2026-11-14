"""Write, load and verify the offline weather snapshot.

Layout (default ``data/snapshots/union_county/``)::

    raw/power_daily.json     untouched POWER response bytes
    raw/fetch_meta.json      query URL, params, status, retrieval time
    daily.parquet            normalized full-calendar daily table
    manifest.json            source, grid, coverage, missing dates, hashes

``daily.parquet`` is written with fixed options so re-normalizing ``raw/`` reproduces it
byte-for-byte *on the same pyarrow version*; the manifest records the pyarrow version and
also a library-independent hash of the canonical CSV form of the table.
"""

from __future__ import annotations

import contextvars
import hashlib
import io
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow
import pyarrow as pa
import pyarrow.parquet as pq

from fieldshift.weather.coverage import coverage_report, missing_dates
from fieldshift.weather.normalize import NormalizeResult, normalize_power_response
from fieldshift.weather.power_client import RawFetch
from fieldshift.weather.sources import (
    PARAMETER_NOTES,
    POWER_COMMUNITY,
    POWER_FILL_VALUE,
    POWER_PARAMETERS,
    POWER_TIME_STANDARD,
    SNAPSHOT_END,
    SNAPSHOT_START,
    UNION_COUNTY,
    ReferencePoint,
    derive_grid_cell,
)

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT_DIR = REPO_ROOT / "data" / "snapshots" / "union_county"
RAW_NAME = "power_daily.json"
FETCH_META_NAME = "fetch_meta.json"
PARQUET_NAME = "daily.parquet"
MANIFEST_NAME = "manifest.json"


#: The snapshot directory the current request is answered from. ``load_snapshot()`` with no
#: argument reads it, so code that only wants "the snapshot in use" (response metadata) follows
#: the request's location without being passed anything. ``None`` means the Union County default.
_ACTIVE_DIR: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "fieldshift_active_snapshot_dir", default=None
)


@contextmanager
def active_snapshot_dir(directory: Path | str | None) -> Iterator[None]:
    """Make ``load_snapshot()`` read ``directory`` inside the block (this request only)."""
    token = _ACTIVE_DIR.set(Path(directory) if directory is not None else None)
    try:
        yield
    finally:
        try:
            _ACTIVE_DIR.reset(token)
        except ValueError:  # reset from a copied context; the copy dies with the request
            pass


def set_active_snapshot_dir(directory: Path | str | None) -> None:
    """Set the active directory for the rest of this request (async dependencies)."""
    _ACTIVE_DIR.set(Path(directory) if directory is not None else None)


class SnapshotError(RuntimeError):
    """The snapshot is missing, or its files do not match the manifest hashes."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def daily_to_parquet_bytes(daily: pd.DataFrame) -> bytes:
    """Deterministic parquet serialization of the daily table."""
    # Strip pandas' schema metadata so the bytes do not embed the pandas version.
    table = pa.Table.from_pandas(daily, preserve_index=False).replace_schema_metadata(None)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy", use_dictionary=False)
    return buffer.getvalue()


def daily_canonical_csv(daily: pd.DataFrame) -> bytes:
    """Library-version-independent text form used for the canonical hash."""
    text = daily.to_csv(index=False, date_format="%Y-%m-%d", na_rep="", lineterminator="\n")
    return text.encode("utf-8")


def snapshot_hash(raw_sha256: str, daily_canonical_sha256: str) -> str:
    """The single hash that API responses carry as ``snapshot_hash``."""
    return sha256_bytes(f"{raw_sha256}:{daily_canonical_sha256}".encode())


def build_manifest(
    *,
    point: ReferencePoint,
    fetch: dict[str, Any],
    raw_bytes: bytes,
    result: NormalizeResult,
    parquet_bytes: bytes,
    start: str,
    end: str,
) -> dict[str, Any]:
    payload = json.loads(raw_bytes)
    header = payload.get("header", {})
    geometry = payload.get("geometry", {}).get("coordinates", [None, None, None])
    daily = result.daily
    coverage = coverage_report(daily)
    raw_sha = sha256_bytes(raw_bytes)
    canon_sha = sha256_bytes(daily_canonical_csv(daily))
    notes = []
    if coverage["per_variable"]["precip_mm"]["first_valid"] == "1981-01-01":
        notes.append(
            "Series starts 1981-01-01 (POWER's earliest date). The winter that begins in fall "
            "1980 is incomplete, so the 1981 planting year's winter must be marked incomplete."
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "reference_point": {
            "id": point.id,
            "name": point.name,
            "requested_latitude": point.latitude,
            "requested_longitude": point.longitude,
            "basis": point.basis,
        },
        "source": {
            "name": header.get("title", "NASA/POWER Daily"),
            "api": header.get("api", {}),
            "sources_reported": header.get("sources", []),
            "community": POWER_COMMUNITY,
            "time_standard": header.get("time_standard", POWER_TIME_STANDARD),
            "fill_value": header.get("fill_value", POWER_FILL_VALUE),
            "parameters": POWER_PARAMETERS,
            "parameter_units_reported": {
                k: v.get("units") for k, v in payload.get("parameters", {}).items()
            },
            "parameter_notes": PARAMETER_NOTES,
            "daily_boundary": (
                "time_standard=LST = Local Solar Time (POWER docs): each day is a solar day at the point."
            ),
        },
        "grid": {
            "returned_coordinates": {
                "longitude": geometry[0],
                "latitude": geometry[1],
                "elevation_m": geometry[2],
                "note": "POWER echoes the requested point; it does not return the cell centre",
            },
            "derived_cell": derive_grid_cell(point.latitude, point.longitude),
        },
        "query": {"url": fetch.get("url"), "params": fetch.get("params")},
        "retrieval": {
            "retrieved_at": fetch.get("retrieved_at"),
            "status_code": fetch.get("status_code"),
        },
        "coverage": {
            "requested_start": start,
            "requested_end": end,
            **coverage,
            "missing_dates": missing_dates(daily),
        },
        "normalization": result.log.as_dict(),
        "hashes": {
            "raw_sha256": raw_sha,
            "daily_parquet_sha256": sha256_bytes(parquet_bytes),
            "daily_canonical_csv_sha256": canon_sha,
            "snapshot_hash": snapshot_hash(raw_sha, canon_sha),
        },
        "environment": {"pyarrow_version": pyarrow.__version__, "pandas_version": pd.__version__},
        "notes": notes,
    }


def write_snapshot(
    fetch: RawFetch,
    out_dir: Path | str = DEFAULT_SNAPSHOT_DIR,
    *,
    point: ReferencePoint = UNION_COUNTY,
    start: str = SNAPSHOT_START,
    end: str = SNAPSHOT_END,
) -> dict[str, Any]:
    """Persist a fetch: raw bytes untouched, normalized parquet, manifest. Returns the manifest."""
    out = Path(out_dir)
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "raw" / RAW_NAME).write_bytes(fetch.body)
    fetch_meta = {
        "url": fetch.url,
        "params": fetch.params,
        "status_code": fetch.status_code,
        "retrieved_at": fetch.retrieved_at,
        "elapsed_s": fetch.elapsed_s,
        "raw_file": f"raw/{RAW_NAME}",
        "raw_sha256": sha256_bytes(fetch.body),
    }
    _write_json(out / "raw" / FETCH_META_NAME, fetch_meta)
    return _derive(out, fetch.body, fetch_meta, point, start, end)


def rebuild_snapshot(directory: Path | str = DEFAULT_SNAPSHOT_DIR) -> dict[str, Any]:
    """Re-derive ``daily.parquet`` and ``manifest.json`` from ``raw/`` alone (no network)."""
    d = Path(directory)
    old = json.loads((d / MANIFEST_NAME).read_text(encoding="utf-8"))
    fetch_meta = json.loads((d / "raw" / FETCH_META_NAME).read_text(encoding="utf-8"))
    ref = old["reference_point"]
    point = ReferencePoint(
        id=ref["id"], name=ref["name"], latitude=ref["requested_latitude"],
        longitude=ref["requested_longitude"], basis=ref["basis"],
    )
    raw = (d / "raw" / RAW_NAME).read_bytes()
    cov = old["coverage"]
    return _derive(d, raw, fetch_meta, point, cov["requested_start"], cov["requested_end"])


def _derive(
    out: Path, raw: bytes, fetch_meta: dict[str, Any], point: ReferencePoint, start: str, end: str
) -> dict[str, Any]:
    result = normalize_power_response(raw, start=start, end=end)
    parquet = daily_to_parquet_bytes(result.daily)
    (out / PARQUET_NAME).write_bytes(parquet)
    manifest = build_manifest(
        point=point, fetch=fetch_meta, raw_bytes=raw, result=result,
        parquet_bytes=parquet, start=start, end=end,
    )
    _write_json(out / MANIFEST_NAME, manifest)
    return manifest


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class Snapshot:
    daily: pd.DataFrame
    manifest: dict[str, Any]
    directory: Path

    @property
    def snapshot_hash(self) -> str:
        return self.manifest["hashes"]["snapshot_hash"]


def load_snapshot(directory: Path | str | None = None) -> Snapshot:
    """Read a committed snapshot. Reads files only; never touches the network.

    With no argument: the request's active snapshot (:func:`active_snapshot_dir`), else the Union
    County default.
    """
    d = Path(directory) if directory is not None else (_ACTIVE_DIR.get() or DEFAULT_SNAPSHOT_DIR)
    manifest_path, parquet_path = d / MANIFEST_NAME, d / PARQUET_NAME
    if not manifest_path.exists() or not parquet_path.exists():
        raise SnapshotError(f"snapshot not found in {d}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    parquet_bytes = parquet_path.read_bytes()
    if sha256_bytes(parquet_bytes) != manifest["hashes"]["daily_parquet_sha256"]:
        raise SnapshotError("daily.parquet does not match the manifest hash")
    daily = pd.read_parquet(io.BytesIO(parquet_bytes))
    daily["date"] = pd.to_datetime(daily["date"])
    return Snapshot(daily=daily, manifest=manifest, directory=d)


def verify_snapshot(directory: Path | str = DEFAULT_SNAPSHOT_DIR) -> dict[str, Any]:
    """Check every file against the manifest and re-normalize ``raw/`` from scratch.

    Raises :class:`SnapshotError` on a mismatch. The parquet byte comparison is only
    enforced when this pyarrow version matches the one recorded in the manifest; the canonical
    CSV hash is always enforced.
    """
    d = Path(directory)
    manifest = json.loads((d / MANIFEST_NAME).read_text(encoding="utf-8"))
    hashes = manifest["hashes"]
    raw_bytes = (d / "raw" / RAW_NAME).read_bytes()
    if sha256_bytes(raw_bytes) != hashes["raw_sha256"]:
        raise SnapshotError("raw response hash does not match the manifest")
    parquet_bytes = (d / PARQUET_NAME).read_bytes()
    if sha256_bytes(parquet_bytes) != hashes["daily_parquet_sha256"]:
        raise SnapshotError("daily.parquet hash does not match the manifest")
    cov = manifest["coverage"]
    result = normalize_power_response(
        raw_bytes, start=cov["requested_start"], end=cov["requested_end"]
    )
    if sha256_bytes(daily_canonical_csv(result.daily)) != hashes["daily_canonical_csv_sha256"]:
        raise SnapshotError("re-normalizing raw/ does not reproduce the canonical daily table")
    parquet_checked = manifest["environment"]["pyarrow_version"] == pyarrow.__version__
    if parquet_checked and daily_to_parquet_bytes(result.daily) != parquet_bytes:
        raise SnapshotError("re-normalizing raw/ does not reproduce daily.parquet byte-for-byte")
    return {"ok": True, "parquet_byte_check": parquet_checked, "snapshot_hash": snapshot_hash(
        hashes["raw_sha256"], hashes["daily_canonical_csv_sha256"])}
