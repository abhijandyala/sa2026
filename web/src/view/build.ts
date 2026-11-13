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
  /** Rye end date from the slider, MM-DD; null = the plan's proposed date. */
  ryeEnd?: string | null;
}

export type SweepPoint = SensitivityResponse["points"][number];

/** The rye deep-dive (Phase 5). Every number is a value from the backend's sweep. */
export interface RyeVM {
  points: SweepPoint[];
  denominator: number;
  index: number;
  proposedIndex: number;
  earlierIndex: number | null;
  /** Last point with a gap of 14 days or more (the boundary of NC State's guidance). */
  boundaryIndex: number | null;
  chosen: SweepPoint;
  proposed: SweepPoint;
  plant: string;
  seed: string;
  changed: boolean;
  thisYear: { year: number; flagged: boolean | null } | null;
  era: EraVM | null;
  rule: { label: string; source: { title: string; url: string } | null };
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

/** One bar in the rainfall chart (card 3.3). Values straight from the backend. */
export interface BarVM {
  year: number;
  mm: number | null;
  status: SpringYear["status"];
  isDry: boolean | null;
  selected: boolean;
}

export interface ChartVM {
  bars: BarVM[];
  medianMm: number | null;
  cutoffMm: number | null;
  /** Axis top, rounded up to a clean step. Drawing scale only; fixed per planting window. */
  axisMax: number;
  axisStep: number;
  excluded: number[];
}

export interface WetnessVM {
  points: Array<{ year: number; value: number; selected: boolean }>;
  selected: number | null;
  missingYears: number[];
}

/** One field in the 3D view (Phase 4): the plan and the selected spring for its own window. */
export interface StripVM {
  key: CardKey;
  name: string;
  plan: Plan | null;
  selected: boolean;
  status: CardStatus;
  /** Raw values from the backend; the scene maps them to visuals only. */
  weather: {
    year: number | null;
    complete: boolean;
    totalMm: number | null;
    medianMm: number | null;
    wetness: number | null;
    wetnessRange: [number, number] | null;
  };
}

/** Playbook p.23: show at least 15 complete years before relative labels. */
export const MIN_COMPLETE_YEARS = 15;

export interface ViewModel {
  dataKind: DataKind;
  locationLabel: string;
  gridNote: string;
  grid: { lat: number; lon: number; source: string };
  requestId: string;
  snapshotHash: string;
  catalogVersion: string;
  window: SpringWindow | null;
  windowLabel: string;
  windowEra: EraVM | null;
  tiles: TileVM[];
  selectedYear: YearVM | null;
  shortcuts: { typical: number | null; dry: number | null };
  /** Too few complete years, or the backend did not rank this window: no dry labels anywhere. */
  labelsWithheld: boolean;
  /** No meaningful dry contrast (the backend sent no dry replay year). */
  contrastWithheld: boolean;
  chart: ChartVM;
  wetness: WetnessVM;
  cards: CardVM[];
  strips: StripVM[];
  rye: RyeVM | null;
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

/** Same gate as the strip, for any planting window. */
function withheld(w: SpringWindow | null): boolean {
  if (!w || w.threshold.status !== "complete" || w.dry_count === null) return true;
  return w.years.filter((y) => y.status === "complete").length < MIN_COMPLETE_YEARS;
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
  const year =
    sel.year ??
    window?.shortcuts.typical ??
    window?.years.find((y) => y.status === "complete")?.year ??
    years.shortcuts.typical;

  const complete = (window?.years ?? []).filter((y) => y.status === "complete");
  const labelsWithheld =
    !window ||
    window.threshold.status !== "complete" ||
    window.dry_count === null ||
    complete.length < MIN_COMPLETE_YEARS;
  const contrastWithheld = labelsWithheld || !window?.shortcuts.dry;
  const typicalYear = labelsWithheld ? null : (window?.shortcuts.typical ?? null);
  const dryYear = contrastWithheld ? null : (window?.shortcuts.dry ?? null);

  const tiles: TileVM[] = (window?.years ?? []).map((y) => ({
    year: y.year,
    status: y.status,
    percentile: labelsWithheld ? null : y.percentile,
    isDry: labelsWithheld ? null : y.is_dry,
    marker: y.year === typicalYear ? "typical" : y.year === dryYear ? "dry" : undefined,
    selected: y.year === year,
    description:
      y.status === "complete"
        ? `${y.total_mm === 0 ? "0.0 mm, no rain" : `${y.total_mm?.toFixed(1)} mm`}${!labelsWithheld && y.is_dry ? ", among the driest 20%" : ""}`
        : y.status === "partial"
          ? "incomplete record, not compared"
          : "no weather record",
  }));

  const totals = complete.map((y) => y.total_mm ?? 0);
  const peak = Math.max(0, ...totals, window?.median_mm ?? 0);
  const axisStep = peak <= 60 ? 10 : peak <= 150 ? 25 : peak <= 300 ? 50 : 100;
  const chart: ChartVM = {
    bars: (window?.years ?? []).map((y) => ({
      year: y.year,
      mm: y.status === "complete" ? y.total_mm : null,
      status: y.status,
      isDry: labelsWithheld ? null : y.is_dry,
      selected: y.year === year,
    })),
    medianMm: labelsWithheld ? null : (window?.median_mm ?? null),
    cutoffMm: labelsWithheld ? null : (window?.threshold.value ?? null),
    axisMax: Math.max(axisStep, Math.ceil(peak / axisStep) * axisStep),
    axisStep,
    excluded: (window?.years ?? []).filter((y) => y.status !== "complete").map((y) => y.year),
  };

  const wetness: WetnessVM = {
    points: complete
      .filter((y) => y.gwetroot_window_mean !== null)
      .map((y) => ({ year: y.year, value: y.gwetroot_window_mean!, selected: y.year === year })),
    selected: complete.find((y) => y.year === year)?.gwetroot_window_mean ?? null,
    missingYears: complete.filter((y) => y.gwetroot_window_mean === null).map((y) => y.year),
  };

  const row = window?.years.find((y) => y.year === year) ?? null;
  const selectedYear: YearVM | null = row
    ? {
        year: row.year,
        status: row.status,
        totalMm: row.total_mm,
        window: [row.start, row.end],
        rank: labelsWithheld ? null : row.rank,
        of: labelsWithheld ? null : row.of,
        isDry: labelsWithheld ? null : row.is_dry,
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

    const eraSource = ruleApplies ? plan.eras["rye_soy_short_gap_moisture"] : withheld(w) ? undefined : w?.eras.dry_spring;
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
    } else if (!ruleApplies && yr.is_dry && !withheld(w)) {
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

  // ---------------------------------------------------------------- rye slider (Phase 5)
  const sens = data.sensitivity;
  const rye12 = planById.get("rye_12d") ?? null;
  const rye19 = planById.get("rye_19d") ?? null;
  let rye: RyeVM | null = null;
  if (sens && rye12 && rye12.sequence.winter.type === "cover" && sens.points.length) {
    const pts = sens.points;
    const proposedMd = rye12.sequence.winter.terminate;
    const proposedIndex = Math.max(0, pts.findIndex((p) => p.terminate === proposedMd));
    const chosenIndex = sel.ryeEnd ? pts.findIndex((p) => p.terminate === sel.ryeEnd) : -1;
    const index = chosenIndex >= 0 ? chosenIndex : proposedIndex;
    const chosen = pts[index]!;
    const earlierMd = rye19?.sequence.winter.type === "cover" ? rye19.sequence.winter.terminate : null;
    const earlierIndex = earlierMd ? pts.findIndex((p) => p.terminate === earlierMd) : -1;
    let boundaryIndex: number | null = null;
    pts.forEach((p, i) => {
      if (p.gap_days >= 14) boundaryIndex = i;
    });
    const check12 = rye12.spring_checks.find((c) => c.check_id === sens.check_id);
    rye = {
      points: pts,
      denominator: sens.denominator,
      index,
      proposedIndex,
      earlierIndex: earlierIndex >= 0 ? earlierIndex : null,
      boundaryIndex,
      chosen,
      proposed: pts[proposedIndex]!,
      plant: sens.fixed.next_plant,
      seed: sens.fixed.seed,
      changed: index !== proposedIndex,
      thisYear:
        year === null ? null : { year, flagged: chosen.qualifying_years ? chosen.qualifying_years.includes(year) : null },
      era: eraVM(chosen.eras, spans),
      rule: { label: check12?.fires_when ?? "gap < 14 days AND (dry replay OR grower low-moisture concern)", source: check12?.source ?? null },
    };

    // The cover card, its 3D field and its calendar row follow the chosen date.
    if (rye.changed) {
      const ci = cards.findIndex((c) => c.key === "cover" && c.plan?.plan_id === "rye_12d");
      const card = cards[ci];
      if (card && card.plan && card.plan.sequence.winter.type === "cover") {
        const plan: Plan = {
          ...card.plan,
          sequence: { ...card.plan.sequence, winter: { ...card.plan.sequence.winter, terminate: chosen.terminate } },
          calendar: {
            ...card.plan.calendar,
            termination_gap_days: chosen.gap_days,
            living_cover_days_planned: chosen.living_cover_days_planned,
          },
        };
        const w = windowFor(compare, plan);
        const yr = w?.years.find((y) => y.year === year);
        let status: CardStatus = null;
        if (!yr || yr.status !== "complete") status = { kind: "unavailable", text: "Weather unavailable for this year" };
        else if (!chosen.qualifying_years) status = { kind: "unavailable", text: "This spring's check is not available for this date" };
        else if (chosen.qualifying_years.includes(year ?? -1)) status = { kind: "check", text: "Check field moisture" };
        const eraBase = eraVM(chosen.eras, spans);
        cards[ci] = {
          ...card,
          plan,
          soil: { ...card.soil, mm: chosen.rain_mm_without_cover_median },
          check: { applies: true, count: chosen.checks_count, denominator: sens.denominator },
          era: eraBase ? { ...eraBase, measure: "Springs with a field-moisture check" } : null,
          metrics: [`${chosen.gap_days} days before soybean planting`, `${chosen.living_cover_days_planned} planned days with living rye`],
          status,
        };
      }
    }
  }

  return {
    dataKind: data.origin === "live" ? "live" : compare.meta.draft ? "draft" : "saved",
    locationLabel: years.location.label,
    gridNote: years.location.grid.note,
    grid: { lat: years.location.grid.lat, lon: years.location.grid.lon, source: years.location.grid.source },
    requestId: compare.meta.request_id,
    snapshotHash: compare.meta.snapshot_hash,
    catalogVersion: compare.meta.catalog_version,
    window,
    windowLabel: window ? window.label : "Planting window",
    windowEra: labelsWithheld ? null : eraVM(window?.eras.dry_spring, spans),
    tiles,
    selectedYear,
    rye,
    strips: cards.map((c) => {
      const w = windowFor(compare, c.plan);
      const yr = w?.years.find((r) => r.year === year) ?? null;
      const wets = (w?.years ?? []).map((r) => r.gwetroot_window_mean).filter((v): v is number => v !== null);
      return {
        key: c.key,
        name: c.content.name,
        plan: c.plan,
        selected: c.key === sel.card,
        status: c.status,
        weather: {
          year: yr?.year ?? null,
          complete: yr?.status === "complete",
          totalMm: yr?.status === "complete" ? yr.total_mm : null,
          medianMm: withheld(w) ? null : (w?.median_mm ?? null),
          wetness: yr?.gwetroot_window_mean ?? null,
          wetnessRange: wets.length ? [Math.min(...wets), Math.max(...wets)] : null,
        },
      };
    }),
    shortcuts: { typical: typicalYear, dry: dryYear },
    labelsWithheld,
    contrastWithheld,
    chart,
    wetness,
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
