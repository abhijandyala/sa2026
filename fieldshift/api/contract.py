"""Freeze the API contract: ``docs/api/openapi.json`` plus real example responses.

    python -m fieldshift.api.contract          # regenerate (offline; reads only the snapshot)
    python -m fieldshift.api.contract --check  # exit 1 if the committed files are stale

Examples are generated from the real Union County sample by calling the app with the network
disabled (``FIELDSHIFT_OFFLINE=1``). Only ``meta.request_id`` is replaced (``req_example``) so
the files are stable. ``tests/api/test_api_contract.py`` validates every example against the
frozen schema and fails when the committed files drift from the code.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "docs" / "api"
EXAMPLES_DIR = API_DIR / "examples"
REQUESTS_DIR = EXAMPLES_DIR / "requests"
OPENAPI_PATH = API_DIR / "openapi.json"


@dataclass(frozen=True)
class Example:
    name: str
    method: str
    path: str  # OpenAPI path template
    url: str  # concrete URL (with query)
    body: dict[str, Any] | None
    status: int


def example_specs() -> list[Example]:
    bad_plan = _sample_plan("corn_soy__rye")
    bad_plan["winter"]["terminate"] = "05-20"  # terminates after planting
    return [
        Example("compare", "post", "/v1/plans/compare", "/v1/plans/compare",
                {"rotation_ids": ["current_practice", "winter_cover", "add_grain_crop"]}, 200),
        Example("compare_unsupported_location", "post", "/v1/plans/compare", "/v1/plans/compare",
                {"plan_ids": ["corn_soy__rye"],
                 "location": {"latitude": 35.78, "longitude": -78.64}}, 200),
        Example("error_invalid_input", "post", "/v1/plans/compare", "/v1/plans/compare",
                {"plans": [bad_plan]}, 400),
        Example("replay", "get", "/v1/seasons/{year}/replay",
                "/v1/seasons/2008/replay?plan=corn_soy__rye", None, 200),
        Example("sensitivity", "post", "/v1/plans/sensitivity", "/v1/plans/sensitivity",
                {"plan_id": "corn_soy__rye"}, 200),
        Example("years", "get", "/v1/years", "/v1/years?plan=corn_soy__rye", None, 200),
        Example("rotations", "get", "/v1/rotations", "/v1/rotations", None, 200),
        Example("health", "get", "/health", "/health", None, 200),
    ]


def _sample_plan(plan_id: str) -> dict[str, Any]:
    doc = json.loads((ROOT / "data" / "samples" / "union_plans.json").read_text(encoding="utf-8"))
    return next(s["plan"] for s in doc["samples"] if s["plan_id"] == plan_id)


def build_openapi() -> dict[str, Any]:
    os.environ["FIELDSHIFT_OFFLINE"] = "1"
    from fieldshift.api.app import create_app

    spec = create_app().openapi()
    spec["info"]["description"] = (
        "Field Shift backend. Labels and values ship together; every response carries "
        "meta {plan_version, catalog_version, snapshot_hash, request_id}. Partial results keep "
        "per-metric statuses in the body; HTTP 400 is only for invalid input."
    )
    return json.loads(json.dumps(spec, sort_keys=True))


def _normalize(body: Any) -> Any:
    if isinstance(body, dict):
        meta = body.get("meta")
        if isinstance(meta, dict) and "request_id" in meta:
            meta["request_id"] = "req_example"
        if "request_id" in body:  # the flat invalid_input envelope
            body["request_id"] = "req_example"
    return body


def build_examples() -> dict[str, tuple[Example, dict[str, Any] | None, Any]]:
    os.environ["FIELDSHIFT_OFFLINE"] = "1"
    from fastapi.testclient import TestClient

    from fieldshift.api.app import create_app

    client = TestClient(create_app())
    out: dict[str, tuple[Example, dict[str, Any] | None, Any]] = {}
    for ex in example_specs():
        resp = (client.get(ex.url) if ex.method == "get" else client.post(ex.url, json=ex.body))
        if resp.status_code != ex.status:
            raise RuntimeError(f"{ex.name}: expected {ex.status}, got {resp.status_code}")
        out[ex.name] = (ex, ex.body, _normalize(resp.json()))
    return out


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def render() -> dict[Path, str]:
    """Every file this module owns, as ``{path: text}``."""
    files: dict[Path, str] = {OPENAPI_PATH: _dump(build_openapi())}
    for name, (ex, body, resp) in build_examples().items():
        files[EXAMPLES_DIR / f"{name}.json"] = _dump(resp)
        files[REQUESTS_DIR / f"{name}.json"] = _dump(
            {"method": ex.method.upper(), "url": ex.url, "status": ex.status, "body": body}
        )
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fieldshift.api.contract")
    ap.add_argument("--check", action="store_true", help="fail if committed files are stale")
    args = ap.parse_args(argv)
    files = render()
    if args.check:
        stale = [str(p.relative_to(ROOT)) for p, text in files.items()
                 if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print("stale contract files (run python -m fieldshift.api.contract):", *stale, sep="\n  ")
            return 1
        print("contract files are current")
        return 0
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"wrote {len(files)} files under {API_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
