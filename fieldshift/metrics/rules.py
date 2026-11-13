"""Rule engine: turns catalog rules into per-season checks (Phase 4b).

The engine consumes one season of one plan, shaped like the ``SeasonFacts`` contract
(CLAUDE.md §2). It never reads weather itself and never changes a metric: it only reads
``spring`` (dryness), ``grower`` (concerns), ``termination_gap_days``, ``dates``, ``region``,
``production_system`` and ``crop_sequence``. Facts may be mappings or objects with attributes.

Per rule, per season, it returns a :class:`RuleCheck` with a status from the shared vocabulary:

``inapplicable``  the rule does not apply (crop, previous/next crop, region, production system,
                  or stage do not match); the reason says which.
``manual_check``  the rule is qualitative or has no matching measurement in the facts.
``unknown``       an input the rule needs is missing (the missing inputs are listed).
``complete``      the rule was evaluated; ``condition_met``, ``verdict`` and ``flagged`` say how.

Semantics of a completed check
------------------------------
* ``preferred`` / ``acceptable`` rules state a recommended condition. Met -> verdict is the
  rule's suitability. Not met -> verdict ``caution`` and ``flagged``.
* ``caution`` / ``avoid`` rules describe a hazard condition. Met -> verdict is the rule's
  suitability and ``flagged``. Not met -> no verdict (the check is clear).
* A rule with an ``applies_when`` gate (see ``GATES``) is evaluated only when the gate is
  active. Gate off -> clear (``gate_active=False``). Gate undeterminable -> ``unknown``.
* Rules the catalog declares as conflicting ("Conflicts with <rule_id>" in ``guidance``) are
  both returned, flagged with ``conflict=True``, and no winner is picked.
* Window dates are inclusive at both ends and compare MM-DD only (a window with start > end
  wraps the year end).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from fieldshift.catalogs.index import CatalogIndex
from fieldshift.catalogs.models import CropRule
from fieldshift.catalogs.validate import parse_mm_dd
from fieldshift.field.regions import region_match

Status = Literal[
    "complete",
    "partial",
    "unavailable",
    "unknown",
    "inapplicable",
    "unsupported",
    "invalid_input",
    "manual_check",
    "insufficient_data",
]
Verdict = Literal[
    "preferred", "acceptable", "caution", "avoid", "manual_check", "unknown", "inapplicable"
]

#: Stages that belong to the winter-cover -> spring-planting transition the engine evaluates by
#: default. In-season stages (silking, R1-R5, pollination, ...) are ``inapplicable`` unless the
#: caller passes ``stages`` explicitly (the irrigation tools do).
TRANSITION_STAGES = frozenset(
    {
        "seeding",
        "establishment",
        "spring",
        "planting",
        "preplant",
        "germination",
        "emergence",
        "season",
        "at corn planting",
    }
)

#: Production-system requirement text in the catalog -> required plan tags.
SYSTEM_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "organic": ("organic",),
    "no-till": ("no-till",),
    "no-till into cover crop": ("no-till", "winter cover crop"),
    "irrigated": ("irrigated",),
    "late planting": ("late planting",),
    "double_crop": ("double_crop",),
    "full season": ("full season",),
    "grain": ("grain",),
    "winter cover crop": ("winter cover crop",),
    "winter annual": ("winter cover crop",),
}
#: Tags derived from the crop sequence rather than declared by the grower.
DERIVED_TAGS = frozenset({"winter cover crop", "double_crop", "full season", "grain"})

#: ``applies_when`` gates. Keyed by rule_id because the catalog's ``applies_when`` is free text.
GATES: dict[str, str] = {
    "cr_tt_01": "dry_or_moisture_concern",  # "dry spring concern"
    "cr_tt_03": "dry_or_moisture_concern",  # handbook: gap < 14 and (dry replay or concern)
    "cr_tt_04": "pest_spillover_concern",  # "insect pest spillover is a concern"
}
#: Rules surfaced as optional checks (shown only when their gate is on).
OPTIONAL_RULES = frozenset({"cr_tt_04"})

#: condition_key -> (name of the numeric input in ``inputs``, expected rule unit).
NUMERIC_INPUTS: dict[str, tuple[str, str]] = {
    "seed_zone_soil_temperature": ("soil_temp_f", "degF"),
    "forecast_precipitation": ("forecast_precip_in", "in"),
    "soil_ph": ("soil_ph", "pH"),
    "water_table_depth": ("water_table_depth_in", "in"),
    "maturity_group": ("maturity_group", "maturity_group"),
    "gdd_accumulation_after_planting": ("gdd_after_planting_f", "GDD_F"),
    "weeks_before_first_frost": ("weeks_before_first_frost", "weeks"),
}

_CONFLICT_RE = re.compile(r"[Cc]onflicts? with ([a-z]+_[a-z]+_\d+)")
_PEST_KEYS = ("pest_spillover_concern", "insect_spillover_concern")


# --------------------------------------------------------------------------- result models


class RuleSource(BaseModel):
    title: str | None
    url: str | None
    locator: str | None
    verified_date: str | None


class RuleCheck(BaseModel):
    """One rule evaluated against one season."""

    rule_id: str
    crop_id: str
    rule_type: str | None
    suitability: str | None
    status: Status
    verdict: Verdict | None = None
    condition_met: bool | None = None
    gate_active: bool | None = None
    flagged: bool = False
    optional: bool = False
    chronology_conflict: bool = False
    conflict: bool = False
    conflicts_with: list[str] = Field(default_factory=list)
    reason: str
    inputs_used: dict[str, Any] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)
    # A published number carried by a rule that cannot be evaluated against this season (for
    # example the NCDA&CS N range in fc_nut_01). It is a sourced reference, never the grower's
    # target. ``None`` when the rule carries no number; a real 0 (sb_nut_01) is kept.
    reference: dict[str, Any] | None = None
    source: RuleSource


class SeasonEvaluation(BaseModel):
    year: int | None
    plan_id: str | None
    status: Status  # complete | unsupported | invalid_input
    errors: list[str] = Field(default_factory=list)
    checks: list[RuleCheck] = Field(default_factory=list)

    def check(self, rule_id: str) -> RuleCheck | None:
        return next((c for c in self.checks if c.rule_id == rule_id), None)

    @property
    def flagged(self) -> list[RuleCheck]:
        return [c for c in self.checks if c.flagged]


# --------------------------------------------------------------------------- facts adapter


_MISSING = object()


def _get(obj: Any, path: str, default: Any = None) -> Any:
    """Dotted-path read through mappings or attributes; ``default`` when any hop is absent."""
    cur = obj
    for part in path.split("."):
        if cur is None:
            return default
        if isinstance(cur, Mapping):
            cur = cur.get(part, _MISSING)
        else:
            cur = getattr(cur, part, _MISSING)
        if cur is _MISSING:
            return default
    return cur


def _as_date(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        return None


@dataclass(frozen=True)
class SeasonView:
    """The slice of ``SeasonFacts`` the engine reads, normalised."""

    year: int | None
    plan_id: str | None
    region: str | None
    previous_cash: str | None
    winter_crop: str | None
    next_cash: str | None
    production_tags: frozenset[str] | None  # declared by the grower; None = not given
    derived_tags: frozenset[str]  # derived from the crop sequence (always known)
    dates: dict[str, date | None]
    gap_days: int | None
    spring_status: str | None
    spring_is_dry: bool | None  # None unless spring.status == "complete"
    low_moisture_concern: bool | None
    pest_concern: bool | None
    inputs: dict[str, Any] = field(default_factory=dict)

    def crops(self) -> list[str]:
        return [c for c in (self.previous_cash, self.winter_crop, self.next_cash) if c]


def _parse_sequence(seq: Any) -> tuple[str | None, str | None, str | None] | str:
    """Return ``(previous_cash, winter_crop, next_cash)`` or an error message."""
    if isinstance(seq, Mapping):
        prev = seq.get("previous_crop_id") or seq.get("previous")
        winter = (
            seq.get("winter_crop_id")
            or seq.get("cover_crop_id")
            or seq.get("winter")
            or seq.get("cover")
        )
        nxt = seq.get("next_crop_id") or seq.get("next")
        return prev, winter, nxt
    if isinstance(seq, Sequence) and not isinstance(seq, str):
        items = [s for s in seq]
        if len(items) == 2:
            return items[0], None, items[1]
        if len(items) == 3:
            return items[0], items[1], items[2]
    return "crop_sequence must be [previous, next], [previous, winter, next] or a mapping"


def _production_tags(raw: Any) -> frozenset[str] | None:
    if raw is None or raw == "" or raw == []:
        return None
    items = [raw] if isinstance(raw, str) else list(raw)
    return frozenset(str(i).strip().lower() for i in items if str(i).strip())


def build_view(
    facts: Any, index: CatalogIndex, inputs: Mapping[str, Any] | None = None
) -> SeasonView | str:
    parsed = _parse_sequence(_get(facts, "crop_sequence"))
    if isinstance(parsed, str):
        return parsed
    prev, winter, nxt = parsed
    tags = _production_tags(_get(facts, "production_system"))
    derived: set[str] = set()
    winter_crop = index.crop(winter) if winter else None
    if winter_crop is not None and winter_crop.crop_role == "cover_crop":
        derived.add("winter cover crop")
    if winter == "winter_wheat" and nxt == "soybean":
        derived.add("double_crop")
    if nxt == "soybean" and "double_crop" not in derived:
        derived.add("full season")
    if not (tags and "silage" in tags):
        derived.add("grain")
    dates = {
        k: _as_date(_get(facts, f"dates.{k}")) for k in ("harvest", "seed", "terminate", "plant")
    }
    spring_status = _get(facts, "spring.status")
    is_dry = _get(facts, "spring.is_dry")
    usable_dry = is_dry if spring_status == "complete" and isinstance(is_dry, bool) else None
    obs = _get(facts, "grower.observations")
    pest: bool | None = None
    if isinstance(obs, Mapping):
        for k in _PEST_KEYS:
            if obs.get(k) is not None:
                pest = bool(obs[k])
    elif isinstance(obs, Iterable) and not isinstance(obs, str):
        pest = True if any(k in obs for k in _PEST_KEYS) else None
    gap = _get(facts, "termination_gap_days")
    if isinstance(gap, int | float) and not isinstance(gap, bool) and not math.isfinite(gap):
        return "termination_gap_days must be a finite number of days"
    view = SeasonView(
        year=_get(facts, "year"),
        plan_id=_get(facts, "plan_id"),
        region=_get(facts, "region"),
        previous_cash=prev,
        winter_crop=winter,
        next_cash=nxt,
        production_tags=tags,
        derived_tags=frozenset(derived),
        dates=dates,
        gap_days=gap if isinstance(gap, int | float) and not isinstance(gap, bool) else None,
        spring_status=spring_status,
        spring_is_dry=usable_dry,
        low_moisture_concern=_get(facts, "grower.low_moisture_concern"),
        pest_concern=pest,
        inputs=dict(inputs or {}),
    )
    return view


# --------------------------------------------------------------------------- applicability


@dataclass
class _Outcome:
    status: Status
    reason: str
    verdict: Verdict | None = None
    met: bool | None = None
    gate_active: bool | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    chronology_conflict: bool = False


def _crop_applicability(rule: CropRule, view: SeasonView, index: CatalogIndex) -> str | None:
    """Return an ``inapplicable`` reason, or ``None`` when crop and neighbours match."""
    focus = [c for c in (view.winter_crop, view.next_cash) if c]
    if rule.crop_id not in focus:
        if rule.crop_id == view.previous_cash:
            return (
                f"rule is for {rule.crop_id}, the previous crop; its own planting and growth "
                "rules are outside this winter-cover-to-planting transition"
            )
        plan = ", ".join(view.crops()) or "no crops"
        return f"rule is for {rule.crop_id}; the plan's crops are {plan}"
    if rule.previous_crop_id:
        prev_role = index.crop(rule.previous_crop_id)
        is_cover_prev = prev_role is not None and prev_role.crop_role == "cover_crop"
        winter = index.crop(view.winter_crop) if view.winter_crop else None
        winter_is_grain = winter is not None and winter.crop_role == "cash_crop"
        if rule.crop_id == view.winter_crop:
            actual = view.previous_cash
        elif is_cover_prev or winter_is_grain:
            # the winter crop (cover or harvested winter grain) is the immediate predecessor
            actual = view.winter_crop
        else:
            actual = view.previous_cash
        if actual != rule.previous_crop_id:
            return (
                f"rule needs previous crop {rule.previous_crop_id}; "
                f"the plan has {actual or 'none'} there"
            )
    if rule.next_crop_id and view.next_cash != rule.next_crop_id:
        return f"rule needs next crop {rule.next_crop_id}; the plan has {view.next_cash or 'none'}"
    return None


def _system_applicability(rule: CropRule, view: SeasonView) -> tuple[str, str] | None:
    """``("inapplicable"|"unknown", reason)`` when the production system rules it out."""
    req = rule.production_system
    if not req:
        return None
    tags_needed = SYSTEM_REQUIREMENTS.get(req.strip().lower())
    if tags_needed is None:
        return "unknown", f"production system requirement '{req}' is not in the mapping table"
    for tag in tags_needed:
        if tag in DERIVED_TAGS:
            if tag not in view.derived_tags:
                return (
                    "inapplicable",
                    f"rule needs '{req}'; the plan's sequence does not match ({tag})",
                )
            continue
        if view.production_tags is None:
            return (
                "unknown",
                f"rule needs production system '{req}'; the plan's system was not given",
            )
        if tag not in view.production_tags:
            have = sorted(view.production_tags)
            return "inapplicable", f"rule needs production system '{req}'; the plan is {have}"
    return None


# --------------------------------------------------------------------------- evaluators


def _compare(rule: CropRule, value: float) -> bool:
    op, lo, hi = rule.operator, rule.value_min, rule.value_max
    assert lo is not None
    if op == "gte":
        return value >= lo
    if op == "gt":
        return value > lo
    if op == "lte":
        return value <= lo
    if op == "lt":
        return value < lo
    if op == "eq":
        return value == lo
    assert op == "between" and hi is not None
    return lo <= value <= hi


def _describe(rule: CropRule) -> str:
    unit = f" {rule.unit}" if rule.unit else ""
    lo, hi = rule.value_min, rule.value_max
    sym = {"gte": ">=", "gt": ">", "lte": "<=", "lt": "<", "eq": "="}.get(rule.operator or "")
    if rule.operator == "between":
        return f"between {lo:g} and {hi:g}{unit}"
    return f"{sym} {lo:g}{unit}"


def _in_window(rule: CropRule, d: date) -> bool:
    start = parse_mm_dd(rule.window_start_mm_dd or "")
    end = parse_mm_dd(rule.window_end_mm_dd or "")
    assert start and end
    md = (d.month, d.day)
    return start <= md <= end if start <= end else (md >= start or md <= end)


def _eval_gap(rule: CropRule, view: SeasonView) -> _Outcome:
    gap = view.gap_days
    if gap is None:
        return _Outcome(
            "unknown",
            "termination-to-planting gap is not available",
            missing=["termination_gap_days"],
        )
    met = _compare(rule, gap)
    verb = "meets" if met else "does not meet"
    return _Outcome(
        "complete",
        f"{gap:g}-day termination-to-planting gap {verb} the rule ({_describe(rule)})",
        met=met,
        inputs={"termination_gap_days": gap},
    )


def _eval_numeric(rule: CropRule, view: SeasonView) -> _Outcome:
    name, unit = NUMERIC_INPUTS[rule.condition_key or ""]
    if rule.unit != unit:
        return _Outcome(
            "invalid_input", f"rule unit '{rule.unit}' does not match expected '{unit}'"
        )
    raw = view.inputs.get(name)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return _Outcome("unknown", f"input '{name}' is not available", missing=[name])
    try:
        if isinstance(raw, bool):
            raise ValueError(raw)
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError(raw)
    except (TypeError, ValueError, OverflowError):
        return _Outcome("invalid_input", f"input '{name}'={raw!r} is not a finite number")
    met = _compare(rule, value)
    verb = "meets" if met else "does not meet"
    return _Outcome(
        "complete", f"{name}={value:g} {unit} {verb} the rule ({_describe(rule)})", met=met,
        inputs={name: value},
    )  # fmt: skip


#: Stages whose window the plant/seed dates in the facts can answer.
_WINDOW_DATE_STAGES = frozenset({None, "planting", "seeding", "preplant"})
_DATE_KEY_FOR_ACTION = {"plant": "plant", "seed": "seed", "seed_after_harvest": "seed"}


def _eval_window(rule: CropRule, view: SeasonView) -> _Outcome:
    action = rule.management_action or ""
    key = _DATE_KEY_FOR_ACTION.get(action)
    if key is None:
        return _Outcome("manual_check", f"no date input maps to action '{action}'")
    if rule.growth_stage not in _WINDOW_DATE_STAGES:
        # e.g. fc_wt_03 is about the silking date; the facts hold seed/plant dates only.
        return _Outcome(
            "manual_check",
            f"window applies to the '{rule.growth_stage}' stage; no {rule.growth_stage} date is available",
        )
    d = view.dates.get(key)
    window = f"{rule.window_start_mm_dd} to {rule.window_end_mm_dd}"
    if d is None:
        return _Outcome("unknown", f"{key} date is not available", missing=[f"dates.{key}"])
    in_win = _in_window(rule, d)
    inputs: dict[str, Any] = {f"dates.{key}": d.isoformat()}
    chrono = False
    reason = f"{key} date {d.isoformat()} is {'inside' if in_win else 'outside'} {window}"
    met = in_win
    if action == "seed_after_harvest":
        h = view.dates.get("harvest")
        if h is None:
            return _Outcome(
                "unknown", "harvest date is not available", missing=["dates.harvest"], inputs=inputs
            )
        inputs["dates.harvest"] = h.isoformat()
        end = parse_mm_dd(rule.window_end_mm_dd or "")
        assert end
        # Seeding must follow harvest *and* fall in the window. Impossible when harvest is
        # already after the window's last day: a hard chronology conflict.
        if (h.month, h.day) > end:
            chrono = True
            met = False
            reason = (
                f"harvest {h.isoformat()} is after the window end ({rule.window_end_mm_dd}), so "
                f"seeding cannot both follow harvest and fall in {window}"
            )
        elif d < h:
            chrono = True
            met = False
            reason = f"seeding {d.isoformat()} is before harvest {h.isoformat()}"
        else:
            reason = f"seeding {d.isoformat()} follows harvest and is {'inside' if in_win else 'outside'} {window}"
    return _Outcome("complete", reason, met=met, inputs=inputs, chronology_conflict=chrono)


def _gate_state(gate: str, view: SeasonView) -> tuple[bool | None, str, dict[str, Any]]:
    if gate == "dry_or_moisture_concern":
        inputs = {
            "spring_is_dry": view.spring_is_dry,
            "spring_status": view.spring_status,
            "grower_low_moisture_concern": view.low_moisture_concern,
        }
        if view.spring_is_dry is True or view.low_moisture_concern is True:
            src = "dry replay" if view.spring_is_dry else "grower-reported low-moisture concern"
            return True, f"active: {src}", inputs
        if view.spring_is_dry is None:
            return (
                None,
                (
                    "cannot tell: dryness is unavailable "
                    f"(spring status {view.spring_status!r}) and no low-moisture concern was reported"
                ),
                inputs,
            )
        return (
            False,
            "not active: replay is not dry and no low-moisture concern was reported",
            inputs,
        )
    if gate == "pest_spillover_concern":
        inputs = {"grower_pest_spillover_concern": view.pest_concern}
        if view.pest_concern is True:
            return True, "active: grower-reported pest-spillover concern", inputs
        return False, "not active: no pest-spillover concern was reported", inputs
    raise KeyError(gate)


def _sequence_rule(rule: CropRule) -> bool:
    return (
        rule.rule_type == "rotation_compatibility"
        and rule.window_start_mm_dd is None
        and (rule.previous_crop_id is not None or rule.next_crop_id is not None)
        and rule.management_action not in ("reseed", "aerial_overseed")
    )


def _eval_sequence(rule: CropRule, view: SeasonView) -> _Outcome:
    note = ""
    if rule.condition_key:  # e.g. sb_rc_01 yield_gain_vs_continuous: a published result
        note = (
            f" ({rule.condition_key} {rule.value_min:g} {rule.unit or ''} is the source's "
            "published result, not a measurement on this field)"
            if rule.value_min is not None
            else f" ({rule.condition_key} is context from the source, not measured here)"
        )
    return _Outcome("complete", "crop sequence matches the rule" + note, met=True)


def reference_of(rule: CropRule) -> dict[str, Any] | None:
    """The rule's published number(s) as a sourced reference; ``None`` if it has none."""
    if rule.value_min is None and rule.value_max is None:
        return None
    return {
        "kind": "published_reference",
        "condition_key": rule.condition_key,
        "operator": rule.operator,
        "value_min": rule.value_min,
        "value_max": rule.value_max,
        "unit": rule.unit,
        "value_text": rule.value_text,
        "is_grower_target": False,
        "source_url": rule.source_url,
        "verified_date": rule.verified_date.isoformat() if rule.verified_date else None,
    }


def _reference_reason(rule: CropRule, ref: dict[str, Any]) -> str:
    lo, hi, unit = ref["value_min"], ref["value_max"], ref["unit"] or ""
    shown = (
        f"{lo:g}-{hi:g}"
        if lo is not None and hi is not None and hi != lo
        else f"{(lo if lo is not None else hi):g}"
    )
    if rule.rule_type == "nutrient_guidance" and rule.condition_key == "n_rate":
        return (
            f"sourced reference N rate {shown} {unit} ({rule.source_title}); "
            "it is not the grower's target: the target comes from the soil test"
        )
    return f"published reference value {shown} {unit}; not measured on this field"


def _choose_evaluator(rule: CropRule) -> Callable[[CropRule, SeasonView], _Outcome] | None:
    if rule.condition_key == "days_between_termination_and_planting" and rule.operator:
        return _eval_gap
    if rule.condition_key in NUMERIC_INPUTS and rule.operator:
        return _eval_numeric
    if rule.condition_key is None and rule.window_start_mm_dd and rule.window_end_mm_dd:
        return _eval_window
    if _sequence_rule(rule):
        return _eval_sequence
    return None


# --------------------------------------------------------------------------- one rule


def _source(rule: CropRule) -> RuleSource:
    return RuleSource(
        title=rule.source_title,
        url=rule.source_url,
        locator=rule.source_locator,
        verified_date=rule.verified_date.isoformat() if rule.verified_date else None,
    )


def _check(rule: CropRule, status: Status, reason: str, **kw: Any) -> RuleCheck:
    return RuleCheck(
        rule_id=rule.rule_id,
        crop_id=rule.crop_id,
        rule_type=rule.rule_type,
        suitability=rule.suitability,
        status=status,
        reason=reason,
        optional=rule.rule_id in OPTIONAL_RULES,
        source=_source(rule),
        **kw,
    )


def _verdict(rule: CropRule, met: bool) -> tuple[Verdict | None, bool]:
    suit = rule.suitability
    if rule.management_action == "seed_after_harvest":
        # cc_rc_01/02: "seeding must follow harvest and fall within the window" is a requirement
        # (the caution is to compare actual dates). Violated -> caution; satisfied -> clear.
        return (None, False) if met else ("caution", True)
    if suit in ("preferred", "acceptable"):
        return (suit, False) if met else ("caution", True)  # type: ignore[return-value]
    if suit in ("caution", "avoid"):
        return (suit, True) if met else (None, False)  # type: ignore[return-value]
    return "manual_check", False  # informational row with no suitability


def evaluate_rule(
    rule: CropRule,
    view: SeasonView,
    index: CatalogIndex,
    stages: frozenset[str] | None = TRANSITION_STAGES,
) -> RuleCheck:
    # 1. structural applicability: crop, neighbours, stage, region, production system
    if (why := _crop_applicability(rule, view, index)) is not None:
        return _check(rule, "inapplicable", why, verdict="inapplicable")
    if stages is not None and rule.growth_stage and rule.growth_stage not in stages:
        return _check(
            rule,
            "inapplicable",
            f"growth stage '{rule.growth_stage}' is outside the evaluated stages",
            verdict="inapplicable",
        )
    match, why = region_match(rule.region, view.region)
    if match == "no_match":
        return _check(rule, "inapplicable", why, verdict="inapplicable")
    if match == "unknown":
        return _check(rule, "unknown", why, verdict="unknown", missing_inputs=["region"])
    sys_issue = _system_applicability(rule, view)
    if sys_issue is not None:
        status, why = sys_issue
        return _check(
            rule,
            status,  # type: ignore[arg-type]
            why,
            verdict="inapplicable" if status == "inapplicable" else "unknown",
            missing_inputs=["production_system"] if status == "unknown" else [],
        )

    # 2. evaluation
    evaluator = _choose_evaluator(rule)
    if evaluator is None:
        why = (
            "qualitative rule: " + (rule.value_text or rule.applies_when or "no measurement")
            if rule.condition_key is None
            else f"no evaluator for condition '{rule.condition_key}'"
        )
        ref = reference_of(rule)
        if ref is not None:
            why = _reference_reason(rule, ref)
        return _check(rule, "manual_check", why, verdict="manual_check", reference=ref)
    out = evaluator(rule, view)
    if out.status == "unknown" and (gate_name := GATES.get(rule.rule_id)) is not None:
        gate_state, gate_reason, gate_inputs = _gate_state(gate_name, view)
        if gate_state is False:
            # The gate is off, so the prompt cannot fire whatever the missing input would say.
            return _check(
                rule, "complete", f"{out.reason}; applies_when {gate_reason}", verdict=None,
                condition_met=None, gate_active=False, inputs_used={**out.inputs, **gate_inputs},
            )  # fmt: skip
    if out.status != "complete":
        verdict: Verdict | None = {"unknown": "unknown", "manual_check": "manual_check"}.get(
            out.status
        )
        return _check(
            rule,
            out.status,
            out.reason,
            verdict=verdict,
            inputs_used=out.inputs,
            missing_inputs=out.missing,
        )
    assert out.met is not None

    # 3. gate (applies_when)
    gate_active: bool | None = None
    inputs = dict(out.inputs)
    reason = out.reason
    if (gate := GATES.get(rule.rule_id)) is not None:
        gate_active, gate_reason, gate_inputs = _gate_state(gate, view)
        inputs.update(gate_inputs)
        reason = f"{reason}; applies_when {gate_reason}"
        if gate_active is None and out.met and rule.suitability in ("preferred", "acceptable"):
            # The recommended condition is met, so the gated prompt cannot fire whatever the
            # gate is (handbook: at gap >= 14 the check clears). Dryness is not needed.
            reason += "; gate not needed because the recommended condition is met"
        elif gate_active is None:
            return _check(
                rule, "unknown", reason, verdict="unknown", condition_met=out.met,
                gate_active=None, inputs_used=inputs,
                missing_inputs=["spring.is_dry or grower.low_moisture_concern"],
            )  # fmt: skip
        elif gate_active is False:
            return _check(
                rule, "complete", reason, verdict=None, condition_met=out.met,
                gate_active=False, flagged=False, inputs_used=inputs,
            )  # fmt: skip

    verdict, flagged = _verdict(rule, out.met)
    if out.chronology_conflict:
        verdict, flagged = "caution", True
    return _check(
        rule, "complete", reason, verdict=verdict, condition_met=out.met,
        gate_active=gate_active, flagged=flagged, inputs_used=inputs,
        chronology_conflict=out.chronology_conflict,
    )  # fmt: skip


# --------------------------------------------------------------------------- one season


def _mark_conflicts(checks: list[RuleCheck], index: CatalogIndex) -> None:
    by_id = {c.rule_id: c for c in checks}
    # A rule is "live" when it applies, or might: missing location/system leaves it undecided,
    # so it cannot yet be declared in conflict.
    undecided = {"region", "production_system"}
    live = {
        rid
        for rid, c in by_id.items()
        if c.status != "inapplicable" and not (undecided & set(c.missing_inputs))
    }
    for rid in list(live):
        rule = index.rule(rid)
        if rule is None or not rule.guidance:
            continue
        for other in _CONFLICT_RE.findall(rule.guidance):
            if other in live and other != rid:
                for a, b in ((rid, other), (other, rid)):
                    chk = by_id[a]
                    chk.conflict = True
                    if b not in chk.conflicts_with:
                        chk.conflicts_with.append(b)


def evaluate_season(
    facts: Any,
    index: CatalogIndex,
    *,
    inputs: Mapping[str, Any] | None = None,
    stages: Iterable[str] | None | Literal["all"] = None,
    rule_ids: Iterable[str] | None = None,
) -> SeasonEvaluation:
    """Evaluate every catalog rule (or ``rule_ids``) against one season of one plan.

    ``inputs`` carries field measurements the season facts do not hold, by name:
    ``soil_temp_f``, ``soil_ph``, ``forecast_precip_in``, ``water_table_depth_in``,
    ``maturity_group``, ``gdd_after_planting_f``, ``weeks_before_first_frost``.
    ``stages`` overrides the evaluated growth stages (``"all"`` disables the filter).
    """
    year, plan_id = _get(facts, "year"), _get(facts, "plan_id")
    view = build_view(facts, index, inputs)
    if isinstance(view, str):
        return SeasonEvaluation(year=year, plan_id=plan_id, status="invalid_input", errors=[view])
    unsupported = [c for c in view.crops() if index.crop(c) is None]
    if unsupported:
        return SeasonEvaluation(
            year=year,
            plan_id=plan_id,
            status="unsupported",
            errors=[f"crop '{c}' is not in the catalog" for c in unsupported],
        )
    stage_set: frozenset[str] | None
    if stages is None:
        stage_set = TRANSITION_STAGES
    elif stages == "all":
        stage_set = None
    else:
        stage_set = frozenset(stages)
    wanted = set(rule_ids) if rule_ids is not None else None
    rules = [r for r in index.catalog.rules if wanted is None or r.rule_id in wanted]
    checks = [evaluate_rule(r, view, index, stage_set) for r in rules]
    _mark_conflicts(checks, index)
    return SeasonEvaluation(year=year, plan_id=plan_id, status="complete", checks=checks)


def evaluate_seasons(
    seasons: Iterable[Any], index: CatalogIndex, **kwargs: Any
) -> list[SeasonEvaluation]:
    return [evaluate_season(s, index, **kwargs) for s in seasons]


# --------------------------------------------------------------------------- across seasons


class SkippedYear(BaseModel):
    year: int | None
    status: Status
    reason: str


class CheckSummary(BaseModel):
    """One rule across many seasons: who qualified, who was skipped, and why."""

    rule_id: str
    source: RuleSource | None
    optional: bool
    count: int  # seasons flagged
    denominator: int  # seasons the rule was evaluated for (status == complete)
    qualifying_years: list[int]
    clear_years: list[int]
    skipped_years: list[SkippedYear]


def summarize_checks(evaluations: Sequence[SeasonEvaluation]) -> list[CheckSummary]:
    """Per-rule count / denominator over seasons. Rules inapplicable to every season are omitted."""
    ids: list[str] = []
    for ev in evaluations:
        for c in ev.checks:
            if c.rule_id not in ids:
                ids.append(c.rule_id)
    out: list[CheckSummary] = []
    for rid in ids:
        qual: list[int] = []
        clear: list[int] = []
        skipped: list[SkippedYear] = []
        source: RuleSource | None = None
        optional = False
        for ev in evaluations:
            c = ev.check(rid)
            if c is None:
                continue
            source, optional = c.source, c.optional
            if c.status == "complete":
                (qual if c.flagged else clear).append(ev.year)  # type: ignore[arg-type]
            else:
                skipped.append(SkippedYear(year=ev.year, status=c.status, reason=c.reason))
        if not qual and not clear and all(s.status == "inapplicable" for s in skipped):
            continue
        out.append(
            CheckSummary(
                rule_id=rid,
                source=source,
                optional=optional,
                count=len(qual),
                denominator=len(qual) + len(clear),
                qualifying_years=qual,
                clear_years=clear,
                skipped_years=skipped,
            )
        )
    return out


class CombinedCount(BaseModel):
    rule_ids: list[str]
    count: int  # seasons with at least one component flagged; each season counts once
    denominator: int
    qualifying_years: list[int]
    components: dict[int, list[str]]  # year -> the rule ids that flagged it


def combine_checks(
    evaluations: Sequence[SeasonEvaluation], rule_ids: Sequence[str]
) -> CombinedCount:
    """Count each season once across several rules and list the component events.

    A season is in the denominator when every component rule was evaluated for it, or when any
    component flagged it (a flagged season is evaluable by definition).
    """
    components: dict[int, list[str]] = {}
    denominator = 0
    for ev in evaluations:
        checks = [c for rid in rule_ids if (c := ev.check(rid)) is not None]
        flagged = [c.rule_id for c in checks if c.flagged]
        if flagged:
            components[ev.year] = flagged  # type: ignore[index]
        every_component = len(checks) == len(rule_ids) and all(
            c.status == "complete" for c in checks
        )
        if flagged or every_component:
            denominator += 1
    return CombinedCount(
        rule_ids=list(rule_ids),
        count=len(components),
        denominator=denominator,
        qualifying_years=sorted(components),
        components=components,
    )
