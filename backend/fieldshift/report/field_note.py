"""Field note (Phase 9): one JSON document for a plan and (optionally) one fixed alternative.

JSON only; the front end renders and prints it. Sections: the plan, the alternative(s), winter and
spring results, the two-period era comparison, the action calendar (with dry/wet scenarios), the
unresolved checks, the sources, and blank adviser-note fields.

Every number is an audited object ``{value, unit, audit_id}`` (see ``report.audit``) and resolves to
an entry in ``audit.entries`` saying whether it came from NASA data, USDA, a published extension
source, the grower, or a calculation, with the inputs behind it. Years and identifiers are strings.
A missing value is ``null`` (never ``0``), and each section carries its own status.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fieldshift.compare import engine
from fieldshift.compare.context import Context
from fieldshift.contracts import Plan, Status
from fieldshift.metrics.spring import SPRING_DRY_PREFIX
from fieldshift.planner.backup import (
    BackupPlan,
    build_backup_plan,
    compare_fixed_plans,
    distinct_ids,
)
from fieldshift.planner.calendar import (
    ActionCalendar,
    add_scenarios,
    build_action_calendar,
)
from fieldshift.planner.checker import default_planting_year, plan_version
from fieldshift.report.audit import AuditBook, finalize, source_ref
from fieldshift.report.meta import response_meta

NOTE_VERSION = "1"  # a label, not a quantity
ADVISER_FIELDS = (
    ("adviser_name", "Adviser name"),
    ("organization", "Organization"),
    ("reviewed_on", "Date reviewed"),
    ("agreement", "Agreement with the plan (agree / agree with changes / disagree)"),
    ("changes_suggested", "Changes suggested"),
    ("local_knowledge", "Local knowledge the data does not capture"),
    ("follow_up", "Follow-up actions and who owns them"),
)


class _Nums:
    """Shorthand for audited numbers that share a snapshot / plan / threshold context."""

    def __init__(self, book: AuditBook, ctx: Context, plan: Plan, dates_basis: str):
        self.book, self.ctx, self.plan, self.dates_basis = book, ctx, plan, dates_basis
        self.ts: Any = None  # the frozen ThresholdSet, set once the comparison has run
        self.snapshot = source_ref(
            "weather_snapshot", ctx.snapshot_hash,
            label="NASA POWER daily (MERRA-2 / POWER), Union County snapshot",
        )  # fmt: skip

    def nasa(self, v: Any, unit: str, what: str, **inputs: Any) -> dict[str, Any] | None:
        return self.book.num(v, unit, "nasa", self.snapshot, {"what": what, **inputs})

    def calc(
        self, v: Any, unit: str | None, what: str, ref: dict[str, Any] | None = None, **inputs: Any
    ):
        ref = ref or source_ref("calculation", what)
        return self.book.num(v, unit, "calculation", ref, {"what": what, **inputs})

    def plan_calc(self, v: Any, unit: str, what: str, **inputs: Any) -> dict[str, Any] | None:
        """A number computed from the plan's own dates: ``grower`` entered or ``assumed`` demo."""
        ref = source_ref("plan_input", self.plan.plan_id, dates_basis=self.dates_basis)
        return self.book.num(v, unit, "calculation", ref, {"what": what, **inputs})

    def threshold(self, name: str, value: Any) -> dict[str, Any] | None:
        """A frozen threshold's value. Published ones (``Threshold.source``) are ``extension``."""
        th = self.ts.thresholds.get(name) if self.ts is not None else None
        sid = self.ts.threshold_set_id if self.ts is not None else None
        if th is not None and th.source is not None:
            ref = source_ref(
                "catalog_rule", th.source.rule_id, url=th.source.url, locator=th.source.locator,
                threshold_set_id=sid,
            )  # fmt: skip
            return self.book.num(
                value,
                th.unit,
                "extension",
                ref,
                {"what": f"published threshold {name}", "method": th.method},
            )
        return self.calc(value, th.unit if th else None, f"frozen threshold {name}",
                         ref=source_ref("threshold", name, threshold_set_id=sid))  # fmt: skip

    def extension(self, v: Any, unit: str | None, rule_id: str, url: str | None, what: str):
        ref = source_ref("catalog_rule", rule_id, url=url)
        return self.book.num(v, unit, "extension", ref, {"what": what})


def _src(src: Any) -> dict[str, Any] | None:
    if src is None:
        return None
    return src if isinstance(src, dict) else src.model_dump(mode="json")


def _years(ys: list[int] | None) -> list[str]:
    return [str(y) for y in (ys or [])]


# --------------------------------------------------------------------------- sections


def _plan_section(plan: Plan, n: _Nums, cal: ActionCalendar, label: str | None) -> dict[str, Any]:
    c = cal.check_result.calendar if cal.check_result else None
    out: dict[str, Any] = {
        "plan_id": plan.plan_id,
        "label": label or plan.label,
        "previous_crop": plan.previous_crop_id,
        "prev_harvest": plan.prev_harvest,
        "winter": plan.winter.model_dump(mode="json", exclude_none=True),
        "next_crop": plan.next_crop_id,
        "next_plant": plan.next_plant,
        "region": plan.region,
        "production_system": plan.production_system,
        "dates_basis": n.dates_basis,
        "grower_inputs": plan.grower.model_dump(mode="json"),
        "planting_year": str(cal.year),
    }
    if c is not None and c.grain is not None:
        # a harvested winter grain is not a living cover: cover metrics are null, not 0
        out["calendar"] = {
            "winter_days": n.plan_calc(c.winter_days, "days", "previous harvest to next planting"),
            "wheat_season_days": n.plan_calc(
                c.grain.days, "days", "winter grain planting to harvest"
            ),
            "living_cover_days_planned": None,
            "days_without_planned_cover": None,
            "termination_gap_days": None,
            "establishment": "inapplicable",
            "cover_label": None,
        }
    elif c is not None:
        cover_days = c.cover.days if c.cover else 0
        out["calendar"] = {
            "winter_days": n.plan_calc(
                c.winter_days, "days", "winter window [prev_harvest, next_plant)"
            ),
            "living_cover_days_planned": n.plan_calc(
                cover_days, "days", "planned living-cover days [seed, terminate)"
            ),
            "days_without_planned_cover": n.plan_calc(
                c.winter_days - cover_days, "days", "winter days outside planned cover"
            ),
            "termination_gap_days": n.plan_calc(
                c.termination_gap_days, "days", "next_plant - terminate"
            ),
            "establishment": "uncertain" if c.cover else "inapplicable",
            "cover_label": "planned (not observed)" if c.cover else None,
        }
    return out


def _winter_section(res: Any, n: _Nums) -> dict[str, Any]:
    w = res.winter
    if w is None:
        return {"status": str(res.status), "reason": res.reason}
    med = w.per_season_median
    return {
        "status": str(w.status),
        "label": "Rain that fell while no living cover was planned (a weather record, not erosion)",
        "seasons": n.calc(w.seasons, "seasons", "planting years replayed"),
        "eligible_seasons": n.calc(w.eligible_seasons, "seasons", "seasons with a complete winter record"),
        "per_season_median": {
            "rain_mm_outside_cover": n.calc(
                med.get("rain_mm_outside_cover"), "mm", "median over eligible seasons of rain outside planned cover",
                ref=n.snapshot, eligible_seasons=w.eligible_seasons,
            ),
            "heavy_rain_days_outside_cover": n.calc(
                med.get("heavy_rain_days_outside_cover"), "days",
                "median over eligible seasons of heavy-rain days outside planned cover",
                ref=n.snapshot, eligible_seasons=w.eligible_seasons,
            ),
        },
        "seasons_with_heavy_rain_outside_cover": n.calc(
            w.seasons_with_heavy_rain_outside_cover, "seasons", "seasons with at least one heavy-rain day outside cover"
        ),
        "segments": w.segments,
        "reasons": w.reasons,
        "residue_context": res.residue_context,
    }  # fmt: skip


def _spring_section(res: Any, n: _Nums, ts: Any, plan: Plan) -> dict[str, Any]:
    s = res.spring
    if s is None:
        return {"status": str(res.status), "reason": res.reason}
    n.ts = n.ts or ts
    return {
        "status": str(s.status),
        "window_days": n.plan_calc(s.window_days, "days", "30 days before next_plant, inclusive"),
        "dry_cutoff_mm": n.threshold(f"{SPRING_DRY_PREFIX}{plan.next_plant}", s.cutoff_mm),
        "eligible_seasons": n.calc(
            s.eligible_seasons, "seasons", "seasons with a complete spring window"
        ),
        "dry_seasons": n.calc(s.dry_seasons, "seasons", "seasons at or below the dry cutoff"),
        "dry_years": _years(s.dry_years),
        "median_total_mm": n.calc(
            s.median_total_mm,
            "mm",
            "median 30-day precipitation over eligible seasons",
            ref=n.snapshot,
        ),
        "excluded_years": [
            {"year": str(e.get("year")), **{k: v for k, v in e.items() if k != "year"}}
            for e in s.excluded_years
        ],
    }


def _checks_section(res: Any, n: _Nums) -> list[dict[str, Any]]:
    out = []
    for c in res.spring_checks:
        out.append(
            {
                "check_id": c.check_id, "label": c.label, "fires_when": c.fires_when,
                "optional": c.optional, "rule_ids": c.rule_ids,
                "count": n.calc(c.count, "seasons", f"seasons the check would have fired ({c.check_id})"),
                "denominator": n.calc(c.denominator, "seasons", f"seasons the check could be evaluated ({c.check_id})"),
                "pct": n.calc(c.pct, "percent", "count / denominator * 100"),
                "qualifying_years": _years(c.qualifying_years),
                "skipped_years": [
                    {"year": str(k.get("year")), "status": k.get("status"), "reason": k.get("reason")}
                    for k in c.skipped_years
                ],
                "source": _src(c.source),
            }
        )  # fmt: skip
    return out


def _eras_section(res: Any, n: _Nums) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, e in res.eras.items():

        def era(stats: Any, name: str = name) -> dict[str, Any]:
            return {
                "start": str(stats.start), "end": str(stats.end),
                "seasons": n.calc(stats.seasons, "seasons", f"planting years in the era ({name})"),
                "evaluable": n.calc(stats.evaluable, "seasons", f"evaluable seasons, the denominator ({name})"),
                "events": n.calc(stats.events, "seasons", f"seasons with the event ({name})"),
                "pct": n.calc(stats.pct, "percent", "events / evaluable * 100"),
                "not_evaluable": [{"year": str(m.year), "reason": m.reason} for m in stats.not_evaluable],
            }  # fmt: skip

        out[name] = {
            "status": str(e.status), "result": e.result, "caveat": e.caveat,
            "diff_pp": n.calc(e.diff_pp, "percentage points", "recent pct - earlier pct"),
            "similarity_band_pp": n.calc(e.similarity_band_pp, "percentage points", "fixed similarity band"),
            "min_evaluable_per_era": n.calc(e.min_evaluable_per_era, "seasons", "fixed minimum coverage per era"),
            "basis": e.basis,
            "threshold_set_id": e.threshold_set_id,
            "thresholds": {k: n.threshold(k, v) for k, v in e.thresholds.items()},
            "excluded_from_eras": _years(list(e.excluded_from_eras)),
            "earlier": era(e.earlier), "recent": era(e.recent),
        }  # fmt: skip
    return out


def _thresholds_section(ts: Any, n: _Nums) -> list[dict[str, Any]]:
    """Every frozen threshold used, with its method and (when published) its source."""
    out = []
    for name, t in sorted(ts.thresholds.items()):
        out.append(
            {
                "name": name, "method": t.method, "status": str(t.status), "unit": t.unit,
                "value": n.threshold(name, t.value), "reference_span": t.reference_span,
                "note": t.note, "published": t.source is not None,
                **(
                    {"title": t.source.title, "url": t.source.url, "locator": t.source.locator,
                     "verified_date": t.source.verified_date}
                    if t.source is not None else {}
                ),
            }
        )  # fmt: skip
    return out


def _reference(ref: dict[str, Any] | None, n: _Nums, rule_id: str) -> dict[str, Any] | None:
    if ref is None:
        return None
    url = ref.get("source_url")
    unit = ref.get("unit")
    return {
        "kind": ref["kind"], "operator": ref.get("operator"), "unit": unit,
        "value_min": n.extension(ref.get("value_min"), unit, rule_id, url, "published reference value (minimum)"),
        "value_max": n.extension(ref.get("value_max"), unit, rule_id, url, "published reference value (maximum)"),
        "is_grower_target": False, "source_url": url,
        "label": "published reference, not the grower's target",
    }  # fmt: skip


def _calendar_section(cal: ActionCalendar, n: _Nums) -> dict[str, Any]:
    if cal.status != Status.COMPLETE:
        return {"status": str(cal.status), "notes": cal.notes}
    actions = []
    for a in cal.actions:
        actions.append(
            {
                "action_id": a.action_id, "kind": a.kind, "date": a.date.isoformat(),
                "end_date": a.end_date.isoformat() if a.end_date else None,
                "label": a.label, "zone": a.zone, "trigger": a.trigger,
                "status": str(a.status), "flagged": a.flagged,
                "evidence": [
                    {
                        "rule_id": e.rule_id, "status": str(e.status), "verdict": e.verdict,
                        "reason": e.reason, "missing_inputs": e.missing_inputs,
                        "reference": _reference(e.reference, n, e.rule_id), "source": e.source,
                    }
                    for e in a.evidence
                ],
            }
        )  # fmt: skip
    return {
        "status": str(cal.status),
        "year": str(cal.year),
        "actions": actions,
        "scenarios": _scenarios(cal.scenarios, n),
        "notes": cal.notes,
    }


def _scenarios(sc: dict[str, Any], n: _Nums) -> dict[str, Any]:
    if not sc or sc.get("status") != Status.COMPLETE.value:
        return sc or {"status": Status.UNAVAILABLE.value}
    out: dict[str, Any] = {"status": sc["status"]}
    for name in ("typical", "dry", "wet"):
        e = sc.get(name)
        if e is None:
            out[name] = {"status": Status.UNAVAILABLE.value}
            continue
        y = str(e["year"])
        s, w, win = e["spring"], e["wetness"], e["winter"]
        item: dict[str, Any] = {
            "year": y, "replay": e["replay"],
            "spring": {
                "total_mm": n.nasa(s["total_mm"], "mm", "30-day precipitation before planting", year=y),
                "rank": n.calc(s["rank"], "rank (1 = driest)", "rank of this spring among eligible springs", ref=n.snapshot, year=y),
                "of": n.calc(s["of"], "seasons", "eligible springs ranked", ref=n.snapshot),
                "cutoff_mm": n.calc(s["cutoff_mm"], "mm", "frozen dry cutoff", ref=n.snapshot),
                "is_dry": s["is_dry"], "status": s["status"],
            },
            "wetness": {
                "gwettop_window_mean": n.nasa(w["gwettop_window_mean"], "fraction 0-1", "modeled surface wetness, window mean (GWETTOP)", year=y),
                "gwetroot_window_mean": n.nasa(w["gwetroot_window_mean"], "fraction 0-1", "modeled root-zone wetness, window mean (GWETROOT)", year=y),
                "label": "modeled (a model estimate, not a field measurement)", "status": w["status"],
            },
            "winter": {
                "rain_outside_cover_mm": n.nasa(win["rain_outside_cover_mm"], "mm", "rain outside planned cover", year=y),
                "heavy_rain_days_outside_cover": n.calc(win["heavy_rain_days_outside_cover"], "days", "heavy-rain days outside planned cover", ref=n.snapshot, year=y),
            },
        }  # fmt: skip
        if "decisions_that_could_change" in e:
            item["decisions_that_could_change"] = e["decisions_that_could_change"]
            item["decisions_note"] = e["decisions_note"]
        if "drainage_access_checks" in e:
            d = e["drainage_access_checks"]
            item["drainage_access_checks"] = {
                **{k: v for k, v in d.items() if k != "heavy_rain_days_outside_cover"},
                "heavy_rain_days_outside_cover": n.calc(
                    d.get("heavy_rain_days_outside_cover"), "days", "heavy-rain days outside planned cover", ref=n.snapshot, year=y
                ),
            }  # fmt: skip
        out[name] = item
    return out


def _unresolved(cal: ActionCalendar, res: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for a in cal.actions:
        if a.kind != "check" or a.status == Status.COMPLETE and not a.flagged:
            continue
        for e in a.evidence:
            items.append(
                {
                    "rule_id": e.rule_id, "status": str(e.status), "flagged": a.flagged,
                    "due": a.date.isoformat(), "what": a.label, "reason": e.reason,
                    "missing_inputs": e.missing_inputs, "source": e.source,
                }
            )  # fmt: skip
    cr = cal.check_result
    if cr is not None:
        for g in cr.conflicts:
            items.append({"rule_id": ", ".join(g.rule_ids), "status": "manual_check", "flagged": True,
                          "what": "conflicting catalog rules", "reason": g.note, "source": None})  # fmt: skip
        for p in cr.path_notes:
            items.append({"rule_id": p.path, "status": str(p.status), "flagged": False,
                          "what": "path not fully evaluable", "reason": p.reason, "source": None})  # fmt: skip
    for x in res.other_checks:
        if x.flagged and not any(i["rule_id"] == x.rule_id for i in items):
            items.append({"rule_id": x.rule_id, "status": str(x.status), "flagged": True,
                          "what": x.reason, "reason": x.reason, "source": x.source})  # fmt: skip
    return items


def _alternative_section(
    alt: Plan,
    alt_cal: ActionCalendar,
    backup: BackupPlan,
    alt_res: Any,
    base_res: Any,
    n: _Nums,
    ts: Any,
) -> dict[str, Any]:
    d = backup.comparison or {}
    diff = d.get("fallback_minus_default", {})
    block: dict[str, Any] = {
        "kind": "fixed_alternative",
        "plan": _plan_section(alt, n, alt_cal, alt_res.label if alt_res else None),
        "status": str(backup.status),
        "winter": _winter_section(alt_res, n) if alt_res else None,
        "spring_checks": _checks_section(alt_res, n)
        if alt_res and alt_res.status == Status.COMPLETE
        else [],
        "fallback_source": backup.fallback_source,
        "divergence": backup.divergence.model_dump(mode="json") if backup.divergence else None,
        "switch_condition": backup.switch_condition.model_dump(mode="json")
        if backup.switch_condition
        else None,
        "decision_deadline": backup.decision_deadline.isoformat()
        if backup.decision_deadline
        else None,
        "next_check_date": backup.next_check_date.isoformat() if backup.next_check_date else None,
        "timing": backup.timing,
        "backtest": backup.backtest,
        "assumptions": backup.assumptions,
        "difference_vs_default": {
            "label": "alternative minus default",
            "living_cover_days_planned": n.calc(
                diff.get("living_cover_days_planned"), "days", "alternative minus default"
            ),
            "termination_gap_days": n.calc(
                diff.get("termination_gap_days"), "days", "alternative minus default"
            ),
            "rain_mm_outside_cover_median": n.calc(
                diff.get("rain_mm_outside_cover_median"),
                "mm",
                "alternative minus default",
                ref=n.snapshot,
            ),
            "heavy_rain_days_outside_cover_median": n.calc(
                diff.get("heavy_rain_days_outside_cover_median"),
                "days",
                "alternative minus default",
                ref=n.snapshot,
            ),
            "spring_check_counts": {
                cid: {
                    "default": n.calc(
                        v["default"], "seasons", f"seasons the default would have fired ({cid})"
                    ),
                    "alternative": n.calc(
                        v["fallback"],
                        "seasons",
                        f"seasons the alternative would have fired ({cid})",
                    ),
                    "default_denominator": n.calc(
                        v["default_denominator"], "seasons", f"evaluable seasons, default ({cid})"
                    ),
                    "alternative_denominator": n.calc(
                        v["fallback_denominator"],
                        "seasons",
                        f"evaluable seasons, alternative ({cid})",
                    ),
                    "same_denominator": v["same_denominator"],
                }
                for cid, v in diff.get("spring_check_counts", {}).items()
            },
            "note": d.get("note"),
        },  # fmt: skip
    }
    return block


def _cross_calendar_alternative(
    default: Plan,
    alt: Plan,
    backup: BackupPlan,
    n: _Nums,
    ctx: Context,
    index: Any,
    year: int,
    inputs: dict[str, Any] | None,
) -> dict[str, Any]:
    """An alternative that plants in a different calendar window (e.g. wheat then double-crop).

    Each plan keeps its own baseline; only raw 30-day totals are shown side by side.
    """
    acal = build_action_calendar(alt, index, year=year, inputs=inputs)
    cmp = backup.comparison or {}
    d, f = cmp.get("default"), cmp.get("fallback")

    def side(b: dict[str, Any] | None, plan: Plan) -> dict[str, Any] | None:
        if b is None:
            return None
        nums = _Nums(n.book, ctx, plan, n.dates_basis)
        nums.ts = engine.threshold_set_for(ctx, [plan.next_plant])
        return {
            "plan_id": b["plan_id"], "next_plant": b["next_plant"], "plant_date": b["plant_date"],
            "window": {"plant_md": b["window"]["plant_md"], "example": b["window"]["example"]},
            "median_total_mm": nums.calc(b["median_total_mm"], "mm", "median 30-day precipitation, own window", ref=nums.snapshot),
            "eligible_seasons": nums.calc(b["eligible_seasons"], "seasons", "seasons with a complete window"),
        }  # fmt: skip

    diff = (cmp.get("fallback_minus_default") or {}).get("median_total_mm")
    return {
        "kind": "fixed_alternative",
        "comparison_label": cmp.get("label", "different-calendar"),
        "plan": _plan_section(alt, n, acal, alt.label),
        "status": str(backup.status),
        "fallback_source": backup.fallback_source,
        "divergence": backup.divergence.model_dump(mode="json") if backup.divergence else None,
        "switch_condition": backup.switch_condition.model_dump(mode="json")
        if backup.switch_condition
        else None,
        "decision_deadline": backup.decision_deadline.isoformat()
        if backup.decision_deadline
        else None,
        "next_check_date": backup.next_check_date.isoformat() if backup.next_check_date else None,
        "timing": backup.timing,
        "backtest": backup.backtest,
        "assumptions": backup.assumptions,
        "raw_totals": {
            "default": side(d, default),
            "alternative": side(f, alt),
            "median_total_mm_difference": n.calc(
                diff, "mm", "alternative minus default raw median totals", ref=n.snapshot
            ),
            "note": cmp.get("note"),
        },
    }


def _collect_sources(note: dict[str, Any], ctx: Context) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str], dict[str, Any]] = {}

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            if set(x) >= {"url", "locator"} or set(x) >= {"title", "url"}:
                key = (str(x.get("url")), str(x.get("locator")))
                seen.setdefault(
                    key, {k: x.get(k) for k in ("title", "url", "locator", "verified_date")}
                )
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk({k: v for k, v in note.items() if k != "audit"})
    rows = sorted(seen.values(), key=lambda r: (r["title"] or "", r["locator"] or ""))
    pr = ctx.manifest.get("retrieval", {})
    rows.append(
        {
            "title": "NASA POWER Daily API (AG community), Union County reference grid cell",
            "url": "https://power.larc.nasa.gov/docs/services/api/temporal/daily/",
            "locator": "PRECTOTCORR, T2M, T2M_MAX, T2M_MIN, GWETTOP, GWETROOT",
            "verified_date": pr.get("retrieved_at"),
            "snapshot_hash": ctx.snapshot_hash,
        }
    )
    return rows


def build_field_note(
    plan: Plan,
    ctx: Context,
    *,
    alternative: Plan | None = None,
    year: int | None = None,
    as_of: date | None = None,
    inputs: dict[str, Any] | None = None,
    dates_assumed: bool = False,
    alt_dates_assumed: bool | None = None,
    maturity_group: Any = None,
    compare_to_plan: Plan | None = None,
) -> dict[str, Any]:
    """Build the field note JSON for ``plan`` (and one fixed ``alternative``).

    A ``winter_grain`` (wheat) plan gets the wheat note (``report.wheat_note``); the maturity group
    and a full-season ``compare_to_plan`` only apply to it.
    """
    index = ctx.index
    year = year or default_planting_year()
    if plan.winter.kind == "winter_grain":
        from fieldshift.report.wheat_note import build_wheat_note

        return build_wheat_note(
            plan, ctx, year=year, as_of=as_of, inputs=inputs, maturity_group=maturity_group,
            dates_assumed=dates_assumed, alternative=alternative,
            alt_dates_assumed=alt_dates_assumed, compare_to_plan=compare_to_plan,
        )  # fmt: skip
    if alternative is not None:
        alternative = distinct_ids(plan, alternative)  # results are keyed by plan_id
    cross_alt = alternative is not None and alternative.winter.kind == "winter_grain"
    plans = [plan] + ([alternative] if alternative is not None and not cross_alt else [])
    results, ts, _shared = engine.compare_plans(plans, ctx)
    base = results[0]
    version = plan_version(plan, year, inputs)
    meta = response_meta(version)
    if base.status != Status.COMPLETE:
        return {
            "meta": meta, "note_version": NOTE_VERSION, "status": str(base.status),
            "plan": {"plan_id": plan.plan_id}, "reason": base.reason, "unresolved_checks": [],
            "adviser_note": _adviser(), "limits": _limits(False, []),
            "audit": AuditBook().as_dict(),
        }  # fmt: skip

    book = AuditBook()
    basis = "assumed" if dates_assumed else "grower"
    n = _Nums(book, ctx, plan, basis)
    n.ts = ts
    cal = add_scenarios(build_action_calendar(plan, index, year=year, inputs=inputs), plan, ctx)

    note: dict[str, Any] = {
        "meta": meta,
        "note_version": NOTE_VERSION,
        "status": str(Status.COMPLETE),
        "plan": _plan_section(plan, n, cal, base.label),
        "winter": _winter_section(base, n),
        "spring": _spring_section(base, n, ts, plan),
        "spring_checks": _checks_section(base, n),
        "eras": _eras_section(base, n),
        "thresholds": _thresholds_section(ts, n),
        "calendar": _calendar_section(cal, n),
        "unresolved_checks": _unresolved(cal, base),
    }
    alts: list[dict[str, Any]] = []
    if alternative is not None:
        alt_basis = (
            "assumed"
            if (alt_dates_assumed if alt_dates_assumed is not None else dates_assumed)
            else "grower"
        )
        an = _Nums(book, ctx, alternative, alt_basis)
        an.ts = ts
        acal = build_action_calendar(alternative, index, year=year, inputs=inputs)
        backup = build_backup_plan(plan, alternative, index, year=year, as_of=as_of, inputs=inputs)
        backup = compare_fixed_plans(backup, plan, alternative, ctx)
        if cross_alt:
            alts.append(
                _cross_calendar_alternative(plan, alternative, backup, an, ctx, index, year, inputs)
            )
        else:
            alts.append(_alternative_section(alternative, acal, backup, results[1], base, an, ts))
    note["alternatives"] = alts
    note["sources"] = _collect_sources(note, ctx)
    note["adviser_note"] = _adviser()
    note["limits"] = _limits(dates_assumed, alts)
    note = finalize(note, book)
    note["audit"] = book.as_dict()
    return note


def _adviser() -> dict[str, Any]:
    return {
        "instructions": "For the adviser to complete; the backend leaves these blank.",
        "fields": [
            {"field_id": fid, "label": label, "value": None} for fid, label in ADVISER_FIELDS
        ],
    }


def _limits(dates_assumed: bool, alts: list[dict[str, Any]]) -> list[str]:
    out = [
        "Descriptive comparison of two historical periods only; not a trend, cause or forecast.",
        "Weather values are NASA POWER estimates for a regional grid cell, not field measurements.",
        "Soil wetness (GWETTOP / GWETROOT) is modeled and is shown as modeled everywhere.",
        "Cover-crop establishment is uncertain; living cover is planned, not observed.",
        "Catalog rules are guidance from the cited sources; checks marked manual_check or unknown "
        "need a person or more input.",
        "Rain outside planned cover is a rainfall record, not an erosion or soil-loss estimate.",
    ]
    if dates_assumed:
        out.append(
            "Plan dates are demo defaults (assumed), not grower-entered; edit them before use."
        )
    if alts:
        out.append(
            "The alternative is compared as a fixed plan; no forecast of which plan will do better."
        )
    return out
