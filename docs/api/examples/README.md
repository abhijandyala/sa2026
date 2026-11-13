# API examples (DRAFT)

These are hand-written drafts for the Union County sample, written so the frontend can build against the response shape before the backend is ready. **The numbers in them are illustrative and are not real results.**

- Every file has `"draft": true` in `meta`. Agent A replaces each one with real generated output in Phase 10.
- Field names are the contract. If a name or structure needs to change, post it in `docs/handoff.md` first, so the frontend isn't surprised.
- Every response has the same `meta` block: `plan_version`, `catalog_version`, `snapshot_hash`, `request_id`, `draft`. The frontend should ignore any response whose `request_id` doesn't match its latest request.
- Statuses use the CLAUDE.md vocabulary: `complete | partial | unavailable | unknown | inapplicable | unsupported | invalid_input | manual_check | insufficient_data`.
- Thresholds (heavy rain, the dry cutoff) always come back in `thresholds`. **Don't hardcode them.** The heavy-rain definition is still pending from the handbook.

**Plan and rotation IDs:** see `docs/api/presets.md`. Termination and planting dates are editable fields on a plan; the 12-day vs 19-day rye case is one plan (`corn_soy__rye`) edited, shown in `sensitivity.json`.

| File | Endpoint |
|---|---|
| `years.json` | `GET /v1/years` |
| `compare.json` | `POST /v1/plans/compare` |
| `sensitivity.json` | `POST /v1/plans/sensitivity` |
| `replay.json` | `GET /v1/seasons/{year}/replay?plan=corn_soy__rye` |
