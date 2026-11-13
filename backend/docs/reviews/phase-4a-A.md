CHANGES NEEDED

medium | fieldshift/metrics/spring.py:98 | Reference includes years outside the required 1981–2025 baseline, changing ranks and cutoff. | Restrict baseline years; test a longer record.

medium | fieldshift/metrics/spring.py:185 | Cached reference’s planting date is unchecked; a stale reference silently supplies another window’s total and rank. | Reject mismatched `plant_md`; add regression coverage.

medium | fieldshift/seasons/facts.py:48 | Missing cutoff yields `is_dry=None` with `status=complete`; the threshold’s `insufficient_data` status is lost. | Propagate classification status into spring facts while retaining coverage separately.

medium | tests/metrics/test_metrics_spring.py:186 | Acceptance case 5 never asserts rank recomputation. | Assert expected ranks for both planting windows using data where ranks differ.

## Agent A responses (2026-11-12)
All four fixed with tests: baseline fixed to planting years 1981-2025 (later years are scored but never change the baseline; reason `outside_baseline_years`); `compute_spring` rejects a reference for another planting date; `SeasonFacts.spring.status` now carries `insufficient_data` when the cutoff is missing (coverage status kept in `coverage`); the planting-date-edit test asserts different ranks (1 vs 45).
