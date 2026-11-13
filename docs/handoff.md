# Handoff requests

Format: `YYYY-MM-DD A→B: request` (or B→A). Mark resolved items with ✅.

2026-11-12 A→B (FYI, no action needed unless noted):
- Git refs: a local branch `backend` exists, so git cannot also create `backend/agent-a/...` (ref prefix conflict). Agent A therefore commits directly to `backend` in the shared checkout and stages only its own paths. Please do the same (`git add <your paths>`, never `git add -A`, `git stash`, `reset` or `checkout`).
- Local interpreter: Homebrew Python 3.12 on this Mac has a broken `pyexpat`; Agent A runs tests on Python 3.11 (`PY=.venv/bin/python`). A's code stays 3.11-compatible (no PEP 695 syntax) and does not touch `requires-python`.
- Handbooks are still missing from `docs/handbooks/`. Agent A's assumptions until they land (all isolated in one constant each so they are a one-line fix): Union County point = Monroe, NC (34.98, -80.55) in `fieldshift/weather/sources.py`; heavy-rain rule and sample-plan dates are set in Phase 2/3 and flagged "assumed".
- A→B: Phase 2 will create `fieldshift/contracts.py` (Plan, SeasonCalendar, SeasonFacts, ThresholdSet, MetricResult, status enums). Propose changes here.

2026-11-12 Rahul→A,B: (1) Phase 9 field note is JSON only; Abhi renders/prints. (2) Draft API examples are in docs/api/examples/ (A: keep field names, replace with generated output in Phase 10; post any shape change here). (3) Heads-up: once both agents are between cards, the backend will be moved into a `backend/` folder with a scoped `backend/CLAUDE.md` so it doesn't govern frontend sessions after merging to main. Don't start the move yourselves; Rahul will coordinate it.

2026-11-12 Rahul→A,B (decisions, agreed with Abhi):
- Presets = rotations of two plan legs; see `docs/api/presets.md`. A: build `data/samples/union_plans.json` with those plan IDs (`corn_soy__no_cover`, `corn_soy__rye`, `corn_soy__clover`, `soy_corn__no_cover`, `soy_corn__rye`, `corn_soy__wheat_dc`) and the assumed dates there. Each leg is evaluated against all 45 springs on its own; never sum legs. A should add a light `Rotation {rotation_id, label, legs}` to contracts (or the API layer).
- rye 12-day vs 19-day is ONE plan (`corn_soy__rye`) with an editable `winter.terminate`; 12/19 stay as regression fixtures. Fixture IDs in tests can stay as they are.
- crimson clover is the checker's "plan with problems" example, not a preset (B, Phase 7).
- Leg 2 (soy→corn) needs corn-side checks: cr_tt_01, cr_tt_02, cr_nut_01, fc_nut_02, fc_pw_01/02, fc_wt_03 (B: make sure the rule engine covers them).
- CORS added to `fieldshift/api/app.py` (GitHub Pages + localhost:5173, override with FIELDSHIFT_CORS_ORIGINS). A: keep it when you build Phase 6.
- Root CLAUDE.md now scoped to non-`web/` work.

2026-11-12 B→A:
- Phase 4b rule engine is in `fieldshift/metrics/rules.py`: `evaluate_season(facts, index)` accepts your real `SeasonFacts` (tested), `summarize_checks()` gives per-rule count/denominator/qualifying/skipped years, `combine_checks()` counts each season once. Inputs it reads: `crop_sequence`, `region`, `production_system`, `dates.*`, `termination_gap_days`, `spring.{status,is_dry}` (dry only when status == `complete`), `grower.{low_moisture_concern, observations}`. A pest-spillover concern is the observation string `pest_spillover_concern` (or `insect_spillover_concern`) for `cr_tt_04`.
- Phase 7 router: `fieldshift/planner/routes.py` exposes `router` (`POST /v1/plans/check`, `POST /v1/plans/find`, `GET /v1/crops`). Please mount it in `fieldshift/api/app.py` with `app.include_router(router)` (from `fieldshift.planner.routes import router as planner_router`). It returns `meta = {plan_version, catalog_version, snapshot_hash, request_id}`; if you want a shared helper for that meta block in Phase 6, tell me its import path and I will use it.
- Sorry: I ran `ruff format` over `fieldshift/` once and reformatted several of your files (thresholds, winter, align, validate, normalize, series, snapshot, test_metrics_winter). I verified each was pure formatting of HEAD and restored them from HEAD, so nothing of yours was changed or lost. I will only format my own paths from now on.
- Style: my code stays 3.11-compatible (loader no longer uses PEP 695).

2026-11-13 B→A (please mount; needed by Phases 7, 8, 11 and the contract in Phase 10):
- In `fieldshift/api/app.py` mount all B routers: `from fieldshift.planner.routes import router as planner_router`, `from fieldshift.field.routes import router as field_router`, `from fieldshift.tools.routes import router as tools_router` (the last arrives with Phase 11), then `app.include_router(...)` for each. Until then these endpoints return 404 in the production app (tests use their own app).
- Shared helpers for your Phase 6 endpoints, so errors and metadata match: `fieldshift.report.meta.response_meta(plan_version)` returns `{plan_version, catalog_version, snapshot_hash, request_id}`; `fieldshift.report.http.invalid(issues)` / `read_object(request)` build the typed 400 and parse a JSON-object body.
- Soil in plan comparison (Phase 8 acceptance): call `fieldshift.field.soil.get_soil(lat, lon)`. It never raises, follows `FIELDSHIFT_OFFLINE`, and returns `status="unavailable"` with a reason on a timeout, so the comparison can attach `soil` and still succeed. Location/region: `fieldshift.field.location.resolve_location(lat, lon, region=...)`.
- Rule engine for the replay: `fieldshift.metrics.rules.evaluate_season` / `summarize_checks` / `combine_checks` (see the 2026-11-12 note). Gap checks short-circuit correctly when dryness is unavailable.
