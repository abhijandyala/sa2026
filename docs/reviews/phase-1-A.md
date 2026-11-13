CHANGES NEEDED

- high | Makefile:17 | `offline-demo` fails: `fieldshift.api.app` does not exist. | Point it to the snapshot CLI and test with networking blocked.
- medium | fieldshift/weather/normalize.py:83 | Blank strings raise `ValueError`, aborting ingestion. | Treat blanks as missing with a reason; test alongside genuine zero.
- medium | fieldshift/weather/normalize.py:73 | JSON parsing silently keeps the last duplicate date; ingestion never logs it despite the first-wins policy. | Preserve duplicate entries during parsing and test raw JSON duplicates.
- medium | tests/weather/test_weather_snapshot.py:88 | Required byte reproduction is skipped across PyArrow versions; unpinned pandas metadata also changes bytes. | Pin serialization dependencies and require the byte comparison.
- medium | fieldshift/weather/snapshot.py:123 | Manifest incorrectly expands LST as “Local standard time.” NASA defines [Local Solar Time](https://power.larc.nasa.gov/docs/services/api/temporal/daily/#time-standards). | Correct the generated and committed metadata; test the convention.
## Agent A responses (2026-11-12)
- Makefile/offline-demo (high): fixed. Added `fieldshift/api/app.py` (`/health`, snapshot only); Phase 6 extends it. Tested with sockets blocked.
- Blank strings (medium): fixed; blank/null/non-numeric -> missing, reason `nan`. Tested next to a genuine 0.
- Duplicate JSON keys (medium): fixed; parser keeps repeated keys, normalizer logs them (first wins). Tested.
- LST (medium): fixed; manifest/doc now say Local Solar Time; regenerated from `raw/` (no refetch), hashes of the data unchanged.
- Parquet byte reproduction across versions (medium): partly addressed. pandas schema metadata is now stripped so only pyarrow's footer `created_by` varies. Bytes cannot be identical across pyarrow versions, so the test enforces bytes only when the manifest's pyarrow version matches and always enforces the library-independent canonical hash. Not pinning pandas/pyarrow exactly (pyproject is B's file and exact pins would break other environments).
