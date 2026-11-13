"""``GET /v1/years``: every planting year with its coverage status and typical/dry/wet shortcuts."""

from __future__ import annotations

from typing import Any

from fieldshift.compare.context import Context
from fieldshift.compare.engine import YEARS, eras_block, reference_for
from fieldshift.compare.models import YearRow
from fieldshift.contracts import Plan, Status
from fieldshift.seasons.align import build_calendar
from fieldshift.seasons.coverage import season_coverage


def years_payload(plan: Plan, ctx: Context) -> dict[str, Any]:
    """Coverage by year for ``plan``'s dates. Shortcuts use the spring totals of its window."""
    rows: list[YearRow] = []
    for y in YEARS:
        cov = season_coverage(build_calendar(plan, y), ctx.series)
        m = cov.metrics
        reasons = sorted({r for k in ("winter", "spring", "full_season") for r in m[k].reasons})
        rows.append(YearRow(
            year=y, spring=m["spring"].status, winter=m["winter"].status,
            full_season=m["full_season"].status,
            reason=(
                "Series starts 1981-01-01; the prior fall is not covered"
                if "record_starts_after_window_start" in reasons
                else ", ".join(reasons) or None
            ),
        ))
    ref = reference_for(ctx, plan.next_plant)
    ordered = sorted(ref.totals, key=lambda y: (ref.totals[y], y))
    median_total = sorted(ref.totals.values())[len(ref.totals) // 2] if ref.totals else None
    typical = (
        min(ref.totals, key=lambda y: (abs(ref.totals[y] - median_total), y))  # type: ignore[operator]
        if ref.totals else None
    )
    cfg = ctx.manifest["reference_point"]
    grid = ctx.manifest["grid"]["derived_cell"]
    return {
        "location": {
            "id": ctx.location_id,
            "label": "Union County, NC (sample)",
            "grid": {
                "lat": cfg["requested_latitude"], "lon": cfg["requested_longitude"],
                "cell_center_lat": grid["center_latitude"],
                "cell_center_lon": grid["center_longitude"],
                "source": "NASA POWER daily",
                "note": "Historical NASA estimates for the regional grid near the field",
            },
        },
        "plan_basis": {"plan_id": plan.plan_id, "next_plant": plan.next_plant,
                       "prev_harvest": plan.prev_harvest},
        "years": rows,
        "shortcuts": {
            "typical": typical,
            "dry": ordered[0] if ordered else None,
            "wet": ordered[-1] if ordered else None,
        },
        "eras": eras_block(),
    }


__all__ = ["Status", "years_payload"]
