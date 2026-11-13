from datetime import date
from types import SimpleNamespace

import pytest

from fieldshift.metrics.rules import (
    combine_checks,
    evaluate_season,
    evaluate_seasons,
    summarize_checks,
)
from tests.fixtures.season_facts import frozen_copy, season_facts

CLOVER = ("field_corn", "crimson_clover", "soybean")


def ck(ev, rule_id):
    c = ev.check(rule_id)
    assert c is not None, rule_id
    return c


# ---------------------------------------------------------------- handbook regression cases


def test_typical_year_unknown_moisture_gives_no_dry_prompt(index):
    ev = evaluate_season(season_facts(gap_days=12, is_dry=False, concern=None), index)
    c = ck(ev, "cr_tt_03")
    assert (c.status, c.flagged, c.gate_active, c.condition_met) == (
        "complete",
        False,
        False,
        False,
    )
    assert c.verdict is None


def test_12_day_gap_in_dry_year_prompts_moisture_check(index):
    ev = evaluate_season(season_facts(gap_days=12, is_dry=True), index)
    c = ck(ev, "cr_tt_03")
    assert (c.status, c.flagged, c.gate_active, c.verdict) == ("complete", True, True, "caution")
    assert c.inputs_used["termination_gap_days"] == 12
    assert c.source.url and "rotational-considerations" in c.source.url


def test_19_day_gap_clears_and_leaves_spring_facts_untouched(index):
    facts = season_facts(gap_days=19, is_dry=True)
    before = frozen_copy(facts)
    ev = evaluate_season(facts, index)
    c = ck(ev, "cr_tt_03")
    assert (c.flagged, c.condition_met, c.verdict) == (False, True, "preferred")
    assert facts == before  # the engine reads, never writes
    # the spring dryness fields feeding the engine are identical to the 12-day case
    assert facts["spring"] == season_facts(gap_days=12, is_dry=True)["spring"]


def test_missing_weather_with_grower_concern_still_fires(index):
    facts = season_facts(gap_days=12, spring_status="unavailable", is_dry=None, concern=True)
    c = ck(evaluate_season(facts, index), "cr_tt_03")
    assert (c.status, c.flagged) == ("complete", True)
    assert "grower-reported" in c.reason
    assert c.inputs_used["spring_status"] == "unavailable"


def test_missing_weather_and_no_concern_is_unknown_not_clear(index):
    facts = season_facts(gap_days=12, spring_status="unavailable", is_dry=None, concern=None)
    c = ck(evaluate_season(facts, index), "cr_tt_03")
    assert (c.status, c.flagged, c.verdict) == ("unknown", False, "unknown")
    assert c.missing_inputs


def test_partial_spring_window_is_not_treated_as_dry(index):
    facts = season_facts(spring_status="partial", is_dry=True, concern=None)
    assert ck(evaluate_season(facts, index), "cr_tt_03").status == "unknown"


@pytest.mark.parametrize(("gap", "flagged"), [(13, True), (14, False), (15, False), (0, True)])
def test_14_day_boundary_is_inclusive_on_the_clear_side(index, gap, flagged):
    c = ck(evaluate_season(season_facts(gap_days=gap, is_dry=True), index), "cr_tt_03")
    assert c.flagged is flagged


def test_cr_tt_04_is_its_own_optional_check_conditioned_on_concern(index):
    off = ck(evaluate_season(season_facts(gap_days=12, is_dry=True), index), "cr_tt_04")
    assert off.optional and off.gate_active is False and not off.flagged
    on = evaluate_season(
        season_facts(gap_days=12, observations={"pest_spillover_concern": True}), index
    )
    assert ck(on, "cr_tt_04").flagged
    ok = evaluate_season(season_facts(gap_days=24, observations=["pest_spillover_concern"]), index)
    assert (ck(ok, "cr_tt_04").flagged, ck(ok, "cr_tt_04").condition_met) == (False, True)
    # cr_tt_03 and cr_tt_04 do not interfere
    assert not ck(ok, "cr_tt_03").flagged


def test_no_cover_plan_has_no_rye_checks(index):
    facts = season_facts(sequence=("field_corn", "soybean"), gap_days=None)
    ev = evaluate_season(facts, index)
    c = ck(ev, "cr_tt_03")
    assert c.status == "inapplicable" and "cereal_rye" in c.reason


# ---------------------------------------------------------------- applicability


def test_organic_rule_is_inapplicable_to_conventional_with_reason(index):
    facts = season_facts(
        sequence=("soybean", "cereal_rye", "field_corn"),
        production_system="conventional",
        plant=date(2010, 5, 10),
    )
    ev = evaluate_season(facts, index)
    c = ck(ev, "fc_pw_03")
    assert c.status == "inapplicable" and "organic" in c.reason and "conventional" in c.reason
    organic = evaluate_season({**facts, "production_system": ["organic"]}, index)
    assert ck(organic, "fc_pw_03").status == "complete"
    assert ck(organic, "fc_pw_03").verdict == "preferred"  # May 10 inside Apr 20-May 20


def test_unknown_production_system_is_unknown_not_inapplicable(index):
    facts = season_facts(sequence=("soybean", "cereal_rye", "field_corn"), production_system=None)
    c = ck(evaluate_season(facts, index), "fc_pw_03")
    assert c.status == "unknown" and c.missing_inputs == ["production_system"]


def test_catalog_declared_conflicts_return_both_rules(index):
    facts = season_facts(sequence=("soybean", "cereal_rye", "field_corn"), plant=date(2010, 4, 15))
    ev = evaluate_season(facts, index, inputs={"soil_temp_f": 52})
    a, b = ck(ev, "fc_pw_01"), ck(ev, "fc_pw_02")
    assert a.conflict and b.conflict
    assert a.conflicts_with == ["fc_pw_02"] and b.conflicts_with == ["fc_pw_01"]
    # at 52 F: fc_pw_01 (>=55 recommended) not met -> caution; fc_pw_02 (<50 hazard) is clear
    assert (a.verdict, a.flagged) == ("caution", True)
    assert (b.verdict, b.flagged) == (None, False)


def test_conflicts_are_flagged_even_when_inputs_are_missing(index):
    facts = season_facts(sequence=("soybean", "cereal_rye", "field_corn"))
    ev = evaluate_season(facts, index)
    assert ck(ev, "fc_pw_01").status == "unknown" and ck(ev, "fc_pw_01").conflict
    assert ck(ev, "fc_pw_01").missing_inputs == ["soil_temp_f"]


def test_sb_pw_conflict_only_when_both_regions_apply(index):
    piedmont = evaluate_season(
        season_facts(sequence=("field_corn", "soybean"), gap_days=None, plant=date(2010, 5, 25)),
        index,
    )
    assert ck(piedmont, "sb_pw_04").status == "inapplicable"  # Hertford / northeastern rule
    assert not ck(piedmont, "sb_pw_01").conflict
    coastal = evaluate_season(
        season_facts(
            sequence=("field_corn", "soybean"),
            gap_days=None,
            region="Hertford County",
            plant=date(2010, 5, 25),
        ),
        index,
    )
    a, b = ck(coastal, "sb_pw_01"), ck(coastal, "sb_pw_04")
    assert a.conflict and b.conflict
    assert (a.verdict, b.verdict) == ("caution", "preferred")  # both reported, no winner


def test_window_end_is_inclusive(index):
    seq = ("field_corn", "soybean")
    for day, verdict in ((date(2010, 5, 20), "preferred"), (date(2010, 5, 21), "caution")):
        ev = evaluate_season(season_facts(sequence=seq, gap_days=None, plant=day), index)
        assert ck(ev, "sb_pw_01").verdict == verdict
    ev = evaluate_season(season_facts(sequence=seq, gap_days=None, plant=date(2010, 4, 20)), index)
    assert ck(ev, "sb_pw_01").verdict == "preferred"


def test_out_of_state_rules_are_inapplicable(index):
    ev = evaluate_season(season_facts(gap_days=12), index)
    c = ck(ev, "cr_tt_02")  # Pennsylvania, rye before corn: wrong crop AND region
    assert c.status == "inapplicable"
    clover = evaluate_season(season_facts(sequence=CLOVER, gap_days=None), index, stages="all")
    assert ck(clover, "cc_soil_03").status == "inapplicable"
    assert "outside North Carolina" in ck(clover, "cc_soil_03").reason


def test_unknown_field_region_blocks_region_specific_rules_only(index):
    ev = evaluate_season(season_facts(region="somewhere"), index)
    assert ck(ev, "cr_tt_03").status == "complete"  # "North Carolina" covers all NC
    assert ck(ev, "cr_pw_01").status == "unknown"  # "NC Piedmont" needs a known region


def test_in_season_stages_are_inapplicable_by_default(index):
    facts = season_facts(sequence=("soybean", "cereal_rye", "field_corn"))
    ev = evaluate_season(facts, index)
    assert ck(ev, "fc_wd_03").status == "inapplicable"  # pollination water use
    all_stages = evaluate_season(facts, index, stages="all")
    assert ck(all_stages, "fc_wd_03").status != "inapplicable"


# ---------------------------------------------------------------- chronology and crops


def test_clover_after_late_corn_harvest_is_a_chronology_conflict(index):
    facts = season_facts(
        sequence=CLOVER, gap_days=None, harvest=date(2009, 10, 10), seed=date(2009, 10, 12)
    )
    ev = evaluate_season(facts, index)
    c = ck(ev, "cc_rc_02")
    assert c.chronology_conflict and c.flagged and c.verdict == "caution"
    assert "after the window end" in c.reason
    assert ck(ev, "cc_pw_01").verdict == "caution"  # seeded Oct 12, outside Aug 25-Oct 1
    assert ck(ev, "sb_rc_02").flagged  # legume before soybean
    assert ck(ev, "cc_soil_02").status == "manual_check"  # Piedmont clay manual check


def test_clover_seeded_in_window_after_early_harvest_is_clear(index):
    facts = season_facts(
        sequence=CLOVER, gap_days=None, harvest=date(2009, 9, 5), seed=date(2009, 9, 15)
    )
    c = ck(evaluate_season(facts, index), "cc_rc_02")
    assert (c.chronology_conflict, c.flagged, c.condition_met, c.verdict) == (
        False,
        False,
        True,
        None,
    )


def test_clover_seeded_after_oct_1_is_flagged_even_after_a_timely_harvest(index):
    facts = season_facts(
        sequence=CLOVER, gap_days=None, harvest=date(2009, 9, 5), seed=date(2009, 10, 5)
    )
    c = ck(evaluate_season(facts, index), "cc_rc_02")
    assert (c.flagged, c.condition_met, c.chronology_conflict) == (True, False, False)
    assert "outside 08-25 to 10-01" in c.reason


def test_seed_before_harvest_is_a_chronology_conflict(index):
    facts = season_facts(
        sequence=CLOVER, gap_days=None, harvest=date(2009, 9, 20), seed=date(2009, 9, 10)
    )
    assert ck(evaluate_season(facts, index), "cc_rc_02").chronology_conflict


def test_unsupported_crop_is_unsupported_not_unknown(index):
    ev = evaluate_season(season_facts(sequence=("field_corn", "quinoa", "soybean")), index)
    assert ev.status == "unsupported" and ev.checks == []
    assert "quinoa" in ev.errors[0]


def test_bad_sequence_is_invalid_input(index):
    ev = evaluate_season({**season_facts(), "crop_sequence": ["only_one"]}, index)
    assert ev.status == "invalid_input"


def test_sequence_rules_fire_from_the_crop_sequence(index):
    ev = evaluate_season(season_facts(sequence=("field_corn", "cereal_rye", "soybean")), index)
    assert ck(ev, "cr_rc_02").verdict == "acceptable"
    assert ck(ev, "sb_rc_01").verdict == "preferred"  # soybean after corn
    assert ck(ev, "sb_rc_02").status == "inapplicable"  # no legume cover
    wheat = evaluate_season(season_facts(sequence=("field_corn", "winter_wheat", "soybean")), index)
    assert ck(wheat, "ww_rc_01").verdict == "caution" and ck(wheat, "ww_rc_01").flagged


def test_qualitative_rules_become_manual_check(index):
    ev = evaluate_season(season_facts(), index)
    assert ck(ev, "cr_tt_05").status == "manual_check"
    assert ck(ev, "sb_wt_01").status == "manual_check"
    assert ck(ev, "cc_rc_04").status == "inapplicable"  # clover rule, rye plan


def test_facts_may_be_objects_with_attributes(index):
    d = season_facts(gap_days=12, is_dry=True)
    obj = SimpleNamespace(
        year=d["year"],
        plan_id=d["plan_id"],
        crop_sequence=d["crop_sequence"],
        region=d["region"],
        production_system=d["production_system"],
        dates=SimpleNamespace(**d["dates"]),
        termination_gap_days=12,
        spring=SimpleNamespace(**d["spring"]),
        grower=SimpleNamespace(**d["grower"]),
    )
    assert evaluate_season(obj, index).model_dump() == evaluate_season(d, index).model_dump()


def test_every_catalog_rule_gets_a_check_for_every_plan(index):
    for seq in (
        ("field_corn", "soybean"),
        ("field_corn", "cereal_rye", "soybean"),
        CLOVER,
        ("soybean", "cereal_rye", "field_corn"),
        ("field_corn", "winter_wheat", "soybean"),
    ):
        ev = evaluate_season(
            season_facts(sequence=seq, gap_days=None if len(seq) == 2 else 10), index
        )
        assert ev.status == "complete"
        assert {c.rule_id for c in ev.checks} == set(index.rules)
        assert all(c.source.url for c in ev.checks)


# ---------------------------------------------------------------- across seasons


def _seasons(index):
    years = {
        2001: dict(is_dry=True),  # flagged
        2002: dict(is_dry=False),  # clear (gate off)
        2003: dict(spring_status="unavailable", is_dry=None, concern=None),  # unknown
        2004: dict(spring_status="unavailable", is_dry=None, concern=True),  # flagged by concern
        2005: dict(is_dry=True, gap_days=19),  # cleared by gap
    }
    return [season_facts(year=y, gap_days=kw.pop("gap_days", 12), **kw) for y, kw in years.items()]


def test_summary_counts_denominator_and_skipped_years(index):
    evs = evaluate_seasons(_seasons(index), index)
    s = {x.rule_id: x for x in summarize_checks(evs)}["cr_tt_03"]
    assert s.qualifying_years == [2001, 2004]
    assert s.clear_years == [2002, 2005]
    assert (s.count, s.denominator) == (2, 4)
    assert [(k.year, k.status) for k in s.skipped_years] == [(2003, "unknown")]
    assert s.source and s.source.url
    assert "cr_tt_02" not in {x.rule_id for x in summarize_checks(evs)}  # never applicable


def test_combined_count_counts_each_season_once(index):
    seasons = [
        season_facts(
            year=2001, gap_days=12, is_dry=True, observations={"pest_spillover_concern": True}
        ),
        season_facts(year=2002, gap_days=12, is_dry=True),
        season_facts(year=2003, gap_days=12, is_dry=False),
    ]
    evs = evaluate_seasons(seasons, index)
    both = combine_checks(evs, ["cr_tt_03", "cr_tt_04"])
    assert both.components == {2001: ["cr_tt_03", "cr_tt_04"], 2002: ["cr_tt_03"]}
    assert (both.count, both.denominator) == (2, 3)
    assert both.qualifying_years == [2001, 2002]


def test_accepts_the_real_season_facts_contract(index):
    from fieldshift.contracts import SeasonFacts

    d = season_facts(gap_days=12, is_dry=True, observations=["pest_spillover_concern"])
    d["dates"] = {k: v for k, v in d["dates"].items() if k != "spring_window"} | {
        "spring_start": date(2010, 4, 12),
        "spring_end": date(2010, 5, 11),
    }
    facts = SeasonFacts.model_validate(d)
    ev = evaluate_season(facts, index)
    assert ck(ev, "cr_tt_03").flagged and ck(ev, "cr_tt_04").flagged
    assert ev.model_dump() == evaluate_season(d, index).model_dump()


# ---------------------------------------------------------------- review fixes (phase-4b-B)


def test_wheat_before_soybean_matches_sb_rc_03_and_warns_on_low_maturity_group(index):
    seq = ("field_corn", "winter_wheat", "soybean")
    ev = evaluate_season(season_facts(sequence=seq), index, inputs={"maturity_group": 3})
    c = ck(ev, "sb_rc_03")
    assert (c.status, c.flagged, c.verdict) == ("complete", True, "caution")
    ok = evaluate_season(season_facts(sequence=seq), index, inputs={"maturity_group": 5})
    assert ck(ok, "sb_rc_03").flagged is False
    assert ck(evaluate_season(season_facts(sequence=seq), index), "sb_rc_03").status == "unknown"
    # soybean after wheat is not "soybean after corn"
    assert ck(ev, "sb_rc_01").status == "inapplicable"


def test_gap_at_or_above_14_clears_even_when_dryness_is_missing(index):
    facts = season_facts(gap_days=19, spring_status="unavailable", is_dry=None, concern=None)
    c = ck(evaluate_season(facts, index), "cr_tt_03")
    assert (c.status, c.flagged, c.condition_met, c.gate_active) == ("complete", False, True, None)
    assert c.verdict == "preferred"
    short = season_facts(gap_days=10, spring_status="unavailable", is_dry=None, concern=None)
    assert ck(evaluate_season(short, index), "cr_tt_03").status == "unknown"


def test_northeast_rules_need_a_northeastern_field(index):
    def run(region):
        facts = season_facts(
            sequence=("field_corn", "soybean"),
            gap_days=None,
            region=region,
            plant=date(2010, 5, 25),
        )
        return evaluate_season(facts, index)

    assert ck(run("Piedmont"), "sb_pw_04").status == "inapplicable"
    unsure = ck(run("Coastal Plain"), "sb_pw_04")
    assert unsure.status == "unknown" and "sub-region" in unsure.reason
    assert not ck(run("Coastal Plain"), "sb_pw_01").conflict  # undecided rules are not conflicts
    assert ck(run("Tidewater"), "sb_pw_04").status == "unknown"  # Tidewater is not Hertford
    assert ck(run("Hertford County, NC"), "sb_pw_04").status == "complete"
    # "NC outside Tidewater" cannot be decided for a generic Coastal Plain field either
    assert ck(run("Coastal Plain"), "sb_pw_02").status in ("manual_check", "unknown")
    assert ck(run("Piedmont"), "sb_pw_02").status == "manual_check"


@pytest.mark.parametrize("bad", ["", "  ", None])
def test_blank_numeric_inputs_are_missing_not_errors(index, bad):
    facts = season_facts(sequence=("soybean", "cereal_rye", "field_corn"))
    c = ck(evaluate_season(facts, index, inputs={"soil_temp_f": bad}), "fc_pw_01")
    assert c.status == "unknown" and c.missing_inputs == ["soil_temp_f"]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "warm", True])
def test_non_finite_or_non_numeric_inputs_are_invalid_not_clear(index, bad):
    facts = season_facts(sequence=("soybean", "cereal_rye", "field_corn"))
    ev = evaluate_season(facts, index, inputs={"soil_temp_f": bad})
    for rid in ("fc_pw_01", "fc_pw_02"):
        assert ck(ev, rid).status == "invalid_input" and not ck(ev, rid).flagged


def test_a_real_zero_input_is_evaluated_not_treated_as_missing(index):
    facts = season_facts(sequence=("soybean", "cereal_rye", "field_corn"))
    ev = evaluate_season(facts, index, inputs={"soil_temp_f": 0})
    assert ck(ev, "fc_pw_02").flagged and ck(ev, "fc_pw_02").status == "complete"


def test_sb_rc_01_states_its_value_is_a_published_result(index):
    c = ck(evaluate_season(season_facts(), index), "sb_rc_01")
    assert c.verdict == "preferred" and "published result" in c.reason


def test_combined_count_needs_every_requested_component(index):
    evs = evaluate_seasons([season_facts(year=2001, gap_days=12, is_dry=False)], index)
    only03 = [
        ev.model_copy(update={"checks": [c for c in ev.checks if c.rule_id == "cr_tt_03"]})
        for ev in evs
    ]
    both = combine_checks(only03, ["cr_tt_03", "cr_tt_04"])
    assert both.denominator == 0  # cr_tt_04 was never evaluated for the season
    assert combine_checks(evs, ["cr_tt_03", "cr_tt_04"]).denominator == 1


# ---------------------------------------------------------------- review fixes (phase-4b-B r2)


def test_false_gate_clears_even_when_the_gap_is_missing(index):
    facts = season_facts(gap_days=None, is_dry=False, concern=None)
    c = ck(evaluate_season(facts, index), "cr_tt_03")
    assert (c.status, c.flagged, c.gate_active, c.condition_met) == ("complete", False, False, None)
    dry = season_facts(gap_days=None, is_dry=True)
    assert ck(evaluate_season(dry, index), "cr_tt_03").status == "unknown"  # gate on: gap needed


def test_silking_window_is_not_answered_with_the_planting_date(index):
    facts = season_facts(sequence=("soybean", "cereal_rye", "field_corn"), plant=date(2010, 7, 5))
    c = ck(evaluate_season(facts, index, stages="all"), "fc_wt_03")
    assert c.status == "manual_check" and "silking" in c.reason


@pytest.mark.parametrize("gap", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_gap_is_invalid_input(index, gap):
    ev = evaluate_season({**season_facts(), "termination_gap_days": gap}, index)
    assert ev.status == "invalid_input" and "finite" in ev.errors[0]


def test_real_zero_gap_stays_zero(index):
    c = ck(evaluate_season(season_facts(gap_days=0, is_dry=True), index), "cr_tt_03")
    assert c.flagged and c.inputs_used["termination_gap_days"] == 0
