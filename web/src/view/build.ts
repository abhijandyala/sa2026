import type { CompareResponse, Era, OtherCheck, Plan, SensitivityResponse, SpringWindow, SpringYear, YearsResponse } from "../api/schema";
import type { Origin } from "../api/client";
import { CARDS, type CardContent, type CardKey } from "../content/strategies";

/*
  Turns backend responses into exactly what the screen shows. Selection only: it never
  computes a total, rank, flag or count (handbook p.4). Where the backend has not sent
  a value, the view says "not available" instead of filling one in.
*/

export type DataKind = "draft" | "saved" | "live";

export interface Selection {
  card: CardKey;
  year: number | null;
}

export interface TileVM {
  year: number;
  status: SpringYear["status"];
  percentile: number | null;
  isDry: boolean | null;
  marker?: "typical" | "dry";
  selected: boolean;
  description: string;
}

export interface YearVM {
  year: number;
  status: SpringYear["status"];
  totalMm: number | null;
  window: [string, string];
  rank: number | null;
  of: number | null;
  isDry: boolean | null;
  wetnessRoot: number | null;
}

export interface EraVM {
  earlier: { label: string; count: number; denominator: number };
  recent: { label: string; count: number; denominator: number };
  result: Era["result"];
  caveat: string;
}

export type CardStatus =
  | { kind: "check"; text: string }
  | { kind: "dry"; text: string }
  | { kind: "unavailable"; text: string }
  | null;

export interface CardVM {
  key: CardKey;
  content: CardContent;
  plan: Plan | null;
  missing: boolean;
  /** Soil-protection side: median winter rain on ground with no planned living cover. */
  soil: { mm: number | null; seasons: number | null };
  /** Risk side: springs that would have prompted the NC State field-moisture check. */
  check: { applies: boolean; count: number | null; denominator: number | null };
  /** Earlier vs recent for the check where it applies, otherwise for dry planting windows. */
  era: (EraVM & { measure: string }) | null;
  metrics: string[];
  status: CardStatus;
  checks: OtherCheck[];
}

export interface ViewModel {
  dataKind: DataKind;
  locationLabel: string;
  gridNote: string;
  requestId: string;
  window: SpringWindow | null;
  windowLabel: string;
  windowEra: EraVM | null;
  tiles: TileVM[];
  selectedYear: YearVM | null;
  shortcuts: { typical: number | null; dry: number | null };
  cards: CardVM[];
  thresholds: CompareResponse["thresholds"];
  eraSpans: { earlier: string; recent: string };
}

const span = (e: { start: number; end: number }) => `${e.start}–${e.end}`;

function windowFor(compare: CompareResponse, plan: Plan | null): SpringWindow | null {
  const id = plan?.spring_window_id;
  if (!id || !compare.spring_windows) return null;
  return compare.spring_windows[id] ?? null;
}

function eraVM(era: Era | undefined, spans: { earlier: string; recent: string }): EraVM | null {
  if (!era) return null;
  return {
    earlier: { label: spans.earlier, count: era.earlier.count, denominator: era.earlier.denominator },
    recent: { label: spans.recent, count: era.recent.count, denominator: era.recent.denominator },
    result: era.result,
    caveat: era.caveat,
  };
}

function plantedLabel(plan: Plan): string {
  const w = plan.sequence.winter;
  if (w.type === "cover") return "rye";
  if (w.type === "winter_grain") return "wheat";
  return "cover";
}

export function buildView(
  data: { years: YearsResponse; compare: CompareResponse; sensitivity: SensitivityResponse | null; origin: Origin },
  sel: Selection,
): ViewModel {
  const { years, compare } = data;
  const spans = { earlier: span(years.eras.earlier), recent: span(years.eras.recent) };
  const planById = new Map(compare.plans.map((p) => [p.plan_id, p]));

  const selectedContent = CARDS.find((c) => c.key === sel.card) ?? CARDS[0]!;
  const selectedPlan = planById.get(selectedContent.planId) ?? null;
  const window = windowFor(compare, selectedPlan);
  const year = sel.year ?? window?.shortcuts.typical ?? years.shortcuts.typical;

  const tiles: TileVM[] = (window?.years ?? []).map((y) => ({
    year: y.year,
    status: y.status,
    percentile: y.percentile,
    isDry: y.is_dry,
    marker: y.year === window?.shortcuts.typical ? "typical" : y.year === window?.shortcuts.dry ? "dry" : undefined,
    selected: y.year === year,
    description:
      y.status === "complete"
        ? `${y.total_mm?.toFixed(1)} mm${y.is_dry ? ", among the driest 20%" : ""}`
        : "no complete record",
  }));

  const row = window?.years.find((y) => y.year === year) ?? null;
  const selectedYear: YearVM | null = row
    ? {
        year: row.year,
        status: row.status,
        totalMm: row.total_mm,
        window: [row.start, row.end],
        rank: row.rank,
        of: row.of,
        isDry: row.is_dry,
        wetnessRoot: row.gwetroot_window_mean,
      }
    : null;

  const cards: CardVM[] = CARDS.map((content) => {
    const plan = planById.get(content.planId) ?? null;
    if (!plan) {
      return {
        key: content.key,
        content,
        plan: null,
        missing: true,
        soil: { mm: null, seasons: null },
        check: { applies: false, count: null, denominator: null },
        era: null,
        metrics: [],
        status: { kind: "unavailable", text: "Not available from the service yet" },
        checks: [],
      };
    }
    const w = windowFor(compare, plan);
    const check = plan.spring_checks.find((c) => c.check_id === "rye_soy_short_gap_moisture");
    const ruleApplies = Boolean(check && check.status !== "inapplicable" && check.count !== null);

    const eraSource = ruleApplies ? plan.eras["rye_soy_short_gap_moisture"] : w?.eras.dry_spring;
    const eraBase = eraVM(eraSource, spans);
    const era = eraBase
      ? { ...eraBase, measure: ruleApplies ? "Springs with a field-moisture check" : "Dry planting windows" }
      : null;

    const cal = plan.calendar;
    const metrics: string[] = [];
    if (cal.termination_gap_days !== null) {
      metrics.push(`${cal.termination_gap_days} days before soybean planting`);
      metrics.push(`${cal.living_cover_days_planned} planned days with living ${plantedLabel(plan)}`);
    } else if (cal.harvest_to_plant_days != null) {
      metrics.push(`${cal.harvest_to_plant_days} days between wheat harvest and soybean planting`);
      metrics.push(`${cal.living_cover_days_planned} planned days with living ${plantedLabel(plan)}`);
    } else {
      metrics.push(`${cal.days_without_planned_cover} days without planned living cover`);
    }

    const yr = w?.years.find((y) => y.year === year);
    let status: CardStatus = null;
    if (!yr || yr.status !== "complete") {
      status = { kind: "unavailable", text: "Weather unavailable for this year" };
    } else if (ruleApplies && check!.qualifying_years.includes(year ?? -1)) {
      status = { kind: "check", text: "Check field moisture" };
    } else if (!ruleApplies && yr.is_dry) {
      status = { kind: "dry", text: "A dry planting window this year" };
    }

    return {
      key: content.key,
      content,
      plan,
      missing: false,
      soil: { mm: plan.winter.per_season_median.rain_mm_without_cover, seasons: plan.winter.eligible_seasons ?? null },
      check: { applies: ruleApplies, count: ruleApplies ? check!.count : null, denominator: ruleApplies ? check!.denominator : null },
      era,
      metrics,
      status,
      checks: plan.other_checks,
    };
  });

  return {
    dataKind: data.origin === "live" ? "live" : compare.meta.draft ? "draft" : "saved",
    locationLabel: years.location.label,
    gridNote: years.location.grid.note,
    requestId: compare.meta.request_id,
    window,
    windowLabel: window ? window.label : "Planting window",
    windowEra: eraVM(window?.eras.dry_spring, spans),
    tiles,
    selectedYear,
    shortcuts: { typical: window?.shortcuts.typical ?? null, dry: window?.shortcuts.dry ?? null },
    cards,
    thresholds: compare.thresholds,
    eraSpans: spans,
  };
}

/** True when a year exists for the selected card's window (used to validate links). */
export function validYears(compare: CompareResponse): Set<number> {
  const out = new Set<number>();
  for (const w of Object.values(compare.spring_windows ?? {})) for (const y of w.years) out.add(y.year);
  return out;
}
