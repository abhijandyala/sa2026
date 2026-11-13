import { z } from "zod";

/*
  Types for Rahul's backend API (backend branch, docs/api/examples/, draft of Nov 12 2026).
  Field names here are the contract: they match the draft examples exactly. Objects use
  .passthrough() so a new backend field never breaks the page.

  Frontend additions the drafts do not carry yet are marked "REQUESTED" and listed in
  web/docs/api-requests.md. The UI treats each of them as optional.
*/

export const Status = z.enum([
  "complete",
  "partial",
  "unavailable",
  "unknown",
  "inapplicable",
  "unsupported",
  "invalid_input",
  "manual_check",
  "insufficient_data",
]);
export type Status = z.infer<typeof Status>;

export const Verdict = z.enum(["preferred", "acceptable", "caution", "avoid", "manual_check", "unknown", "inapplicable"]);
export type Verdict = z.infer<typeof Verdict>;

export const EraResult = z.enum(["more_frequent_recent", "less_frequent_recent", "similar", "insufficient_data"]);
export type EraResult = z.infer<typeof EraResult>;

const md = z.string().regex(/^\d{2}-\d{2}$/, "expected MM-DD");
const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "expected YYYY-MM-DD");

export const Meta = z
  .object({
    plan_version: z.string().nullable(),
    catalog_version: z.string(),
    snapshot_hash: z.string(),
    request_id: z.string(),
    draft: z.boolean().optional(),
  })
  .passthrough();

export const Threshold = z
  .object({
    value: z.number().nullable(),
    unit: z.string(),
    method: z.string(),
    reference_span: z.string().optional(),
    window: z.string().optional(),
    status: Status,
  })
  .passthrough();

const EraPart = z.object({ count: z.number().int(), denominator: z.number().int(), pct: z.number().nullable() }).passthrough();
export const Era = z
  .object({
    earlier: EraPart,
    recent: EraPart,
    diff_pp: z.number().nullable(),
    result: EraResult,
    caveat: z.string(),
  })
  .passthrough();
export type Era = z.infer<typeof Era>;

export const SpringCheck = z
  .object({
    check_id: z.string(),
    rule_ids: z.array(z.string()),
    label: z.string().optional(),
    fires_when: z.string().optional(),
    status: Status.optional(),
    count: z.number().int().nullable(),
    denominator: z.number().int().nullable(),
    pct: z.number().nullable(),
    qualifying_years: z.array(z.number().int()),
    skipped_years: z.array(z.unknown()),
    source: z.object({ title: z.string(), url: z.string() }).passthrough().optional(),
  })
  .passthrough();
export type SpringCheck = z.infer<typeof SpringCheck>;

export const OtherCheck = z
  .object({
    rule_id: z.string(),
    verdict: Verdict,
    status: Status.optional(),
    reason: z.string(),
  })
  .passthrough();
export type OtherCheck = z.infer<typeof OtherCheck>;

const Winter = z.union([
  z.object({ type: z.literal("none") }).passthrough(),
  z.object({ type: z.literal("cover"), crop_id: z.string(), seed: md, terminate: md }).passthrough(),
  z.object({ type: z.literal("winter_grain"), crop_id: z.string(), plant: md, harvest: md }).passthrough(),
]);

export const Plan = z
  .object({
    plan_id: z.string(),
    label: z.string(),
    status: Status.optional(),
    sequence: z
      .object({
        previous_crop_id: z.string(),
        prev_harvest: md,
        winter: Winter,
        next_crop_id: z.string(),
        next_plant: md,
      })
      .passthrough(),
    spring_window_id: z.string().optional(), // REQUESTED
    calendar: z
      .object({
        living_cover_days_planned: z.number().int(),
        days_without_planned_cover: z.number().int(),
        termination_gap_days: z.number().int().nullable(),
        harvest_to_plant_days: z.number().int().nullable().optional(),
        establishment: z.string(),
      })
      .passthrough(),
    winter: z
      .object({
        status: Status,
        per_season_median: z
          .object({
            rain_mm_without_cover: z.number().nullable(),
            heavy_rain_days_without_cover: z.number().nullable(),
          })
          .passthrough(),
        eligible_seasons: z.number().int().optional(),
        segments: z.array(z.string()),
        per_season: z // REQUESTED
          .array(z.object({ year: z.number().int(), rain_mm_without_cover: z.number().nullable(), status: Status }).passthrough())
          .optional(),
      })
      .passthrough(),
    spring_checks: z.array(SpringCheck),
    other_checks: z.array(OtherCheck),
    eras: z.record(Era),
    residue_context: z.object({ status: Status, note: z.string() }).passthrough().optional(),
  })
  .passthrough();
export type Plan = z.infer<typeof Plan>;

export const SpringYear = z
  .object({
    year: z.number().int(),
    start: isoDate,
    end: isoDate,
    total_mm: z.number().min(0).nullable(),
    status: Status,
    rank: z.number().int().nullable(),
    of: z.number().int().nullable(),
    percentile: z.number().nullable(),
    is_dry: z.boolean().nullable(),
    gwettop_window_mean: z.number().nullable(),
    gwetroot_window_mean: z.number().nullable(),
  })
  .passthrough();
export type SpringYear = z.infer<typeof SpringYear>;

// REQUESTED: per-year spring results for each planting window.
export const SpringWindow = z
  .object({
    id: z.string(),
    label: z.string(),
    plant: md,
    start: md,
    end: md,
    threshold: Threshold,
    median_mm: z.number().nullable(),
    dry_count: z.number().int().nullable(),
    denominator: z.number().int(),
    shortcuts: z.object({ typical: z.number().int().nullable(), dry: z.number().int().nullable(), wet: z.number().int().nullable() }),
    years: z.array(SpringYear),
    eras: z.object({ dry_spring: Era }).passthrough(),
  })
  .passthrough();
export type SpringWindow = z.infer<typeof SpringWindow>;

export const CompareResponse = z
  .object({
    meta: Meta,
    request_echo: z.object({ location_id: z.string(), plan_ids: z.array(z.string()) }).passthrough(),
    thresholds: z.object({ heavy_rain: Threshold, dry_spring: Threshold }).passthrough(),
    shared_eligible_years: z.object({ spring: z.number().int(), winter: z.number().int() }).passthrough(),
    plans: z.array(Plan).min(1),
    spring_window: z.object({ start: md, end: md, note: z.string().optional() }).passthrough(),
    spring_windows: z.record(SpringWindow).optional(), // REQUESTED
  })
  .passthrough();
export type CompareResponse = z.infer<typeof CompareResponse>;

export const YearsResponse = z
  .object({
    meta: Meta,
    location: z
      .object({
        id: z.string(),
        label: z.string(),
        grid: z.object({ lat: z.number(), lon: z.number(), source: z.string(), note: z.string() }).passthrough(),
      })
      .passthrough(),
    years: z.array(
      z
        .object({
          year: z.number().int(),
          spring: Status,
          winter: Status,
          full_season: Status,
          reason: z.string().nullable(),
        })
        .passthrough(),
    ),
    shortcuts: z.object({ typical: z.number().int().nullable(), dry: z.number().int().nullable(), wet: z.number().int().nullable() }),
    eras: z
      .object({
        earlier: z.object({ start: z.number().int(), end: z.number().int() }),
        recent: z.object({ start: z.number().int(), end: z.number().int() }),
        excluded_from_eras: z.array(z.number().int()),
      })
      .passthrough(),
  })
  .passthrough();
export type YearsResponse = z.infer<typeof YearsResponse>;

export const SensitivityResponse = z
  .object({
    meta: Meta,
    base_plan_id: z.string(),
    varied: z.literal("terminate"),
    fixed: z.object({ next_plant: md, seed: md }).passthrough(),
    check_id: z.string(),
    denominator: z.number().int(),
    points: z
      .array(
        z
          .object({
            terminate: md,
            gap_days: z.number().int(),
            living_cover_days_planned: z.number().int(),
            rain_mm_without_cover_median: z.number().nullable(),
            checks_count: z.number().int().nullable(),
          })
          .passthrough(),
      )
      .min(1),
  })
  .passthrough();
export type SensitivityResponse = z.infer<typeof SensitivityResponse>;

export const ReplayDay = z
  .object({
    date: isoDate,
    precip_mm: z.number().min(0).nullable(),
    status: Status.optional(),
    tmax_c: z.number().nullable().optional(),
    tmin_c: z.number().nullable().optional(),
    gwettop: z.number().nullable().optional(),
    gwetroot: z.number().nullable().optional(),
    cover_status: z.string(),
    segment: z.string(),
  })
  .passthrough();
export type ReplayDay = z.infer<typeof ReplayDay>;

/** GET /v1/seasons/{year}/replay?plan=… (draft replay.json). */
export const ReplayResponse = z
  .object({
    meta: Meta,
    year: z.number().int(),
    plan_id: z.string(),
    dates: z.object({ next_plant: isoDate, spring_window: z.object({ start: isoDate, end: isoDate }) }).passthrough(),
    coverage: z.object({ winter: Status, spring: Status }).passthrough(),
    spring: z
      .object({
        total_mm: z.number().nullable(),
        rank: z.number().int().nullable(),
        of: z.number().int().nullable(),
        percentile: z.number().nullable(),
        is_dry: z.boolean().nullable(),
        status: Status,
      })
      .passthrough(),
    wetness: z
      .object({
        gwettop_window_mean: z.number().nullable(),
        gwetroot_window_mean: z.number().nullable(),
        unit: z.string(),
        label: z.string(),
        status: Status,
      })
      .passthrough(),
    checks_triggered: z.array(z.object({ check_id: z.string(), rule_ids: z.array(z.string()), reason: z.string() }).passthrough()),
    key_rain_days: z.array(z.object({ date: isoDate, precip_mm: z.number().nullable(), segment: z.string() }).passthrough()),
    daily_scope: z.string().optional(),
    daily: z.array(ReplayDay),
  })
  .passthrough();
export type ReplayResponse = z.infer<typeof ReplayResponse>;

/** Plan input the farm form sends to POST /v1/plans/compare when the live API is available. */
export interface PlanInput {
  plan_id: string;
  prev_harvest: string;
  winter:
    | { type: "none" }
    | { type: "cover"; crop_id: string; seed: string; terminate: string }
    | { type: "winter_grain"; crop_id: string; plant: string; harvest: string };
  next_plant: string;
  low_moisture_concern: "yes" | "no" | "unknown";
}
