CHANGES NEEDED

P1 | fieldshift/field/regions.py:113 | “VA Piedmont” and “SC Coastal Plain” still return complete and receive NC guidance. | Detect state abbreviations before region normalization; add regression tests.

P2 | fieldshift/planner/routes.py:91 | Numeric validation accepts “garbage”/“NaN”, returning HTTP 200/complete; an integer such as 10**310 causes HTTP 500. | Validate finite numeric values with overflow handling; return 400 with field issues.