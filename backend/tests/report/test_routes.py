import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fieldshift.report.audit import verify
from fieldshift.report.routes import router

from .conftest import YEAR

META = {"plan_version", "catalog_version", "snapshot_hash", "request_id"}


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_note_for_a_sample_plan_with_an_alternative(client):
    r = client.get(
        "/v1/plans/corn_soy__rye/note",
        params={"alternative": "corn_soy__no_cover", "year": YEAR, "as_of": "2027-04-01"},
    )
    assert r.status_code == 200
    note = r.json()
    assert set(note["meta"]) == META and note["status"] == "complete"
    assert note["plan"]["dates_basis"] == "assumed"  # sample dates are demo defaults
    assert [a["plan"]["plan_id"] for a in note["alternatives"]] == ["corn_soy__no_cover"]
    assert verify(note) == []


def test_post_note_with_an_edited_plan_drops_the_assumed_label(client):
    from fieldshift.api.samples import load_samples

    p = load_samples().plans["corn_soy__rye"].plan.model_dump(mode="json")
    same = client.post("/v1/plans/note", json={"plan": p, "year": YEAR}).json()
    assert same["plan"]["dates_basis"] == "assumed"  # untouched sample
    p["winter"]["terminate"] = "04-20"
    edited = client.post("/v1/plans/note", json={"plan": p, "year": YEAR})
    assert edited.status_code == 200 and edited.json()["plan"]["dates_basis"] == "grower"
    assert edited.json()["plan"]["calendar"]["termination_gap_days"]["value"] == 22
    assert verify(edited.json()) == []


@pytest.mark.parametrize(
    "path,json_body,field",
    [("/v1/plans/note", {}, "plan"),
     ("/v1/plans/note", {"plan_id": "nope"}, "plan_id"),
     ("/v1/plans/note", {"plan_id": "corn_soy__rye", "year": 1700}, "year"),
     ("/v1/plans/note", {"plan_id": "corn_soy__rye", "as_of": "tomorrow"}, "as_of"),
     ("/v1/plans/note", {"plan_id": "corn_soy__rye", "inputs": {"soil_temp_f": "hot"}}, "inputs.soil_temp_f"),
     ("/v1/plans/note", {"plan_id": "corn_soy__rye", "alternative_id": "nope"}, "alternative_id"),
     ("/v1/plans/note", {"plan_id": "corn_soy__rye", "plan": {}}, "plan"),
     ("/v1/plans/calendar", {"plan_id": "corn_soy__rye", "scenarios": "yes"}, "scenarios"),
     ("/v1/plans/backup", {"plan_id": "corn_soy__rye", "fallback_id": "nope"}, "fallback_id")],
)  # fmt: skip
def test_bad_requests_are_400_with_typed_issues_and_metadata(client, path, json_body, field):
    r = client.post(path, json=json_body)
    assert r.status_code == 400 and r.json()["status"] == "invalid_input"
    assert r.json()["issues"][0]["field"].startswith(field) and "request_id" in r.json()


def test_malformed_bodies_and_chronology_errors(client):
    for content in (b"{no", b"[1]"):
        r = client.post(
            "/v1/plans/note", content=content, headers={"content-type": "application/json"}
        )
        assert r.status_code == 400
    from fieldshift.api.samples import load_samples

    p = load_samples().plans["corn_soy__rye"].plan.model_dump(mode="json")
    p["winter"]["seed"] = "09-01"
    r = client.post("/v1/plans/calendar", json={"plan": p, "year": YEAR})
    assert r.status_code == 400 and r.json()["issues"][0]["field"] == "plan.winter.seed"


def test_get_note_bad_query_values(client):
    assert client.get("/v1/plans/corn_soy__rye/note", params={"year": "abc"}).status_code == 400
    assert client.get("/v1/plans/nope/note").status_code == 400


def test_calendar_route_with_diff(client):
    from fieldshift.api.samples import load_samples

    base = load_samples().plans["corn_soy__rye"].plan.model_dump(mode="json")
    new = {**base, "winter": {**base["winter"], "terminate": "04-14"}}
    r = client.post("/v1/plans/calendar", json={"plan": new, "previous_plan": base, "year": YEAR})
    assert r.status_code == 200 and set(r.json()["meta"]) == META
    body = r.json()
    assert body["calendar"]["status"] == "complete" and set(body["calendar"]["scenarios"]) >= {
        "dry",
        "wet",
    }
    d = body["diff"]
    assert d["plan_edits"][0]["field"] == "winter.terminate"
    assert {c["action_id"] for c in d["changes"]} >= {"terminate", "check:cr_tt_03"}
    no_scen = client.post(
        "/v1/plans/calendar", json={"plan_id": "corn_soy__rye", "year": YEAR, "scenarios": False}
    ).json()
    assert no_scen["calendar"]["scenarios"] is None and no_scen["diff"] is None


def test_backup_route_suggests_a_fallback_and_compares_fixed_plans(client):
    r = client.post(
        "/v1/plans/backup", json={"plan_id": "corn_soy__rye", "year": YEAR, "as_of": "2027-04-22"}
    )
    assert r.status_code == 200
    b = r.json()["backup"]
    assert b["status"] == "complete" and b["fallback_source"] == "suggested"
    assert b["timing"] == "due" and b["decision_deadline"] == "2027-04-27"
    assert b["comparison"]["basis"] == "fixed_plans"
    assert b["backtest"]["status"] == "unavailable"


def test_unsupported_plan_is_a_200_with_a_status(client):
    from fieldshift.api.samples import load_samples

    p = load_samples().plans["corn_soy__rye"].plan.model_dump(mode="json")
    p["next_crop_id"] = "quinoa"
    n = client.post("/v1/plans/note", json={"plan": p, "year": YEAR})
    assert n.status_code == 200 and n.json()["status"] == "unsupported"
    c = client.post("/v1/plans/calendar", json={"plan": p, "year": YEAR})
    assert c.status_code == 200 and c.json()["calendar"]["status"] == "unsupported"


def test_a_plan_valid_in_the_requested_year_but_not_in_every_replay_year_is_a_typed_400(client):
    # Feb 28 seed and Feb 29 termination: fine in leap 2028, but the terminate day collapses onto
    # the seed day in non-leap years, which the historical replay would hit.
    from fieldshift.api.samples import load_samples

    p = load_samples().plans["corn_soy__rye"].plan.model_dump(mode="json")
    p["winter"].update(seed="02-28", terminate="02-29")
    p["next_plant"], p["prev_harvest"] = "03-10", "10-01"
    for path in ("/v1/plans/note", "/v1/plans/calendar", "/v1/plans/backup"):
        r = client.post(path, json={"plan": p, "year": 2028})
        assert r.status_code == 400, path
        assert (
            r.json()["issues"][0]["field"].startswith("plan.winter")
            and "planting year" in r.json()["issues"][0]["message"]
        )


def test_backup_route_with_a_suggestion_that_would_break_in_some_year_is_not_a_500(client):
    from fieldshift.api.samples import load_samples

    p = load_samples().plans["corn_soy__rye"].plan.model_dump(mode="json")
    p["winter"].update(seed="02-28", terminate="03-01")
    p["prev_harvest"], p["next_plant"] = "10-01", "03-14"
    r = client.post("/v1/plans/backup", json={"plan": p, "year": 2028})
    assert r.status_code in (200, 400), r.text
    if r.status_code == 200:
        assert r.json()["backup"]["status"] in ("complete", "unsupported")
