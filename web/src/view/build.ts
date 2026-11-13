import type { CompareResponse, Era, OtherCheck, Plan, SensitivityResponse, SpringWindow, SpringYear, YearsResponse } from "../api/schema";
import type { Origin } from "../api/client";
import { reasonText } from "../data/format";
import {
  CARDS,
  PRIORITY_FIT,
  PRIORITY_INFO,
  PRIORITY_ORDER,
  type CardContent,
  type CardKey,
  type Claim,
  type Leg,
  type Priority,
  type PriorityFit,
} from "../content/strategies";

/*
  Turns backend responses into exactly what the screen shows. Selection only: it never
  computes a total, rank, flag or count (handbook p.4). Where the backend has not sent
  a value, the view says "not available" instead of filling one in.
*/

export type DataKind = "draft" | "saved" | "live";

export interface Selection {
  card: CardKey;
  /** Up to two grower priorities (Phase 7.1). They add badges; they never change a number. */
  priorities?: Priority[];
  /** What the grower reported about the field (Phase 7.3). Unknown is a real answer. */
  observation?: { moisture: Tri; irrigation: Tri };
  year: number | null;
  /** Which winter the strip, charts, 3D and card details show. Default 1 (corn → soybeans). */
  leg?: Leg;
  /** The grower's earlier rye end date to compare on the slider, MM-DD. */
  earlierRyeEnd?: string | null;
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

/** Headline numbers for one leg, shown side by side on the card and never added together. */
type Tri = "yes" | "no" | "unknown";

/** How one plan relates to one chosen priority, with its sourced reason. */
export interface PriorityFitVM {
  priority: Priority;
  label: string;
  fit: PriorityFit;
  reason: Claim;
  /** A backend value or an availability note that belongs next to the reason. */
  detail: string | null;
}

/** A note from what the grower reported about the field. */
export interface ObservationVM {
  kind: "reported" | "unknown" | "context";
  text: string;
  source: Claim["source"];
}

export interface LegSummaryVM {
  leg: Leg;
  title: string;
  short: string;
  plant: string | null;
  planId: string;
  available: boolean;
  reason: string | null;
  soilMm: number | null;
  check: { applies: boolean; count: number | null; denominator: number | null };
  /** Days between ending the cover and planting, from the backend's calendar. */
  gapDays: number | null;
  /** Planned days with living cover (rye or wheat), from the backend's calendar. */
  livingDays: number | null;
  /** This winter's plan, for drawing its calendar. */
  plan: Plan | null;
  /** Every spring in this winter's planting window, for the one-dot-per-spring grid. */
  springs: Array<{ year: number; complete: boolean; dry: boolean | null }>;
  /** Springs where the backend says the moisture check applies. Empty when it does not apply. */
  checkYears: number[];
  selected: boolean;
}

export interface CardVM {
  key: CardKey;
  content: CardContent;
  /** The selected leg's plan; everything below describes that leg. */
  plan: Plan | null;
  leg: Leg;
  legs: LegSummaryVM[];
  missing: boolean;
  /** Why the selected leg is not evaluated (backend reason, code prefix removed). */
  unavailableReason: string | null;
  /** Soil-protection side: median winter rain on ground with no planned living cover. */
  soil: { mm: number | null; seasons: number | null };
  /** Risk side: springs that would have prompted the NC State field-moisture check. */
  check: { applies: boolean; count: number | null; denominator: number | null };
  /** Earlier vs recent for the check where it applies, otherwise for dry planting windows. */
  era: (EraVM & { measure: string }) | null;
  metrics: string[];
  status: CardStatus;
  checks: OtherCheck[];
  priorityFits: PriorityFitVM[];
  observations: ObservationVM[];
  /** One plain sentence that reads the card's two winters (backend values, no comparison between plans). */
  verdict: string;
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
  shortcuts: { typical: number | null; dry: number | null; wet: number | null };
  leg: Leg;
  legTitles: Record<Leg, string>;
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

const CROP: Record<string, string> = { soybean: "soybean", field_corn: "corn" };
export const LEG_TITLE: Record<Leg, string> = { 1: "Corn → soybeans", 2: "Soybeans → corn" };
const cleanReason = (r: string | undefined) => reasonText(r);

function plantedLabel(plan: Plan): string {
  const w = plan.sequence?.winter;
  if (!w) return "cover";
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

  const leg: Leg = sel.leg ?? 1;
  const selectedContent = CARDS.find((c) => c.key === sel.card) ?? CARDS[0]!;
  const selectedPlan = planById.get(selectedContent.legs[leg]) ?? null;
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
  const wetYear = labelsWithheld ? null : (window?.shortcuts.wet ?? null);

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

  // ---------------------------------------------------------------- one leg's details
  type LegDetail = Omit<CardVM, "key" | "content" | "leg" | "legs" | "priorityFits" | "observations" | "verdict">;

  function legDetail(plan: Plan | null): LegDetail {
    if (!plan) {
      return {
        plan: null,
        missing: true,
        unavailableReason: "Not available from the service yet",
        soil: { mm: null, seasons: null },
        check: { applies: false, count: null, denominator: null },
        era: null,
        metrics: [],
        status: { kind: "unavailable", text: "Not available from the service yet" },
        checks: [],
      };
    }
    if (plan.status === "unavailable" || !plan.sequence || !plan.calendar || !plan.winter) {
      const reason = cleanReason(plan.reason) ?? "Not evaluated yet";
      return {
        plan,
        missing: true,
        unavailableReason: reason,
        soil: { mm: null, seasons: null },
        check: { applies: false, count: null, denominator: null },
        era: null,
        metrics: [],
        status: { kind: "unavailable", text: "Not evaluated yet" },
        checks: plan.other_checks,
      };
    }
    const w = windowFor(compare, plan);
    const check = plan.spring_checks.find((c) => c.check_id === "rye_soy_short_gap_moisture");
    const ruleApplies = Boolean(check && check.status !== "inapplicable" && check.count !== null);
    const eraSource = ruleApplies ? plan.eras["rye_soy_short_gap_moisture"] : withheld(w) ? undefined : w?.eras.dry_spring;
    const eraBase = eraVM(eraSource, spans);
    const next = CROP[plan.sequence.next_crop_id] ?? plan.sequence.next_crop_id;
    const cal = plan.calendar;
    const metrics: string[] = [];
    if (cal.termination_gap_days !== null) {
      metrics.push(`${cal.termination_gap_days} days before ${next} planting`);
      metrics.push(`${cal.living_cover_days_planned} planned days with living ${plantedLabel(plan)}`);
    } else if (cal.harvest_to_plant_days != null) {
      metrics.push(`${cal.harvest_to_plant_days} days between wheat harvest and ${next} planting`);
      metrics.push(`${cal.living_cover_days_planned} planned days with living ${plantedLabel(plan)}`);
    } else {
      metrics.push(`${cal.days_without_planned_cover} days without planned living cover`);
    }
    const yr = w?.years.find((y) => y.year === year);
    let status: CardStatus = null;
    if (!yr || yr.status !== "complete") status = { kind: "unavailable", text: "Weather unavailable for this year" };
    else if (ruleApplies && check!.qualifying_years.includes(year ?? -1)) status = { kind: "check", text: "Check field moisture" };
    else if (!ruleApplies && yr.is_dry && !withheld(w)) status = { kind: "dry", text: "A dry planting window this year" };
    return {
      plan,
      missing: false,
      unavailableReason: null,
      soil: { mm: plan.winter.per_season_median.rain_mm_without_cover, seasons: plan.winter.eligible_seasons ?? null },
      check: { applies: ruleApplies, count: ruleApplies ? check!.count : null, denominator: ruleApplies ? check!.denominator : null },
      era: eraBase ? { ...eraBase, measure: ruleApplies ? "Springs with a field-moisture check" : "Dry planting windows" } : null,
      metrics,
      status,
      checks: plan.other_checks,
    };
  }

  function legSprings(d: LegDetail): LegSummaryVM["springs"] {
    if (!d.plan || d.missing) return [];
    const w = windowFor(compare, d.plan);
    return (w?.years ?? []).map((yy) => ({ year: yy.year, complete: yy.status === "complete", dry: withheld(w) ? null : yy.is_dry }));
  }

  function summary(l: Leg, planId: string, d: LegDetail): LegSummaryVM {
    return {
      leg: l,
      title: LEG_TITLE[l],
      short: l === 1 ? "Corn → soy" : "Soy → corn",
      plant: d.plan?.sequence?.next_plant ?? null,
      planId,
      available: !d.missing,
      reason: d.unavailableReason,
      soilMm: d.soil.mm,
      check: d.check,
      gapDays: d.plan?.calendar?.termination_gap_days ?? null,
      livingDays: d.missing ? null : (d.plan?.calendar?.living_cover_days_planned ?? null),
      plan: d.plan,
      springs: legSprings(d),
      checkYears: d.check.applies ? (d.plan?.spring_checks.find((c) => c.check_id === "rye_soy_short_gap_moisture")?.qualifying_years ?? []) : [],
      selected: l === leg,
    };
  }

  const cards: CardVM[] = CARDS.map((content) => {
    const details: Record<Leg, LegDetail> = {
      1: legDetail(planById.get(content.legs[1]) ?? null),
      2: legDetail(planById.get(content.legs[2]) ?? null),
    };
    return {
      key: content.key,
      content,
      leg,
      legs: ([1, 2] as Leg[]).map((l) => summary(l, content.legs[l], details[l])),
      ...details[leg],
      priorityFits: [],
      observations: [],
      verdict: "",
    };
  });

  // ---------------------------------------------------------------- rye slider (Phase 5), leg 1 of winter cover
  const sens = data.sensitivity;
  const ryeContent = CARDS.find((c) => c.key === "cover")!;
  const ryePlan = planById.get(sens?.base_plan_id ?? ryeContent.legs[1]) ?? null;
  let rye: RyeVM | null = null;
  if (sens && ryePlan?.sequence?.winter.type === "cover" && sens.points.length) {
    const pts = sens.points;
    const proposedMd = ryePlan.sequence.winter.terminate;
    const proposedIndex = Math.max(0, pts.findIndex((p) => p.terminate === proposedMd));
    const chosenIndex = sel.ryeEnd ? pts.findIndex((p) => p.terminate === sel.ryeEnd) : -1;
    const index = chosenIndex >= 0 ? chosenIndex : proposedIndex;
    const chosen = pts[index]!;
    const earlierIndex = sel.earlierRyeEnd ? pts.findIndex((p) => p.terminate === sel.earlierRyeEnd) : -1;
    let boundaryIndex: number | null = null;
    pts.forEach((p, i) => {
      if (p.gap_days >= 14) boundaryIndex = i;
    });
    const baseCheck = ryePlan.spring_checks.find((c) => c.check_id === sens.check_id);
    rye = {
      points: pts,
      denominator: sens.denominator,
      index,
      proposedIndex,
      earlierIndex: earlierIndex >= 0 && earlierIndex !== proposedIndex ? earlierIndex : null,
      boundaryIndex,
      chosen,
      proposed: pts[proposedIndex]!,
      plant: sens.fixed.next_plant,
      seed: sens.fixed.seed,
      changed: index !== proposedIndex,
      thisYear: year === null || leg !== 1 ? null : { year, flagged: chosen.qualifying_years ? chosen.qualifying_years.includes(year) : null },
      era: eraVM(chosen.eras, spans),
      rule: { label: baseCheck?.fires_when ?? "gap < 14 days AND (dry replay OR grower low-moisture concern)", source: baseCheck?.source ?? null },
    };

    // The winter-cover card's leg 1, its 3D field and its calendar row follow the chosen date.
    if (rye.changed) {
      const ci = cards.findIndex((c) => c.key === "cover");
      const card = cards[ci]!;
      const seq = ryePlan.sequence;
      const moved: Plan = {
        ...ryePlan,
        sequence: { ...seq, winter: { ...seq.winter, terminate: chosen.terminate } },
        calendar: { ...ryePlan.calendar!, termination_gap_days: chosen.gap_days, living_cover_days_planned: chosen.living_cover_days_planned },
      };
      const legs = card.legs.map((l) =>
        l.leg === 1
          ? {
              ...l,
              soilMm: chosen.rain_mm_without_cover_median,
              check: { applies: true, count: chosen.checks_count, denominator: sens.denominator },
              gapDays: chosen.gap_days,
              livingDays: chosen.living_cover_days_planned,
              plan: moved,
              checkYears: chosen.qualifying_years ?? [],
            }
          : l,
      );
      if (leg === 1) {
        const w = windowFor(compare, moved);
        const yr = w?.years.find((y) => y.year === year);
        let status: CardStatus = null;
        if (!yr || yr.status !== "complete") status = { kind: "unavailable", text: "Weather unavailable for this year" };
        else if (!chosen.qualifying_years) status = { kind: "unavailable", text: "This spring's check is not available for this date" };
        else if (chosen.qualifying_years.includes(year ?? -1)) status = { kind: "check", text: "Check field moisture" };
        const eraBase = eraVM(chosen.eras, spans);
        cards[ci] = {
          ...card,
          legs,
          plan: moved,
          soil: { ...card.soil, mm: chosen.rain_mm_without_cover_median },
          check: { applies: true, count: chosen.checks_count, denominator: sens.denominator },
          era: eraBase ? { ...eraBase, measure: "Springs with a field-moisture check" } : null,
          metrics: [`${chosen.gap_days} days before soybean planting`, `${chosen.living_cover_days_planned} planned days with living rye`],
          status,
        };
      } else {
        cards[ci] = { ...card, legs };
      }
    }
  }

  // ---------------------------------------------------------------- priorities and field observations (Phase 7)
  // Badges and notes only: the card order and every number stay as the backend sent them.
  const chosenPriorities = PRIORITY_ORDER.filter((p) => sel.priorities?.includes(p));
  const observation = sel.observation ?? { moisture: "unknown", irrigation: "unknown" };
  for (let i = 0; i < cards.length; i++) {
    const card = cards[i]!;
    const notEvaluated = card.legs.filter((l) => !l.available).map((l) => `The ${l.short.toLowerCase()} winter is not evaluated yet.`);
    const priorityFits: PriorityFitVM[] = chosenPriorities.flatMap((p) => {
      const f = PRIORITY_FIT[card.key][p];
      if (!f) return [];
      const moistureCheck = card.legs.find((l) => l.check.applies && l.check.count !== null);
      const detail =
        p === "water" && f.fit === "tradeoff" && moistureCheck
          ? `Check field moisture in ${moistureCheck.check.count} of ${moistureCheck.check.denominator} springs (${moistureCheck.short.toLowerCase()}).`
          : notEvaluated.length && f.fit !== "tradeoff"
            ? notEvaluated.join(" ")
            : null;
      return [{ priority: p, label: PRIORITY_INFO[p].short, fit: f.fit, reason: f.reason, detail }];
    });
    // Field observations matter only where the NC State moisture check applies (rye before soybeans).
    const checked = card.legs.find((l) => l.check.applies);
    const observations: ObservationVM[] = [];
    if (checked) {
      if (observation.moisture === "yes") {
        observations.push({
          kind: "reported",
          text:
            "You reported a field moisture concern. NC State suggests ending rye at least 14 days before soybean planting" +
            (checked.gapDays !== null ? `; this plan ends it ${checked.gapDays} days before.` : "."),
          source: "ncs-soy-4",
        });
      } else if (observation.moisture === "unknown") {
        observations.push({
          kind: "unknown",
          text: "Field moisture concern: unknown. Check the field before deciding when to end the rye.",
          source: null,
        });
      }
      if (observation.irrigation === "yes") {
        observations.push({ kind: "context", text: "Irrigation noted as context. It does not change the moisture check.", source: null });
      }
    }
    cards[i] = { ...card, priorityFits, observations, verdict: verdictFor(card.legs) };
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
    shortcuts: { typical: typicalYear, dry: dryYear, wet: wetYear },
    leg,
    legTitles: LEG_TITLE,
    labelsWithheld,
    contrastWithheld,
    chart,
    wetness,
    cards,
    // Each planting date has its own dry cutoff; the screens read the selected window's.
    thresholds: { ...compare.thresholds, dry_spring: window?.threshold ?? compare.thresholds.dry_spring },
    eraSpans: spans,
  };
}

/** True when a year exists for the selected card's window (used to validate links). */
export function validYears(compare: CompareResponse): Set<number> {
  const out = new Set<number>();
  for (const w of Object.values(compare.spring_windows ?? {})) for (const y of w.years) out.add(y.year);
  return out;
}

/** A plain reading of one card's two winters. Wording only: every number is the backend's. */
export function verdictFor(legs: LegSummaryVM[]): string {
  const short = (l: LegSummaryVM) => l.short.toLowerCase();
  const available = legs.filter((l) => l.available);
  const living = available.filter((l) => (l.livingDays ?? 0) > 0);
  const bare = available.filter((l) => l.livingDays === 0);
  const parts: string[] = [];
  if (living.length) {
    parts.push(`Living cover is planned for ${living.map((l) => `${l.livingDays} days (${short(l)})`).join(" and ")}.`);
  }
  if (bare.length) {
    parts.push(
      bare.length === legs.length
        ? "No living cover is planned in either winter."
        : `No living cover is planned in the ${bare.map(short).join(" and ")} winter.`,
    );
  }
  const checked = available.filter((l) => l.check.applies && l.check.count !== null);
  for (const l of checked) parts.push(`Check field moisture in ${l.check.count} of ${l.check.denominator} springs (${short(l)}).`);
  if (!checked.length && available.length === legs.length && !living.length) parts.push("The rye timing check does not apply.");
  for (const l of legs.filter((x) => !x.available)) parts.push(`The ${short(l)} winter is not evaluated yet.`);
  return parts.join(" ");
}
