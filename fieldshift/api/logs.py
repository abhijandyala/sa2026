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

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

LOGGER_NAME = "fieldshift.access"
_GROWER_KEYS = ("residue_report", "observations", "low_moisture_concern", "grower")
REDACTED = "[redacted: log message mentioned grower fields]"


class ScrubFilter(logging.Filter):
    """Replaces a whole message that mentions any grower field name."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging
            return True
        lowered = msg.lower()
        if any(key in lowered for key in _GROWER_KEYS):
            record.msg, record.args, record.exc_info, record.exc_text = REDACTED, None, None, None
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
    for name in (LOGGER_NAME, "fieldshift"):
        _add_once(logging.getLogger(name), ScrubFilter())
    _add_once(logging.getLogger("uvicorn.access"), QueryStripFilter())
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, ScrubFilter) for f in handler.filters):
            handler.addFilter(ScrubFilter())


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        started = time.perf_counter()
        response = await call_next(request)
        logging.getLogger(LOGGER_NAME).info(
            "%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response
