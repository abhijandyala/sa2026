CHANGES NEEDED

medium | fieldshift/report/routes.py:212 | Suggested fallbacks bypass historical-year validation: seed 02-28, terminate 03-01, plant 03-14 in 2028 generates termination 02-29 and returns HTTP 500. | Validate generated fallbacks across requested and replay years; skip invalid suggestions.

medium | fieldshift/planner/backup.py:138 | Clearing pest rule cr_tt_04 with a 19→28-day gap produces a dry-weather switch condition; calendar triggers also mislabel it. | Select switch conditions and trigger text by each rule’s actual gate.