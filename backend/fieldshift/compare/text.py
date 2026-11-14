"""Plain-language text for the API: reason codes and default plan labels (owner: Agent A).

``reason`` stays a machine code (or a sentence the engine already wrote); ``reason_text`` is a short
plain sentence next to a code, so clients need no table of their own. A reason that is already a
sentence gets no ``reason_text``.
"""

from __future__ import annotations

import re
from typing import Any

from fieldshift.catalogs.index import CatalogIndex
from fieldshift.contracts import Plan

REASON_TEXT: dict[str, str] = {
    "catalog_missing": "The catalog has no rows for this path yet.",
    "unsupported_location": (
        "This place is outside North Carolina, so it is not evaluated: guidance and weather "
        "history cover North Carolina only."
    ),
    "no_weather_snapshot": (
        "We have no stored weather history for this part of North Carolina yet."
    ),
    "unsupported": "This plan uses a crop, region or system the guidance does not cover.",
    "unavailable": "This result is not available right now.",
    "weather_history_not_available_for_location": (
        "There is no weather history for this place yet."
    ),
    "plan_unavailable": "This plan is not available.",
    "not_evaluable": "This season could not be evaluated.",
    "no_result_for_year": "This season has no result.",
}

# The wheat path under catalog v2 is `partial`; its reason is a long sentence for debugging.
WHEAT_PARTIAL_TEXT = (
    "The catalog has no numeric Piedmont dates for wheat: enter your own wheat harvest and "
    "soybean planting dates."
)

_CODE = re.compile(r"^([a-z][a-z0-9_]*)(?::\s*(.*))?$")


def reason_text(reason: str | None) -> str | None:
    """A plain sentence for a reason code (``"code"`` or ``"code: detail"``), else ``None``."""
    if not reason:
        return None
    m = _CODE.match(reason.strip())
    if not m:
        return None  # already a sentence
    return REASON_TEXT.get(m.group(1))


def _crop_name(index: CatalogIndex, crop_id: str) -> str:
    crop = index.crop(crop_id)
    name = (crop.common_name if crop else None) or crop_id.replace("_", " ")
    return name[:1].upper() + name[1:] if name else crop_id


def default_label(plan: Plan, index: CatalogIndex) -> str:
    """``previous crop -> winter -> next crop``, for example ``Field corn → Cereal rye cover →
    Soybean``. Built from the crop ids and winter kind only (no grower data)."""
    w = plan.winter
    if w.kind == "cover" and w.crop_id:
        mid = f"{_crop_name(index, w.crop_id)} cover"
    elif w.kind == "winter_grain" and w.crop_id:
        mid = _crop_name(index, w.crop_id)
    else:
        mid = "No winter cover"
    return " → ".join(
        [_crop_name(index, plan.previous_crop_id), mid, _crop_name(index, plan.next_crop_id)]
    )


def finalize(results: list[Any], plans: dict[str, Plan | None], index: CatalogIndex) -> None:
    """Fill ``label`` (generated, flagged) and ``reason_text`` on comparison results in place."""
    for r in results:
        plan = plans.get(r.plan_id)
        if not r.label and plan is not None:
            r.label, r.label_generated = default_label(plan, index), True
        r.reason_text = reason_text(r.reason)
        dc = getattr(r, "double_crop", None)
        if r.reason_text is None and dc and str(r.status) == "partial":
            r.reason_text = WHEAT_PARTIAL_TEXT
        if dc:
            _text_blocks(dc)


def _text_blocks(block: Any) -> None:
    """Add ``reason_text`` beside a ``reason`` code in a nested result block (in place)."""
    if isinstance(block, dict):
        if isinstance(block.get("reason"), str) and "reason_text" not in block:
            text = reason_text(block["reason"])
            if text:
                block["reason_text"] = text
        for v in block.values():
            _text_blocks(v)
    elif isinstance(block, list):
        for v in block:
            _text_blocks(v)
