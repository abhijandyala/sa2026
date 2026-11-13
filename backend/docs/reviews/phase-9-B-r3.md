CHANGES NEEDED

medium | fieldshift/report/routes.py:262 | Non-wheat notes accept `inputs.maturity_group=5` with HTTP 200; calendar/backup also lack wheat-only guards. | Validate wheat-only inputs across all routes, including nested inputs.

medium | fieldshift/report/routes.py:178 | Calendar and backup accept wheat `inputs.maturity_group=99` as complete. | Reuse `_effective_inputs` validation and return typed HTTP 400 issues.

medium | fieldshift/report/field_note.py:503 | Wheat alternatives use `_plan_section`, reporting 0 living-cover days and the entire winter uncovered despite the wheat interval. | Provide wheat-specific date metrics; use null for unsupported cover metrics.

medium | fieldshift/report/wheat_note.py:299 | Cross-calendar comparisons include dry cutoffs despite the raw-totals-only requirement; alternative and backup comparisons do likewise. | Keep cutoffs in each plan’s own spring section and omit them from comparisons.

medium | fieldshift/report/models.py:477 | Response wrappers leave backup comparisons and calendar scenarios as unrestricted dictionaries, so these results lack field-level OpenAPI schemas. | Add nested Pydantic models for both structures.