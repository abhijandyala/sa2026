"""Phase 11 tool routes: ``POST /v1/fertilizer/calc`` and ``POST /v1/irrigation/check``.

Mounted by the API app (owner: Agent A). Bad input is a 400 with typed issues and the response
metadata; calculations that cannot be done for a *valid* request (a product with none of the
requested nutrient) are 400 ``invalid_input`` with the field that caused it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from fieldshift.report.http import invalid, issue, read_object
from fieldshift.report.meta import get_index, response_meta
from fieldshift.tools.fertilizer import Product, calculate
from fieldshift.tools.irrigation import check_irrigation

router = APIRouter(prefix="/v1", tags=["tools"])


@router.post("/fertilizer/calc")
async def post_fertilizer(request: Request) -> Any:
    """Body: ``{targets: {n_lb_per_acre, p2o5_lb_per_acre, k2o_lb_per_acre}, product: {fertilizer_id | grade},
    area_acres?, basis?, crop_id?}``. No nutrient target is ever invented."""
    body, err = await read_object(request)
    if err is not None:
        return err
    assert body is not None
    targets, prod = body.get("targets", {}), body.get("product", {})
    problems = []
    if not isinstance(targets, dict):
        problems.append(issue("targets", "invalid_type", "targets must be an object"))
    if not isinstance(prod, dict):
        problems.append(issue("product", "invalid_type", "product must be an object"))
    for key in ("basis", "crop_id"):
        if body.get(key) is not None and not isinstance(body[key], str):
            problems.append(issue(key, "invalid_type", f"{key} must be a string"))
    if problems:
        return invalid(problems)
    try:
        product = Product(**{k: v for k, v in prod.items() if k in Product.model_fields})
    except ValueError:
        return invalid([issue("product", "invalid_type", "product fields must be strings")])
    result = calculate(
        targets, product, get_index(), area_acres=body.get("area_acres"),
        basis=body.get("basis"), crop_id=body.get("crop_id"),
    )  # fmt: skip
    if result.status == "invalid_input":
        return invalid(
            [i.model_dump() for i in result.issues],
            n_reference=result.n_reference.model_dump(mode="json") if result.n_reference else None,
            notes=result.notes,
        )
    return {"meta": response_meta(), "result": result.model_dump(mode="json")}


@router.post("/irrigation/check")
async def post_irrigation(request: Request) -> Any:
    """Body: ``{crop_id, stage?, awc_in?, start_storage_in?, weather?: [{date, precip_mm|precip_in}],
    irrigation?: [{date, amount_in}], water_table_depth_in?}``. A numeric balance is returned only
    when every input is present; otherwise ``insufficient_data`` lists what is missing."""
    body, err = await read_object(request)
    if err is not None:
        return err
    assert body is not None
    crop_id = body.get("crop_id")
    if not isinstance(crop_id, str) or not crop_id:
        return invalid([issue("crop_id", "required", "crop_id is required")])
    stage = body.get("stage")
    if stage is not None and not isinstance(stage, str):
        return invalid([issue("stage", "invalid_type", "stage must be a string")])
    result = check_irrigation(
        get_index(), crop_id=crop_id, stage=stage, awc_in=body.get("awc_in"),
        start_storage_in=body.get("start_storage_in"), weather=body.get("weather"),
        irrigation=body.get("irrigation"), water_table_depth_in=body.get("water_table_depth_in"),
    )  # fmt: skip
    if result.status == "invalid_input":
        return invalid([i.model_dump() for i in result.issues])
    return {"meta": response_meta(), "result": result.model_dump(mode="json")}
