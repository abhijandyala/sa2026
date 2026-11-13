CHANGES NEEDED

medium | fieldshift/field/regions.py:59 | Generic Tidewater locations still match Hertford-specific guidance without sufficient location evidence | Require county/subregion evidence; otherwise return unknown.

medium | fieldshift/metrics/rules.py:646 | Missing gap returns unknown before a false moisture/pest gate can clear the check, shrinking denominators | Short-circuit false gates before requiring gap data; add regressions.

medium | fieldshift/metrics/rules.py:457 | With stages="all", fc_wt_03 evaluates its July silking window against planting date | Require a silking date or return manual_check.

medium | fieldshift/metrics/rules.py:292 | Gap validation still accepts NaN/infinity; infinity silently clears cr_tt_03 | Reject non-finite gaps as invalid_input; preserve zero and test both cases.