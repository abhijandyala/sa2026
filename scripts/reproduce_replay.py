#!/usr/bin/env python3
"""Reproduce one season replay from the raw NASA POWER response alone (standard library only).

    python scripts/reproduce_replay.py --raw data/snapshots/union_county/raw/power_daily.json \
        --plans data/samples/union_plans.json --plan corn_soy__rye --year 2008

It does not import ``fieldshift`` and does not use the API. It re-derives, from ``raw/``:
the heavy-rain threshold (P95 of wet days >= 1 mm, Sep-May, 1981-2025 record), the fixed
bottom-20% spring cutoff (ceil(0.2 n)-th smallest of the complete 30-day windows), the spring
total and rank, and the winter rain by segment. Missing/fill/negative values are treated
exactly as in ``fieldshift/weather/normalize.py``. Prints JSON.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, timedelta

FILL = -999.0
BASELINE = range(1981, 2026)


def load_precip(raw_path: str) -> dict[date, float | None]:
    with open(raw_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    fill = float(payload.get("header", {}).get("fill_value", FILL))
    out: dict[date, float | None] = {}
    for key, value in payload["properties"]["parameter"]["PRECTOTCORR"].items():
        d = date(int(key[:4]), int(key[4:6]), int(key[6:8]))
        v = None if value is None else float(value)
        out[d] = None if v is None or math.isnan(v) or v == fill or v < 0 else v
    return out


def resolve(year: int, md: str) -> date:
    month, day = (int(x) for x in md.split("-"))
    if month == 2 and day == 29 and not _leap(year):
        day = 28
    return date(year, month, day)


def _leap(y: int) -> bool:
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def percentile(values: list[float], q: float) -> float:
    v = sorted(values)
    pos = (len(v) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def window_total(p: dict[date, float | None], start: date, end_incl: date) -> float | None:
    total, d = 0.0, start
    while d <= end_incl:
        v = p.get(d)
        if v is None:
            return None
        total += v
        d += timedelta(days=1)
    return round(total, 3)


def after(anchor: date, md: str) -> date:
    c = resolve(anchor.year, md)
    return c if c >= anchor else resolve(anchor.year + 1, md)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--plans", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--year", type=int, required=True)
    a = ap.parse_args()

    precip = load_precip(a.raw)
    with open(a.plans, encoding="utf-8") as fh:
        plan = next(s["plan"] for s in json.load(fh)["samples"] if s["plan_id"] == a.plan)
    plant_md, harvest_md = plan["next_plant"], plan["prev_harvest"]

    wet = [
        v for d, v in precip.items()
        if v is not None and d.month in (9, 10, 11, 12, 1, 2, 3, 4, 5) and v >= 1.0
    ]
    heavy = round(percentile(wet, 95.0), 3)

    totals = {}
    for y in BASELINE:
        plant = resolve(y, plant_md)
        t = window_total(precip, plant - timedelta(days=30), plant - timedelta(days=1))
        if t is not None:
            totals[y] = t
    k = math.ceil(0.20 * len(totals) - 1e-9)
    cutoff = sorted(totals.values())[k - 1]

    y = a.year
    plant = resolve(y, plant_md)
    h_year = y - 1 if tuple(map(int, harvest_md.split("-"))) > tuple(map(int, plant_md.split("-"))) else y
    harvest = resolve(h_year, harvest_md)
    spring = totals.get(y)
    out = {
        "plan_id": a.plan, "year": y,
        "heavy_rain_threshold_mm": heavy, "spring_dry_cutoff_mm": cutoff,
        "spring_total_mm": spring,
        "spring_rank": None if spring is None else 1 + sum(v < spring for v in totals.values()),
        "spring_is_dry": None if spring is None else spring <= cutoff,
        "n_eligible_springs": len(totals),
    }
    w = plan["winter"]
    seed = term = None
    if w["kind"] == "cover":
        seed = after(harvest, w["seed"])
        term = after(seed, w["terminate"])
    seg = {"living_cover": 0.0, "outside_cover": 0.0}
    heavy_days_outside = 0
    complete = True
    d = harvest
    while d < plant:
        v = precip.get(d)
        if v is None:
            complete = False
        else:
            living = seed is not None and seed <= d < term
            seg["living_cover" if living else "outside_cover"] += v
            if not living and v >= heavy:
                heavy_days_outside += 1
        d += timedelta(days=1)
    out["winter_complete"] = complete
    out["rain_outside_cover_mm"] = round(seg["outside_cover"], 3) if complete else None
    out["rain_living_cover_mm"] = round(seg["living_cover"], 3) if complete else None
    out["heavy_rain_days_outside_cover"] = heavy_days_outside if complete else None
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
