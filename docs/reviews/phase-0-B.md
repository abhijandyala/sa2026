CHANGES NEEDED

medium | fieldshift/catalogs/loader.py:288 | References are checked against crops later rejected, leaving usable rules with missing crops. | Validate references against usable crops; add regression tests.

medium | fieldshift/catalogs/loader.py:112 | NaN/infinity pass as numeric bounds and exposure durations; NaN bypasses between-bound ordering. | Reject nonfinite numbers in both parsing paths; test each field.

medium | fieldshift/catalogs/validate.py:102 | Duplicate headers produce only an order warning; dict construction silently overwrites values, including IDs. | Reject duplicate column names before parsing rows; add a duplicate-header test.