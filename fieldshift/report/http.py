"""Shared request helpers: read a JSON object body and build typed 400 responses with metadata."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from fieldshift.contracts import FieldIssue
from fieldshift.report.meta import response_meta


def issue(field: str, code: str, message: str) -> dict[str, str]:
    return FieldIssue(field=field, code=code, message=message).model_dump()


def invalid(issues: list[dict[str, str]]) -> JSONResponse:
    """HTTP 400 with ``status: invalid_input``, typed field issues and the response metadata."""
    return JSONResponse(
        status_code=400, content={"status": "invalid_input", "issues": issues, **response_meta()}
    )


async def read_object(request: Request) -> tuple[dict[str, Any] | None, JSONResponse | None]:
    """Parse the body as a JSON object. Malformed JSON or a non-object is a typed 400."""
    try:
        body = json.loads(await request.body())
    except (ValueError, UnicodeDecodeError):
        return None, invalid([issue("body", "invalid_json", "request body is not valid JSON")])
    if not isinstance(body, dict):
        return None, invalid([issue("body", "not_an_object", "request body must be a JSON object")])
    return body, None
