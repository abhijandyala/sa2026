# Field Shift — Backend Phase Cards

Scope: **backend only** (Rahul). Frontend (Abhi) consumes the API contract defined in Phase 10.
Each card is self-contained: hand one to a build session, finish its acceptance checks, then move on.

## Stack decision

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Fits data and calculation work; pandas is available for the weather series |
| API | FastAPI + Pydantic v2 | Typed request/response models become the contract with Abhi (OpenAPI is generated automatically) |
| Reference data | Versioned files in `data/` (CSV catalogs, Parquet/CSV weather snapshot, JSON manifests) | The brief says no DB server; everything must be reproducible and work offline |
| Cache for live lookups | On-disk JSON cache keyed by request hash, with fetch time and validity | Keeps fresh, saved, and unavailable data distinguishable |
| HTTP client | `httpx` with timeouts and retries | NASA POWER, USDA SDA, NWS, and USDM |
| Tests | `pytest` with labeled fixtures in `tests/fixtures/` | The handbook regression cases plus the synthetic era fixtures |
| Packaging | `uv` + `pyproject.toml`; `make offline-demo` runs with network disabled | Offline sample path |

Layout:

```
fieldshift/
  catalogs/      # loader, validation, rule lookup
  weather/       # POWER client, normalizer, snapshot, manifest
  seasons/       # date alignment, windows, coverage
  metrics/       # winter exposure, spring dryness, rule checks
  compare/       # plan comparison, two-period comparison, sensitivity
  planner/       # crop/date checker, action calendar, backup plan
  field/         # location, soil (SDA), zones, live conditions
  tools/         # irrigation, fertilizer
  report/        # field note, audit trail
  api/           # FastAPI routers + response models
data/
  catalogs/v1/   # crops.csv, crop_rules.csv, fertilizers.csv (Perplexity, verbatim)
  snapshots/union_county/  # raw + normalized weather, manifest.json
  samples/       # sample field, zones, plans
tests/
  fixtures/      # synthetic weather and plans (labeled as fixtures)
```

## Known catalog gaps (from the v1 CSVs)

Report these to Perplexity. Do not wait on them.

1. **Winter wheat has only rotation rules** (`ww_rc_01`, `sb_rc_03`). There are no planting window, harvest timing, or double-crop soybean planting window rows yet. The wheat path stays `unavailable` until they arrive.
2. **`fc_nut_01` and `sb_nut_01` have a blank `verified_date`.** The loader flags them, and it keeps them as "no automatic N rate" rows.
3. **Corn days-to-maturity for the Piedmont is missing.** `fc_gd_01` covers Hertford County only. Harvest dates must come from the grower or the sample plan, not from the catalog.
4. **There is no heavy-rain day definition in the catalogs.** It comes from the handbook or a published product rule (Phase 4).
5. **`fc_pw_01` and `fc_pw_02` conflict (55 °F vs 50 °F), and so do `sb_pw_01` and `sb_pw_04` (May 20 vs May 30).** These conflicts are intentional. Surface both rules and do not pick a winner.
6. **There are no cereal rye termination-to-harvest or establishment-window rows.** The living-cover interval stays "planned" from seeding to termination, and establishment is labeled uncertain.

The handbooks (`Field-Shift-Backend-Rahul.pdf`, `Field-Shift-Charlotte-Playbook-2.pdf`) are **not in the workspace yet**. Add them to `docs/handbooks/`. Phases 1, 2 and 4 need their Union County point, sample plan dates, heavy-rain rule, and regression values.

---

## Phase 0 — Scaffold and catalog ingestion

**Goal:** a project that loads the three Perplexity catalogs and validates them strictly, with per-row errors.

**Build**
- `pyproject.toml`, the package layout above, `pytest`, `ruff`, and a `Makefile` (`test`, `serve`, `offline-demo`).
- `catalogs/loader.py`: typed models `Crop`, `CropRule`, `Fertilizer`. Blank values become `None`, never 0. A genuine `0` stays a number.
- `catalogs/validate.py` checks:
  - the header matches the contract
  - IDs are unique and lowercase snake_case
  - every `crop_id`, `previous_crop_id` and `next_crop_id` exists in crops
  - `rule_type`, `operator` and `suitability` are in their allowed sets
  - `between` has both bounds with min ≤ max
  - single-bound operators have no `value_max`
  - `MM-DD` dates and `YYYY-MM-DD` `verified_date` values parse
  - units are known
  - `source_url` and `source_locator` are present
  - the fertilizer `grade` string matches `n/p/k` percentages (ignore trailing S/Zn), and percentages are between 0 and 100
- Validation result: a list of `{file, row, field, severity, message}`. Usable rows are kept even when other rows fail.
- `catalogs/index.py`: lookups by crop, rule_type, previous/next crop, region, and production system.
- A catalog manifest with a file hash, row counts, and the load time.

**Acceptance**
- The v1 CSVs load. The two blank `verified_date` rows appear as warnings, not errors.
- Fixture CSVs with a bad operator, a dangling crop ref, a reversed `between`, a duplicate ID, or a grade mismatch each produce the exact file, row, and field.
- The `exposure_duration` value `several` (`sb_wt_02`) is preserved as qualitative and is not coerced.


**Status (B, 2026-11-13): done.** v1 catalogs load (5 crops, 85 rules, 5 fertilizers; only the two blank-`verified_date` warnings). Codex review r1 (3 medium) and r2 (1 medium: parse-error crops orphaning rules) all fixed with tests; no r3 run.

**Catalog v2 (B, 2026-11-13): done.** Units `seeds/ft2` and `seeds/acre` added; `data/catalogs/v2` loads with 0 errors and 0 warnings (98 rules); `DEFAULT_CATALOG_DIR` is v2 and the v1 regression tests stay on v1. `fc_nut_01` (120-160 lb N/ac) is shown in the checker, calendar and fertilizer tool as a sourced reference (`is_grower_target: false`), never used as the grower's target; `sb_nut_01 = 0` is kept as a real zero. Also: `organic_grain` requirement mapped (organic + grain), mid-June/mid-July maturity-group rows honor a planting-date context, and the residual-stubble rule is `manual_check`. Codex r1 (2 medium) and r2 (1 medium) fixed with tests; no r3. `docs/api/*` was regenerated (catalog_version and rule text changed).
---

## Phase 1 — NASA weather ingestion and offline snapshot (Union County)

**Goal:** a verified, reproducible daily record for the Union County reference point, packaged offline.

**Build**
- Confirm the eligible dataset against the challenge Resources list. The candidate is the NASA POWER Daily API (`community=AG`). For the chosen POWER source, record:
  - the source product for `PRECTOTCORR`, `T2M_MAX`, `T2M_MIN`, `T2M`, `GWETTOP`, and `GWETROOT`
  - the native grid (MERRA-2 is ~0.5° × 0.625°, and POWER precipitation comes from a different source; verify this)
  - the time convention (LST vs UTC)
  - the fill value (`-999`)
  - the units
- `weather/power_client.py`: fetch by lat/lon and date range, with timeouts and retries. Save the **raw response untouched**, along with the query URL, coordinates, returned grid cell, parameters, API version, and retrieval time.
- `weather/normalize.py`:
  - converts to a daily table: `date, precip_mm, tmax_c, tmin_c, tmean_c, gwettop, gwetroot`
  - marks fill values, negatives, and NaN as missing (with a reason)
  - de-duplicates dates (and logs it)
  - keeps real zeros
  - reindexes to a full calendar so missing dates are explicit rows
- `weather/snapshot.py`: writes `data/snapshots/union_county/{raw/, daily.parquet, manifest.json}`. The manifest holds the source, version, query, grid, coverage start and end, missing-date list, hashes, and retrieval date.
- A coverage report showing the first and last valid date per variable.
- Fetch span: start as early as the source allows (the target is the 1980 fall, so the 1981 winter is complete) and run through mid-2025.

**Acceptance**
- `make offline-demo` reads only the snapshot.
- Re-normalizing the raw response reproduces `daily.parquet` byte-for-byte (hash match).
- Fixture tests cover:
  - a fill value
  - a negative precipitation value
  - a duplicate date
  - a gap
  - a real 0.0 mm day
- If the series starts on 1981-01-01, the manifest says so. Phase 2 must then mark winter 1981 incomplete.

**Status (A, 2026-11-13): done.** `weather/{sources,power_client,normalize,snapshot,coverage}.py`, `python -m fieldshift.weather {build,verify,report}`, committed snapshot `data/snapshots/union_county/` (POWER AG daily, 1981-01-01..2025-06-30, 16,252 days, no gaps; series starts 1981-01-01 so winter 1981 is partial). Point = Monroe NC ASSUMED (handbook missing). `/health` stub serves `offline-demo` from the snapshot only. Codex r1 and r2 fixed; parquet bytes only reproducible on the same pyarrow version (canonical hash always enforced; see review reply).

---

## Phase 2 — Season alignment and coverage

**Goal:** map one plan onto every historical planting year, with explicit inclusive/exclusive windows and coverage.

**Build**
- A `Plan` model with these fields:
  - `previous_crop_id` and `prev_harvest` (MM-DD)
  - winter management: `none`, `cover(crop_id, seed MM-DD, terminate MM-DD)`, or `winter_grain(crop_id, plant, harvest)`
  - `next_crop_id`, `next_plant` (MM-DD), production system, and grower-reported moisture concern
- `seasons/align.py`: for each planting year Y in 1981–2025, build a `SeasonCalendar`:
  - Previous harvest happens in Y−1 if its MM-DD is later than the next planting MM-DD, otherwise in Y.
  - The winter rain window runs `[prev_harvest, next_plant)`, so the harvest day is included and the planting day is excluded.
  - The living-cover interval runs `[seed, terminate)`, labeled `planned`, and establishment is uncertain.
  - The spring window is `[next_plant − 30d, next_plant − 1d]`; for May 12 that is Apr 12–May 11.
  - The termination gap is `next_plant − terminate` in days.
- **Leap days:** dates are MM-DD anchored per year. Feb 29 in a plan resolves to Feb 28 in non-leap years (document this). Window lengths are computed from real dates, so a winter spanning Feb 29 has one more day.
- Chronology validation, which raises `invalid_input` with the field when:
  - seeding comes before harvest
  - termination comes after planting
  - a window would be negative
- `seasons/coverage.py`: for each metric (winter, spring, full season), count expected, valid, and missing days. The status is `complete`, `partial`, or `unavailable`, and a missing input makes only that metric unavailable.

**Acceptance**
- May 12 planting gives a spring window of Apr 12–May 11 (30 days).
- With data starting 1981-01-01, the 1981 spring is `complete` and the 1981 winter is `incomplete`. A 45-spring record gives 44 complete winters.
- Leap-year fixture: the winter window that crosses 2020-02-29 is one day longer than the one that crosses 2019-02-28.
- Invalid chronology returns a typed error, not an exception trace.

**Status (A, 2026-11-13): done.** `fieldshift/contracts.py` (Plan, SeasonCalendar, SeasonFacts, ThresholdSet, MetricResult, `Status`), `seasons/{dates,validate,align,coverage,facts}.py`, `weather/series.py`. 45 planting years 1981-2025; 1981 spring complete, 1981 winter partial (44 complete winters); leap-day rule documented in `seasons/dates.py`; typed `invalid_input` errors. Codex r1 (4 medium) and r2 (1 medium) fixed with tests.

---

## Phase 3 — Winter soil-protection exposure

**Goal:** per season, measure how much rain fell while no living cover was planned.

**Build**
- Heavy-rain day definition. Use the **handbook / published product rule first**. If it is relative (for example, the 95th percentile of wet days), derive it **once** from the location's full-record seasonal reference, then freeze it in a `ThresholdSet` with the method, value, and reference span. Every plan and both eras share the same `ThresholdSet`.
- `metrics/winter.py`, per season:
  - Counts living-cover days and days outside cover within the winter window.
  - Splits outside days into `before_establishment`, `after_termination`, and `no_planned_cover`.
  - Totals rain (mm) and heavy-rain days in each segment.
  - Lists the heavy-rain events by date and segment.
  - Records `residue_context` (corn residue / cover residue / grower-reported) separately. This never changes the living-cover indicator.
- Paired plans use the same weather rows. The output carries the weather snapshot hash so the frontend can verify this.

**Acceptance**
- A fixture heavy-rain day the day before seeding counts as `before_establishment`.
- A fixture heavy-rain day on the termination day counts as `after_termination`, because the termination day is outside the `[seed, terminate)` interval.
- A grower residue report stays visible and does not change any count.
- No cover vs. rye: identical total winter rain and identical event dates; only the segment labels differ.

**Status (A, 2026-11-13): done.** `metrics/thresholds.py` (frozen `ThresholdSet`), `metrics/winter.py`. Heavy-rain rule is ASSUMED (P95 of wet days >= 1 mm, Sep-May, full record) because the handbook is missing; one constant (`HEAVY_RAIN_RULE`) to change. Codex r1 (2 medium) fixed; r2 PASS. **2026-11-13 update: the ASSUMED P95 rule is replaced by the published fixed threshold (daily precip >= 76.2 mm, catalog v2 `fc_v2_ref_very_heavy_rain`, source/URL/locator frozen in the ThresholdSet, POWER LST convention in the note); r3 PASS.**

---

## Phase 4 — Spring planting conditions and rule checks

**Goal:** dryness rank per window, plus a sourced rule engine that turns rules into per-season checks.

**Build**
- `metrics/spring.py`:
  - 30-day precipitation total for each eligible year
  - rank (1 = driest) and percentile
  - the dry label uses a **fixed cutoff**: the bottom 20% of the full eligible 1981–2025 record for that location and window. The cutoff value is frozen in a `ThresholdSet`.
  - Tie rule: years equal to the cutoff count as dry. Document this.
  - Incomplete windows are excluded from both the ranking and the denominator, and they are listed with a reason.
  - Modeled wetness (GWETTOP and GWETROOT window means) is reported separately and labeled `modeled`.
- `metrics/rules.py`, the rule engine:
  - Maps a `condition_key` to an evaluator, such as `days_between_termination_and_planting`, `seed_zone_soil_temperature`, `forecast_precipitation`, or window dates.
  - Checks applicability by crop, previous/next crop, region, production system, and stage. A non-matching rule is `inapplicable`, with a reason.
  - A qualitative rule, or one without a matching measurement, becomes `manual_check`.
  - `unknown` covers missing inputs, and conflicting applicable rules are both returned with `conflict` flagged.
- The handbook rye→soybean check (`cr_tt_03`) triggers when:
  - `gap < 14` **and** (the replay is dry, **or** the grower reported a low-moisture concern). At gap ≥ 14 it clears.
  - `cr_tt_04` (21–28 days, insect spillover) is surfaced as its own optional check, conditioned on concern.
- Per-check result: the qualifying years, skipped years with reasons, count / denominator, and the source rule IDs and URLs. When a combined count is shown, each season counts once and the component events are listed.

**Acceptance (handbook regression cases)**
1. Typical year with unknown field moisture: no dry-replay prompt.
2. 12-day rye gap in a dry replay year: moisture check prompted.
3. Edit the rye termination to make a 19-day gap: the check clears, and the spring rainfall window, total, and rank are **unchanged**.
4. Weather missing for the window, with a grower-reported concern: the check still fires from the concern, and the calendar metrics stay valid; the dryness metric is `unavailable`.
5. Editing the planting date recomputes the window and the rank.


**Status (B, 2026-11-13): 4b (rule engine) done; 4a and the regression cases are A's.** `fieldshift/metrics/rules.py` (+ `field/regions.py`) covers applicability, `manual_check`/`unknown`, catalog-declared conflicts, `cr_tt_03` (gap < 14 and (dry or concern); clears at gap >= 14 even with dryness missing) and optional `cr_tt_04`, and per-check qualifying/skipped/count/denominator. It reads the real `SeasonFacts`. Codex r1 (7 medium) and r2 (4 medium) fixed with tests; no r3 run. A: pass regression cases 1-5 once 4a lands (see docs/handoff.md).

**Status (A, 2026-11-13): 4a done; regression cases 1-5 pass** against B's rule engine (`tests/metrics/test_metrics_spring.py`). `metrics/spring.py`: fixed 1981-2025 baseline, bottom-20% cutoff = ceil(20% n)-th smallest, ties at the cutoff are dry, modeled wetness. Codex r1 (4 medium) and r2 (2 medium) fixed with tests; no r3 run.
---

## Phase 5 — Two-period comparison (1981–2000 vs 2006–2025)

**Goal:** a descriptive earlier-vs-recent comparison with honest denominators.

**Build**
- `compare/eras.py`, which computes for each indicator (dry spring windows, winter heavy-rain days outside cover, each plan check):
  - the event count, eligible count, and percentage for each era
  - the percentage-point difference
  - the shared `ThresholdSet` that was used
- Minimum coverage: each era needs ≥ 15 of its 20 seasons evaluable, or the result is `insufficient_data`. Document the constant.
- Result label:
  - `more_frequent_recent`, `less_frequent_recent`, or `similar`, with a documented similarity band (for example, |Δ| < 10 pp)
  - `insufficient_data` when coverage is too thin
  - Each label comes with fixed explanatory text: descriptive only, no trend/cause/forecast claim.
- 2001–2005 stays out of both eras, though those years remain in the full record and replay.
- For cross-plan comparisons, use only the complete years both plans share, or label the coverage difference.

**Acceptance**
- A fixture with dry windows concentrated in 2006–2025 gives the exact expected counts and pp difference.
- A similar-frequency fixture gives `similar`.
- A fixture with 10 missing seasons in one era gives `insufficient_data`.
- The cutoff value is identical in both eras' outputs.

---

## Phase 6 — Plan comparison, replay, and sensitivity API

**Goal:** the first end-to-end API for the core stress test (build-order step 1 is complete after this phase).

**Build**
- Sample plans in `data/samples/union_plans.json`:
  - corn → no cover → soybean
  - corn → rye (12-day gap) → soybean
  - corn → rye (19-day gap) → soybean
  - corn → crimson clover → soybean. This flags `sb_rc_02` (legume before soybean), `cc_rc_02` (seed window after corn harvest), and `cc_soil_02` (Piedmont clay manual check).
- Endpoints:
  - `POST /v1/plans/compare`: up to N plans. Returns:
    - per-plan calendars, winter exposure, spring checks, and era comparison
    - shared eligible years and the threshold sets
    - a `result_id` and the `input_hash`
  - `GET /v1/seasons/{year}/replay?plan=...`: daily rows (precipitation, temperature, wetness, cover status, segment) for the exact season dates, plus triggered checks and their evidence.
  - `POST /v1/plans/sensitivity`: sweeps termination dates over the valid range and returns, per date:
    - living-cover days
    - winter rain outside cover
    - the number of historical checks. With the fixed 14-day rule this is a step function: the dry-year count below 14 days and 0 at or above.
  - `GET /v1/years`: every year with status `complete`, `partial`, or `unavailable`, plus typical/dry/wet shortcuts.
- Every response carries `{plan_version, catalog_version, snapshot_hash, request_id}` so stale results can't overwrite newer ones.

**Acceptance**
- Choosing a replay year changes only the replay payload. The aggregate and era results are byte-identical.
- The sensitivity curve is flat on both sides of 14 days, and the step size equals the dry-year count.
- One replay can be reproduced by a standalone script from `raw/` alone, without the API (a reproducibility test).

**Status (A, 2026-11-13): Phase 5 done; Phase 6 done.** Phase 5: `compare/eras.py` (constants EARLIER 1981-2000, RECENT 2006-2025, MIN 15 of 20 evaluable, similarity band 10 pp, fixed caveat text, shared-year cross-plan helper); Codex r1 (2 medium) fixed, r2 PASS. Phase 6: `api/{app,routes,samples}.py`, `compare/{engine,models,replay,sensitivity,years,context}.py`, `data/samples/union_plans.json` (dates ASSUMED per docs/api/presets.md), `scripts/reproduce_replay.py` (stdlib-only reproduction of the replay from `raw/`); endpoints `POST /v1/plans/compare`, `GET|POST /v1/seasons/{year}/replay`, `POST /v1/plans/sensitivity`, `GET /v1/years`, `GET /v1/rotations`; B's routers mounted. Codex r1 (8 medium/low) and r2 (1 high, 3 medium) fixed with tests; no r3. See docs/handoff.md for shape differences from the drafts.

---

## Phase 7 — Crop and date checker

**Goal:** evaluate any supported crop sequence against the catalog (build-order step 2).

**Build**
- `planner/checker.py`: given previous crop and harvest date, winter management, next crop and date, region, production system, and field facts, return each applicable rule as `{rule_id, verdict: preferred|acceptable|caution|avoid|manual_check|unknown|inapplicable, reason, inputs_used, source}`.
- Covers:
  - planting and seeding windows (`cr_pw_*`, `cc_pw_*`, `sb_pw_*`, `fc_pw_*`)
  - rotation compatibility (`cr_rc_*`, `cc_rc_*`, `sb_rc_*`, `ww_rc_01`)
  - termination timing (`cr_tt_*`, `cc_tt_*`)
  - soil fit, nutrient trade-offs (`cr_nut_01`, `fc_nut_03`, `cc_trait_01`), and water and light context
- Hard conflicts come from chronology, such as clover seeding after Oct 1 following a late corn harvest.
- `POST /v1/plans/check` and `GET /v1/crops` (supported crops, with roles and which paths are available).
- "Help me find a plan": enumerate the winter options supported for a given cash-crop pair and rank them by grower priority (soil protection / planting window / limited water). Ranking only reorders the results; it never changes the facts.

**Acceptance**
- Clover after a corn harvest on Oct 10 is a chronology conflict against `cc_rc_02`.
- `fc_pw_03` (organic, Piedmont) is `inapplicable` to a conventional plan, and the reason says why.
- `fc_pw_01` and `fc_pw_02` are both returned and flagged as a conflict.
- An unsupported crop or location returns `unsupported` (distinct from `unknown`).


**Status (B, 2026-11-13): done.** `planner/checker.py`, `finder.py`, `crops.py`, `routes.py` (`POST /v1/plans/check`, `POST /v1/plans/find`, `GET /v1/crops`). Acceptance cases tested. Codex r1 (3 P1, 3 P2) and r2 (1 P1, 1 P2) fixed with tests; no r3 run. **Left for A:** mount the router in `api/app.py` (handoff).
---

## Phase 8 — Locations and soil

**Goal:** any eligible North Carolina point gets its weather grid and soil context.

**Build**
- `field/location.py`:
  - validates the point is inside the NC bounds
  - resolves the POWER grid cell
  - reuses a cached history when the grid cell matches, otherwise fetches it through the Phase 1 pipeline
  - separates `weather_supported` from `guidance_supported`. Regions are matched against the rule `region` text with an explicit mapping table (Piedmont / Coastal Plain / Mountains / statewide), and an unmapped region becomes `unknown`.
- `field/soil.py`: query USDA Soil Data Access (SDA, a REST SQL endpoint) for the map unit at the point and return:
  - the dominant component
  - surface texture, drainage class, and available water capacity by depth (with units)
  - the survey version, and provenance
- On failure, the response is `unavailable` with a reason, and the rest of the response still works.
- Grower observations and soil tests are stored as separate evidence, each with the observation date and zone.
- `POST /v1/locations/resolve`, `GET /v1/soil?lat&lon`.

**Acceptance**
- The Union County sample resolves offline from the snapshot.
- When SDA times out, the plan comparison still succeeds and `soil.status = unavailable`.
- A point outside NC returns `unsupported_location`.


**Status (B, 2026-11-13): done, except two items that are A's.** `field/location.py`, `soil.py`, `evidence.py`, `routes.py` (`POST /v1/locations/resolve`, `GET /v1/soil`). Union sample resolves offline; SDA failure gives `soil.status=unavailable`; outside NC gives `unsupported_location` (coarse offline outline, ~10 km at the border). Codex r1 (1 high, 7 medium) and r2 (4 medium) fixed with tests; no r3 run. **Left for A:** mount the router, and call `get_soil()` from plan comparison (handoff).
---

## Phase 9 — Decision tools: action calendar, backup plan, field note, audit

**Goal:** turn analysis into an actionable, traceable plan (build-order step 3).

**Build**
- `planner/calendar.py`: produce dated actions (seed, terminate, plant, harvest, checks), each with its zone, trigger, evidence, and status. The dry scenario shows which decision could change; the wet scenario shows drainage or access checks when supported.
- `planner/backup.py`: a default plan plus a fallback, with a switch condition, the next check date, and a decision deadline. The first release compares the two as fixed plans. An optional backtest may use only data available at the decision date, and its cutoffs are frozen in advance.
- `report/audit.py`: every displayed number carries `{value, unit, derivation: nasa|usda|extension|grower|calculation, source_ref, inputs}`.
- `report/field_note.py`: `GET /v1/plans/{id}/note` returns **structured JSON only**. The frontend (Abhi) owns rendering and printing, as agreed on 2026-11-12. The backend does not produce HTML or PDF. It includes the plan and alternatives, winter and spring results, eras, the calendar, unresolved checks, sources, and adviser note fields.
- Wetness playback: aligned daily values in the replay (from Phase 6), labeled modeled.

**Acceptance**
- Editing a crop or date regenerates the calendar, and a diff shows what changed and why.
- Every number in the field note resolves to an audit entry, and a test walks all of them.
- One fixed alternative and one changed planting calendar both produce correct notes.


**Status (B, 2026-11-13): done (JSON-only note).** `planner/calendar.py` (actions with zone/trigger/evidence/status, typical/dry/wet scenarios, edit diff with reasons), `planner/backup.py` (default + fallback, switch condition by the rule's own gate, deadline, next check, fixed-plan comparison; backtest `unavailable`), `report/audit.py`, `report/field_note.py`, `report/routes.py` (`POST /v1/plans/calendar|backup|note`, `GET /v1/plans/{id}/note`). A test walks every number in the note to an audit entry. Codex r1 (3 high, 4 medium) and r2 (2 medium) fixed with tests; no r3. Assumption labeled: next check = deadline - 7 days. Wetness playback is the replay's (A) with the modeled label; the note carries window means.
---

## Phase 10 — API contract and reliability (Abhi handoff)

Start this in parallel with Phase 6, then finalize it here.

**Build**
- Freeze the OpenAPI schema as `docs/api/openapi.json`, plus example requests and responses in `docs/api/examples/`, generated from the real sample.
- Error taxonomy: `invalid_input` (400, with field), `unsupported`, `unknown_evidence`, `unavailable_data`, and `inapplicable`. These go in the response body per metric, not as HTTP errors, so a partial result is preserved.
- Labels and values ship together, so the frontend never re-derives eligibility.
- Timeouts per provider, the cache policy (POWER history: permanent; SDA: 30 days; NWS: minutes), and freshness labels `fresh | cached(at) | snapshot | unavailable`.
- Logging scrubs grower-entered data. Public fixtures contain no real grower data.
- `docs/backend-runbook.md`: offline run, test commands, method notes, and source list.

**Acceptance**
- With the network disabled in a fresh clone, `make offline-demo` serves the sample and all core calculations.
- A contract test checks that the example responses validate against the schema.

**Status (A, 2026-11-13): done.** `api/{contract,logs,schemas}.py`, frozen `docs/api/openapi.json`, real examples + requests in `docs/api/examples/` (replacing the drafts), `docs/backend-runbook.md`. Contract tests validate every example against the schema and fail on drift (`python -m fieldshift.api.contract --check`); typed 400/500/404/405 envelopes with the four metadata fields (OpenAPI documents 400, not 422); freshness labels in `data_sources`; log scrubbing (whole-message redaction, tracebacks reduced to locations, uvicorn query strings stripped); offline-demo verified in a fresh process that refuses non-loopback connections. Codex r1 (2 high, 2 medium, 1 low) and r2 (1 high, 1 medium, 1 low) fixed with tests; no r3.

---

## Phase 11 — Field tools: zones, live conditions, irrigation, fertilizer

**Goal:** supporting tools (build-order step 4).

**Build**
- **Zones:** predefined sample zones in `data/samples/zones.json`, with elevation and slope summarized from USGS 3DEP. Each zone records its terrain source, date, resolution, and drainage. Grower ponding reports trigger an inspection prompt when heavy rain falls in a plausible collection zone. If the grower reports regrading or drainage changes after the terrain survey, the affected findings are flagged `verify`.
- **Live:** NWS API forecast and alerts, plus U.S. Drought Monitor for the county. These live in a separate `live` block with fetch time and validity, and they never feed historical checks.
- **Irrigation:**
  - Stage checks come from `*_wd_*` rules (for example, soybean R1–R5, corn pollination).
  - A numeric water balance is returned only when crop stage, weather, soil AWC, recent irrigation, and a starting moisture value are all present. Otherwise the response lists what's missing.
  - Crop demand (`fc_wd_02/03`, `sb_wd_02–05`) is kept separate from supplemental irrigation need.
- **Fertilizer:** `POST /v1/fertilizer/calc`. The input is a nutrient target (from the soil test or guidance), the product (from the catalog or a grower-entered grade), and the area. The output is:
  - lb/ac, total product, and nutrients delivered
  - the excess or shortfall per nutrient
  - Zero-content nutrients are handled safely, single-product blend limits are noted, and the response never invents an N rate (see `fc_nut_01` and `sb_nut_01`).

**Acceptance**
- 120 lb N/ac with urea (46%) gives 260.9 lb product/ac. Asking for a P target with urea gives a "product supplies no P₂O₅" result, not a divide-by-zero.
- When NWS is down, the live block is `unavailable` and the history is unchanged.


**Status (B, 2026-11-13): done.** `field/zones.py` (+ sample `data/samples/zones.json`), `field/live.py`, `tools/irrigation.py`, `tools/fertilizer.py`, `tools/routes.py`, zone/live routes in `field/routes.py`. Acceptance cases tested (120 lb N urea = 260.9 lb/ac; P target with urea = `product_supplies_none`; NWS down = live block `unavailable`, history unchanged). Codex r1 (1 high, 8 medium) and r2 (3 medium: tiny-grade/overflow, extreme irrigation amounts, unknown change-report zone) fixed with tests; no r3 run. **Left for A:** mount the field and tools routers (handoff).
---

## Phase 12 — Winter wheat double-crop and SMAP (when evidence lands)

**Goal:** a changed-calendar path and a wetness cross-check.

**Build**
- Once Perplexity supplies the wheat planting and harvest rows and the double-crop soybean window, enable `winter_grain(winter_wheat)`. The soybean planting window moves to after the wheat harvest.
  - Its dry percentile is computed against **its own** window baseline and labeled that way.
  - Cross-calendar comparisons use raw totals or a common rule only.
  - `ww_rc_01` (head scab after corn) and `sb_rc_03` (MG < 4 caution) fire.
- Stretch: an NSIDC SMAP L3/L4 soil moisture series for matching years (2015 onward), compared against POWER GWETTOP. Both are labeled and kept distinct.

**Acceptance**
- A wheat→double-crop plan shows its own planting window dates, and the comparison against full-season soybean is explicitly labeled as different-calendar.
- Without wheat rows, the path returns `unavailable: catalog_missing` and everything else still works.


**Status (B, 2026-11-13): double-crop path done; SMAP skipped (stretch).** `planner/wheat_path.py` + `POST /v1/plans/wheat`, `GET /v1/plans/wheat/template`. Grower enters wheat plant/harvest and soybean planting dates (catalog v2 has no numeric Piedmont windows); MG checked with `sb_v2_mg_mid_june/july` (planting-date context, mid-month = 15th +/- 7 days, assumed) and `sb_rc_03`; qualitative and map rows `manual_check`; `organic_grain` rows inapplicable to conventional; dry label uses its own window baseline; cross-calendar comparison against full-season soybean is labeled `different-calendar` with raw totals only; catalog v1 gives `unavailable: catalog_missing`. Codex r1 (1 high, 3 medium) fixed with tests. **Left for A:** `analyze_plan` still returns unavailable for `winter_grain` plans; route them to `evaluate_wheat_double_crop`. The Phase 9 field note does not cover wheat plans yet.
---

## Phase order at a glance

| Phase | Depends on | Unlocks |
|---|---|---|
| 0 Catalogs | — | 4, 7 |
| 1 Weather snapshot | handbook point | 2 |
| 2 Alignment | 1 | 3, 4 |
| 3 Winter exposure | 2 | 5, 6 |
| 4 Spring + rules | 0, 2 | 5, 6 |
| 5 Eras | 3, 4 | 6 |
| 6 Compare API | 3–5 | 9, 10 |
| 7 Checker | 0 | 9, 12 |
| 8 Location/soil | 1 | 11 |
| 9 Decision tools | 6, 7 | — |
| 10 Contract | 6 | Abhi |
| 11 Field tools | 8 | — |
| 12 Wheat / SMAP | 7 + Perplexity | — |
