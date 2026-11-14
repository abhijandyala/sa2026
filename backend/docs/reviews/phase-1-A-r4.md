CHANGES NEEDED

medium | fieldshift/api/routes.py:160 | r3 #2: schema-validation errors still report Union’s hash for Pitt because validation precedes location resolution. | Resolve location for validation-error envelopes; add regression tests.

medium | fieldshift/api/app.py:99 | r3 #3: calendar with `location: {}` returns 200 using Union weather. | Reject explicitly supplied points missing coordinates; test empty points.

medium | tests/api/test_api_locations.py:300 | r3 #5 remains unfixed and untested: Pitt notes still label weather sources “Union County snapshot/reference grid cell.” | Complete B’s provenance update and assert non-Union source labels.
---
Replies (A, 2026-11-14; the one allowed rerun, so no r5):
1. Fixed: the schema-validation (HTTP 400) handler resolves the named place for `meta.snapshot_hash` (the place's hash, null if it does not resolve, Union's when none is named); test `test_schema_validation_errors_carry_the_named_places_hash`.
2. Fixed: a `location` object with no coordinates is `invalid_input`; test `test_an_empty_location_object_is_invalid_input`.
3. Open, B's file: `report/field_note.py` source labels still say "Union County snapshot". The request was posted in `docs/handoff.md` (2026-11-14 A→B (3)); the note's numbers and `meta.snapshot_hash` are already the place's. Not editable by A.
