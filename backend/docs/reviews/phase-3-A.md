CHANGES NEEDED

medium | fieldshift/metrics/winter.py:133 | An all-zero record produces no wet-day threshold, suppressing known rainfall totals as None; the zero test bypasses this with a fixed threshold. | Preserve rainfall totals independently of threshold availability; test with build_threshold_set.

medium | fieldshift/metrics/winter.py:164 | A snapshot_hash differing from thresholds.snapshot_hash is accepted as complete, allowing thresholds from another snapshot under misleading provenance. | Reject mismatched hashes and add a regression test.

## Agent A responses (2026-11-12)
- All-zero record: fixed. Rain totals now depend only on window coverage; only the heavy-rain counts become `None` (status `partial`, reason `heavy_rain_threshold_unavailable`). Tested via `build_threshold_set`.
- Snapshot mismatch: fixed. `compute_winter` raises `ThresholdMismatchError` when `thresholds.snapshot_hash != snapshot_hash`. Tested.
