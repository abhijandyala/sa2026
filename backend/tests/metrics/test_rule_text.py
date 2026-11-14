import itertools
import re
from datetime import date

import pytest

from fieldshift.catalogs import V1_CATALOG_DIR, V2_CATALOG_DIR, CatalogIndex, load_catalog
from fieldshift.metrics.rule_text import explain, has_placeholder, should_print
from fieldshift.metrics.rules import evaluate_season
from tests.fixtures.season_facts import season_facts

NUM = re.compile(r"\d+(?:\.\d+)?")
RULE_ID = re.compile(r"\b[a-z]{2,3}_[a-z0-9_]*\d[a-z0-9_]*\b")


@pytest.fixture(scope="module")
def v2():
    return CatalogIndex(load_catalog(V2_CATALOG_DIR))


@pytest.fixture(scope="module")
def v1():
    return CatalogIndex(load_catalog(V1_CATALOG_DIR))


def scenarios():
    """Every status shape the engine can produce for one rule."""
    yield dict(status="inapplicable")
    yield dict(status="invalid_input")
    for missing in ([], ["soil_temp_f"], ["region"], ["production_system"], ["dates.plant"],
                    ["spring.is_dry or grower.low_moisture_concern"], ["soil_ph", "maturity_group"]):  # fmt: skip
        yield dict(status="unknown", missing_inputs=missing)
    yield dict(status="manual_check")
    for flagged, met, gate, verdict in itertools.product(
        (False, True), (None, True, False), (None, True, False), (None, "caution", "preferred")
    ):
        yield dict(
            status="complete", flagged=flagged, condition_met=met, gate_active=gate, verdict=verdict
        )
    yield dict(status="complete", flagged=True, chronology_conflict=True)


def allowed_numbers(rule) -> set[float]:
    out: set[float] = set()
    for v in (rule.value_min, rule.value_max, rule.exposure_duration):
        if v is not None:
            out.add(float(v))
    for field in (rule.guidance, rule.value_text, rule.applies_when):
        out |= {float(x) for x in NUM.findall(field or "")}
    for md in (rule.window_start_mm_dd, rule.window_end_mm_dd):
        if md:
            out |= {float(int(md[:2])), float(int(md[3:]))}
    return out


# ------------------------------------------------------------------ every rule, every status


@pytest.mark.parametrize("catalog", ["v1", "v2"])
def test_every_rule_in_every_status_gives_clean_non_empty_text(catalog, v1, v2):
    index = v2 if catalog == "v2" else v1
    n = 0
    for rule in index.catalog.rules:
        for sc in scenarios():
            text = explain(rule, **sc)
            n += 1
            assert text and text.strip() == text, (rule.rule_id, sc)
            assert not has_placeholder(text), (rule.rule_id, sc, text)
            assert text[-1] in ".", (rule.rule_id, sc, text)
            assert len(text) <= 260, (rule.rule_id, sc, len(text), text)
            assert "\n" not in text
    assert n > 1000


def test_text_never_invents_a_number_not_in_the_catalog_row(v2):
    for rule in v2.catalog.rules:
        allowed = allowed_numbers(rule)
        for sc in scenarios():
            text = RULE_ID.sub("", explain(rule, **sc))
            for tok in NUM.findall(text):
                assert float(tok) in allowed, (rule.rule_id, sc, tok, text)


def test_a_real_zero_in_the_row_is_shown_as_zero(v2):
    sb = v2.rule("sb_nut_01")
    assert sb.value_min == 0.0
    text = explain(sb, status="manual_check")
    assert "0 lb N/acre" in text and "your soil test sets your own target" in text
    fc = explain(v2.rule("fc_nut_01"), status="manual_check")
    assert "120 to 160 lb N/acre" in fc and "your soil test sets your own target" in fc


def test_text_has_no_engine_wording(v2):
    banned = (
        "no evaluator",
        "condition_key",
        "qualitative rule",
        "is not available",
        "_",
        "inputs_used",
        "evaluator",
    )
    for rule in v2.catalog.rules:
        for sc in scenarios():
            text = RULE_ID.sub("", explain(rule, **sc))
            assert not any(b in text for b in banned), (rule.rule_id, sc, text)


# ------------------------------------------------------------------ examples a grower would read


def test_examples_from_the_request(v2):
    assert explain(v2.rule("sb_soil_03"), status="manual_check").startswith(
        "Check soil pH: the guide's target is 6.0"
    )
    slope = explain(v2.rule("sb_soil_01"), status="manual_check")
    assert slope.startswith("Ask your adviser about slope position")
    unknown = explain(v2.rule("fc_pw_01"), status="unknown", missing_inputs=["soil_temp_f"])
    assert (
        unknown.startswith("Enter your soil temperature (°F) so this can be checked")
        and "at least 55 °F" in unknown
    )
    organic = explain(v2.rule("fc_pw_03"), status="unknown", missing_inputs=["production_system"])
    assert "production system" in organic and "whether this applies" in organic
    assert explain(v2.rule("fc_pw_03"), status="inapplicable") == "Does not apply to this plan."


def ev(index, **kw):
    inputs = kw.pop("inputs", None)
    facts = season_facts(**kw)
    return {c.rule_id: c for c in evaluate_season(facts, index, inputs=inputs, stages="all").checks}


def test_engine_checks_carry_text_and_keep_the_engine_reason(v2):
    c = ev(v2, sequence=("field_corn", "cereal_rye", "soybean"))
    slope = c["sb_soil_01"]
    assert (
        slope.status == "manual_check" and "no evaluator" in slope.reason
    )  # the debug wording stays
    assert (
        slope.text.startswith("Ask your adviser about slope position")
        and slope.text != slope.reason
    )
    cr = ev(v2, gap_days=12, is_dry=True)["cr_tt_03"]
    assert cr.flagged and cr.text.startswith("Heads-up:") and "14 days" in cr.text
    assert "gap" in cr.reason and "gap" not in cr.text.lower()
    sb = ev(v2)["sb_rc_01"]
    assert sb.text == "Good fit: soybean yields rose about 5 bu/acre after corn."


def test_every_check_the_engine_returns_has_text(v2, v1):
    for index in (v2, v1):
        for seq in (("field_corn", "soybean"), ("field_corn", "cereal_rye", "soybean"),
                    ("soybean", "crimson_clover", "field_corn"), ("field_corn", "winter_wheat", "soybean")):  # fmt: skip
            gap = None if len(seq) == 2 else 12
            for c in ev(
                index, sequence=seq, gap_days=gap, inputs={"maturity_group": 3, "soil_temp_f": 40}
            ).values():
                assert c.text and not has_placeholder(c.text), (c.rule_id, c.text)
                assert isinstance(c.print, bool)


def test_conflicting_rules_say_so_and_print(v2):
    c = ev(
        v2,
        sequence=("soybean", "cereal_rye", "field_corn"),
        inputs={"soil_temp_f": 52},
        plant=date(2010, 4, 15),
        gap_days=None,
    )
    a, b = c["fc_pw_01"], c["fc_pw_02"]
    assert a.conflict and b.conflict and a.print and b.print
    assert "sources disagree" in a.text and "fc_pw_02" in a.text and "neither is chosen" in a.text


# ------------------------------------------------------------------ the print rule


def test_print_rule(v2):
    r = v2.rule
    # fired checks print
    assert should_print(r("cr_tt_03"), status="complete", flagged=True)
    assert should_print(r("cc_rc_02"), status="complete", flagged=True, chronology_conflict=True)
    # a blocking decision rule that is checkable but unresolved prints
    assert should_print(r("cr_tt_03"), status="unknown", flagged=False, has_gate=True)
    assert should_print(r("sb_rc_03"), status="unknown", flagged=False)
    assert (
        should_print(r("fc_pw_01"), status="unknown", flagged=False) is False
    )  # suitability acceptable
    assert should_print(
        r("fc_pw_02"), status="unknown", flagged=False
    )  # caution + numeric planting rule
    # qualitative cautions apply to every plan: screen only
    for rid in ("sb_pw_02", "sb_pw_03", "sb_pw_05", "cc_pw_02", "sb_v2_pw_delay_yield"):
        assert should_print(r(rid), status="manual_check", flagged=False) is False, rid
    # soil, nutrient, weather, water rows never block a decision
    for rid in ("sb_soil_01", "sb_soil_03", "fc_nut_01", "sb_wt_02", "sb_wd_06", "cr_trait_01"):
        assert should_print(r(rid), status="manual_check", flagged=False) is False, rid
    # clear, gated-off and inapplicable never print
    assert not should_print(r("cr_tt_04"), status="complete", flagged=False)
    assert not should_print(r("fc_pw_03"), status="inapplicable", flagged=False)


def test_only_a_handful_of_checks_print_for_a_typical_plan(v2):
    for kw in (dict(sequence=("field_corn", "cereal_rye", "soybean"), gap_days=12),
               dict(sequence=("field_corn", "cereal_rye", "soybean"), gap_days=12, is_dry=True),
               dict(sequence=("soybean", "cereal_rye", "field_corn"), gap_days=10),
               dict(sequence=("field_corn", "soybean"), gap_days=None)):  # fmt: skip
        checks = ev(v2, **kw)
        live = [c for c in checks.values() if c.status != "inapplicable"]
        printed = [c.rule_id for c in live if c.print]
        assert 0 <= len(printed) <= 6, (kw, printed)
        assert len(live) > 15  # and there is a lot more on screen
        assert all(
            c.flagged or c.conflict or c.status in ("manual_check", "unknown")
            for c in live
            if c.print
        )
    dry = ev(v2, sequence=("field_corn", "cereal_rye", "soybean"), gap_days=12, is_dry=True)
    assert dry["cr_tt_03"].flagged and dry["cr_tt_03"].print


# ------------------------------------------------------------------ review fixes (phase-4b r3)


def test_text_keeps_the_conditions_the_row_attaches_to_its_number(v2):
    t = explain(v2.rule("fc_pw_04"), status="manual_check")
    assert "more than 65 °F" in t and "for at least 2 days" in t  # how long it must hold
    ph = explain(v2.rule("fc_soil_01"), status="manual_check")
    assert "target is 6.0" in ph and "mineral soil" in ph
    assert "mineral soil" in explain(v2.rule("sb_soil_03"), status="manual_check")
    heat = explain(v2.rule("sb_wt_02"), status="manual_check")
    assert "more than 85 °F" in heat and "for several days" in heat
    rain = explain(v2.rule("fc_wt_01"), status="unknown", missing_inputs=["forecast_precip_in"])
    assert "more than 2 in" in rain and "over 7 days" in rain


def test_wheat_map_row_names_both_limits_and_prints(v2):
    rule = v2.rule("ww_v2_pw_local_map")
    t = explain(rule, status="manual_check")
    assert "0 to 21 days after it" in t and "before Thanksgiving" in t
    assert should_print(rule, status="manual_check", flagged=False)  # it decides the planting date


def test_trial_row_outside_its_planting_context_says_so(v2):
    t = explain(v2.rule("sb_v2_mg_mid_july"), status="manual_check")
    assert (
        "outside the mid-July planting timing" in t
        and "5 to 7" in t
        and "for this planting date" not in t
    )
    j = explain(v2.rule("sb_v2_mg_mid_june"), status="manual_check")
    assert "outside the mid-June double-crop planting timing" in j and "4 to 7" in j


def test_conflict_text_is_one_sentence_and_printed_conflicts_reach_the_calendar(v2):
    c = ev(
        v2,
        sequence=("soybean", "cereal_rye", "field_corn"),
        inputs={"soil_temp_f": 60},
        plant=date(2010, 5, 5),
        gap_days=None,
    )
    for rid, other in (("fc_pw_01", "fc_pw_02"), ("fc_pw_02", "fc_pw_01")):
        chk = c[rid]
        assert chk.conflict and chk.print and chk.status == "complete"
        assert chk.text.endswith(".") and chk.text.count(".") == 1 and f"(see {other})" in chk.text
        assert "neither is chosen" in chk.text
    from fieldshift.contracts import Plan, WinterManagement
    from fieldshift.planner.calendar import build_action_calendar

    plan = Plan(plan_id="p", previous_crop_id="soybean", prev_harvest="10-20", winter=WinterManagement(kind="none"),
                next_crop_id="field_corn", next_plant="05-05", region="NC Piedmont", production_system="no-till")  # fmt: skip
    cal = build_action_calendar(plan, v2, year=2027, inputs={"soil_temp_f": 60})
    ids = {a.action_id for a in cal.actions}
    assert {"check:fc_pw_01", "check:fc_pw_02"} <= ids
    ev_texts = {e.rule_id: e.text for a in cal.actions for e in a.evidence}
    assert ev_texts["fc_pw_01"] == cal.check_result.rule("fc_pw_01").text


def test_wheat_plan_prints_only_a_handful(v2):
    c = ev(v2, sequence=("field_corn", "winter_wheat", "soybean"), gap_days=None, production_system="conventional",
           plant=date(2010, 6, 12), inputs={"maturity_group": 3})  # fmt: skip
    printed = sorted(r for r, x in c.items() if x.print)
    assert len(printed) <= 8, printed
    assert {"sb_rc_03", "ww_rc_01", "ww_v2_pw_local_map"} <= set(printed)
