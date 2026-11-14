"""CLI: ``python -m fieldshift.weather {build,verify,report}``.

``build`` is the only command that uses the network (and refuses to run when
``FIELDSHIFT_OFFLINE=1``). ``verify`` and ``report`` read the committed snapshot only.
"""

from __future__ import annotations

import argparse
import json
import sys

from fieldshift.weather.coverage import coverage_report
from fieldshift.weather.power_client import fetch_daily
from fieldshift.weather.snapshot import (
    DEFAULT_SNAPSHOT_DIR,
    load_snapshot,
    verify_snapshot,
    write_snapshot,
)
from fieldshift.weather.sources import SNAPSHOT_END, SNAPSHOT_START, UNION_COUNTY


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fieldshift.weather")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="fetch POWER and write the snapshot (needs network)")
    build.add_argument("--start", default=SNAPSHOT_START)
    build.add_argument("--end", default=SNAPSHOT_END)
    build.add_argument("--out", default=str(DEFAULT_SNAPSHOT_DIR))
    locs = sub.add_parser(
        "build-locations", help="fetch one snapshot per county grid cell and write index.json"
    )
    locs.add_argument("--force", action="store_true", help="refetch snapshots that exist")
    sub.add_parser("verify-locations", help="verify index.json and every snapshot (offline)")
    for name in ("verify", "report"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--dir", default=str(DEFAULT_SNAPSHOT_DIR))
    args = parser.parse_args(argv)

    if args.command == "build":
        fetch = fetch_daily(UNION_COUNTY.latitude, UNION_COUNTY.longitude, args.start, args.end)
        manifest = write_snapshot(fetch, args.out, start=args.start, end=args.end)
        print(json.dumps(manifest["hashes"], indent=2))
    elif args.command == "build-locations":
        from fieldshift.weather.locations import build_locations

        doc = build_locations(force=args.force)
        print(json.dumps([(e["id"], e["snapshot_dir"], e["snapshot_hash"][:12])
                          for e in doc["locations"]], indent=2))
    elif args.command == "verify-locations":
        from fieldshift.weather.locations import verify_index

        print(json.dumps(verify_index(), indent=2))
    elif args.command == "verify":
        print(json.dumps(verify_snapshot(args.dir), indent=2))
    else:
        snap = load_snapshot(args.dir)
        print(f"snapshot_hash {snap.snapshot_hash}")
        print(json.dumps(coverage_report(snap.daily), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
