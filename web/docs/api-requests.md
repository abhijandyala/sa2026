# Frontend and backend: where things stand

From Abhi (frontend) to Rahul (backend). Updated Nov 14 2026, checked against backend commit `d7d3367` (wheat winter exposure, flagged years per sweep point, shortcuts and wetness in compare, generated labels, `reason_text`, rule `text` and `print`).

## Status after your 00:15 push

Thank you: everything below marked done is now read by the frontend and shown.

| Ask | Status | What the frontend does with it |
|---|---|---|
| 0. Plain words for each rule | Done | Plan detail lists `text`; the printed summary lists the lines with `print: true` |
| 1. Wetness for each spring in compare | Done | Read from `seasons[]`; `wetness.json` is only a fallback now |
| 2. Typical, dry and wet springs for edited dates | Done | Read from `spring.shortcuts` |
| 3. Flagged years on each sweep point | Done | The rye page lights the point's own `qualifying_years` |
| 4. The grain plan in compare | Done | "Add a grain crop" shows its own winter rain (119 mm in winter 1) and its June window |
| 5. Other places | Open | Any other cell is still `unsupported_location`; the picker's other counties show dates only |
| 6. Small things | Done | `label` and `reason_text` are used; `localhost:5174` is allowed |

**Still open.**
- **Other places (5).** Tell me if fetching a cell on demand is out for this weekend and I will cut the picker to Union County plus "enter coordinates".
- **The service address.** Nothing is deployed yet, so the frontend has no `VITE_API_BASE` and runs on the saved record. Abhi has to create the Railway project (admin).
- **`eras[].missing_years[].reason`** codes have no plain text; the frontend does not show them today, so this is low priority.

## What is connected

The frontend no longer uses the synthetic draft sample. It loads your real responses and reads them through one file, `web/src/api/adapt.ts`, which is the only place that knows the backend's field names. Saved data and live calls go through the same adapter.

| Screen data | Endpoint | Status |
|---|---|---|
| Three plans, both winters | `POST /v1/plans/compare` | connected |
| Plan names by leg | `GET /v1/rotations` | connected |
| Typical, dry and wet springs | `GET /v1/years?plan=…` | connected, one call per planting date |
| Rye end-date sweep | `POST /v1/plans/sensitivity` | connected |
| Daily values for one spring | `GET /v1/seasons/{year}/replay?plan=…` | connected |
| Another place | `POST /v1/locations/resolve` | connected; only the Union County cell has weather |
| Edited dates | `POST /v1/plans/compare` with `plans` | connected; sends your plan fields (`winter.kind`, `grower.low_moisture_concern`) |

The saved copy lives in `web/public/data/nasa/` and is your responses exactly as returned. Regenerate it with the backend running:

```bash
npm run data
```

## The original requests (kept for the record)

All but "other places" are done as of `d7d3367`; the text below is what was asked on Nov 13.

### 0. Plain words for each rule

The real `other_checks[].reason` strings are written for the engine: "no evaluator for condition 'slope_position'", "qualitative rule: Before mid-April", "input 'soil_temp_f' is not available". A grower cannot act on those, and one plan can carry 15 to 20 of them.

Today: the plan page groups them (talk over, check in the field, already fine, could not be checked), lists identical lines once, and shows one group at a time. The printed summary keeps the first eight and counts the rest.

Ask: a short `text` on each rule line saying what to look at in the field ("Check soil pH: the guide's target is 6.0"), plus a flag for the handful worth printing.

### 1. Wetness for each spring, in compare

`plans[].seasons[]` has the spring total, rank and dry flag for every year but no modeled wetness. The past-springs page shows wetness for the picked year, and the 3D field's water band uses it.

Today: `npm run data` collects the `wetness` block from all 180 replays into `wetness.json`. That works for the saved sample only. With edited dates the wetness is blank.

Ask: add `gwetroot_window_mean` and `gwettop_window_mean` to each season in `plans[].seasons[]`.

### 2. Typical, dry and wet springs for edited dates

`GET /v1/years?plan=<id>` answers for the sample plan's own planting date. When the grower edits a planting date, there is no way to ask for that date's shortcut years, so the three gauges on the past-springs page are empty.

Ask: either `shortcuts` on each plan's `spring` block in compare, or let `/v1/years` take a plan body.

### 3. Which springs each rye end date flags

Sensitivity points carry `checks_count` but not the years. The rye page lights one dot per flagged spring.

Today: the adapter uses the sweep's top-level `dry_years` for a point only when that point's count equals the length of that list, and an empty list when the count is 0. Any other count (a grower-reported moisture concern, for example) leaves the years unknown and the dots show the count only.

Ask: `qualifying_years` on each point, as the compare check already has.

### 4. The grain plan in compare

`corn_soy__wheat_dc` comes back `unavailable` with `reason: "catalog_missing"`, so "Add a grain crop" shows "Not evaluated yet" for winter 1 on every page. Your handoff notes say `evaluate_wheat_double_crop` exists and compare does not route to it yet.

Ask: route `winter_grain` plans through it in compare, or tell me to call `POST /v1/plans/wheat` for that card and I will add it.

### 5. Other places

Compare returns `unsupported_location` for any cell but Union County's. The place picker lists seven more NC counties, which today can only show dates.

Ask: is fetching and caching a cell on demand planned for the live service? If not, I will trim the picker to Union County plus "enter coordinates".

### 6. Small things

- **Reason codes.** `reason` is sometimes a code (`catalog_missing`) and sometimes a sentence. The frontend keeps a short table of plain words for known codes in `src/data/format.ts`. A `reason_text` next to the code would let me drop it.
- **`label` on inline plans.** Plans sent in the request come back with `label: null`; the frontend falls back to the plan id.
- **`other_checks[].verdict` can be null** when a rule cannot be evaluated. The frontend shows those as "unknown" or "manual check" from `status`.
- **CORS.** Allowed origins are GitHub Pages and `localhost:5173`. Local previews sometimes land on 5174.
- **The Render address** is not written in the repo. I need it for `VITE_API_BASE`.

## Things the frontend noticed

- **The rye check is a step.** Your real sweep is 0 of 45 for every end date with 14 or more days, then 9 of 45. The "8 → 3 of 45" line in the old phase cards cannot happen and should be removed from the demo script.
- **The numbers moved from the draft.** Rain with nothing growing is 682 mm and 78 mm in winter 1 (the draft sample had 437 and 46), and 534 mm and 35 mm in winter 2. The check is still 9 of 45, on different years.
- **Endpoints with no screen yet:** action calendar with scenarios, backup plan, field note, plan checker and finder, soil, live conditions, zones, irrigation and fertilizer. Tell me which two you most want shown.
