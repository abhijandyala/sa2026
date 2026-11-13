CHANGES NEEDED

medium | fieldshift/metrics/spring.py:191 | Cached references from another snapshot pass validation when planting dates match; reproduced rank 46 with 45 eligible years. | Bind references to snapshot identity and reject mismatches.

medium | fieldshift/metrics/spring.py:102 | Iterating record calendar years omits complete January windows for the following planting year; data ending Dec 2024 wrongly excludes Jan 1, 2025. | Iterate all baseline years 1981–2025 and determine eligibility from window coverage.