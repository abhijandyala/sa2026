import { z } from "zod";
import {
  CompareResponse,
  Meta,
  SensitivityResponse,
  Status,
  Threshold,
  YearsResponse,
  type Era,
  type Plan,
  type PlanInput,
  type ReplayResponse,
  type SpringWindow,
} from "./schema";

/*
  The boundary with Rahul's backend (Phase 12, backend branch at b51c804, Nov 14 2026).

  `Backend*` below are the real response shapes, field for field (docs/api/openapi.json and
  the generated examples). `adapt*` turns them into the model the screens were built on
  (schema.ts). Adapting only renames, selects and regroups values the backend already
  returned. It never computes a total, a rank, a count or a threshold.

  Since d7d3367 the compare and sensitivity responses carry everything the screens need:
  typical / dry / wet springs (`spring.shortcuts`), modeled soil wetness for each spring
  (`seasons[].gwet*_window_mean`), the springs each rye end date flags (`qualifying_years`),
  a plain sentence for each rule (`other_checks[].text`, `print`) and for each reason code
  (`reason_text`). The older sources (GET /v1/years, the saved wetness.json, the sweep's
  `dry_years`) are read only when a response from an older service leaves a value out.

  Since b51c804 every response is for one place (`location_id` or a point in the request,
  `weather_location` and that place's own thresholds in the answer). A plan compared outside
  the region its sample dates were assumed for carries a `region_note`.
*/

const md = z.string().regex(/^\d{2}-\d{2}$/, "expected MM-DD");
const int = z.number().int();

const BackendEraPart = z.object({ evaluable: int, events: int, pct: z.number().nullable() }).passthrough();
const BackendEra = z
  .object({ earlier: BackendEraPart, recent: BackendEraPart, diff_pp: z.number().nullable(), result: z.string(), caveat: z.string() })
  .passthrough();
type BackendEra = z.infer<typeof BackendEra>;

const BackendPlanDates = z
  .object({
    plan_id: z.string(),
    previous_crop_id: z.string(),
    prev_harvest: md,
    next_crop_id: z.string(),
    next_plant: md,
    winter: z
      .object({
        kind: z.enum(["none", "cover", "winter_grain"]),
        crop_id: z.string().nullable().optional(),
        seed: md.nullable().optional(),
        terminate: md.nullable().optional(),
        plant: md.nullable().optional(),
        harvest: md.nullable().optional(),
      })
      .passthrough(),
  })
  .passthrough();

const BackendSeason = z
  .object({
    year: int,
    spring_status: Status,
    spring_total_mm: z.number().nullable(),
    spring_rank: int.nullable(),
    spring_is_dry: z.boolean().nullable(),
    winter_status: Status,
    rain_outside_cover_mm: z.number().nullable(),
    // Modeled soil wetness over the same spring window as the replay; null when the window is incomplete.
    gwettop_window_mean: z.number().nullable().optional(),
    gwetroot_window_mean: z.number().nullable().optional(),
  })
  .passthrough();

const Shortcuts = z.object({ typical: int.nullable(), dry: int.nullable(), wet: int.nullable() }).passthrough();

const BackendPlan = z
  .object({
    plan_id: z.string(),
    label: z.string().nullable().optional(),
    status: Status,
    reason: z.string().nullable().optional(),
    // A plain sentence beside a reason that is a code (or the short form of a long one).
    reason_text: z.string().nullable().optional(),
    leg: z.union([z.literal(1), z.literal(2)]).nullable().optional(),
    rotation_id: z.string().nullable().optional(),
    editable: z.array(z.string()).nullable().optional(),
    dates_assumed: z.boolean().nullable().optional(),
    // At a place outside the region the sample dates were assumed for, the backend says so.
    region_note: z.string().nullable().optional(),
    plan: BackendPlanDates.nullable().optional(),
    calendar: z
      .object({
        living_cover_days_planned: int,
        days_without_planned_cover: int,
        termination_gap_days: int.nullable(),
        establishment: z.string(),
        spring_window: z.object({ start: md, end: md }).passthrough(),
      })
      .passthrough()
      .nullable()
      .optional(),
    winter: z
      .object({
        status: Status,
        eligible_seasons: int.optional(),
        segments: z.array(z.string()).default([]),
        per_season_median: z
          .object({ rain_mm_outside_cover: z.number().nullable(), heavy_rain_days_outside_cover: z.number().nullable() })
          .passthrough(),
      })
      .passthrough()
      .nullable()
      .optional(),
    spring: z
      .object({
        status: Status,
        median_total_mm: z.number().nullable(),
        dry_seasons: int.nullable(),
        eligible_seasons: int,
        // Typical, dry and wet springs for this plan's own planting date (so edited dates get them too).
        shortcuts: Shortcuts.nullable().optional(),
      })
      .passthrough()
      .nullable()
      .optional(),
    spring_checks: z
      .array(
        z
          .object({
            check_id: z.string(),
            rule_ids: z.array(z.string()),
            label: z.string().optional(),
            fires_when: z.string().optional(),
            count: int.nullable(),
            denominator: int.nullable(),
            pct: z.number().nullable(),
            qualifying_years: z.array(int),
            skipped_years: z.array(z.unknown()),
            source: z.object({ title: z.string(), url: z.string() }).passthrough().nullable().optional(),
          })
          .passthrough(),
      )
      .default([]),
    other_checks: z
      .array(
        z
          .object({
            rule_id: z.string(),
            verdict: z.string().nullable(),
            status: Status.optional(),
            reason: z.string(),
            // One sentence for the grower, and whether the line is worth a printed page.
            text: z.string().optional(),
            print: z.boolean().optional(),
          })
          .passthrough(),
      )
      .default([]),
    eras: z.record(BackendEra).default({}),
    seasons: z.array(BackendSeason).default([]),
    // A wheat double-crop plan also carries its own block (its dates and its own-window baseline).
    double_crop: z
      .object({ winter_exposure: z.object({ status: Status, reason: z.string().nullable().optional() }).passthrough().nullable().optional() })
      .passthrough()
      .nullable()
      .optional(),
  })
  .passthrough();
type BackendPlan = z.infer<typeof BackendPlan>;

export const BackendCompare = z
  .object({
    meta: Meta,
    request_echo: z.object({ location_id: z.string().nullable().optional() }).passthrough(),
    thresholds: z.object({ heavy_rain: Threshold, dry_spring: z.record(Threshold) }).passthrough(),
    // The real service lists the years; the draft examples gave only how many.
    shared_eligible_years: z.object({ spring: z.array(int), winter: z.array(int) }).passthrough(),
    plans: z.array(BackendPlan).min(1),
  })
  .passthrough();
export type BackendCompare = z.infer<typeof BackendCompare>;

export const BackendRotations = z
  .object({ rotations: z.array(z.object({ rotation_id: z.string(), label: z.string(), legs: z.array(z.string()).min(1) }).passthrough()) })
  .passthrough();
export type BackendRotations = z.infer<typeof BackendRotations>;

/** GET /v1/years?plan=…: the same shape the screens use, plus which plan's dates it was built on. */
export const BackendYears = YearsResponse.and(z.object({ plan_basis: z.object({ plan_id: z.string(), next_plant: md }).passthrough().optional() }));
export type BackendYears = z.infer<typeof BackendYears>;

export const BackendSensitivity = z
  .object({
    meta: Meta,
    base_plan_id: z.string(),
    varied: z.literal("terminate"),
    fixed: z.object({ next_plant: md, seed: md }).passthrough(),
    check_id: z.string(),
    denominator: int,
    dry_years: z.array(int).optional(),
    points: z
      .array(
        z
          .object({
            terminate: md,
            gap_days: int,
            living_cover_days_planned: int,
            rain_outside_cover_mm_median: z.number().nullable(),
            checks_count: int.nullable(),
            // The springs this end date would have flagged.
            qualifying_years: z.array(int).optional(),
          })
          .passthrough(),
      )
      .min(1),
  })
  .passthrough();
export type BackendSensitivity = z.infer<typeof BackendSensitivity>;

const WetnessBlock = z.object({ gwettop_window_mean: z.number().nullable(), gwetroot_window_mean: z.number().nullable() }).passthrough();
/** wetness.json: plan id → year → the `wetness` block of that season's replay. */
export const SavedWetness = z.record(z.record(WetnessBlock.nullable()));
export type SavedWetness = z.infer<typeof SavedWetness>;

/** GET /v1/seasons/{year}/replay: daily rows carry `in_spring_window`. */
const BackendReplayDay = z.object({ in_spring_window: z.boolean().optional() }).passthrough();

// ------------------------------------------------------------------ helpers

const VERDICTS = ["preferred", "acceptable", "caution", "avoid", "manual_check", "unknown", "inapplicable"] as const;
type Verdict = (typeof VERDICTS)[number];
const asVerdict = (v: string | null | undefined, status: string | undefined): Verdict =>
  (VERDICTS as readonly string[]).includes(v ?? "") ? (v as Verdict) : (VERDICTS as readonly string[]).includes(status ?? "") ? (status as Verdict) : "unknown";

const ERA_RESULTS = ["more_frequent_recent", "less_frequent_recent", "similar", "insufficient_data"] as const;
function era(e: BackendEra): Era {
  return {
    ...e,
    earlier: { ...e.earlier, count: e.earlier.events, denominator: e.earlier.evaluable, pct: e.earlier.pct },
    recent: { ...e.recent, count: e.recent.events, denominator: e.recent.evaluable, pct: e.recent.pct },
    diff_pp: e.diff_pp,
    result: (ERA_RESULTS as readonly string[]).includes(e.result) ? (e.result as Era["result"]) : "insufficient_data",
    caveat: e.caveat,
  };
}

/** One spring window per planting date. The id is only a key the screens use to look it up. */
export const windowId = (plant: string) => `plant_${plant}`;

const CROP_LABEL: Record<string, string> = { soybean: "soybean", field_corn: "corn" };

function plan(p: BackendPlan): Plan {
  const d = p.plan ?? null;
  const w = d?.winter;
  const sequence = d
    ? {
        previous_crop_id: d.previous_crop_id,
        prev_harvest: d.prev_harvest,
        next_crop_id: d.next_crop_id,
        next_plant: d.next_plant,
        winter:
          w?.kind === "cover" && w.crop_id && w.seed && w.terminate
            ? ({ type: "cover", crop_id: w.crop_id, seed: w.seed, terminate: w.terminate } as const)
            : w?.kind === "winter_grain" && w.crop_id && w.plant && w.harvest
              ? ({ type: "winter_grain", crop_id: w.crop_id, plant: w.plant, harvest: w.harvest } as const)
              : ({ type: "none" } as const),
      }
    : undefined;
  return {
    plan_id: p.plan_id,
    label: p.label ?? p.plan_id,
    rotation_id: p.rotation_id ?? undefined,
    leg: p.leg ?? undefined,
    status: p.status,
    // The backend's plain sentence when it gives one; with no winter figure, its words for that figure.
    reason: p.reason_text || (!p.winter && p.double_crop?.winter_exposure?.reason) || p.reason || undefined,
    double_crop: p.double_crop ?? undefined,
    editable: p.editable ?? undefined,
    dates_assumed: p.dates_assumed ?? undefined,
    region_note: p.region_note ?? undefined,
    sequence,
    spring_window: p.calendar ? { start: p.calendar.spring_window.start, end: p.calendar.spring_window.end } : undefined,
    spring_window_id: d ? windowId(d.next_plant) : undefined,
    calendar: p.calendar
      ? {
          living_cover_days_planned: p.calendar.living_cover_days_planned,
          days_without_planned_cover: p.calendar.days_without_planned_cover,
          termination_gap_days: p.calendar.termination_gap_days,
          establishment: p.calendar.establishment,
        }
      : undefined,
    winter: p.winter
      ? {
          status: p.winter.status,
          eligible_seasons: p.winter.eligible_seasons,
          segments: p.winter.segments,
          per_season_median: {
            rain_mm_without_cover: p.winter.per_season_median.rain_mm_outside_cover,
            heavy_rain_days_without_cover: p.winter.per_season_median.heavy_rain_days_outside_cover,
          },
          per_season: p.seasons.map((s) => ({ year: s.year, rain_mm_without_cover: s.rain_outside_cover_mm, status: s.winter_status })),
        }
      : undefined,
    spring_checks: p.spring_checks.map((c) => ({ ...c, source: c.source ?? undefined })),
    other_checks: p.other_checks.map((c) => ({ ...c, verdict: asVerdict(c.verdict, c.status) })),
    eras: Object.fromEntries(Object.entries(p.eras).map(([k, e]) => [k, era(e)])),
  };
}

/** Fallback values for a response from an older service, keyed by planting date (MM-DD). */
export interface CompareExtras {
  rotations?: BackendRotations | null;
  /** Shortcut years per planting date, from GET /v1/years for a plan with that date. */
  shortcuts?: Record<string, { typical: number | null; dry: number | null; wet: number | null }>;
  wetness?: SavedWetness | null;
}

/** Shortcut years keyed by the planting date each /v1/years answer was built on. */
export function shortcutsByPlant(years: Array<BackendYears | null | undefined>): NonNullable<CompareExtras["shortcuts"]> {
  const out: NonNullable<CompareExtras["shortcuts"]> = {};
  for (const y of years) if (y?.plan_basis) out[y.plan_basis.next_plant] = y.shortcuts;
  return out;
}

export function adaptCompare(real: BackendCompare, extras: CompareExtras = {}): CompareResponse {
  const windows: Record<string, SpringWindow> = {};
  for (const p of real.plans) {
    const d = p.plan;
    if (!d || !p.calendar || !p.spring) continue;
    const id = windowId(d.next_plant);
    if (windows[id]) continue;
    const threshold = real.thresholds.dry_spring[d.next_plant];
    const dry = p.eras["dry_spring"];
    if (!threshold || !dry) continue;
    const wet = extras.wetness?.[p.plan_id];
    const of = p.spring.eligible_seasons;
    windows[id] = {
      id,
      label: `The 30 days before ${CROP_LABEL[d.next_crop_id] ?? "the next crop's"} planting`,
      plant: d.next_plant,
      start: p.calendar.spring_window.start,
      end: p.calendar.spring_window.end,
      threshold,
      median_mm: p.spring.median_total_mm,
      dry_count: p.spring.dry_seasons,
      denominator: of,
      shortcuts: p.spring.shortcuts ?? extras.shortcuts?.[d.next_plant] ?? { typical: null, dry: null, wet: null },
      years: p.seasons.map((s) => ({
        year: s.year,
        start: `${s.year}-${p.calendar!.spring_window.start}`,
        end: `${s.year}-${p.calendar!.spring_window.end}`,
        total_mm: s.spring_total_mm,
        status: s.spring_status,
        rank: s.spring_rank,
        of: s.spring_rank === null ? null : of,
        percentile: null,
        is_dry: s.spring_is_dry,
        gwettop_window_mean: s.gwettop_window_mean !== undefined ? s.gwettop_window_mean : (wet?.[String(s.year)]?.gwettop_window_mean ?? null),
        gwetroot_window_mean: s.gwetroot_window_mean !== undefined ? s.gwetroot_window_mean : (wet?.[String(s.year)]?.gwetroot_window_mean ?? null),
      })),
      eras: { dry_spring: era(dry) },
    };
  }
  const first = real.plans.find((p) => p.plan)?.plan?.next_plant;
  const out = {
    ...real,
    request_echo: { ...real.request_echo, location_id: real.request_echo.location_id ?? "custom" },
    shared_eligible_years: {
      ...real.shared_eligible_years,
      spring: real.shared_eligible_years.spring.length,
      winter: real.shared_eligible_years.winter.length,
      spring_years: real.shared_eligible_years.spring,
      winter_years: real.shared_eligible_years.winter,
    },
    thresholds: {
      ...real.thresholds,
      heavy_rain: real.thresholds.heavy_rain,
      // The screens read one cutoff at a time; the view builder swaps in the selected window's own.
      dry_spring: (first && real.thresholds.dry_spring[first]) ?? Object.values(real.thresholds.dry_spring)[0] ?? { value: null, unit: "mm", method: "not available", status: "unavailable" as const },
      dry_spring_by_plant: real.thresholds.dry_spring,
    },
    plans: real.plans.map(plan),
    rotations: (extras.rotations?.rotations ?? []).map((r) => ({
      rotation_id: r.rotation_id,
      label: r.label,
      legs: r.legs.slice(0, 2).map((plan_id, i) => ({ leg: (i + 1) as 1 | 2, plan_id })),
    })),
    spring_windows: windows,
  };
  // The adapted object must satisfy the model the screens were built on.
  return CompareResponse.parse(out);
}

export function adaptSensitivity(real: BackendSensitivity): SensitivityResponse {
  const dry = real.dry_years;
  return SensitivityResponse.parse({
    ...real,
    points: real.points.map((p) => ({
      ...p,
      rain_mm_without_cover_median: p.rain_outside_cover_mm_median,
      // The point's own list. An older service gave only the sweep's dry springs: use that list
      // just when the point's count says every one of them is flagged, else leave the years unknown.
      qualifying_years: p.qualifying_years ?? (p.checks_count === 0 ? [] : dry && p.checks_count === dry.length ? dry : undefined),
    })),
  });
}

/** Keeps the days inside the 30-day planting window, which is what the evidence table lists. */
export function adaptReplay(r: ReplayResponse): ReplayResponse {
  const days = r.daily.filter((d) => BackendReplayDay.parse(d).in_spring_window !== false);
  return days.length === r.daily.length ? r : { ...r, daily: days, daily_scope: "spring_window" };
}

/** The request body for POST /v1/plans/compare: the backend's plan fields (`winter.kind`, `grower`). */
export function toBackendPlan(p: PlanInput) {
  const w = p.winter;
  return {
    plan_id: p.plan_id,
    previous_crop_id: p.previous_crop_id,
    prev_harvest: p.prev_harvest,
    next_crop_id: p.next_crop_id,
    next_plant: p.next_plant,
    winter:
      w.type === "cover"
        ? { kind: "cover", crop_id: w.crop_id, seed: w.seed, terminate: w.terminate }
        : w.type === "winter_grain"
          ? { kind: "winter_grain", crop_id: w.crop_id, plant: w.plant, harvest: w.harvest }
          : { kind: "none" },
    grower: { low_moisture_concern: p.low_moisture_concern === "yes" ? true : p.low_moisture_concern === "no" ? false : null },
  };
}
