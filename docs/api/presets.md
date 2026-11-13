# Presets, rotations, and plan IDs (decided 2026-11-12)

## Model

- A **plan** is one winter transition: previous cash crop → winter management → next cash crop. It matches `fieldshift.contracts.Plan`, so one plan has one spring window and one set of checks.
- A **rotation** (what the frontend calls a preset) is two plans, called legs:
  - Leg 1 is the corn → soybean winter.
  - Leg 2 is the soybean → corn winter.
- Each leg is its own plan with its own ID, dates, spring window, and checks.
- **Legs are not chained to alternating years.** Each leg is stress-tested against every eligible spring from 1981 to 2025 on its own, so each leg has its own denominators. A rotation-level view shows the two legs side by side; it never adds their counts together.
- **Termination and planting dates are editable fields on a plan, not separate plans.** The handbook's 12-day and 19-day rye gaps are the same plan, `corn_soy__rye`, with a different `winter.terminate`. An edit keeps `plan_id` and changes `plan_version`. The 12/19-day pair lives on as regression fixtures and as the sensitivity sweep.

## Presets

| Rotation ID | Display name (frontend) | Leg 1 (corn → soybean) | Leg 2 (soybean → corn) |
|---|---|---|---|
| `current_practice` | Current practice | `corn_soy__no_cover` | `soy_corn__no_cover` |
| `winter_cover` | Winter cover | `corn_soy__rye`, with the default termination giving a 12-day gap (handbook case) | `soy_corn__rye` |
| `add_grain_crop` | Add a grain crop | `corn_soy__wheat_dc` (winter wheat → double-crop soybean). Status is `unavailable: catalog_missing` until Perplexity's wheat rows land | `soy_corn__no_cover` |

**Crimson clover is not a preset.** `corn_soy__clover` is the checker's "plan with problems" example. It flags:
- `sb_rc_02`: legume cover before soybean
- `cc_rc_02`: the seeding window after the corn harvest
- `cc_soil_02`: Piedmont clay needs a manual check

Soybean → clover → corn is the well-supported clover use (`fc_nut_03` N credit, `cc_rc_01`). It could become a later alternative for leg 2.

## Sample dates (ASSUMED until the handbook lands; each is flagged `assumed` in data)

| Plan | Previous harvest | Cover seed | Terminate | Next plant | Gap |
|---|---|---|---|---|---|
| `corn_soy__no_cover` | 09-20 | — | — | 05-12 | — |
| `corn_soy__rye` | 09-20 | 10-01 | 04-30 | 05-12 | 12 d |
| `corn_soy__clover` | 09-20 | 10-01 | 04-20 | 05-12 | 22 d |
| `soy_corn__no_cover` | 10-15 | — | — | 04-15 | — |
| `soy_corn__rye` | 10-15 | 10-20 | 04-05 | 04-15 | 10 d (`cr_tt_01` prefers 7–14 d before corn) |
| `corn_soy__wheat_dc` | 09-20 | wheat plant TBD | wheat harvest TBD | soybean TBD | — |

Leg-2 checks come from the corn-side rules: `cr_tt_01`, `cr_tt_02`, `cr_nut_01`, `fc_nut_02`, `fc_pw_01`/`fc_pw_02` (conflict surfaced), and `fc_wt_03`.
