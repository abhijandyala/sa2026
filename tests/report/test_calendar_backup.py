from datetime import date

from fieldshift.contracts import GrowerInputs
from fieldshift.planner.backup import (
    CHECK_LEAD_DAYS,
    build_backup_plan,
    compare_fixed_plans,
    suggest_fallback,
)
from fieldshift.planner.calendar import add_scenarios, build_action_calendar, diff_calendars

from .conftest import YEAR, edited


def by_id(cal):
    return {a.action_id: a for a in cal.actions}


# ------------------------------------------------------------------ calendar


def test_calendar_has_dated_plan_actions_in_order_with_trigger_and_zone(ctx, rye):
    cal = build_action_calendar(rye, ctx.index, year=YEAR)
    assert cal.status == "complete"
    acts = by_id(cal)
    assert acts["harvest"].date == date(2026, 9, 20) and acts["seed"].date == date(2026, 10, 1)
    assert acts["terminate"].date == date(2027, 4, 30) and acts["plant"].date == date(2027, 5, 12)
    assert acts["spring_window"].date == date(2027, 4, 12) and acts[
        "spring_window"
    ].end_date == date(2027, 5, 11)
    dates = [a.date for a in cal.actions]
    assert dates == sorted(dates)
    for a in cal.actions:
        assert a.trigger and a.zone is None and a.status in ("complete", "manual_check", "unknown")


def test_moisture_check_is_due_on_the_termination_date_and_unknown_without_weather(ctx, rye):
    c = by_id(build_action_calendar(rye, ctx.index, year=YEAR))["check:cr_tt_03"]
    assert c.date == date(2027, 4, 30) and c.status == "unknown" and not c.flagged
    assert c.evidence[0].source["url"] and "dry" in c.trigger


def test_grower_concern_flags_the_check(ctx, rye):
    worried = rye.model_copy(update={"grower": GrowerInputs(low_moisture_concern=True)})
    c = by_id(build_action_calendar(worried, ctx.index, year=YEAR))["check:cr_tt_03"]
    assert c.flagged and c.status == "manual_check"


def test_n_reference_row_is_an_action_with_the_sourced_reference_not_a_target(ctx):
    from fieldshift.contracts import Plan, WinterManagement

    p = Plan(plan_id="sc", previous_crop_id="soybean", prev_harvest="10-20",
             winter=WinterManagement(kind="none"), next_crop_id="field_corn", next_plant="04-25",
             region="NC Piedmont", production_system="no-till")  # fmt: skip
    c = by_id(build_action_calendar(p, ctx.index, year=YEAR))["check:fc_nut_01"]
    ref = c.evidence[0].reference
    assert (ref["value_min"], ref["value_max"], ref["is_grower_target"]) == (120.0, 160.0, False)
    assert c.date == date(2027, 4, 25)


def test_in_season_monitoring_rows_are_not_dated_actions(ctx, rye):
    ids = set(by_id(build_action_calendar(rye, ctx.index, year=YEAR)))
    assert "check:sb_wd_01" not in ids and "check:sb_wt_02" not in ids


def test_dry_scenario_lists_decisions_that_could_change_wet_lists_drainage_checks(ctx, rye):
    cal = add_scenarios(build_action_calendar(rye, ctx.index, year=YEAR), rye, ctx)
    sc = cal.scenarios
    assert sc["status"] == "complete" and {"typical", "dry", "wet"} <= set(sc)
    dry = sc["dry"]
    assert dry["spring"]["is_dry"] is True and dry["spring"]["rank"] == 1
    d = dry["decisions_that_could_change"]
    assert [x["rule_id"] for x in d] == ["cr_tt_03"] and d[0]["date"] == "2027-04-30"
    assert "decisions_that_could_change" not in sc["typical"]
    assert sc["typical"]["spring"]["is_dry"] is False
    wet = sc["wet"]["drainage_access_checks"]
    assert wet["status"] == "complete" and [i["zone"] for i in wet["items"]] == ["zone_ne"]
    assert wet["items"][0]["status"] == "manual_check" and wet["items"][0]["due"] == "2027-05-12"
    assert dry["wetness"]["label"] == "modeled" and sc["wet"]["wetness"]["label"] == "modeled"


def test_scenarios_do_not_change_the_plan_dates(ctx, rye):
    base = build_action_calendar(rye, ctx.index, year=YEAR)
    full = add_scenarios(build_action_calendar(rye, ctx.index, year=YEAR), rye, ctx)
    assert [(a.action_id, a.date) for a in base.actions] == [
        (a.action_id, a.date) for a in full.actions
    ]


def test_invalid_and_unsupported_plans_do_not_build_a_calendar(ctx, rye):
    bad = edited(rye, seed="09-01")
    assert build_action_calendar(bad, ctx.index, year=YEAR).status == "invalid_input"
    quinoa = rye.model_copy(update={"next_crop_id": "quinoa"})
    assert build_action_calendar(quinoa, ctx.index, year=YEAR).status == "unsupported"


# ------------------------------------------------------------------ diff


def test_editing_the_termination_date_regenerates_the_calendar_and_explains_the_diff(ctx, rye):
    new = edited(rye, terminate="04-14")
    before = build_action_calendar(rye, ctx.index, year=YEAR)
    after = build_action_calendar(new, ctx.index, year=YEAR)
    d = diff_calendars(before, after, rye, new)
    assert d["plan_edits"] == [{"field": "winter.terminate", "before": "04-30", "after": "04-14"}]
    ch = {c["action_id"]: c for c in d["changes"]}
    assert ch["terminate"]["days_moved"] == -16 and ch["terminate"]["date_after"] == "2027-04-14"
    assert ch["terminate"]["why"] == ["winter.terminate: 04-30 -> 04-14"]
    assert d["termination_gap_days"] == {"before": 12, "after": 28}
    assert "check:cr_tt_03" in ch  # the 28-day gap clears the moisture check
    assert "plant" not in ch and "harvest" not in ch  # untouched dates are not reported


def test_editing_the_planting_date_moves_plant_window_and_gap(ctx, rye):
    new = rye.model_copy(update={"next_plant": "05-19"})
    d = diff_calendars(build_action_calendar(rye, ctx.index, year=YEAR),
                       build_action_calendar(new, ctx.index, year=YEAR), rye, new)  # fmt: skip
    ch = {c["action_id"]: c for c in d["changes"]}
    assert ch["plant"]["days_moved"] == 7 and ch["spring_window"]["days_moved"] == 7
    assert ch["plant"]["why"] == ["next_plant: 05-12 -> 05-19"]
    assert d["termination_gap_days"] == {"before": 12, "after": 19}


def test_editing_the_cover_crop_changes_seed_label_and_rules(ctx, rye):
    new = edited(rye, crop_id="crimson_clover", seed="10-05", terminate="04-20")
    d = diff_calendars(build_action_calendar(rye, ctx.index, year=YEAR),
                       build_action_calendar(new, ctx.index, year=YEAR), rye, new)  # fmt: skip
    ch = {c["action_id"]: c for c in d["changes"]}
    assert "winter.crop_id: cereal_rye -> crimson_clover" in ch["seed"]["why"]
    assert ch["check:cr_tt_03"]["change"] == "removed"  # rye-only check
    assert any(k.startswith("check:cc_") or k == "check:sb_rc_02" for k in ch)


def test_no_edit_means_an_empty_diff(ctx, rye):
    cal = build_action_calendar(rye, ctx.index, year=YEAR)
    d = diff_calendars(cal, build_action_calendar(rye, ctx.index, year=YEAR), rye, rye)
    assert d["unchanged"] is True and d["changes"] == []


# ------------------------------------------------------------------ backup plan


def test_suggested_fallback_keeps_the_seeding_and_ends_the_cover_earlier(ctx, rye):
    fb = suggest_fallback(rye, ctx.index, year=YEAR)
    assert fb.winter.seed == rye.winter.seed and fb.winter.crop_id == rye.winter.crop_id
    assert fb.winter.terminate == "04-28" and fb.plan_id.startswith("corn_soy__rye__fallback")


def test_backup_plan_dates_and_switch_condition(ctx, rye):
    b = build_backup_plan(rye, None, ctx.index, year=YEAR, as_of=date(2027, 4, 1))
    assert b.status == "complete" and b.fallback_source == "suggested"
    assert b.divergence.action_id == "terminate" and b.divergence.first_date == date(2027, 4, 28)
    assert b.decision_deadline == date(2027, 4, 27)
    assert b.next_check_date == date(2027, 4, 27) - __import__("datetime").timedelta(
        days=CHECK_LEAD_DAYS
    )
    assert b.timing == "upcoming"
    sc = b.switch_condition
    assert sc.kind == "dry_or_moisture_concern" and sc.rule_ids == ["cr_tt_03"]
    assert "2027-04-27" in sc.text and "low-moisture" in sc.text
    assert b.backtest["status"] == "unavailable"
    assert any("assumed" in a for a in b.assumptions)


def test_backup_timing_due_and_past_deadline(ctx, rye):
    due = build_backup_plan(rye, None, ctx.index, year=YEAR, as_of=date(2027, 4, 22))
    assert due.timing == "due" and due.next_check_date == date(2027, 4, 22)
    late = build_backup_plan(rye, None, ctx.index, year=YEAR, as_of=date(2027, 4, 29))
    assert late.timing == "past_deadline" and late.next_check_date is None
    assert late.decision_deadline == date(2027, 4, 27)


def test_backup_with_a_grower_fallback_and_fixed_plan_comparison(ctx, rye):
    fb = edited(rye, terminate="04-14").model_copy(update={"plan_id": "my_fallback"})
    b = build_backup_plan(rye, fb, ctx.index, year=YEAR, as_of=date(2027, 4, 1))
    assert b.fallback_source == "grower" and b.divergence.first_date == date(2027, 4, 14)
    b = compare_fixed_plans(b, rye, fb, ctx)
    c = b.comparison
    assert c["basis"] == "fixed_plans" and "not a forecast" in c["note"]
    d, f, diff = c["default"], c["fallback"], c["fallback_minus_default"]
    assert d["termination_gap_days"] == 12 and f["termination_gap_days"] == 28
    assert diff["termination_gap_days"] == 16 and diff["living_cover_days_planned"] == -16
    counts = diff["spring_check_counts"]["rye_soy_short_gap_moisture"]
    assert (
        counts["default"] > 0 and counts["fallback"] == 0
    )  # a 28-day gap never fires the 14-day check


def test_backup_identical_plans_have_nothing_to_switch(ctx, rye):
    b = build_backup_plan(rye, rye.model_copy(update={"plan_id": "same"}), ctx.index, year=YEAR)
    assert b.divergence is None and b.decision_deadline is None and b.timing is None
    assert any("nothing to switch" in n for n in b.notes)


def test_backup_for_invalid_fallback_reports_the_issue(ctx, rye):
    b = build_backup_plan(rye, edited(rye, seed="09-01"), ctx.index, year=YEAR)
    assert b.status == "invalid_input" and b.issues[0]["field"] == "fallback"


# ------------------------------------------------------------------ review fixes (phase-9-B)


def test_crop_only_change_with_identical_dates_still_diverges(ctx, rye):
    clover = edited(rye, crop_id="crimson_clover").model_copy(
        update={"plan_id": "clover_same_dates"}
    )
    b = build_backup_plan(rye, clover, ctx.index, year=YEAR)
    assert b.divergence is not None and b.divergence.action_id in ("seed", "terminate")
    assert "cereal_rye" in b.divergence.what and "crimson_clover" in b.divergence.what
    assert b.decision_deadline == b.divergence.first_date - __import__("datetime").timedelta(days=1)
    assert not any("nothing to switch" in n for n in b.notes)


def test_later_termination_is_not_called_a_dry_weather_switch(ctx, rye):
    later = edited(rye, terminate="05-05").model_copy(update={"plan_id": "later"})
    sc = build_backup_plan(rye, later, ctx.index, year=YEAR).switch_condition
    assert sc.kind == "grower_decision" and "does not end the cover earlier" in sc.text


def test_an_earlier_termination_that_still_fires_the_check_is_not_a_dry_switch(ctx, rye):
    a_bit_earlier = edited(
        rye, terminate="04-29"
    )  # 13-day gap, still < 14.model_copy(update={"plan_id": "bit_earlier"})
    sc = build_backup_plan(rye, a_bit_earlier, ctx.index, year=YEAR).switch_condition
    assert sc.kind == "grower_decision" and "still triggers the same moisture check" in sc.text


def test_edited_alternative_with_the_same_plan_id_keeps_its_own_results(ctx, rye):
    same_id = edited(rye, terminate="04-14")  # plan_id identical to the default's
    b = compare_fixed_plans(
        build_backup_plan(rye, same_id, ctx.index, year=YEAR), rye, same_id, ctx
    )
    c = b.comparison
    assert (
        c["default"]["termination_gap_days"] == 12 and c["fallback"]["termination_gap_days"] == 28
    )
    assert c["fallback_minus_default"]["termination_gap_days"] == 16
    counts = c["fallback_minus_default"]["spring_check_counts"]["rye_soy_short_gap_moisture"]
    assert counts["default"] > 0 and counts["fallback"] == 0


def test_denominators_are_reported_separately_when_coverage_differs(ctx, rye):
    july = edited(rye, terminate="06-28").model_copy(
        update={"next_plant": "07-05", "plan_id": "july"}
    )
    b = compare_fixed_plans(build_backup_plan(rye, july, ctx.index, year=YEAR), rye, july, ctx)
    c = b.comparison["fallback_minus_default"]["spring_check_counts"]["rye_soy_short_gap_moisture"]
    assert (c["default_denominator"], c["fallback_denominator"]) == (45, 44)
    assert c["same_denominator"] is False


def test_calendar_summaries_use_the_requested_year_not_2025(ctx, rye):
    a = edited(rye, terminate="03-01", seed="10-01").model_copy(
        update={"next_plant": "03-20", "plan_id": "a"}
    )
    c = edited(a, terminate="02-27").model_copy(update={"plan_id": "c"})
    b = compare_fixed_plans(build_backup_plan(a, c, ctx.index, year=2028), a, c, ctx)
    # 2028 is a leap year: Feb 29 is inside the window, so the 3-day difference is real
    assert (
        b.comparison["default"]["living_cover_days_planned"]
        - b.comparison["fallback"]["living_cover_days_planned"]
        == 3
    )
    assert b.comparison["fallback_minus_default"]["living_cover_days_planned"] == -3
    assert b.comparison["fallback_minus_default"]["termination_gap_days"] == 3


# ------------------------------------------------------------------ review fixes (phase-9-B r2)


def test_pest_gated_rule_gets_a_pest_switch_condition_not_a_dry_one(ctx, rye):
    from fieldshift.contracts import GrowerInputs

    worried = edited(rye, terminate="04-23").model_copy(  # a 19-day gap: outside 21-28
        update={"grower": GrowerInputs(observations=["pest_spillover_concern"]), "plan_id": "pest"}
    )
    cal = build_action_calendar(worried, ctx.index, year=YEAR)
    check = by_id(cal)["check:cr_tt_04"]
    assert check.flagged and "insect-pest" in check.trigger and "dry" not in check.trigger
    b = build_backup_plan(worried, None, ctx.index, year=YEAR, as_of=date(2027, 4, 1))
    sc = b.switch_condition
    assert sc.kind == "pest_spillover_concern" and sc.rule_ids == ["cr_tt_04"]
    assert "pest" in sc.text and "dry" not in sc.text.lower() and "moisture" not in sc.text.lower()
    assert sc.inputs_needed == ["a grower-reported pest-spillover concern"]


def test_dry_gate_trigger_text_is_specific_to_the_moisture_rule(ctx, rye):
    c = by_id(build_action_calendar(rye, ctx.index, year=YEAR))["check:cr_tt_03"]
    assert "low-moisture concern" in c.trigger and "pest" not in c.trigger


def test_suggested_fallback_never_returns_a_plan_that_breaks_in_a_historical_year(ctx, rye):
    from fieldshift.compare.engine import YEARS
    from fieldshift.planner.calendar import plan_year_issues

    # a fallback gap of 14 days before Mar 14 lands on Feb 29 in 2028 only
    tricky = edited(rye, seed="02-28", terminate="03-01").model_copy(
        update={"prev_harvest": "10-01", "next_plant": "03-14", "plan_id": "tricky"}
    )
    fb = suggest_fallback(tricky, ctx.index, year=2028)
    assert fb is None or plan_year_issues(fb, [2028, *YEARS]) == []
    b = build_backup_plan(tricky, None, ctx.index, year=2028)
    assert b.status in ("complete", "unsupported")
