CHANGES NEEDED

medium | fieldshift/compare/engine.py:339 | Shared-era metadata gives corn’s results soybean’s cutoff (64.18 instead of 53.51). | Attach each plan’s actual threshold; test mixed planting dates.

medium | fieldshift/compare/sensitivity.py:90 | Leap crossings break the promised step: March 10 planting gives 8 checks at gap 13 versus 9 at gap 12. | Account explicitly for historical year gaps; add leap-crossing tests.

medium | fieldshift/compare/engine.py:370 | Shared full-season years are always empty despite 44 complete sample seasons. | Intersect actual full-season coverage and test it.

medium | fieldshift/compare/replay.py:75 | Filtering triggered checks to GATES hides clover’s flagged rules, including cc_rc_02 and sb_rc_02. | Return every applicable flagged check with evidence.

medium | fieldshift/api/routes.py:236 | Unknown rule_id returns HTTP 200 with a zero-count, zero-denominator curve. | Validate supported rule IDs; return typed 400 naming rule_id.

medium | fieldshift/api/routes.py:255 | /v1/rotations returns a bare list without the four required metadata fields. | Wrap results in the standard metadata envelope; test it.

medium | scripts/reproduce_replay.py:104 | Script and tests reproduce selected aggregates, not replay daily rows, temperatures, wetness, or checks. | Extend raw-only reproduction and assertions to the replay payload.

low | fieldshift/api/app.py:72 | Health status "ok" violates the mandated status vocabulary. | Use "complete" and assert the allowed vocabulary.
## Agent A responses (2026-11-13)
All eight fixed with tests: shared-era results keep each plan's own cutoff; sensitivity reports `gap_days_in_leap_years` where a Feb 29 crossing changes the gap (each season uses its real gap); shared full-season years computed from coverage; replay returns every flagged check; unknown `rule_id` is a typed 400 (check-id aliases accepted; a rule that never applies returns `status: inapplicable`); `/v1/rotations` uses the standard `meta` envelope; `scripts/reproduce_replay.py` now reproduces the daily rows (precip, temps, wetness), segments, wetness means and the cr_tt_03 trigger from `raw/` alone, asserted in tests; `/health` status is `complete`.
