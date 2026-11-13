"""Request logging that never records grower-entered data.

Logged per request: method, path (no query string), status, duration. Request and response
bodies are never logged. Two more lines of defence:

* :class:`ScrubFilter` replaces any log message that mentions a grower field name
  (``residue_report``, ``observations``, ``low_moisture_concern``, ``grower``) with a fixed
  placeholder. It does not try to parse values out of free text, because that cannot be done
  safely; over-redacting is the safe failure.
* :class:`QueryStripFilter` removes query strings from uvicorn's access log, so a point or a plan
  passed in a URL is not written to disk.
"""

from __future__ import annotations

import logging
import time
import traceback

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

LOGGER_NAME = "fieldshift.access"
_GROWER_KEYS = ("residue_report", "observations", "low_moisture_concern", "grower")
REDACTED = "[redacted: log message mentioned grower fields]"


def _locations_only(exc_info) -> str:
    _type, exc, tb = exc_info
    frames = [f"  {f.filename}:{f.lineno} in {f.name}" for f in traceback.extract_tb(tb)]
    return "\n".join(["Traceback (code locations only; messages withheld):", *frames,
                      type(exc).__name__])


class ScrubFilter(logging.Filter):
    """Replaces a whole message that mentions any grower field name."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging
            return True
        lowered = msg.lower()
        if any(key in lowered for key in _GROWER_KEYS):
            record.msg, record.args = REDACTED, None
        if record.exc_info and record.exc_info[1] is not None:
            # Exception messages can embed request input (e.g. a validation error echoing a
            # value), so a traceback is reduced to code locations and the exception type.
            record.exc_text = _locations_only(record.exc_info)
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = "(traceback withheld)"
        return True


class QueryStripFilter(logging.Filter):
    """uvicorn.access passes ``(client, method, path_with_query, http_version, status)``."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = (*args[:2], args[2].split("?", 1)[0], *args[3:])
        return True


def _add_once(logger: logging.Logger, flt: logging.Filter) -> None:
    if not any(type(f) is type(flt) for f in logger.filters):
        logger.addFilter(flt)


def install_scrub_filter() -> None:
    """Attach the filters to our loggers, uvicorn's access logger and the root handlers."""
    for name in (LOGGER_NAME, "fieldshift", "uvicorn.error", "uvicorn"):
        _add_once(logging.getLogger(name), ScrubFilter())
    _add_once(logging.getLogger("uvicorn.access"), QueryStripFilter())
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, ScrubFilter) for f in handler.filters):
            handler.addFilter(ScrubFilter())


class ErrorEnvelopeMiddleware(BaseHTTPMiddleware):
    """Turns an unhandled exception into the 500 envelope *inside* the CORS middleware, so the
    browser can read it. The log line carries the exception type only."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        try:
            return await call_next(request)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("fieldshift").error(
                "unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path,
                exc_info=exc,
            )
            from fastapi.responses import JSONResponse

            from fieldshift.report.http import issue
            from fieldshift.report.meta import response_meta

            return JSONResponse(
                status_code=500,
                content={
                    "status": "unavailable",
                    "issues": [issue("server", "internal_error",
                                     "unexpected error; the cause is in the server log")],
                    **response_meta(),
                },
            )


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        started = time.perf_counter()
        response = await call_next(request)
        logging.getLogger(LOGGER_NAME).info(
            "%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response
