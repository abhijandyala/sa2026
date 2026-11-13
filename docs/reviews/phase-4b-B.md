CHANGES NEEDED

medium | fieldshift/metrics/rules.py:330 | Wheat→soybean `sb_rc_03` compares wheat against previous cash corn, making the maturity-group warning inapplicable | Match winter grain as the preceding crop; test MG<4.

medium | fieldshift/metrics/rules.py:639 | `cr_tt_03` returns unknown for gap≥14 when dryness is missing, incorrectly shrinking its denominator | Short-circuit the compound condition; test missing-weather clears.

medium | fieldshift/field/regions.py:55 | Hertford/northeastern guidance applies throughout the Coastal Plain, creating unsupported recommendations and conflicts | Preserve geographic scope; return unknown when location is insufficient.

medium | fieldshift/metrics/rules.py:569 | Clover seeded October 5 after September harvest clears `cc_rc_02`, despite violating its October 1 deadline | Interpret these windows as requirements; test late seeding after timely harvest.

medium | fieldshift/metrics/rules.py:435 | Blank numeric inputs raise exceptions; NaN can silently clear hazard checks | Normalize blanks to missing, validate finite numbers, preserve zero, and add tests.

medium | fieldshift/metrics/rules.py:535 | Sequence fallback marks quantitative `sb_rc_01` complete without evaluating `yield_gain_vs_continuous` | Restrict fallback to sequence-only rules; return manual_check for unsupported measurements.

medium | fieldshift/metrics/rules.py:812 | Combined denominator includes seasons missing a requested component check | Require every requested component to exist and complete unless another component flags; test filtered evaluations.
---
Agent B reply (r2 prep): fixed findings 1-5 and 7. Finding 6 (`sb_rc_01`): kept as a sequence-match rule, but the reason now states that `yield_gain_vs_continuous = 5 bu_per_acre` is the source's published result, not a field measurement (test: `test_sb_rc_01_states_its_value_is_a_published_result`).
