import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from fieldshift.api.app import create_app
from fieldshift.api.samples import load_samples
from fieldshift.compare.context import get_context
from fieldshift.planner.backup import build_backup_plan, compare_fixed_plans
from fieldshift.planner.calendar import add_scenarios, build_action_calendar
from fieldshift.planner.wheat_path import demo_plan, plan_from_dates
from fieldshift.report.audit import bare_numbers, verify
from fieldshift.report.field_note import build_field_note
from fieldshift.report.models import FieldNote

YEAR = 2027


@pytest.fixture(scope="module")
def ctx():
    return get_context()


@pytest.fixture(scope="module")
def full():
    return load_samples().plans["corn_soy__no_cover"].plan


def wheat_note(ctx, **kw):
    kw.setdefault("year", YEAR)
    return build_field_note(demo_plan(), ctx, dates_assumed=True, **kw)


def by_id(items, key="rule_id"):
    return {i[key]: i for i in items}


def test_wheat_note_has_the_grower_dates_with_the_basis_label(ctx):
    n = wheat_note(ctx, maturity_group=5)
    assert n["status"] == "partial" and n["path"] == "winter_wheat_double_crop"
    p = n["plan"]
    assert p["dates_basis"] == "assumed" and p["planting_year"] == "2027"
    d = p["dates"]
    assert (d["wheat_plant"], d["wheat_harvest"], d["soybean_plant"]) == (
        "2026-10-25",
        "2027-06-05",
        "2027-06-12",
    )
    assert d["harvest_to_plant_days"]["value"] == 7 and d["wheat_season_days"]["value"] == 223
    assert p["catalog_state"]["status"] == "partial"
    grower = build_field_note(demo_plan(), ctx, year=YEAR, maturity_group=5)
    assert grower["plan"]["dates_basis"] == "grower"
    w = n["soybean_planting_window"]
    assert w["moved_to_after_wheat_harvest"] and w["earliest_planting_date"] == "2027-06-05"
    assert w["days_after_wheat_harvest"]["value"] == 7


def test_every_number_in_the_wheat_note_is_audited(ctx, full):
    alt = load_samples().plans["corn_soy__rye"].plan
    n = wheat_note(ctx, maturity_group=3, compare_to_plan=full, alternative=alt, as_of=None)
    assert verify(n) == [] and n["audit"]["unclassified"] == 0
    body = {k: v for k, v in n.items() if k != "audit"}
    assert list(bare_numbers(body)) == []
    assert {"nasa", "calculation", "grower", "extension"} <= set(n["audit"]["derivations"])
    mg = n["maturity_group"]["input"]
    assert n["audit"]["entries"][mg["audit_id"]]["derivation"] == "grower" and mg["value"] == 3


def test_maturity_group_checks_are_in_the_note(ctx):
    n = wheat_note(ctx, maturity_group=3)
    mg = n["maturity_group"]
    assert mg["status"] == "complete" and mg["input"]["value"] == 3
    c = by_id(mg["checks"])
    assert c["sb_rc_03"]["flagged"] and c["sb_rc_03"]["verdict"] == "caution"
    assert c["sb_v2_mg_mid_june"]["flagged"] and c["sb_v2_mg_mid_july"]["status"] == "manual_check"
    assert "sb_v2_mg_mid_june" in mg["planting_context"]["rows_in_context"]
    ok = wheat_note(ctx, maturity_group=5)["maturity_group"]["checks"]
    assert not by_id(ok)["sb_rc_03"]["flagged"]


def test_missing_maturity_group_is_null_and_unknown_not_zero(ctx):
    n = wheat_note(ctx)
    mg = n["maturity_group"]
    assert mg["input"] is None and mg["status"] == "unknown" and mg["missing"] == ["maturity_group"]
    assert by_id(mg["checks"])["sb_rc_03"]["status"] == "unknown"
    assert "sb_rc_03" in by_id(n["unresolved_checks"])
    zero = wheat_note(ctx, maturity_group=0)["maturity_group"]
    assert zero["input"]["value"] == 0 and zero["status"] == "complete"  # a real zero


def test_unresolved_checks_list_the_manual_rows_with_sources(ctx):
    n = wheat_note(ctx, maturity_group=5)
    items = by_id(n["unresolved_checks"])
    for rid in ("ww_v2_pw_local_map", "ww_v2_gd_harvest_context", "sb_v2_pw_after_wheat_context",
                "sb_v2_seed_late", "sb_v2_spacing_late", "sb_v2_pw_delay_yield"):  # fmt: skip
        assert items[rid]["status"] == "manual_check" and items[rid]["source"]["url"], rid
    assert items["ww_rc_01"]["flagged"]  # wheat after corn
    ref = items["sb_v2_seed_late"]["reference"]
    assert ref["value_min"]["value"] == 165000 and ref["is_grower_target"] is False
    assert any(
        i["rule_id"] == "winter_grain_double_crop" and i["status"] == "partial"
        for i in n["unresolved_checks"]
    )


def test_organic_grain_rows_are_marked_inapplicable_for_conventional_plans(ctx):
    n = wheat_note(ctx, maturity_group=5)
    gone = by_id(n["inapplicable_checks"])
    assert set(gone) == {"ww_v2_pw_freeze_reference", "ww_v2_pw_hessian_fly", "ww_v2_seed_drilled"}
    assert all(
        g["status"] == "inapplicable" and "conventional" in g["reason"] for g in gone.values()
    )
    assert not set(gone) & set(by_id(n["unresolved_checks"]))
    organic = demo_plan().model_copy(update={"production_system": "organic"})
    o = build_field_note(organic, ctx, year=YEAR, maturity_group=5)
    assert o["inapplicable_checks"] == [] and "ww_v2_pw_hessian_fly" in by_id(
        o["unresolved_checks"]
    )


def test_spring_numbers_come_from_the_plans_own_window(ctx):
    n = wheat_note(ctx, maturity_group=5)
    s = n["spring"]
    assert s["baseline"] == "own_window_baseline" and s["window"]["plant_md"] == "06-12"
    assert "own 30-day window before 06-12" in s["baseline_note"]
    cutoff = n["audit"]["entries"][s["dry_cutoff_mm"]["audit_id"]]
    assert (
        cutoff["derivation"] == "calculation"
        and cutoff["source_ref"]["ref"] == "spring_dry_mm@06-12"
    )
    assert (
        s["dry_cutoff_mm"]["value"]
        != build_field_note(load_samples().plans["corn_soy__rye"].plan, ctx, year=YEAR)["spring"][
            "dry_cutoff_mm"
        ]["value"]
    )
    assert all(isinstance(y, str) for y in s["dry_years"])
    assert n["eras"]["dry_spring"]["threshold_set_id"] and n["thresholds"]


def test_cross_calendar_comparison_is_labeled_with_raw_totals_only(ctx, full):
    n = wheat_note(ctx, maturity_group=5, compare_to_plan=full)
    cc = n["cross_calendar"]
    assert cc["label"] == "different-calendar" and "NOT comparable" in cc["note"]
    for side in ("full_season", "double_crop"):
        assert not {"rank", "percentile", "dry_seasons", "dry_years", "era_dry_spring"} & set(
            cc[side]
        )
        assert cc[side]["median_total_mm"]["value"] > 0
        assert cc[side]["baseline"] == "own_window_baseline"
    diff = cc["median_total_mm_difference"]["value"]
    assert diff == pytest.approx(
        cc["double_crop"]["median_total_mm"]["value"]
        - cc["full_season"]["median_total_mm"]["value"],
        abs=1e-3,
    )
    assert "cross_calendar" not in wheat_note(ctx, maturity_group=5)
    assert any("different-calendar" in x for x in n["limits"])


def test_alternative_to_a_wheat_plan_is_compared_as_different_calendar(ctx):
    rye = load_samples().plans["corn_soy__rye"].plan
    n = wheat_note(ctx, maturity_group=5, alternative=rye, as_of=None)
    (a,) = n["alternatives"]
    assert a["comparison_label"] == "different-calendar" and a["kind"] == "fixed_alternative"
    assert a["raw_totals"]["default"]["plan_id"] == "corn_soy__wheat_dc"
    assert a["raw_totals"]["alternative"]["plan_id"] == "corn_soy__rye"
    assert a["raw_totals"]["median_total_mm_difference"]["value"] != 0
    assert "NOT comparable" in a["raw_totals"]["note"]
    assert verify(n) == []


def test_a_non_wheat_note_can_have_a_wheat_alternative(ctx):
    rye = load_samples().plans["corn_soy__rye"].plan
    n = build_field_note(rye, ctx, alternative=demo_plan(), year=YEAR)
    (a,) = n["alternatives"]
    assert (
        a["comparison_label"] == "different-calendar"
        and a["plan"]["winter"]["kind"] == "winter_grain"
    )
    assert a["raw_totals"]["default"]["plan_id"] == "corn_soy__rye"
    assert verify(n) == []


def test_catalog_v1_gives_an_unavailable_note_with_no_numbers(index_v1_ctx):
    n = build_field_note(demo_plan(), index_v1_ctx, year=YEAR, maturity_group=5)
    assert n["status"] == "unavailable" and n["reason"] == "catalog_missing"
    assert list(bare_numbers({k: v for k, v in n.items() if k != "audit"})) == []
    assert n["audit"]["count"] == 0 and n["unresolved_checks"] == [] and n["adviser_note"]["fields"]


def test_invalid_wheat_plan_gives_a_status_note_without_numbers(ctx):
    bad = plan_from_dates(
        prev_harvest="09-20", wheat_plant="10-25", wheat_harvest="06-20", soybean_plant="06-10"
    )
    n = build_field_note(bad, ctx, year=YEAR)
    assert n["status"] == "invalid_input" and n["issues"] and n["audit"]["count"] == 0


# ------------------------------------------------------------------ calendar and backup


def test_calendar_for_a_wheat_plan_has_dated_actions_and_scenarios(ctx):
    cal = add_scenarios(
        build_action_calendar(demo_plan(), ctx.index, year=YEAR, inputs={"maturity_group": 3}),
        demo_plan(),
        ctx,
    )
    assert cal.status == "complete"
    acts = {a.action_id: a for a in cal.actions}
    assert (
        str(acts["seed"].date) == "2026-10-25" and acts["terminate"].label == "Harvest winter_wheat"
    )
    assert str(acts["plant"].date) == "2027-06-12"
    assert acts["check:sb_rc_03"].flagged and acts["check:sb_v2_mg_mid_june"].flagged
    assert acts["check:ww_v2_pw_local_map"].status == "manual_check"
    assert cal.scenarios["status"] == "complete" and {"typical", "dry", "wet"} <= set(cal.scenarios)
    assert cal.scenarios["dry"]["winter"]["rain_outside_cover_mm"] is None  # not computed for wheat


def test_backup_for_a_wheat_plan_compares_as_different_calendar(ctx):
    rye = load_samples().plans["corn_soy__rye"].plan
    b = build_backup_plan(demo_plan(), rye, ctx.index, year=YEAR, as_of=None)
    b = compare_fixed_plans(b, demo_plan(), rye, ctx)
    assert b.status == "complete" and b.comparison["label"] == "different-calendar"
    assert b.comparison["basis"] == "different_calendar"
    assert "rank" not in json.dumps(b.comparison["default"])
    assert b.comparison["fallback_minus_default"]["median_total_mm"] is not None


# ------------------------------------------------------------------ typed responses through the real app


@pytest.fixture(scope="module")
def app_client():
    return TestClient(create_app())


@pytest.fixture(scope="module")
def index_v1_ctx(ctx):
    from fieldshift.catalogs import V1_CATALOG_DIR, CatalogIndex, load_catalog

    return SimpleNamespace(
        index=CatalogIndex(load_catalog(V1_CATALOG_DIR)),
        manifest=ctx.manifest,
        snapshot_hash=ctx.snapshot_hash,
    )


def test_production_app_serves_the_wheat_note_and_it_validates_against_the_model(app_client):
    plan = demo_plan().model_dump(mode="json")
    r = app_client.post(
        "/v1/plans/note",
        json={
            "plan": plan,
            "year": YEAR,
            "maturity_group": 5,
            "compare_to_plan_id": "corn_soy__no_cover",
        },
    )
    assert r.status_code == 200, r.text
    note = FieldNote.model_validate(r.json())
    assert (
        note.path == "winter_wheat_double_crop"
        and note.cross_calendar.label == "different-calendar"
    )
    assert note.maturity_group.input.value == 5
    assert verify(r.json()) == []


def test_wheat_inputs_on_a_non_wheat_plan_and_bad_maturity_group_are_400(app_client):
    r = app_client.post(
        "/v1/plans/note", json={"plan_id": "corn_soy__rye", "year": YEAR, "maturity_group": 5}
    )
    assert r.status_code == 400 and r.json()["issues"][0]["code"] == "wheat_only_input"
    plan = demo_plan().model_dump(mode="json")
    bad = app_client.post("/v1/plans/note", json={"plan": plan, "year": YEAR, "maturity_group": 99})
    assert bad.status_code == 400 and bad.json()["issues"][0]["field"] == "maturity_group"
    conflict = app_client.post(
        "/v1/plans/note",
        json={
            "plan": plan,
            "year": YEAR,
            "maturity_group": 5,
            "compare_to_plan_id": "soy_corn__no_cover",
        },
    )
    assert (
        conflict.status_code == 400 and conflict.json()["issues"][0]["field"] == "compare_to_plan"
    )


def test_wheat_sample_plan_works_in_note_calendar_and_backup_routes(app_client):
    plan_id = "corn_soy__wheat_dc"
    if load_samples().plans[plan_id].plan is None:
        pytest.skip("Agent A's sample wheat plan is not filled in yet")
    note = app_client.get(f"/v1/plans/{plan_id}/note", params={"year": YEAR})
    assert note.status_code == 200 and note.json()["path"] == "winter_wheat_double_crop"
    assert note.json()["plan"]["dates_basis"] == "assumed"
    cal = app_client.post("/v1/plans/calendar", json={"plan_id": plan_id, "year": YEAR})
    assert cal.status_code == 200 and cal.json()["calendar"]["status"] == "complete"
    bk = app_client.post("/v1/plans/backup", json={"plan_id": plan_id, "year": YEAR})
    assert (
        bk.status_code == 200 and bk.json()["backup"]["comparison"]["label"] == "different-calendar"
    )


def test_every_main_variant_validates_against_the_typed_models(app_client):
    for body in (
        {"plan_id": "corn_soy__rye", "year": YEAR, "alternative_id": "corn_soy__no_cover"},
        {"plan_id": "soy_corn__no_cover", "year": YEAR},
        {"plan_id": "corn_soy__clover", "year": YEAR},
    ):
        r = app_client.post("/v1/plans/note", json=body)
        assert r.status_code == 200, (body, r.text)
        FieldNote.model_validate(r.json())
    unsupported = demo_plan().model_dump(mode="json")
    unsupported["previous_crop_id"] = "quinoa"
    r = app_client.post("/v1/plans/note", json={"plan": unsupported, "year": YEAR})
    assert r.status_code == 200 and r.json()["status"] == "unsupported"
    FieldNote.model_validate(r.json())


def test_openapi_has_field_level_schemas_for_calendar_backup_and_note(app_client):
    spec = app_client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    for name in ("FieldNote", "CalendarResponse", "BackupResponse", "AuditedNumber", "AuditBlock",
                 "ActionOut", "EraBlockOut", "UnresolvedOut", "MaturityGroupOut"):  # fmt: skip
        assert name in schemas, name
    assert set(schemas["AuditedNumber"]["properties"]) == {"value", "unit", "audit_id"}
    note_ref = spec["paths"]["/v1/plans/note"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert note_ref["$ref"].endswith("/FieldNote")
    assert (
        "calendar" in schemas["CalendarResponse"]["properties"]
        and "backup" in schemas["BackupResponse"]["properties"]
    )
    assert (
        "spring" in schemas["FieldNote"]["properties"]
        and "audit" in schemas["FieldNote"]["properties"]
    )


# ------------------------------------------------------------------ review fixes (phase-9-B r3)


def test_wheat_only_inputs_are_rejected_for_non_wheat_plans_on_every_route(app_client):
    for path, body in (
        (
            "/v1/plans/note",
            {"plan_id": "corn_soy__rye", "year": YEAR, "inputs": {"maturity_group": 5}},
        ),
        ("/v1/plans/note", {"plan_id": "corn_soy__rye", "year": YEAR, "maturity_group": 5}),
        (
            "/v1/plans/calendar",
            {"plan_id": "corn_soy__rye", "year": YEAR, "inputs": {"maturity_group": 5}},
        ),
        (
            "/v1/plans/backup",
            {"plan_id": "corn_soy__rye", "year": YEAR, "inputs": {"maturity_group": 5}},
        ),
    ):
        r = app_client.post(path, json=body)
        assert r.status_code == 400, (path, body)
        i = r.json()["issues"][0]
        assert i["code"] == "wheat_only_input" and i["field"].endswith("maturity_group")
    blank = app_client.post(
        "/v1/plans/calendar",
        json={"plan_id": "corn_soy__rye", "year": YEAR, "inputs": {"maturity_group": ""}},
    )
    assert blank.status_code == 200  # a blank is "not entered"
    r = app_client.post(
        "/v1/plans/note",
        json={"plan_id": "corn_soy__rye", "year": YEAR, "compare_to_plan_id": "corn_soy__no_cover"},
    )
    assert r.status_code == 400 and r.json()["issues"][0]["field"] == "compare_to_plan"


def test_wheat_maturity_group_is_validated_on_calendar_and_backup(app_client):
    wheat = demo_plan().model_dump(mode="json")
    for path in ("/v1/plans/calendar", "/v1/plans/backup", "/v1/plans/note"):
        bad = app_client.post(
            path, json={"plan": wheat, "year": YEAR, "inputs": {"maturity_group": 99}}
        )
        assert (
            bad.status_code == 400 and bad.json()["issues"][0]["field"] == "inputs.maturity_group"
        ), path
    ok = app_client.post(
        "/v1/plans/calendar", json={"plan": wheat, "year": YEAR, "inputs": {"maturity_group": "3"}}
    )
    assert ok.status_code == 200
    flagged = {a["action_id"] for a in ok.json()["calendar"]["actions"] if a["flagged"]}
    assert {
        "check:sb_rc_03",
        "check:sb_v2_mg_mid_june",
    } <= flagged  # the grower's MG reached the checks
    backup = app_client.post(
        "/v1/plans/backup", json={"plan": wheat, "year": YEAR, "inputs": {"maturity_group": 5}}
    )
    assert backup.status_code == 200 and backup.json()["backup"]["status"] == "complete"


def test_a_wheat_plan_section_has_null_cover_metrics_and_a_wheat_season(ctx):
    rye = load_samples().plans["corn_soy__rye"].plan
    n = build_field_note(rye, ctx, alternative=demo_plan(), year=YEAR)
    cal = n["alternatives"][0]["plan"]["calendar"]
    assert cal["living_cover_days_planned"] is None and cal["days_without_planned_cover"] is None
    assert cal["termination_gap_days"] is None and cal["establishment"] == "inapplicable"
    assert cal["wheat_season_days"]["value"] == 223 and cal["winter_days"]["value"] == 265
    assert verify(n) == []


def test_comparisons_carry_raw_totals_only_no_dry_cutoffs(ctx, full):
    def keys(x):
        out = set()
        if isinstance(x, dict):
            for k, v in x.items():
                out.add(k)
                out |= keys(v)
        elif isinstance(x, list):
            for v in x:
                out |= keys(v)
        return out

    n = wheat_note(
        ctx,
        maturity_group=5,
        compare_to_plan=full,
        alternative=load_samples().plans["corn_soy__rye"].plan,
        as_of=None,
    )
    for part in (n["cross_calendar"], n["alternatives"][0]["raw_totals"]):
        assert not [k for k in keys(part) if "cutoff" in k or "percentile" in k or k == "rank"], (
            part.keys()
        )
    assert "dry_cutoff_mm" in n["spring"]  # cutoffs stay in the plan's own spring section
    rye = load_samples().plans["corn_soy__rye"].plan
    b = compare_fixed_plans(
        build_backup_plan(demo_plan(), rye, ctx.index, year=YEAR), demo_plan(), rye, ctx
    )
    assert not [k for k in keys(b.comparison) if "cutoff" in k or k == "threshold_name"]


def test_calendar_and_backup_schemas_are_field_level(app_client):
    schemas = app_client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("ActionCalendarOut", "RawScenarios", "RawScenario", "RawSpring", "DecisionOut",
                 "BackupPlanOut", "BackupComparison", "PlanBrief", "CrossBrief", "FallbackDiff"):  # fmt: skip
        assert name in schemas, name
    assert "typical" in schemas["RawScenarios"]["properties"]
    assert {"basis", "default", "fallback", "fallback_minus_default", "note"} <= set(
        schemas["BackupComparison"]["properties"]
    )
    assert schemas["BackupComparison"]["properties"]["basis"]["enum"] == [
        "fixed_plans",
        "different_calendar",
    ]


def test_backup_and_calendar_responses_validate_for_every_variant(app_client):
    from fieldshift.report.models import BackupResponse, CalendarResponse

    wheat = demo_plan().model_dump(mode="json")
    for body in ({"plan_id": "corn_soy__rye", "year": YEAR}, {"plan": wheat, "year": YEAR},
                 {"plan_id": "corn_soy__rye", "year": YEAR, "fallback": wheat}):  # fmt: skip
        b = app_client.post("/v1/plans/backup", json=body)
        assert b.status_code == 200, (body, b.text)
        BackupResponse.model_validate(b.json())
        c = app_client.post(
            "/v1/plans/calendar", json={k: v for k, v in body.items() if k != "fallback"}
        )
        assert c.status_code == 200
        CalendarResponse.model_validate(c.json())
