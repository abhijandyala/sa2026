"""Fertilizer calculator (Phase 11).

Given nutrient targets (lb/ac of N, P2O5, K2O), one product and an area, return the product rate,
total product, nutrients delivered, and the excess or shortfall per nutrient.

Rules this module keeps:

* **It never invents a nutrient target.** Targets come from the caller (a soil test or guidance).
  The catalog rows ``fc_nut_01`` and ``sb_nut_01`` supply no automatic N rate, and when a crop is
  given without an N target the response says so and cites them.
* A blank target (``None``) means "not requested"; a real ``0`` is a real target of zero.
* A product with 0 % of a requested nutrient is reported as ``product_supplies_none`` (an
  ``invalid_input`` for that target), never a divide-by-zero.
* One product has one rate. With several targets, the rate is set by one *basis* nutrient; the
  other nutrients come along in the product's fixed ratio, so they may be in excess or short.
  The rate each nutrient would need on its own is listed so the trade-off is visible.
"""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from fieldshift.catalogs.index import CatalogIndex
from fieldshift.contracts import FieldIssue, Status

NUTRIENTS = ("n", "p2o5", "k2o")
LABELS = {"n": "N", "p2o5": "P2O5", "k2o": "K2O"}
SHORT_TONS = 2000.0
_NUM = r"\d+(?:\.\d+)?"
_GRADE_RE = re.compile(rf"^({_NUM})-({_NUM})-({_NUM})((?:-{_NUM}[A-Za-z]+)*)$")
#: Catalog rows that deliberately carry no automatic N rate, keyed by crop.
MAX_TARGET_LB_PER_ACRE = 100_000.0  # far beyond any real rate; guards overflow
MAX_AREA_ACRES = 10_000_000.0
NO_AUTO_N_RULE = {"field_corn": "fc_nut_01", "soybean": "sb_nut_01"}

NutrientOutcome = Literal["met", "excess", "shortfall", "not_requested"]


class Product(BaseModel):
    """Either a catalog ``fertilizer_id`` or a grower-entered ``grade`` such as ``"18-46-0"``."""

    fertilizer_id: str | None = None
    grade: str | None = None
    name: str | None = None


class ProductInfo(BaseModel):
    name: str | None
    grade: str | None
    n_pct: float
    p2o5_pct: float
    k2o_pct: float
    source: str  # "catalog" | "grower"
    source_url: str | None = None
    verified_date: str | None = None
    other_nutrients: str | None = None  # trailing S/Zn text from the grade, not computed


class NutrientLine(BaseModel):
    nutrient: str
    label: str
    outcome: NutrientOutcome  # a per-nutrient result, not a status-vocabulary value
    target_lb_per_acre: float | None
    delivered_lb_per_acre: float | None
    difference_lb_per_acre: float | None  # delivered - target; > 0 excess, < 0 shortfall
    rate_alone_lb_product_per_acre: float | None  # product rate that would meet this target alone
    total_delivered_lb: float | None = None


class FertilizerResult(BaseModel):
    status: Status  # complete | invalid_input
    issues: list[FieldIssue] = Field(default_factory=list)
    product: ProductInfo | None = None
    basis_nutrient: str | None = None
    product_lb_per_acre: float | None = None
    product_lb_per_acre_exact: float | None = None
    area_acres: float | None = None
    total_product_lb: float | None = None
    total_product_short_tons: float | None = None
    nutrients: list[NutrientLine] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    derivation: str = "calculation"


def _bad(field: str, code: str, message: str) -> FertilizerResult:
    return FertilizerResult(
        status=Status.INVALID_INPUT, issues=[FieldIssue(field=field, code=code, message=message)]
    )


def _finite(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return x if math.isfinite(x) else None


def parse_grade(grade: str) -> tuple[float, float, float, str | None] | None:
    """``"46-0-0"`` -> ``(46, 0, 0, None)``; trailing S/Zn parts are returned as text."""
    m = _GRADE_RE.match(grade.strip())
    if not m:
        return None
    n, p, k = (float(x) for x in m.groups()[:3])
    extra = m.group(4).strip("-") or None
    return n, p, k, extra


def resolve_product(product: Product, index: CatalogIndex) -> ProductInfo | FertilizerResult:
    if product.fertilizer_id:
        f = index.fertilizers.get(product.fertilizer_id)
        if f is None:
            return _bad(
                "product.fertilizer_id", "unknown_product",
                f"'{product.fertilizer_id}' is not in the fertilizer catalog",
            )  # fmt: skip
        extra = None
        if f.grade and (g := parse_grade(f.grade)) is not None:
            extra = g[3]
        return ProductInfo(
            name=f.product_name, grade=f.grade, n_pct=f.n_pct or 0.0, p2o5_pct=f.p2o5_pct or 0.0,
            k2o_pct=f.k2o_pct or 0.0, source="catalog", source_url=f.source_url,
            verified_date=f.verified_date.isoformat() if f.verified_date else None,
            other_nutrients=extra,
        )  # fmt: skip
    if product.grade:
        g = parse_grade(product.grade)
        if g is None:
            return _bad("product.grade", "bad_grade", f"'{product.grade}' is not an N-P-K grade")
        n, p, k, extra = g
        if min(n, p, k) < 0 or max(n, p, k) > 100 or n + p + k > 100:
            return _bad(
                "product.grade",
                "grade_range",
                "grade percentages must be 0-100 and sum to at most 100",
            )
        return ProductInfo(
            name=product.name, grade=product.grade, n_pct=n, p2o5_pct=p, k2o_pct=k,
            source="grower", other_nutrients=extra,
        )  # fmt: skip
    return _bad("product", "product_required", "give a catalog fertilizer_id or a grower grade")


def calculate(
    targets: dict[str, Any],
    product: Product,
    index: CatalogIndex,
    *,
    area_acres: Any = None,
    basis: str | None = None,
    crop_id: str | None = None,
) -> FertilizerResult:
    """``targets`` keys: ``n_lb_per_acre``, ``p2o5_lb_per_acre``, ``k2o_lb_per_acre``."""
    info = resolve_product(product, index)
    if isinstance(info, FertilizerResult):
        return info

    want: dict[str, float] = {}
    for nut in NUTRIENTS:
        key = f"{nut}_lb_per_acre"
        raw = targets.get(key)
        if raw is None:
            continue
        v = _finite(raw)
        if v is None or v < 0:
            return _bad(
                f"targets.{key}", "bad_target", "a target must be a finite number >= 0 (lb/ac)"
            )
        want[nut] = v
    unknown = set(targets) - {f"{n}_lb_per_acre" for n in NUTRIENTS}
    if unknown:
        return _bad(
            f"targets.{sorted(unknown)[0]}", "unknown_target", "targets are n, p2o5, k2o (lb/ac)"
        )

    notes: list[str] = []
    if crop_id in NO_AUTO_N_RULE and "n" not in want:
        rid = NO_AUTO_N_RULE[crop_id]
        notes.append(
            f"No N target was given. Catalog rule {rid} supplies no automatic nitrogen rate for "
            f"{crop_id}; use your soil-test recommendation or other applicable guidance."
        )
    if not want:
        res = _bad("targets", "no_target", "give at least one nutrient target; no rate is invented")
        res.notes = notes
        return res

    pct = {"n": info.n_pct, "p2o5": info.p2o5_pct, "k2o": info.k2o_pct}
    # A positive target for a nutrient the product lacks cannot be met: say so, never divide by 0.
    for nut, target in want.items():
        if target > 0 and pct[nut] == 0:
            res = _bad(
                f"targets.{nut}_lb_per_acre", "product_supplies_none",
                f"product supplies no {LABELS[nut]} (grade {info.grade or 'given'}), so a "
                f"{LABELS[nut]} target cannot be met with it",
            )  # fmt: skip
            res.product = info
            res.notes = notes
            return res

    area = None
    if area_acres is not None:
        area = _finite(area_acres)
        if area is None or area <= 0 or area > MAX_AREA_ACRES:
            return _bad(
                "area_acres", "bad_area", "area_acres must be a number > 0 and at most 10,000,000"
            )

    if any(t > MAX_TARGET_LB_PER_ACRE for t in want.values()):
        return _bad(
            "targets", "target_too_large",
            f"targets above {MAX_TARGET_LB_PER_ACRE:g} lb/ac are rejected",
        )  # fmt: skip
    alone = {nut: (t / (pct[nut] / 100.0) if t > 0 else 0.0) for nut, t in want.items()}
    if basis is not None and basis not in want:
        return _bad(
            "basis", "bad_basis", f"basis must be one of the requested nutrients {sorted(want)}"
        )
    basis = basis or next(n for n in NUTRIENTS if n in want)
    rate = alone[basis]

    lines: list[NutrientLine] = []
    for nut in NUTRIENTS:
        delivered = rate * pct[nut] / 100.0
        if nut not in want:
            lines.append(
                NutrientLine(
                    nutrient=nut, label=LABELS[nut], outcome="not_requested", target_lb_per_acre=None,
                    delivered_lb_per_acre=round(delivered, 2), difference_lb_per_acre=None,
                    rate_alone_lb_product_per_acre=None,
                    total_delivered_lb=round(delivered * area, 1) if area else None,
                )
            )  # fmt: skip
            continue
        diff = delivered - want[nut]
        outcome: NutrientOutcome = (
            "met" if abs(diff) < 0.005 else ("excess" if diff > 0 else "shortfall")
        )
        lines.append(
            NutrientLine(
                nutrient=nut, label=LABELS[nut], outcome=outcome, target_lb_per_acre=want[nut],
                delivered_lb_per_acre=round(delivered, 2), difference_lb_per_acre=round(diff, 2),
                rate_alone_lb_product_per_acre=round(alone[nut], 1),
                total_delivered_lb=round(delivered * area, 1) if area else None,
            )
        )  # fmt: skip

    if len(want) > 1:
        notes.append(
            f"One product has one rate: it is set by {LABELS[basis]}. The other nutrients come in "
            "the product's fixed ratio, so they can be in excess or short; each nutrient's "
            "stand-alone rate is listed."
        )
    delivering = [LABELS[n] for n in NUTRIENTS if pct[n] > 0]
    if len(delivering) > 1:
        notes.append(
            f"This is a blend ({', '.join(delivering)}); its nutrients cannot be applied independently."
        )
    if info.other_nutrients:
        notes.append(
            f"The grade also lists {info.other_nutrients}; those nutrients are not calculated."
        )
    if info.source == "grower":
        notes.append("Grade was entered by the grower; it is not from the catalog.")
    elif info.verified_date is None:
        notes.append("This catalog product has no verified date.")

    return FertilizerResult(
        status=Status.COMPLETE,
        product=info,
        basis_nutrient=basis,
        product_lb_per_acre=round(rate, 1),
        product_lb_per_acre_exact=rate,
        area_acres=area,
        total_product_lb=round(rate * area, 1) if area else None,
        total_product_short_tons=round(rate * area / SHORT_TONS, 3) if area else None,
        nutrients=lines,
        notes=notes,
    )
