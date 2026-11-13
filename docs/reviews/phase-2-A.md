CHANGES NEEDED

medium | fieldshift/seasons/validate.py:33 | The 365-day validation cycle collapses Feb 29 onto Feb 28, rejecting valid leap-year intervals and Feb-29 harvest → following Feb-28 planting. | Validate chronology against resolved yearly dates; add boundary tests.

medium | fieldshift/contracts.py:205 | `frozen=True` leaves `thresholds` and nested `parameters` mutable; thresholds and their ID can change between plans/eras. | Make threshold contents deeply immutable; test mutation rejection.

medium | fieldshift/seasons/coverage.py:108 | Planting dates after the snapshot end silently omit 2025 instead of returning its coverage, violating the fixed 1981–2025 mapping. | Retain all historical years and report partial/unavailable coverage; test late planting.

medium | fieldshift/contracts.py:109 | An empty winter `crop_id` passes validation, then triggers `AssertionError` in calendar construction. | Reject blank crop IDs with a field-specific validation error; add a regression test.
## Agent A responses (2026-11-12)
All four medium findings fixed with tests: Feb 29 now validated on a 366-day leap cycle and re-checked on resolved dates per year; thresholds are deeply immutable (`FrozenDict`); `planting_years` now keeps every record year (late planting reports partial/unavailable); blank crop IDs are field validation errors.
