# Field Shift backend runbook

> Run every command below from the `backend/` folder (`cd backend`). Hosting: Railway, configured by `railway.json` (service root directory `backend`, start `python -m uvicorn fieldshift.api.app:app --host 0.0.0.0 --port $PORT`, health check `/health`).

Backend only. The frontend reads the contract in `docs/api/openapi.json` and the generated examples in `docs/api/examples/`.

## 1. Run it offline

The core calculations and the sample run from files in the repo; no network, no database server.

```bash
uv sync                      # Python 3.12, FastAPI, pydantic v2, pandas, httpx, pyarrow
make offline-demo            # FIELDSHIFT_OFFLINE=1 uvicorn fieldshift.api.app:app
curl localhost:8000/health
curl -X POST localhost:8000/v1/plans/compare -H 'content-type: application/json' \
     -d '{"rotation_ids": ["current_practice", "winter_cover"]}'
```

With `FIELDSHIFT_OFFLINE=1`, weather comes only from the committed snapshots under `data/snapshots/` (`index.json` lists them: Union plus seven more NC counties) and no live provider (NWS, USDM, USDA SDA, NASA POWER) is called. A provider with a still-valid on-disk cache entry (SDA 30 days, `data/cache/`, not committed, so empty in a fresh clone) is answered from it and labelled `cached(<time>)`; otherwise it is reported `unavailable`; plan comparison, replay, sensitivity and years all still work. A test (`tests/api/test_api_contract.py::test_offline_demo_...`) starts a fresh process that refuses every non-loopback connection and exercises those endpoints.

Python 3.12 is the target. The code is also 3.11-compatible (no PEP 695 syntax) because the Homebrew 3.12 on one development Mac has a broken `pyexpat`.

## 2. Tests and checks

```bash
make test                    # uv run python -m pytest   (offline; live providers are mocked)
make lint                    # ruff check .
python -m fieldshift.api.contract --check   # exit 1 if docs/api is stale
python -m fieldshift.weather verify         # raw/ -> daily.parquet reproduction + hashes
python -m fieldshift.weather report         # first/last valid date per variable
```

`tests/api/test_api_contract.py` validates every example response against `docs/api/openapi.json`, and fails when the committed contract files drift from the code. Regenerate them with `python -m fieldshift.api.contract` (offline).

Reproduce a replay without the API, from `raw/` alone (standard library only):

```bash
python scripts/reproduce_replay.py --raw data/snapshots/union_county/raw/power_daily.json \
  --plans data/samples/union_plans.json --plan corn_soy__rye --year 2008
```

## 3. Method notes

**Weather source.** NASA POWER Daily API v2.10.3, `community=AG`, point query, parameters `PRECTOTCORR` (MERRA-2 bias-corrected precipitation, mm/day), `T2M_MAX`, `T2M_MIN`, `T2M`, `GWETTOP`, `GWETROOT` (modeled soil wetness, 0-1). Fill value -999; time standard LST (Local Solar Time). The series starts 1981-01-01, so the winter that begins in fall 1980 is incomplete: winter 1981 is `partial`, giving 44 complete winters and 45 complete springs through 2025. The point echoes the request; the 0.5 x 0.625 degree MERRA-2 cell is derived, not returned by the API. The Union County point (Monroe, NC) is **assumed** until the handbook lands.

**Normalization.** Fill values, negative precipitation/wetness, wetness above 1, null/blank/non-numeric values and absent dates are missing with a reason; a real 0 stays 0. Duplicate dates are de-duplicated (first wins) and logged. The table is reindexed to every calendar day.

**Windows.** Plans are `MM-DD` anchored per year; Feb 29 resolves to Feb 28 in non-leap years. Winter window `[prev_harvest, next_plant)`; living-cover interval `[seed, terminate)` labelled `planned` (establishment uncertain; the termination day is not cover); spring window `[next_plant - 30 d, next_plant - 1 d]`; termination gap `next_plant - terminate`.

**Frozen thresholds.** Computed once per request from the whole 1981-2025 record, held in an immutable `ThresholdSet`, and shared by every plan and both eras.
- Heavy-rain day: daily `precip_mm >= 76.2` (3 in), the published "very heavy rain" definition (catalog v2 `fc_v2_ref_very_heavy_rain`, `data/catalogs/v2/weather_references.csv`; NC Climate Science Report: Plain Language Summary, March 2020, PDF p. 4). Source URL and locator are frozen into `thresholds.heavy_rain.source`. POWER daily values are Local Solar Time days, not a rolling 24 h window, so a storm split across two solar days can miss the line; the threshold note says so. It is a rainfall-depth weather metric only, never erosion, runoff or soil loss. Most winters have zero qualifying days (6 days >= 76.2 mm fall in Sep-May over 1981-2025); a zero is a real result, and total rain outside living cover is the main winter indicator. The earlier relative P95 rule was dropped from the ThresholdSet (still available as an explicit `HeavyRainRule` option for experiments).
- Dry spring: the `ceil(20% of n)`-th smallest 30-day total among complete 1981-2025 windows for that planting date (45 eligible years gives the 9th smallest). Years equal to the cutoff count as dry.
- Rank 1 = driest; ties share the lowest rank; percentile is the share of eligible years at or below the total.

**Eras.** Earlier 1981-2000, recent 2006-2025; 2001-2005 are in neither (still in the full record and replay). Each era needs >= 15 of 20 evaluable seasons or the result is `insufficient_data`. `|diff| < 10` percentage points is `similar`. Descriptive only; each label ships with fixed text and no trend, cause or forecast claim. Cross-plan comparisons are also given on the years every plan could be evaluated for.

**Rules.** The rule engine (`fieldshift/metrics/rules.py`) evaluates the Perplexity catalogs against one `SeasonFacts` per season. `cr_tt_03` (rye to soybean): flagged when the gap is under 14 days and (the replay is dry or the grower reports a low-moisture concern); clears at 14 days or more. Conflicting rules (`fc_pw_01`/`fc_pw_02`, `sb_pw_01`/`sb_pw_04`) are both surfaced.

**Sensitivity.** Termination dates from the day after seeding through planting; with the fixed 14-day rule the check count is a step function (the dry-year count below 14 days, 0 at or above). A date whose gap crosses Feb 29 reports `gap_days_in_leap_years`.

## 4. Error taxonomy

HTTP 400 is only for invalid input (typed `{field, code, message}` issues); everything else is a 200 with a status in the body, so a partial result is preserved. Unknown paths/methods (404/405) and unexpected errors (500, no detail beyond a fixed code) use the same envelope with the four metadata fields.

| Card term | Where it appears | Status string |
|---|---|---|
| `invalid_input` | HTTP 400 `{status, issues[{field, code, message}], meta fields}` | `invalid_input` |
| `unsupported` | per plan / per response (unknown crop, or a point outside North Carolina: code `unsupported_location`) | `unsupported` |
| `unavailable` | an NC point whose grid cell has no committed snapshot: code `no_weather_snapshot`, `meta.snapshot_hash` null | `unavailable` |
| `unknown_evidence` | a rule or metric that lacks an input | `unknown` (or `manual_check` for qualitative rules) |
| `unavailable_data` | weather window missing, provider down, catalog rows missing (`reason: catalog_missing`) | `unavailable` / `partial` |
| `inapplicable` | a rule that does not apply to this crop, region or system | `inapplicable` |

Other statuses: `complete`, `partial`, `insufficient_data` (era or cutoff has too few evaluable seasons), `manual_check`.

## 5. Providers, timeouts, cache policy, freshness

| Provider | Used for | Timeout | Cache policy | Offline behaviour |
|---|---|---|---|---|
| NASA POWER Daily | weather history (build only) | 120 s, 3 retries (2 s, 4 s, 8 s backoff) | permanent: the committed snapshot in `data/snapshots/` | never called at serve time; `python -m fieldshift.weather build` (Union) and `build-locations` (the counties) are the only fetches |
| USDA SDA | soil | 15 s | 30 days on disk (`data/cache/sda`, gitignored) | `cached(<time>)` if a valid copy exists, else `unavailable` |
| NWS API | forecast / alerts | 10 s | 15 min / 5 min | `unavailable` |
| US Drought Monitor | county drought | 10 s | 6 h | `unavailable` |

Freshness labels: `fresh | cached(<time>) | snapshot | unavailable`. `data_sources` in the comparison response states the label per input; weather history is always `snapshot`. An expired cached copy is never reported as current.

## 6. Logging and privacy

The access log records method, path (no query string), status and duration only; request and response bodies are never logged. uvicorn's own access log has its query strings stripped, and any log message that mentions `grower`, `residue_report`, `observations` or `low_moisture_concern` is replaced by a fixed placeholder (whole-message redaction, because values cannot be parsed out of free text safely). Fixtures and examples are synthetic or the real public NASA series; there is no real grower data in the repo.

## 7. Sources

- NASA POWER Daily API and parameter metadata: https://power.larc.nasa.gov/docs/services/api/temporal/daily/
- Catalogs v1 (`data/catalogs/v1/`, verbatim from Perplexity, each row with `source_url`, `source_locator`, `verified_date`).
- USDA NRCS Soil Data Access, NWS API, US Drought Monitor (Agent B's `fieldshift/field`).
- Handbooks (`Field-Shift-Backend-Rahul.pdf`, `Field-Shift-Charlotte-Playbook-2.pdf`): the team's original documents, local only (gitignored), reference only. The Union County point and sample plan dates remain labelled assumptions; the heavy-rain rule is the published 76.2 mm definition above.

## 8. Known gaps

Winter wheat double-crop and SMAP (Phase 12) are not built; the wheat path returns `unavailable: catalog_missing`. Catalog gaps are listed at the top of `docs/phase-cards.md` and in `docs/catalog-gaps.md`.

## Weather locations (per-county snapshots)

`data/snapshots/index.json` lists every place with a committed snapshot: `union`, `iredell`, `rowan`, `johnston`, `wayne`, `duplin`, `pitt`, `robeson` (county-centre points from the web place picker, not farms). One snapshot is stored per NASA POWER grid cell (0.5 x 0.625 degrees): Johnston and Wayne share a cell, so Wayne is served from `data/snapshots/johnston/` and carries the same `snapshot_hash`. Each snapshot has the same source, span (1981-01-01 to 2025-06-30), manifest format and hash rule as Union County's.

- **Choosing a place.** Compare, replay, sensitivity, years and the Phase 9 routes read `location_id` (an index id; `union_county_sample` still means Union) or a latitude/longitude (`location: {latitude, longitude}` in a body, or `latitude`/`longitude` in a query). The lookup is by grid cell, so any point inside a served cell uses that snapshot. No place means the Union County default, exactly as before.
- **Meta.** `meta.snapshot_hash` is the snapshot actually used. `weather_location` says which place answered, its region, grid cell and hash, and where the thresholds come from.
- **Thresholds.** Each place gets its own frozen `ThresholdSet`: dry-spring cutoffs from its own 1981-2025 baseline, heavy rain the fixed 76.2 mm. Locations are never mixed in a threshold set, era comparison or shared-year set (one request is one place).
- **No snapshot.** A North Carolina point whose cell has no snapshot returns HTTP 200 `unavailable`, code `no_weather_snapshot`, `reason_text`, `meta.snapshot_hash: null`. A point outside NC stays `unsupported_location`. An unknown `location_id`, or an id and a point that disagree, is HTTP 400 `invalid_input`.
- **Adding a county.** Add it to `PLACES` in `fieldshift/weather/locations.py`, then `python -m fieldshift.weather build-locations` (needs the network once; refuses under `FIELDSHIFT_OFFLINE=1`; fetches only missing cells; compares a place that shares a cell with the stored history and stops if they differ). `python -m fieldshift.weather verify-locations` checks the index and every snapshot offline. Regenerate the contract afterwards.
