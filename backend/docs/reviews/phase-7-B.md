CHANGES NEEDED

P1 | fieldshift/planner/checker.py:52 | “Virginia Piedmont” and “Pennsylvania mountains” return complete instead of unsupported. | Validate NC scope before normalizing region tags; add regression tests.

P1 | fieldshift/planner/routes.py:82 | Unvalidated year/inputs/priorities cause 500s; year=0 silently selects the default year. | Validate request fields before evaluation; return 400 with field issues and test malformed values.

P1 | fieldshift/api/app.py:33 | Planner router is unmounted; production endpoints return 404 while tests use a separate app. | Have owner A mount the router per the handoff and add production-app integration tests.

P2 | fieldshift/planner/routes.py:115 | Finder chronology errors return HTTP 200 with invalid_input. | Convert invalid finder results to 400 with field issues, matching check.

P2 | fieldshift/planner/routes.py:76 | Malformed JSON and non-object bodies return default 422 responses without required metadata. | Have A wire request-validation handling to return 400, typed issues, and all four metadata fields.

P2 | fieldshift/planner/routes.py:84 | plan_version hashes the supplied year, so omitted-year requests retain the same version as the effective season changes. | Hash the resolved result.year in both endpoints; test default-year behavior.