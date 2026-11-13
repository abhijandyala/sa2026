CHANGES NEEDED

medium | fieldshift/metrics/rules.py:638 | `ww_v2_rc_residual_wheat_stubble` flags all organic wheat after soybean, ignoring required no-till and residual-stubble conditions. | Return `manual_check` until those conditions are verified; add a regression test for absent residue.