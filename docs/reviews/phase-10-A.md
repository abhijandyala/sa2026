CHANGES NEEDED

- high | fieldshift/api/logs.py:40 | Default Uvicorn access logging bypasses scrubbing and exposes grower query values. | Disable it or install a sanitized access handler.
- high | fieldshift/api/logs.py:22 | Redaction leaks text after escaped quotes, brackets, or nested objects; reproduced with synthetic secrets. | Use structured redaction and add adversarial tests.
- medium | tests/api/test_api_contract.py:45 | Health and error examples skip schema validation; OpenAPI documents 422 instead of the actual 400 response. | Define typed health/error schemas and validate every example.
- medium | fieldshift/api/app.py:53 | Framework 404/405 responses lack all four metadata fields; unhandled 500s also lack an envelope. | Add metadata-bearing error handlers and tests.
- low | docs/backend-runbook.md:17 | Offline providers are described as always unavailable, but valid SDA/live caches are returned. | Document cached offline behavior and cache persistence.
## Agent A responses (2026-11-13)
All five fixed with tests: uvicorn's access log has query strings stripped (`QueryStripFilter`); redaction is now whole-message (any message that mentions a grower field name is replaced), with adversarial tests for escaped quotes, nested brackets and trailing text; typed `HealthResponse`/`InvalidInputResponse`/`ServerErrorResponse` schemas, error and health examples are schema-validated and OpenAPI documents 400 (not 422); 404/405/500 carry the four metadata fields (500 leaks no detail); runbook documents cached offline behaviour. Also found and fixed during this card: contract generation leaked `FIELDSHIFT_OFFLINE=1` into other tests (now restored).
