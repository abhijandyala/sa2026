"""API-level response models that are not tied to one calculation: errors and health."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from fieldshift.compare.models import Meta
from fieldshift.contracts import Status


class IssueOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    code: str
    message: str


class InvalidInputResponse(BaseModel):
    """HTTP 400. Flat envelope: typed issues plus the four metadata fields."""

    model_config = ConfigDict(extra="forbid")
    status: Literal["invalid_input"]
    issues: list[IssueOut]
    plan_version: str | None
    catalog_version: str | None
    snapshot_hash: str | None
    request_id: str


class ServerErrorResponse(BaseModel):
    """HTTP 500: no detail beyond a fixed code; the cause is in the server log."""

    model_config = ConfigDict(extra="forbid")
    status: Literal["unavailable"]
    issues: list[IssueOut]
    plan_version: str | None
    catalog_version: str | None
    snapshot_hash: str | None
    request_id: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta: Meta
    status: Status
    offline: bool
    snapshot_hash: str
    weather: dict[str, Any]
