CHANGES NEEDED

medium | fieldshift/metrics/rule_text.py:351 | On June planting, the July trial row says “for this planting date” despite being outside its studied context. | Name the catalog’s month and explain the applicability limitation.

medium | fieldshift/metrics/rule_text.py:379 | Numeric prompts omit material qualifications: fc_pw_04 loses “at least two days”; fc_soil_01 loses “mineral soils.” | Preserve catalog timing and soil qualifications in text.

medium | fieldshift/metrics/rule_text.py:348 | ww_v2_pw_local_map presents 0–21 days as unrestricted, omitting the catalog’s before-Thanksgiving advice. | Include both limits.

medium | fieldshift/metrics/rule_text.py:470 | The print filter excludes ww_v2_pw_local_map, an unresolved planting-date check that blocks assessing the plan. | Include essential manual decision checks regardless of suitability; retain a handful-size regression test.

medium | fieldshift/planner/calendar.py:133 | With soil_temp_f=60, both conflicting corn rules have print=true but disappear from calendar evidence; unresolved_checks substitutes different group text. | Carry printable conflicts into evidence and preserve their RuleCheck text in the note.

low | fieldshift/metrics/rules.py:846 | Conflict enrichment produces two sentences, violating the one-short-sentence requirement. | Generate one combined sentence and test final enriched text.