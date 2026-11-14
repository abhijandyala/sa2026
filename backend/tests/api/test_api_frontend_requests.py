"""Frontend requests (web/docs/api-requests.md): sensitivity years, spring shortcuts for edited
dates, spring wetness per season, generated labels and reason text. Real Union County snapshot;
the network is blocked."""

import dataclasses
import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fieldshift.api.app import create_app
from fieldshift.catalogs import V1_CATALOG_DIR, CatalogIndex, load_catalog
from fieldshift.compare import engine, text
from fieldshift.compare.context import get_context
from fieldshift.compare.years import years_payload
from fieldshift.contracts import Plan
from fieldshift.planner.wheat_path import demo_plan

ROOT = Path(__file__).resolve().parents[2]
PLANS = ROOT / "data/samples/union_plans.json"


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("FIELDSHIFT_OFFLINE", "1")

    def refuse(*a, **k):
        raise AssertionError("network access attempted")

    mp.setattr(socket.socket, "connect", refuse)
    yield TestClient(create_app())
    mp.undo()


def sample(plan_id: str) -> dict:
    doc = json.loads(PLANS.read_text())
    return next(s["plan"] for s in doc["samples"] if s["plan_id"] == plan_id)


def compare(client, body):
    r = client.post("/v1/plans/compare", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def plan_of(body, plan_id):
    return next(p for p in body["plans"] if p["plan_id"] == plan_id)


# --- 2. sensitivity qualifying_years -----------------------------------------------------------


def test_every_sensitivity_point_lists_its_qualifying_years(client):
    r = client.post("/v1/plans/sensitivity", json={"plan_id": "corn_soy__rye"}).json()
    assert r["points"]
    for pt in r["points"]:
        assert len(pt["qualifying_years"]) == pt["checks_count"]
        assert pt["qualifying_years"] == sorted(set(pt["qualifying_years"]))
        if pt["checks_count"] == 0:
            assert pt["qualifying_years"] == []
    below = [p for p in r["points"] if p["gap_days"] < 14]
    at_or_above = [p for p in r["points"] if p["gap_days"] >= 14]
    assert below and at_or_above
    # the step: dry years below 14 days, none at or above (no grower concern)
    assert all(p["qualifying_years"] == r["dry_years"] for p in below)
    assert all(p["qualifying_years"] == [] for p in at_or_above)


def test_sensitivity_years_match_the_comparison_check_for_the_same_end_date(client):
    plan = sample("corn_soy__rye")  # terminates 04-30: a 12-day gap before 05-12
    cmp_check = plan_of(compare(client, {"plans": [plan]}), "corn_soy__rye")["spring_checks"][0]
    sens = client.post("/v1/plans/sensitivity", json={"plan": plan}).json()
    pt = next(p for p in sens["points"] if p["terminate"] == "04-30")
    assert pt["checks_count"] == cmp_check["count"] and pt["denominator"] == cmp_check["denominator"]
    assert pt["qualifying_years"] == cmp_check["qualifying_years"]


def test_a_grower_concern_changes_the_years_not_only_the_count(client):
    plan = sample("corn_soy__rye")
    plan["grower"]["low_moisture_concern"] = True
    sens = client.post("/v1/plans/sensitivity", json={"plan": plan}).json()
    short = [p for p in sens["points"] if p["gap_days"] < 14]
    assert short and all(len(p["qualifying_years"]) == p["checks_count"] > len(sens["dry_years"])
                         for p in short)


# --- 3. spring shortcuts follow the plan's own planting date ------------------------------------


def test_spring_shortcuts_equal_years_for_the_sample_plan(client):
    body = compare(client, {"plan_ids": ["corn_soy__rye", "soy_corn__rye"]})
    for pid in ("corn_soy__rye", "soy_corn__rye"):
        sc = plan_of(body, pid)["spring"]["shortcuts"]
        yrs = client.get(f"/v1/years?plan={pid}").json()["shortcuts"]
        assert {k: sc[k] for k in ("typical", "dry", "wet")} == yrs
        assert sc["basis"] == "own_window_baseline"


def test_spring_shortcuts_follow_an_edited_planting_date(client):
    edited = sample("corn_soy__rye")
    edited["plan_id"], edited["next_plant"], edited["winter"]["terminate"] = "edited", "05-28", "05-10"
    sc = plan_of(compare(client, {"plans": [edited]}), "edited")["spring"]["shortcuts"]
    expected = years_payload(Plan.model_validate(edited), get_context())["shortcuts"]
    assert {k: sc[k] for k in ("typical", "dry", "wet")} == expected
    base = client.get("/v1/years?plan=corn_soy__rye").json()["shortcuts"]
    assert expected != base  # a different window gives different years


def test_years_endpoint_is_unchanged(client):
    r = client.get("/v1/years?plan=corn_soy__rye").json()
    assert set(r) >= {"years", "shortcuts", "plan_basis", "eras", "location"}
    assert set(r["shortcuts"]) == {"typical", "dry", "wet"}
    assert len(r["years"]) == 45


# --- 4. spring wetness per season ---------------------------------------------------------------


@pytest.mark.parametrize("plan_id", ["corn_soy__rye", "soy_corn__no_cover", "corn_soy__wheat_dc"])
def test_season_rows_carry_the_replays_modeled_spring_wetness(client, plan_id):
    rows = {r["year"]: r for r in plan_of(compare(client, {"plan_ids": [plan_id]}), plan_id)["seasons"]}
    for year in (1981, 2008, 2025):
        rep = client.get(f"/v1/seasons/{year}/replay?plan={plan_id}").json()["wetness"]
        row = rows[year]
        assert row["gwetroot_window_mean"] == rep["gwetroot_window_mean"]
        assert row["gwettop_window_mean"] == rep["gwettop_window_mean"]
        assert row["wetness_status"] == rep["status"] and row["wetness_label"] == rep["label"] == "modeled"


def test_wetness_is_null_never_zero_when_missing_and_a_fraction_otherwise(client):
    rows = plan_of(compare(client, {"plan_ids": ["corn_soy__rye"]}), "corn_soy__rye")["seasons"]
    for r in rows:
        if r["wetness_status"] == "complete":
            assert 0 < r["gwetroot_window_mean"] < 1 and 0 < r["gwettop_window_mean"] < 1
        else:
            assert r["gwetroot_window_mean"] is None and r["gwettop_window_mean"] is None


# --- 5. generated labels -------------------------------------------------------------------------


def test_inline_plan_without_a_label_gets_a_generated_readable_label(client):
    p = sample("corn_soy__rye")
    p.update(plan_id="edited", label=None)
    res = plan_of(compare(client, {"plans": [p]}), "edited")
    assert res["label"] == "Field corn → Cereal rye cover → Soybean" and res["label_generated"] is True


@pytest.mark.parametrize(
    ("plan_id", "expected"),
    [("corn_soy__no_cover", "Field corn → No winter cover → Soybean"),
     ("corn_soy__wheat_dc", "Field corn → Winter wheat → Soybean")],
)
def test_generated_label_names_the_winter_kind(client, plan_id, expected):
    p = sample(plan_id)
    p.update(plan_id="x", label=None)
    res = plan_of(compare(client, {"plans": [p]}), "x")
    assert (res["label"], res["label_generated"]) == (expected, True)


def test_given_and_sample_labels_are_kept_and_not_marked_generated(client):
    p = sample("corn_soy__rye")
    p.update(plan_id="mine", label="My field")
    body = compare(client, {"plans": [p], "plan_ids": ["corn_soy__no_cover"]})
    assert (plan_of(body, "mine")["label"], plan_of(body, "mine")["label_generated"]) == ("My field", False)
    s = plan_of(body, "corn_soy__no_cover")
    assert s["label"] == "No planted winter cover" and s["label_generated"] is False


# --- 6. reason text ------------------------------------------------------------------------------


def test_reason_codes_get_a_plain_sentence_and_keep_the_code(client):
    body = compare(client, {"plan_ids": ["corn_soy__rye"], "location": {"latitude": 40.0, "longitude": -100.0}})
    res = plan_of(body, "corn_soy__rye")
    assert res["status"] == "unsupported" and res["reason"].startswith("unsupported_location")
    assert res["reason_text"] and not res["reason_text"].startswith("unsupported_location")


def test_catalog_v1_wheat_reason_code_has_text():
    v1 = dataclasses.replace(get_context(), index=CatalogIndex(load_catalog(V1_CATALOG_DIR)))
    results, _ts, _shared = engine.compare_plans([demo_plan()], v1)
    text.finalize(results, {demo_plan().plan_id: demo_plan()}, v1.index)
    r = results[0]
    assert (r.status, r.reason) == ("unavailable", "catalog_missing")
    assert r.reason_text == "The catalog has no rows for this path yet."


def test_wheat_partial_keeps_its_long_reason_and_gets_the_short_text(client):
    body = compare(client, {"rotation_ids": ["add_grain_crop"]})
    wheat = plan_of(body, "corn_soy__wheat_dc")
    assert wheat["status"] == "partial" and " " in wheat["reason"]  # the sentence is kept
    assert wheat["reason_text"] == text.WHEAT_PARTIAL_TEXT and len(wheat["reason_text"]) < len(wheat["reason"])
    other = plan_of(body, "soy_corn__no_cover")
    assert other["reason"] is None and other["reason_text"] is None


# --- rule lines: B's text and print -------------------------------------------------------------


def test_other_checks_carry_text_and_print_for_every_line(client):
    body = compare(client, {"plan_ids": ["corn_soy__clover", "corn_soy__rye", "corn_soy__no_cover"]})
    lines = [ln for p in body["plans"] for ln in p["other_checks"]]
    assert lines
    for ln in lines:
        assert isinstance(ln["text"], str) and ln["text"].strip()  # never null or empty
        assert isinstance(ln["print"], bool)
        assert ln["reason"]  # still there for debugging
    clover = plan_of(body, "corn_soy__clover")["other_checks"]
    assert any(ln["flagged"] and ln["print"] for ln in clover)  # every flagged line prints
    assert all(ln["print"] for ln in lines if ln["flagged"])
    # a rule that cannot be evaluated says so in BOTH status and verdict (`unknown` or
    # `manual_check`); verdict is null only for an evaluated rule that is clear (a hazard rule
    # whose condition was not met)
    undecided = [ln for ln in lines if ln["status"] in ("manual_check", "unknown")]
    assert undecided and all(ln["verdict"] == ln["status"] for ln in undecided)
    assert all(ln["status"] == "complete" and not ln["flagged"] for ln in lines if ln["verdict"] is None)


def test_reason_text_helper():
    assert text.reason_text("catalog_missing")
    assert text.reason_text("unsupported_location: outside NC")
    assert text.reason_text("the catalog has no numeric windows") is None
    assert text.reason_text("some_unknown_code") is None and text.reason_text(None) is None
