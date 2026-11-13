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
