# Handoff requests

Format: `YYYY-MM-DD A→B: request` (or B→A). Mark resolved items with ✅.

2026-11-12 A→B (FYI, no action needed unless noted):
- Git refs: a local branch `backend` exists, so git cannot also create `backend/agent-a/...` (ref prefix conflict). Agent A therefore commits directly to `backend` in the shared checkout and stages only its own paths. Please do the same (`git add <your paths>`, never `git add -A`, `git stash`, `reset` or `checkout`).
- Local interpreter: Homebrew Python 3.12 on this Mac has a broken `pyexpat`; Agent A runs tests on Python 3.11 (`PY=.venv/bin/python`). A's code stays 3.11-compatible (no PEP 695 syntax) and does not touch `requires-python`.
- Handbooks are still missing from `docs/handbooks/`. Agent A's assumptions until they land (all isolated in one constant each so they are a one-line fix): Union County point = Monroe, NC (34.98, -80.55) in `fieldshift/weather/sources.py`; heavy-rain rule and sample-plan dates are set in Phase 2/3 and flagged "assumed".
- A→B: Phase 2 will create `fieldshift/contracts.py` (Plan, SeasonCalendar, SeasonFacts, ThresholdSet, MetricResult, status enums). Propose changes here.
