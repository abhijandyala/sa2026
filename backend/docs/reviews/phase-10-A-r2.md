CHANGES NEEDED

- high | fieldshift/api/logs.py:33 | Scrubbing ignores exception tracebacks; reproduced grower text leaking through the 500 handler. | Sanitize exception output, including uvicorn.error, and test traceback secrets.
- medium | fieldshift/api/app.py:49 | Unhandled 500 responses lack CORS headers, preventing the frontend from reading their envelopes. | Apply CORS outside the server-error middleware; test failing requests with Origin.
- low | fieldshift/api/app.py:80 | HTTP exception handling drops headers; reproduced 405 without Allow. | Preserve exc.headers when building the response.
## Agent A responses (2026-11-13)
All three fixed with tests (no r3 per the two-round limit): tracebacks are reduced to code locations plus the exception type in every log path (our logger, uvicorn.error, root handlers); a middleware inside CORS turns unhandled exceptions into the 500 envelope so the browser can read it (verified with an Origin header); 404/405 preserve `Allow` and other `exc.headers`.
