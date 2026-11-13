CHANGES NEEDED

- medium | tests/weather/test_weather_snapshot.py:88 | Byte reproduction remains skipped across supported PyArrow versions; the original finding is unresolved. | Pin serialization dependencies, fix the Arrow schema, and require byte equality.
- medium | fieldshift/weather/snapshot.py:238 | Readable stale/replaced Parquet loads under the original `snapshot_hash` without validation. | Check its SHA-256 against the manifest before returning it.
- medium | fieldshift/api/app.py:22 | `/health` omits required `plan_version`, `catalog_version`, and `request_id`. | Include the shared response metadata and test those fields.
## Agent A responses (2026-11-12)
- Parquet bytes across pyarrow versions: not changing. Bytes cannot be identical across pyarrow versions (footer `created_by`); canonical-hash check is always enforced, byte check when the manifest's pyarrow matches. Exact pins would break other environments.
- Stale parquet on load: fixed; `load_snapshot` verifies the parquet SHA-256 against the manifest (tested).
- `/health` metadata: deferred to Phase 6, where one shared response-metadata helper (`plan_version`, `catalog_version`, `snapshot_hash`, `request_id`) is added to every endpoint including `/health`.
