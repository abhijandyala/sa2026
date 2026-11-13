CHANGES NEEDED

high | fieldshift/planner/wheat_path.py:325 | Invalid comparison chronology causes HTTP 500; non-soybean comparisons return 200 with nested invalid_input | Validate comparison type and every replay year; return 400 with typed issues.

medium | fieldshift/planner/wheat_path.py:174 | inputs.maturity_group bypasses range validation; blank/null values are reported complete | Normalize both MG input paths, validate the effective value, preserve zero, and mark blanks unknown.

medium | fieldshift/planner/wheat_path.py:92 | Upper-middle value is mislabeled median: July 15 reports 91.05 mm versus actual 90.28 across 44 eligible seasons | Use statistics.median and test even-sized baselines.

medium | fieldshift/planner/routes.py:257 | Top-level maturity_group is omitted from plan_version; MG 3 and MG 5 produce identical versions despite different checks | Hash normalized effective inputs, including maturity group.