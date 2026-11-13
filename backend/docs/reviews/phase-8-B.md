CHANGES NEEDED

high | fieldshift/field/soil.py:333 | Malformed SDA tables and caches raise uncaught KeyError/TypeError, causing 500s. | Validate both schemas; return unavailable on malformed data.

medium | fieldshift/field/routes.py:57 | Soil requests ignore FIELDSHIFT_OFFLINE and contact SDA. | Pass global offline mode into get_soil; test with network forbidden.

medium | fieldshift/field/location.py:98 | Bounding box accepts Columbia, SC, without unsupported_location. | Add an offline NC boundary check and neighboring-state regressions.

medium | fieldshift/field/location.py:254 | Unmapped text such as “Atlantis NC” falls through to supported guidance. | Return guidance.status=unknown for explicitly supplied, unmapped regions.

medium | fieldshift/field/routes.py:35 | Numeric/object region values cause AttributeError; string “false” enables history fetching. | Validate request fields and return invalid_input for invalid types.

medium | fieldshift/field/routes.py:3 | Production app lacks both field routes; docs/handoff.md requests only the planner mount. | Request Agent A mount the field router; verify production endpoints.

medium | tests/field/test_location.py:192 | Timeout test checks only a mocked soil endpoint; plan comparison acceptance remains unverified. | Add comparison integration coverage through Agent A’s ownership/handoff workflow.

medium | fieldshift/field/soil.py:335 | Expired cache fallback reports complete indefinitely after SDA timeouts, contrary to timeout acceptance. | Return soil.status=unavailable after expiry; retain stale data separately if needed.

low | fieldshift/field/soil.py:192 | Component ranking conflates published 0% with missing percentage. | Use an explicit None check so zero ranks above missing.