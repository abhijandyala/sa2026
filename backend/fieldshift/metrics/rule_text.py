"""Plain-language text for rule checks: what the grower should look at or do.

``RuleCheck.reason`` stays as the engine's own wording (for debugging). ``RuleCheck.text`` is one
short sentence for the grower, built from the **catalog row** (guidance, ``value_min`` /
``value_max`` / ``unit``, ``management_action``, ``applies_when``, the window dates) and the
check's status. It never invents a number: every figure in a ``text`` comes from the catalog row
(or is a month/day taken from the row's own window). Tests assert this for every v2 rule.

Shapes, by status:

* ``flagged``      "Heads-up: <the source's own advice>" (or the window/target that was missed);
* ``manual_check`` numeric row: "Check <thing>: the guide <target>."; qualitative row:
                   "Ask your adviser about <thing> <when>.";
* ``unknown``      what to enter so it can be checked (and the target, when the row has one);
* ``complete``     "No action needed: ..." / "Not needed now: this only matters when ...";
* ``inapplicable`` "Does not apply to this plan."

``print`` marks the handful of checks worth putting on a printed page:

1. any **flagged** check (it fired), and any chronology or catalog conflict; and
2. a ``manual_check`` or ``unknown`` check that **blocks a decision**: the catalog gives it a
   ``caution`` or ``avoid`` suitability (or waits on a dry-spring / concern gate such as
   ``cr_tt_03``), it is a planting-window, rotation-compatibility or
   termination-timing rule (the rules that decide whether or when to seed, end a cover, or plant),
   AND it is checkable (the row has a number, a date window, or a gate that waits on an input);
   a planting-window row that measures the planting date itself in days (the wheat "days after the
   mapped start" check) counts as blocking whatever its suitability.
   Purely qualitative cautions ("planting before mid-April costs yield") apply to every plan, so
   they stay on screen only.

Everything else (reference values, in-season monitoring, soil and nutrient notes, checks that
are clear, optional checks whose gate is off, rules that do not apply) is ``print = False``.
"""

from __future__ import annotations

import re
from typing import Any

from fieldshift.catalogs.models import CropRule

#: Rule types whose unresolved checks can block a seeding / termination / planting decision.
DECISION_TYPES = frozenset({"planting_window", "rotation_compatibility", "termination_timing"})
BLOCKING_SUITABILITY = frozenset({"caution", "avoid"})

UNIT_LABEL = {
    "degF": "°F",
    "in": "in",
    "days": "days",
    "weeks": "weeks",
    "hours": "hours",
    "pH": "",
    "lb_N_per_acre": "lb N/acre",
    "bu_per_acre": "bu/acre",
    "in_per_day": "in/day",
    "in_per_ft": "in/ft",
    "GDD_F": "growing degree days",
    "maturity_group": "",
    "seeds/ft2": "seeds/ft²",
    "seeds/acre": "seeds/acre",
}

#: condition_key -> how the grower would say it.
CONDITION_LABEL = {
    "days_between_termination_and_planting": "the days between ending the cover and planting",
    "seed_zone_soil_temperature": "soil temperature at seed depth",
    "daily_mean_air_temperature": "the daily average air temperature",
    "gdd_accumulation_after_planting": "warmth in the first days after planting (growing degree days)",
    "forecast_precipitation": "the rain forecast for the week after planting",
    "seedbed_moisture": "seedbed moisture",
    "seeding_depth": "seeding depth",
    "seeding_rate": "seeding rate",
    "relative_maturity": "hybrid relative maturity",
    "soil_ph_target": "soil pH",
    "soil_ph": "soil pH",
    "n_rate": "the nitrogen rate",
    "legume_n_supply": "the nitrogen the legume cover supplies",
    "soil_moisture_status": "soil moisture",
    "maturity_group": "the soybean maturity group",
    "drainage_class": "drainage",
    "soil_texture": "soil texture",
    "slope_position": "slope position",
    "plant_available_water": "the soil's plant-available water",
    "water_table_depth": "the water table depth",
    "maximum_rooting_depth": "rooting depth",
    "daily_crop_water_use": "daily crop water use",
    "seasonal_crop_water_use": "seasonal crop water use",
    "air_temperature": "air temperature",
    "night_air_temperature": "night-time air temperature",
    "germination_temperature_unspecified": "temperature at germination",
    "growth_temperature_unspecified": "temperature for growth",
    "day_length": "day length",
    "weeks_before_first_frost": "the weeks left before first frost",
    "n_scavenged": "the nitrogen the cover scavenges",
    "aboveground_n": "the nitrogen in the cover",
    "gdd_to_emergence": "warmth needed to emerge (growing degree days)",
    "days_to_r1_increase_per_mg": "days to flowering",
    "drying_days_after_r8": "drying days before harvest",
    "yield_gain_vs_continuous": "yield after the previous crop",
    "previous_crop_nonhost": "the previous crop's disease risk",
    "residual_wheat_stubble": "leftover wheat stubble",
    "planting_map_reference": "your local wheat planting date from the map",
    "hessian_fly_planting_timing": "wheat planting date against Hessian fly timing",
    "days_after_local_mapped_start": "your wheat planting date against the local map date",
    "harvest_season_context": "wheat harvest timing",
    "planting_after_small_grain": "double-crop soybean planting timing",
    "delayed_planting_yield": "late planting",
    "late_planting_narrow_rows": "row spacing for late planting",
}

#: Input names (``RuleCheck.missing_inputs``) in the grower's words.
INPUT_LABEL = {
    "soil_temp_f": "your soil temperature (°F)",
    "soil_ph": "your soil pH",
    "forecast_precip_in": "the rain forecast (inches)",
    "water_table_depth_in": "your water table depth (inches)",
    "maturity_group": "the soybean maturity group you plan to plant",
    "gdd_after_planting_f": "the warmth forecast after planting",
    "weeks_before_first_frost": "the weeks before first frost",
    "region": "your field's region",
    "production_system": "your production system (conventional, organic, no-till, ...)",
    "termination_gap_days": "the date you will end the cover crop",
    "dates.plant": "your planting date",
    "dates.seed": "your seeding date",
    "dates.harvest": "your previous harvest date",
    "spring.is_dry or grower.low_moisture_concern": "a dry-spring reading or your low-moisture concern",
}

_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
#: Sentences in the catalog's guidance that are notes to the engine or the data team, not advice.
_NOISE = re.compile(
    r"(manual (field |pest|residue|moisture|location|check)|conflicts? with|overlaps?|"
    r"not (piedmont|a (wheat|preferred)|an? )|no numeric|no fixed numeric|descriptive|"
    r"this row supplies|do not (calculate|generalize)|piedmont data missing|data missing|"
    r"context only|not a (guarantee|harvest)|illustrative|index is unitless|keep both|"
    r"use (actual|the local map)|treat as a manual|numeric|source does not|v1 |"
    r"^no [\w\- ]+ given|^qualitative|^background|^reference|not a double-crop|"
    r"^table \d|sourced from|^peak demand|reference\.$)",
    re.IGNORECASE,
)


def _num(v: float) -> str:
    return f"{v:g}"


def _with_unit(v: float, unit: str | None) -> str:
    label = UNIT_LABEL.get(unit or "", unit or "")
    return f"{_num(v)} {label}".strip()


def target_phrase(rule: CropRule) -> str | None:
    """What the guide says, from the row's numbers only (``None`` when the row has none)."""
    lo, hi, op = rule.value_min, rule.value_max, rule.operator
    if lo is None and hi is None:
        return None
    if op == "between" and lo is not None and hi is not None:
        unit = UNIT_LABEL.get(rule.unit or "", rule.unit or "")
        return f"{_num(lo)} to {_num(hi)} {unit}".strip()
    v = lo if lo is not None else hi
    assert v is not None
    shown = _with_unit(v, rule.unit)
    return {
        "gte": f"at least {shown}",
        "gt": f"more than {shown}",
        "lte": f"at most {shown}",
        "lt": f"less than {shown}",
        "eq": shown,
    }.get(op or "eq", shown)


def _date(md: str | None) -> str | None:
    if not md or not re.match(r"^\d{2}-\d{2}$", md):
        return None
    return f"{_MONTHS[int(md[:2])]} {int(md[3:])}"


def window_phrase(rule: CropRule) -> str | None:
    a, b = _date(rule.window_start_mm_dd), _date(rule.window_end_mm_dd)
    return f"{a} to {b}" if a and b else None


def subject(rule: CropRule) -> str:
    if rule.condition_key and rule.condition_key in CONDITION_LABEL:
        return CONDITION_LABEL[rule.condition_key]
    if rule.condition_key:
        return rule.condition_key.replace("_", " ")
    return {
        "planting_window": "the planting dates",
        "rotation_compatibility": "this crop order",
        "termination_timing": "when to end the cover",
        "soil_suitability": "the soil",
        "weather_tolerance": "the weather",
        "water_demand": "water",
        "nutrient_guidance": "fertilizer",
        "growth_duration": "timing",
        "light_requirement": "daylight",
        "rotation_trait": "this crop's traits",
    }.get(rule.rule_type or "", "this")


def when_phrase(rule: CropRule) -> str:
    """ "before seeding", "before planting", ... from the row's management action / type."""
    a = rule.management_action
    if a in ("seed", "seed_after_harvest", "reseed", "aerial_overseed", "inoculate"):
        return "before seeding"
    if a in ("terminate",) or rule.rule_type == "termination_timing":
        return "before you end the cover"
    if a in (
        "plant",
        "seed_depth",
        "seeding_rate",
        "row_spacing",
        "select_variety",
        "fertilize_starter",
    ):
        return "before planting"
    if a == "harvest":
        return "before harvest"
    if a == "fertilize_n":
        return "when you set the nitrogen plan"
    if a == "lime":
        return "before planting"
    if a == "supplemental_irrigation":
        return "before you irrigate"
    if a in ("plan_rotation", "rotate"):
        return "when you plan the rotation"
    return ""


def _lower_first(s: str) -> str:
    """Lower-case the first letter unless the first word is an acronym (NC State, MG4-7)."""
    if len(s) > 1 and s[1].isupper():
        return s
    return s[:1].lower() + s[1:] if s else s


def _sentence(s: str) -> str:
    s = s.strip().rstrip(".")
    return s + "." if s else s


def _clean(part: str, limit: int) -> str | None:
    part = part.strip()
    if not part or _NOISE.search(part) or len(part) > limit or len(part.split()) < 3:
        return None
    return _sentence(part)


def tip(rule: CropRule, limit: int = 150) -> str | None:
    """The first piece of the source's own words that reads as advice (no engine notes).

    Looks at the guidance first, then at the row's ``value_text`` when that is a sentence.
    """
    for part in re.split(r"(?<=[.!?])\s+", (rule.guidance or "").strip()):
        got = _clean(part, limit)
        if got:
            return got
    return _clean(rule.value_text or "", limit)


def _applies_when(rule: CropRule) -> str | None:
    aw = (rule.applies_when or "").strip().rstrip(".")
    return _lower_first(aw) if aw else None


def _inputs_phrase(missing: list[str]) -> str:
    names = [INPUT_LABEL.get(m, m.replace("_", " ")) for m in missing]
    if not names:
        return "more information"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


#: subjects that already say when ("the planting dates"), so no "before planting" is added.
_TIMELESS = frozenset(
    {
        "the planting dates",
        "when to end the cover",
        "timing",
        "late planting",
        "row spacing for late planting",
        "double-crop soybean planting timing",
        "wheat planting date against Hessian fly timing",
        "wheat harvest timing",
    }
)
REFERENCE_TYPES = frozenset(
    {"growth_duration", "water_demand", "rotation_trait", "light_requirement"}
)
HAZARD_OPERATORS = frozenset({"lt", "lte", "gt", "gte"})


def _fmt(rule: CropRule, v: float) -> str:
    return f"{v:.1f}" if rule.unit == "pH" else _num(v)


def _guide_clause(rule: CropRule, target: str) -> str:
    """The guide's target / range / warning as a clause (6.0 for pH)."""
    if rule.operator == "eq" and rule.unit == "pH":
        return f"the guide's target is {_fmt(rule, rule.value_min or 0.0)}"
    if rule.operator == "eq":
        return f"the guide's target is {target}"
    if rule.suitability in ("caution", "avoid") and rule.operator in HAZARD_OPERATORS:
        return f"the guide warns about {target}"
    return f"the guide says {target}"


def _qualifier(rule: CropRule, subj: str) -> str:
    """Conditions the row attaches to its number: how long it must hold, and which soils."""
    out = ""
    unit = rule.exposure_unit
    if rule.exposure_duration is not None and unit:
        n = _num(rule.exposure_duration)
        out += (
            f" for at least {n} {unit}"
            if "temperature" in subj and rule.operator in ("gt", "gte")
            else f" over {n} {unit}"
        )
    elif rule.exposure_duration_text and unit:
        out += f" for {rule.exposure_duration_text} {unit}"
    aw = (rule.applies_when or "").strip().rstrip(".")
    if aw and re.search(r"\bsoils?\b", aw, re.IGNORECASE) and len(aw) <= 40:
        out += f" ({_lower_first(aw)})"
    return out


def _ask(rule: CropRule, subj: str, advice: str | None) -> str:
    w = when_phrase(rule)
    when = "" if subj in _TIMELESS or not w else f" {w}"
    extra = f": {_lower_first(advice).rstrip('.')}" if advice and len(advice) <= 120 else ""
    return _sentence(f"Ask your adviser about {subj}{when}{extra}")


def explain(
    rule: CropRule,
    *,
    status: str,
    verdict: str | None = None,
    flagged: bool = False,
    condition_met: bool | None = None,
    gate_active: bool | None = None,
    missing_inputs: list[str] | None = None,
    chronology_conflict: bool = False,
) -> str:
    """One short sentence for the grower. Never empty, never contains a placeholder."""
    subj = subject(rule)
    target = target_phrase(rule)
    window = window_phrase(rule)
    advice = tip(rule)
    mg_row = rule.condition_key == "maturity_group"

    if status == "inapplicable":
        return "Does not apply to this plan."
    if status == "invalid_input":
        return _sentence(f"Check the {subj} you entered: it is not a usable number")
    if status == "unknown":
        missing = list(missing_inputs or [])
        if "region" in missing or "production_system" in missing:
            what = _inputs_phrase([m for m in missing if m in ("region", "production_system")])
            return _sentence(f"Add {what} so we can tell whether this applies")
        if any(m.startswith("spring.is_dry") for m in missing):
            lead = "Depends on a dry spring or your low-moisture concern"
            return _sentence(f"{lead}: {_lower_first(advice).rstrip('.')}" if advice else lead)
        base = f"Enter {_inputs_phrase(missing)} so this can be checked"
        return _sentence(
            f"{base}: {_guide_clause(rule, target)}{_qualifier(rule, subj)}" if target else base
        )
    if status == "manual_check":
        if rule.condition_key == "days_after_local_mapped_start" and rule.value_min is not None:
            limit = (
                ", and advises planting before Thanksgiving"
                if "thanksgiving" in (rule.guidance or "").lower()
                else ""
            )
            return _sentence(
                f"Check your wheat planting date against your local map date: the guide allows "
                f"{_num(rule.value_min)} to {_num(rule.value_max or rule.value_min)} days after it{limit}"
            )
        if mg_row and target:
            # a row studied at one planting time that the plan's planting date is outside of
            timing = _applies_when(rule)
            timing = timing.split(";")[0].strip() if timing else "a different"
            return _sentence(
                f"Your planting date is outside the {timing} timing this row covers (the trials say "
                f"maturity group {target}): check the maturity group with your adviser"
            )
        if rule.condition_key == "n_rate" and target:
            return _sentence(
                f"For reference, the published nitrogen rate is {target}; "
                "your soil test sets your own target"
            )
        reference_like = rule.rule_type in REFERENCE_TYPES and rule.suitability not in (
            "caution",
            "avoid",
        )
        if reference_like or rule.condition_key in (
            "daily_crop_water_use",
            "maximum_rooting_depth",
            "seasonal_crop_water_use",
        ):
            # the source's sentence when it carries a figure, else the row's own numbers
            has_figure = bool(advice and re.search(r"\d", advice))
            if target and not has_figure:
                return _sentence(f"For reference, the guide gives {target} for {subj}")
            if advice:
                return _sentence(f"For reference: {_lower_first(advice).rstrip('.')}")
            return "For reference only; no action needed."
        if target:
            w = when_phrase(rule)
            when = "" if subj in _TIMELESS or not w else f", {w}"
            return _sentence(
                f"Check {subj}: {_guide_clause(rule, target)}{_qualifier(rule, subj)}{when}"
            )
        return _ask(rule, subj, advice)

    # status == "complete"
    if gate_active is False:
        aw = _applies_when(rule)
        return _sentence(
            f"Not needed now: this only matters when {aw}"
            if aw
            else "Not needed now: its trigger is not active"
        )
    if chronology_conflict or (flagged and rule.management_action == "seed_after_harvest"):
        return _sentence(
            f"Dates clash: seeding has to follow harvest and fall in {window or 'the published window'}"
            if chronology_conflict
            else f"Heads-up: seeding has to follow harvest and fall in {window or 'the published window'}; yours does not"
        )
    if flagged:
        if (
            target
            and condition_met is False
            and rule.suitability in ("preferred", "acceptable")
            and rule.condition_key != "days_between_termination_and_planting"
            and not window
        ):
            return _sentence(f"Heads-up: {subj} does not meet the guide ({target})")
        if mg_row and rule.rule_id in VERDICT_ROWS and target:
            return _sentence(
                f"Heads-up: your soybean maturity group is outside the {target} range the trials support for this planting date"
            )
        if window and not (rule.suitability in ("caution", "avoid") and advice):
            kind = {"preferred": "preferred", "acceptable": "acceptable"}.get(
                rule.suitability or "", "published"
            )
            return _sentence(
                f"Heads-up: your {_action_word(rule)} date is outside the {kind} window ({window})"
            )
        if advice:
            return _sentence(f"Heads-up: {_lower_first(advice).rstrip('.')}")
        if target:
            return _sentence(f"Heads-up: {subj} should be {target}")
        return _sentence(f"Heads-up: review {subj}")
    # clear
    if window:
        return _sentence(
            f"No action needed: your {_action_word(rule)} date is inside the window ({window})"
        )
    if rule.rule_type == "rotation_compatibility" and advice:
        return _sentence(f"Good fit: {_lower_first(advice).rstrip('.')}")
    if target and condition_met is not None:
        if rule.suitability in ("caution", "avoid") and rule.operator in HAZARD_OPERATORS:
            return _sentence(f"Not a concern now: {subj} is not {target}")
        return _sentence(f"No action needed: {subj} meets the guide ({target})")
    if advice:
        return _sentence(f"Good fit: {_lower_first(advice).rstrip('.')}")
    return "No action needed."


#: rows whose verdict is mapped from trial wording (kept in step with ``metrics.rules``)
VERDICT_ROWS = frozenset({"sb_v2_mg_mid_june", "sb_v2_mg_mid_july"})


def _action_word(rule: CropRule) -> str:
    return {
        "seed": "seeding",
        "seed_after_harvest": "seeding",
        "plant": "planting",
        "select_variety": "planting",
    }.get(rule.management_action or "", "planting")


def should_print(
    rule: CropRule,
    *,
    status: str,
    flagged: bool,
    conflict: bool = False,
    chronology_conflict: bool = False,
    suitability: str | None = None,
    has_gate: bool = False,
) -> bool:
    """The printed-page rule (see the module docstring)."""
    if flagged or conflict or chronology_conflict:
        return True
    if status in ("manual_check", "unknown"):
        checkable = (
            rule.value_min is not None
            or rule.value_max is not None
            or rule.window_start_mm_dd is not None
            or has_gate
        )
        blocking = (suitability or rule.suitability) in BLOCKING_SUITABILITY or has_gate
        # a planting-date check ("N days after the mapped start") decides the date itself
        date_check = (
            rule.rule_type == "planting_window"
            and rule.management_action == "plant"
            and rule.unit == "days"
        )
        return (blocking or date_check) and rule.rule_type in DECISION_TYPES and checkable
    return False


def has_placeholder(text: str) -> bool:
    """True if a text still contains an unfilled template slot or a Python repr."""
    return bool(re.search(r"[{}]|None|nan\b|\bTrue\b|\bFalse\b|%s|\$\{", text))


__all__: list[Any] = [
    "explain", "should_print", "has_placeholder", "target_phrase", "tip", "window_phrase",
]  # fmt: skip
