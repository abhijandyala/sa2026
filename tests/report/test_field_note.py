import json
from datetime import date

from fieldshift.report.audit import audited_numbers, bare_numbers, verify
from fieldshift.report.field_note import ADVISER_FIELDS, build_field_note

from .conftest import YEAR, edited

AS_OF = date(2027, 4, 1)


def walk_all(note):
    """Every number in the note body, with its audit entry."""
    body = {k: v for k, v in note.items() if k != "audit"}
    return [(p, n, note["audit"]["entries"][n["audit_id"]]) for p, n in audited_numbers(body)]


def test_every_number_in_the_note_resolves_to_an_audit_entry(ctx, rye):
    alt = edited(rye, terminate="04-14").model_copy(update={"plan_id": "alt"})
    note = build_field_note(rye, ctx, alternative=alt, year=YEAR, as_of=AS_OF, dates_assumed=True)
    assert verify(note) == []
    body = {k: v for k, v in note.items() if k != "audit"}
    assert list(bare_numbers(body)) == []  # no number is shown without its audit id
    found = walk_all(note)
    assert len(found) > 80
    assert note["audit"]["unclassified"] == 0
    for path, n, e in found:
        assert e["value"] == n["value"] and e["unit"] == n["unit"], path
        assert e["derivation"] in {"nasa", "usda", "extension", "grower", "calculation", "assumed"}
        assert e["source_ref"]["kind"] and isinstance(e["inputs"], dict)
    assert {"nasa", "calculation", "extension"} <= set(note["audit"]["derivations"])


def test_audit_entries_say_where_the_numbers_came_from(ctx, rye):
    note = build_field_note(rye, ctx, year=YEAR, as_of=AS_OF)
    by_path = {p: e for p, _n, e in walk_all(note)}
    total = by_path["calendar.scenarios.dry.spring.total_mm"]
    assert total["derivation"] == "nasa" and total["source_ref"]["kind"] == "weather_snapshot"
    assert total["source_ref"]["ref"] == ctx.snapshot_hash and total["unit"] == "mm"
    cutoff = by_path["spring.dry_cutoff_mm"]
    assert cutoff["derivation"] == "calculation" and cutoff["source_ref"]["kind"] == "threshold"
    gap = by_path["plan.calendar.termination_gap_days"]
    assert gap["value"] == 12 and gap["source_ref"]["kind"] == "plan_input"
    ref = next(
        e
        for p, _n, e in walk_all(note)
        if p.endswith("reference.value_min") and e["derivation"] == "extension"
    )
    assert ref["source_ref"]["kind"] == "catalog_rule" and ref["source_ref"]["url"]


def test_n_reference_in_the_note_is_sourced_and_not_a_target():
    # the corn leg: fc_nut_01 appears as a reference with both ends audited as "extension"
    from fieldshift.api.samples import load_samples
    from fieldshift.compare.context import get_context

    ctx = get_context()
    p = load_samples().plans["soy_corn__no_cover"].plan
    note = build_field_note(p, ctx, year=YEAR, as_of=AS_OF, dates_assumed=True)
    ev = next(
        e
        for a in note["calendar"]["actions"]
        if a["action_id"] == "check:fc_nut_01"
        for e in a["evidence"]
    )
    ref = ev["reference"]
    assert ref["is_grower_target"] is False and "not the grower's target" in ref["label"]
    assert ref["value_min"]["value"] == 120.0 and ref["value_max"]["value"] == 160.0
    assert verify(note) == []


def test_note_sections_and_blank_adviser_fields(ctx, rye):
    note = build_field_note(rye, ctx, year=YEAR, as_of=AS_OF, dates_assumed=True)
    assert note["status"] == "complete" and note["note_version"] == "1"
    for key in ("plan", "winter", "spring", "spring_checks", "eras", "calendar", "unresolved_checks",
                "alternatives", "sources", "adviser_note", "limits", "audit"):  # fmt: skip
        assert key in note, key
    assert set(note["meta"]) == {"plan_version", "catalog_version", "snapshot_hash", "request_id"}
    assert note["plan"]["dates_basis"] == "assumed" and note["plan"]["planting_year"] == "2027"
    fields = note["adviser_note"]["fields"]
    assert [f["field_id"] for f in fields] == [f for f, _ in ADVISER_FIELDS]
    assert all(f["value"] is None for f in fields)
    assert any("assumed" in x for x in note["limits"])
    assert any("not a trend" in x for x in note["limits"])
    assert note["alternatives"] == []


def test_sources_are_deduplicated_with_urls_and_include_the_weather_snapshot(ctx, rye):
    note = build_field_note(rye, ctx, year=YEAR, as_of=AS_OF)
    urls = [(s["url"], s["locator"]) for s in note["sources"]]
    assert len(urls) == len(set(urls))
    assert any("rotational-considerations" in (u or "") for u, _ in urls)  # cr_tt_03's source
    assert any(
        "NASA POWER" in s["title"] and s["snapshot_hash"] == ctx.snapshot_hash
        for s in note["sources"]
    )


def test_years_and_ids_are_strings_and_missing_values_are_null(ctx, rye):
    note = build_field_note(rye, ctx, year=YEAR, as_of=AS_OF)
    assert all(isinstance(y, str) for y in note["spring"]["dry_years"])
    assert all(isinstance(y, str) for c in note["spring_checks"] for y in c["qualifying_years"])
    for era in note["eras"].values():
        assert isinstance(era["earlier"]["start"], str) and isinstance(
            era["excluded_from_eras"][0], str
        )
    # a gap-free plan has no termination gap: null, not 0
    none = rye.model_copy(
        update={
            "winter": rye.winter.model_copy(
                update={"kind": "none", "crop_id": None, "seed": None, "terminate": None}
            )
        }
    )
    n2 = build_field_note(none, ctx, year=YEAR, as_of=AS_OF)
    assert n2["plan"]["calendar"]["termination_gap_days"] is None
    assert n2["plan"]["calendar"]["living_cover_days_planned"]["value"] == 0  # a real zero
    assert verify(n2) == []


def test_eras_carry_the_descriptive_caveat_and_frozen_thresholds(ctx, rye):
    note = build_field_note(rye, ctx, year=YEAR, as_of=AS_OF)
    e = note["eras"]["dry_spring"]
    assert "not a trend" in e["caveat"] or "forecast" in e["caveat"]
    assert (
        e["earlier"]["evaluable"]["value"] + len(e["earlier"]["not_evaluable"])
        == e["earlier"]["seasons"]["value"]
    )
    assert e["thresholds"] and e["threshold_set_id"]
    ids = {x["threshold_set_id"] for x in note["eras"].values()}
    assert len(ids) == 1  # one frozen ThresholdSet for every indicator


def test_unresolved_checks_list_what_a_person_must_do_with_sources(ctx, rye):
    note = build_field_note(rye, ctx, year=YEAR, as_of=AS_OF)
    items = {i["rule_id"]: i for i in note["unresolved_checks"]}
    assert items["cr_tt_03"]["status"] == "unknown" and items["cr_tt_03"]["due"] == "2027-04-30"
    assert items["cr_tt_03"]["source"]["url"]
    assert all(i["status"] in ("manual_check", "unknown") or i["flagged"] for i in items.values())


def test_note_with_one_fixed_alternative(ctx, rye):
    alt = edited(rye, terminate="04-14").model_copy(
        update={"plan_id": "alt_early_kill", "label": "Rye ended 28 days out"}
    )
    note = build_field_note(rye, ctx, alternative=alt, year=YEAR, as_of=AS_OF, dates_assumed=True)
    (a,) = note["alternatives"]
    assert a["kind"] == "fixed_alternative" and a["plan"]["plan_id"] == "alt_early_kill"
    assert a["plan"]["calendar"]["termination_gap_days"]["value"] == 28
    assert a["difference_vs_default"]["termination_gap_days"]["value"] == 16
    assert a["difference_vs_default"]["living_cover_days_planned"]["value"] == -16
    counts = a["difference_vs_default"]["spring_check_counts"]["rye_soy_short_gap_moisture"]
    assert counts["default"]["value"] > 0 and counts["alternative"]["value"] == 0
    assert a["decision_deadline"] == "2027-04-13" and a["timing"] == "upcoming"
    assert a["switch_condition"]["kind"] == "dry_or_moisture_concern"
    assert a["backtest"]["status"] == "unavailable"
    assert "not a forecast" in a["difference_vs_default"]["note"]
    assert any("fixed plan" in x for x in note["limits"])
    assert verify(note) == []


def test_note_for_a_changed_planting_calendar(ctx, rye):
    moved = rye.model_copy(update={"next_plant": "05-19", "plan_id": "moved"})
    a = build_field_note(rye, ctx, year=YEAR, as_of=AS_OF)
    b = build_field_note(moved, ctx, year=YEAR, as_of=AS_OF)
    assert verify(b) == []
    assert b["plan"]["calendar"]["termination_gap_days"]["value"] == 19
    assert b["plan"]["next_plant"] == "05-19"
    pa = {x["action_id"]: x for x in a["calendar"]["actions"]}
    pb = {x["action_id"]: x for x in b["calendar"]["actions"]}
    assert pa["plant"]["date"] == "2027-05-12" and pb["plant"]["date"] == "2027-05-19"
    assert (
        pb["spring_window"]["date"] == "2027-04-19"
        and pb["spring_window"]["end_date"] == "2027-05-18"
    )
    # a 19-day gap clears the 14-day moisture check, so it no longer needs a person
    assert "check:cr_tt_03" in pa and "check:cr_tt_03" not in pb
    # the dry cutoff is for the NEW window (a different frozen threshold)
    assert a["spring"]["dry_cutoff_mm"]["value"] != b["spring"]["dry_cutoff_mm"]["value"]


def test_unsupported_plan_gives_a_status_note_without_numbers(ctx, rye):
    q = rye.model_copy(update={"next_crop_id": "quinoa"})
    note = build_field_note(q, ctx, year=YEAR)
    assert (
        note["status"] == "unsupported"
        and list(bare_numbers({k: v for k, v in note.items() if k != "audit"})) == []
    )
    assert note["adviser_note"]["fields"] and note["audit"]["count"] == 0


def test_note_is_deterministic_apart_from_the_request_id(ctx, rye):
    a = build_field_note(rye, ctx, year=YEAR, as_of=AS_OF)
    b = build_field_note(rye, ctx, year=YEAR, as_of=AS_OF)
    a["meta"].pop("request_id"), b["meta"].pop("request_id")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ------------------------------------------------------------------ review fixes (phase-9-B)


def test_alternative_with_the_same_plan_id_is_compared_correctly(ctx, rye):
    alt = edited(rye, terminate="04-14")  # same plan_id on purpose
    note = build_field_note(rye, ctx, alternative=alt, year=YEAR, as_of=AS_OF)
    (a,) = note["alternatives"]
    assert note["plan"]["calendar"]["termination_gap_days"]["value"] == 12
    assert a["plan"]["calendar"]["termination_gap_days"]["value"] == 28
    assert a["difference_vs_default"]["termination_gap_days"]["value"] == 16
    assert verify(note) == []


def test_alternative_difference_matches_the_displayed_calendars_in_a_leap_year(ctx, rye):
    a = edited(rye, terminate="03-01").model_copy(update={"next_plant": "03-20", "plan_id": "a"})
    b = edited(a, terminate="02-27").model_copy(update={"plan_id": "b"})
    note = build_field_note(a, ctx, alternative=b, year=2028, as_of=date(2028, 1, 1))
    shown = note["plan"]["calendar"]["living_cover_days_planned"]["value"]
    alt_shown = note["alternatives"][0]["plan"]["calendar"]["living_cover_days_planned"]["value"]
    diff = note["alternatives"][0]["difference_vs_default"]["living_cover_days_planned"]["value"]
    assert diff == alt_shown - shown == -3
    gap_diff = note["alternatives"][0]["difference_vs_default"]["termination_gap_days"]["value"]
    assert (
        gap_diff
        == note["alternatives"][0]["plan"]["calendar"]["termination_gap_days"]["value"]
        - note["plan"]["calendar"]["termination_gap_days"]["value"]
    )


def test_denominators_are_separate_audited_numbers(ctx, rye):
    july = edited(rye, terminate="06-28").model_copy(
        update={"next_plant": "07-05", "plan_id": "july"}
    )
    note = build_field_note(rye, ctx, alternative=july, year=YEAR, as_of=AS_OF)
    c = note["alternatives"][0]["difference_vs_default"]["spring_check_counts"][
        "rye_soy_short_gap_moisture"
    ]
    assert (c["default_denominator"]["value"], c["alternative_denominator"]["value"]) == (45, 44)
    assert c["same_denominator"] is False and verify(note) == []


def test_published_heavy_rain_threshold_is_an_extension_number_with_its_source(ctx, rye):
    note = build_field_note(rye, ctx, year=YEAR, as_of=AS_OF)
    published = [t for t in note["thresholds"] if t["published"]]
    assert published and published[0]["url"] and published[0]["locator"]
    by_path = {p: e for p, _n, e in walk_all(note)}
    heavy = by_path["eras.winter_heavy_rain_outside_cover.thresholds.heavy_rain_mm"]
    assert heavy["derivation"] == "extension" and heavy["source_ref"]["kind"] == "catalog_rule"
    assert heavy["source_ref"]["url"] == published[0]["url"]
    assert any(s["url"] == published[0]["url"] for s in note["sources"])
    # computed (not published) thresholds stay "calculation"
    cutoff = by_path["spring.dry_cutoff_mm"]
    assert cutoff["derivation"] == "calculation"
