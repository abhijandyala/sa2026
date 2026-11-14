CHANGES NEEDED

medium | fieldshift/metrics/rule_text.py:351 | On June planting, the July trial row says “for this planting date” despite being outside its studied context. | Name the catalog’s month and explain the applicability limitation.

medium | fieldshift/metrics/rule_text.py:379 | Numeric prompts omit material qualifications: fc_pw_04 loses “at least two days”; fc_soil_01 loses “mineral soils.” | Preserve catalog timing and soil qualifications in text.

medium | fieldshift/metrics/rule_text.py:348 | ww_v2_pw_local_map presents 0–21 days as unrestricted, omitting the catalog’s before-Thanksgiving advice. | Include both limits.

medium | fieldshift/metrics/rule_text.py:470 | The print filter excludes ww_v2_pw_local_map, an unresolved planting-date check that blocks assessing the plan. | Include essential manual decision checks regardless of suitability; retain a handful-size regression test.

medium | fieldshift/planner/calendar.py:133 | With soil_temp_f=60, both conflicting corn rules have print=true but disappear from calendar evidence; unresolved_checks substitutes different group text. | Carry printable conflicts into evidence and preserve their RuleCheck text in the note.

low | fieldshift/metrics/rules.py:846 | Conflict enrichment produces two sentences, violating the one-short-sentence requirement. | Generate one combined sentence and test final enriched text.

---

## Resolution (B, 2026-11-14)

All six findings were fixed in 8d93d3d, each with a test in `tests/metrics/test_rule_text.py` (or `tests/report/test_field_note.py` for the calendar one). No r4 was run.

- medium, July trial row on a June planting: the text now names the catalog's month and says the row was studied for a different planting date.
- medium, lost qualifiers: `fc_pw_04` keeps "for at least 2 days" and `fc_soil_01` keeps the mineral-soil qualifier.
- medium, `ww_v2_pw_local_map`: the text gives both limits (0-21 days and the before-Thanksgiving advice).
- medium, print filter: an unresolved planting-date check with a day count prints regardless of suitability; the handful-size test (at most 6 for the sample plans, 8 for the wheat demo) still passes.
- medium, conflicting corn rules at 60 °F soil: printable conflicts stay in calendar evidence and the note carries the same RuleCheck text.
- low, two sentences: the conflict note is folded into one sentence and the test checks the final enriched text.
