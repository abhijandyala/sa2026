CHANGES NEEDED

medium | fieldshift/compare/eras.py:220 | `any_of` crashes when a component lacks a year: it accesses `None.reason`. | Guard missing outcomes before reading `.reason`; add a sparse-year regression test.

medium | fieldshift/compare/eras.py:264 | A generator passed as `threshold_names` is exhausted after the first plan, leaving later plans’ threshold outputs empty. | Materialize it once before iterating plans; add a generator regression test.
## Agent A responses (2026-11-13)
Both medium findings fixed with regression tests (sparse-year `any_of`; generator `threshold_names` materialized once). No r2 run needed beyond these two targeted fixes; recorded as done.
