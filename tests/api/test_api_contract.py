"""Phase 10 contract tests: examples validate against the frozen OpenAPI schema; the committed
contract files match what the code generates now; grower data never reaches the logs."""

import json
import logging
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from fieldshift.api import contract
from fieldshift.api.app import create_app

ROOT = Path(__file__).resolve().parents[2]
OPENAPI = json.loads(contract.OPENAPI_PATH.read_text(encoding="utf-8"))
STATUS_VOCAB = {"complete", "partial", "unavailable", "unknown", "inapplicable", "unsupported",
                "invalid_input", "manual_check", "insufficient_data"}


def validate(instance, path, method, status):
    op = OPENAPI["paths"][path][method]
    content = op["responses"][str(status)].get("content", {}).get("application/json")
    assert content, f"{method} {path} {status} has no JSON schema in openapi.json"
    # OpenAPI 3.1 schemas are JSON Schema 2020-12; "#/components/..." refs resolve at the root.
    schema = {**content["schema"], "components": OPENAPI["components"]}
    jsonschema.Draft202012Validator(schema).validate(instance)


def test_a_corrupted_example_fails_validation():
    ex = SPECS["years"]
    body = json.loads((contract.EXAMPLES_DIR / "years.json").read_text(encoding="utf-8"))
    del body["years"][0]["winter"]
    with pytest.raises(jsonschema.ValidationError):
        validate(body, ex.path, ex.method, ex.status)
    body = json.loads((contract.EXAMPLES_DIR / "years.json").read_text(encoding="utf-8"))
    body["years"][0]["spring"] = "ok"  # not in the status vocabulary
    with pytest.raises(jsonschema.ValidationError):
        validate(body, ex.path, ex.method, ex.status)


SPECS = {e.name: e for e in contract.example_specs()}
SCHEMA_CHECKED = ["compare", "compare_unsupported_location", "replay", "sensitivity", "years",
                  "rotations"]


@pytest.mark.parametrize("name", SCHEMA_CHECKED)
def test_example_response_validates_against_the_frozen_schema(name):
    ex = SPECS[name]
    body = json.loads((contract.EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    validate(body, ex.path, ex.method, ex.status)


def test_examples_use_only_the_status_vocabulary_for_status_fields():
    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in {"status", "winter_status", "spring_status", "full_season_status",
                         "winter", "spring", "full_season"} and isinstance(v, str):
                    assert v in STATUS_VOCAB, f"{path}/{k} = {v!r} is not in the status vocabulary"
                walk(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    for name in ("compare", "replay", "sensitivity", "years", "health"):
        walk(json.loads((contract.EXAMPLES_DIR / f"{name}.json").read_text()))


def test_every_example_carries_the_four_meta_fields():
    for name in ("compare", "replay", "sensitivity", "years", "rotations", "health"):
        body = json.loads((contract.EXAMPLES_DIR / f"{name}.json").read_text())
        assert set(body["meta"]) == {"plan_version", "catalog_version", "snapshot_hash", "request_id"}
    err = json.loads((contract.EXAMPLES_DIR / "error_invalid_input.json").read_text())
    assert err["status"] == "invalid_input" and err["issues"][0]["field"]
    assert {"plan_version", "catalog_version", "snapshot_hash", "request_id"} <= set(err)


def test_committed_contract_files_are_current():
    """Fails when the API changed but docs/api was not regenerated."""
    stale = [str(p.relative_to(ROOT)) for p, text in contract.render().items()
             if not p.exists() or p.read_text(encoding="utf-8") != text]
    assert not stale, f"run `python -m fieldshift.api.contract`: {stale}"


def test_openapi_documents_the_core_endpoints_and_error_shape():
    paths = OPENAPI["paths"]
    for p in ("/v1/plans/compare", "/v1/seasons/{year}/replay", "/v1/plans/sensitivity",
              "/v1/years", "/v1/rotations", "/v1/plans/check", "/v1/crops", "/health"):
        assert p in paths, p
    assert OPENAPI["info"]["version"] == "1.0.0"


# --- reliability --------------------------------------------------------------------------------


def test_grower_entered_text_never_reaches_the_logs(caplog):
    secret = "SECRET-FIELD-NOTE-4242"
    plan = json.loads((ROOT / "data/samples/union_plans.json").read_text())["samples"][1]["plan"]
    plan["grower"] = {"low_moisture_concern": True, "residue_report": secret,
                      "observations": [secret]}
    caplog.set_level(logging.DEBUG)
    client = TestClient(create_app())
    ok = client.post("/v1/plans/compare", json={"plans": [plan], "include_soil": False})
    assert ok.status_code == 200 and secret in ok.text  # the response may echo the grower's plan
    bad = dict(plan, prev_harvest="13-99")
    assert client.post("/v1/plans/compare", json={"plans": [bad]}).status_code == 400
    client.post("/v1/seasons/2008/replay", json={"plan": plan})
    assert caplog.records  # access lines were logged
    assert secret not in caplog.text
    assert "/v1/plans/compare" in caplog.text and "residue_report" not in caplog.text


def test_scrub_filter_redacts_grower_fields_in_any_log_message(caplog):
    from fieldshift.api.logs import install_scrub_filter

    install_scrub_filter()
    log = logging.getLogger("fieldshift.test")
    with caplog.at_level(logging.INFO, logger="fieldshift"):
        log.info("payload residue_report='stalks everywhere' observations=['a','b'] ok=1")
    for rec in caplog.records:
        assert "stalks everywhere" not in rec.getMessage() and "[redacted]" in rec.getMessage()


def test_offline_demo_serves_the_sample_and_core_calculations_with_the_network_disabled():
    """A fresh process with every non-loopback connection refused: the app still serves."""
    code = f"""
import os, socket, sys
os.environ['FIELDSHIFT_OFFLINE'] = '1'
real = socket.socket.connect
def guard(self, addr, *a, **k):
    host = addr[0] if isinstance(addr, tuple) else addr
    if host not in ('127.0.0.1', '::1', 'localhost'):
        raise OSError('network disabled: ' + str(host))
    return real(self, addr, *a, **k)
socket.socket.connect = guard
sys.path.insert(0, {str(ROOT)!r})
from fastapi.testclient import TestClient
from fieldshift.api.app import app
c = TestClient(app)
assert c.get('/health').json()['offline'] is True
r = c.post('/v1/plans/compare', json={{'rotation_ids': ['winter_cover']}})
assert r.status_code == 200 and r.json()['plans'][0]['spring']['dry_seasons'] == 9
assert c.get('/v1/seasons/2008/replay?plan=corn_soy__rye').status_code == 200
assert c.post('/v1/plans/sensitivity', json={{'plan_id': 'corn_soy__rye'}}).status_code == 200
print('offline-ok')
"""
    out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True,
                         cwd=ROOT)
    assert out.returncode == 0 and "offline-ok" in out.stdout, out.stderr[-800:]
