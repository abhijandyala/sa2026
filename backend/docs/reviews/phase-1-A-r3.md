CHANGES NEEDED

medium | fieldshift/compare/locations.py:89 | Supplying an ID bypasses the NC boundary check: Robeson plus (34.3, -79.6) evaluates successfully although the point alone is unsupported. | Check NC bounds before accepting ID-plus-point; add regression coverage.

medium | fieldshift/api/routes.py:506 | Core error responses report Union’s hash: Pitt sensitivity with an unknown rule, or Pitt replay for 1980, reproduces this. Unknown-location errors also report Union’s hash. | Use the resolved snapshot hash, or null when unresolved, in error envelopes; test these paths.

medium | fieldshift/api/app.py:92 | Malformed location hints silently disappear. Calendar with both coordinates `"bad"` returns 200 using Union weather. | Distinguish absent input from invalid input and return 400; test malformed coordinates and IDs.

medium | fieldshift/weather/locations.py:250 | Verification accepts Rowan redirected to Pitt’s directory/hash, returning `ok` with only six snapshots. | Validate each directory’s manifest cell against the index cell and enforce one directory per cell; test mismatched mappings.

medium | fieldshift/api/app.py:184 | Newly enabled Pitt field notes still describe their weather sources as “Union County snapshot/reference grid cell.” | Arrange a B-owned provenance-label update through handoff and test non-Union note sources.

low | tests/weather/test_weather_locations.py:112 | Grid tests compare helpers using the same derivation; they cannot detect incorrect boundary behavior. Request-isolation tests are sequential only. | Add independent expected cells at edges and overlapping requests across locations.
---
Replies (A, 2026-11-14):
1. Fixed: `choose()` now checks the NC outline before accepting an id plus a point (`unsupported_location`); test `test_an_id_with_a_point_outside_nc_is_unsupported_not_evaluated`.
2. Fixed: the request's place is resolved first and made the active snapshot, so 400 envelopes carry that snapshot's hash, or null when no place resolved; tests `test_error_responses_carry_the_resolved_snapshot_hash_or_null`.
3. Fixed: a present but malformed `location_id`/point is HTTP 400 `invalid_input` (`invalid_location`, `incomplete_point`, `invalid_point`), never the Union default; tests for malformed body and query hints.
4. Fixed: `verify_index` checks each directory's manifest cell against the index cell and enforces one directory per cell; test with Rowan redirected to Pitt's directory.
5. Handed to B: `docs/handoff.md` 2026-11-14 A→B (3) (`report/field_note.py` source label says "Union County snapshot"). B's file, not edited here.
6. Fixed: edge cells are hard-coded from live POWER probes (identical values inside the edge, different outside), plus a threaded overlapping-request test across six places.
