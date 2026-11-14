CHANGES NEEDED

medium | fieldshift/field/location.py:195 | Malformed index rows escape protection: `snapshot_hash: []` raises validation errors outside the try block; null/empty hashes still report `complete`. | Validate required metadata and guard response construction; return `unavailable` for malformed rows and add null/wrong-type regression tests.

---

## Resolution (B, 2026-11-14)

- medium, malformed index rows: `weather` is built by `_support_from_entry`, which requires non-empty string `id`, `snapshot_hash`, `first_date` and `last_date` and runs inside a try block. A row with a list, null, empty or non-string value gives `unavailable` (with a note), never `complete` or a 500. Tests: `test_a_malformed_index_row_is_unavailable_not_complete_or_a_500`, `test_an_unreadable_index_is_unavailable_not_a_500`. No r2 run.
