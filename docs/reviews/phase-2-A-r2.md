CHANGES NEEDED

medium | fieldshift/contracts.py:222 | Omitting `parameters` leaves a mutable dict because defaults skip validation; mutating it changes `threshold_set_id`. | Enable default validation or use an immutable default factory; add a regression test with omitted parameters.

## Agent A response (2026-11-12)
Fixed: `Threshold.parameters` default now uses `FrozenDict`; regression test added. No further Phase 2 findings.
