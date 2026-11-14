import { z } from "zod";

/*
  The model the screens read. It began as the types of Rahul's draft API examples (Nov 12
  2026) and the screens, the view builder and their tests are written against it.

  Since Phase 12 the real backend responses are parsed and turned into this model in
  adapt.ts, which is the only file that knows the backend's own field names. Objects use
  .passthrough() so an extra field never breaks the page. Fields marked "REQUESTED" are
  ones the real compare response still lacks; adapt.ts says where each comes from instead,
  and web/docs/api-requests.md lists them for Rahul.
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
    /** One plain sentence for the grower; `reason` is the engine's wording, kept for the evidence drawer. */
    text: z.string().optional(),
    /** The backend's call on whether the line is worth a printed page. */
    print: z.boolean().optional(),
  })
  .passthrough();
export type OtherCheck = z.infer<typeof OtherCheck>;

const Winter = z.union([
  z.object({ type: z.literal("none") }).passthrough(),
  z.object({ type: z.literal("cover"), crop_id: z.string(), seed: md, terminate: md }).passthrough(),
  z.object({ type: z.literal("winter_grain"), crop_id: z.string(), plant: md, harvest: md }).passthrough(),
]);

export const Sequence = z
  .object({
    previous_crop_id: z.string(),
    prev_harvest: md,
    winter: Winter,
    next_crop_id: z.string(),
    next_plant: md,
  })
  .passthrough();

const Calendar = z
  .object({
    living_cover_days_planned: z.number().int(),
    days_without_planned_cover: z.number().int(),
    termination_gap_days: z.number().int().nullable(),
    harvest_to_plant_days: z.number().int().nullable().optional(),
    establishment: z.string(),
  })
  .passthrough();

const WinterResult = z
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
  .passthrough();

/**
 * One winter transition (backend docs/api/presets.md). A plan the backend cannot
 * evaluate yet (wheat until its catalog rows land) comes back with
 * status "unavailable" and a reason, and may omit everything else.
 */
export const Plan = z
  .object({
    plan_id: z.string(),
    label: z.string(),
    rotation_id: z.string().optional(),
    leg: z.union([z.literal(1), z.literal(2)]).optional(),
    status: Status.optional(),
    reason: z.string().optional(),
    editable: z.array(z.string()).optional(),
    dates_assumed: z.boolean().optional(),
    region_note: z.string().optional(),
    sequence: Sequence.optional(),
    spring_window: z.object({ start: md, end: md }).passthrough().optional(),
    spring_window_id: z.string().optional(), // REQUESTED
    calendar: Calendar.optional(),
    winter: WinterResult.optional(),
    spring_checks: z.array(SpringCheck).default([]),
    other_checks: z.array(OtherCheck).default([]),
    eras: z.record(Era).default({}),
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

export const Rotation = z
  .object({
    rotation_id: z.string(),
    label: z.string(),
    legs: z.array(z.object({ leg: z.union([z.literal(1), z.literal(2)]), plan_id: z.string() }).passthrough()).min(1),
  })
  .passthrough();
export type Rotation = z.infer<typeof Rotation>;

export const CompareResponse = z
  .object({
    meta: Meta,
    request_echo: z
      .object({ location_id: z.string(), rotation_ids: z.array(z.string()).optional(), plan_ids: z.array(z.string()).optional() })
      .passthrough(),
    thresholds: z.object({ heavy_rain: Threshold, dry_spring: Threshold }).passthrough(),
    shared_eligible_years: z.object({ spring: z.number().int(), winter: z.number().int() }).passthrough(),
    plans: z.array(Plan).min(1),
    rotations: z.array(Rotation).default([]),
    spring_window: z.object({ start: md.optional(), end: md.optional(), note: z.string().optional() }).passthrough().optional(),
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
            qualifying_years: z.array(z.number().int()).optional(), // REQUESTED
            eras: Era.optional(), // REQUESTED
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
  previous_crop_id: string;
  next_crop_id: string;
  prev_harvest: string;
  winter:
    | { type: "none" }
    | { type: "cover"; crop_id: string; seed: string; terminate: string }
    | { type: "winter_grain"; crop_id: string; plant: string; harvest: string };
  next_plant: string;
  low_moisture_concern: "yes" | "no" | "unknown";
}

/* ------------------------------------------------------------------ POST /v1/locations/resolve (Phase 9)
   Body {lat, lon, fetch_history}. Weather and guidance support are separate on purpose:
   a point can have weather history while its guidance region is unknown, and the reverse. */
export const LocationResolveResponse = z
  .object({
    location: z
      .object({
        status: z.string(),
        latitude: z.number(),
        longitude: z.number(),
        code: z.string().nullable().optional(),
        reason: z.string().nullable().optional(),
        cell_id: z.string().nullable().optional(),
        bounds: z.object({ in_nc: z.boolean() }).passthrough().optional(),
        grid_cell: z
          .object({ center_latitude: z.number(), center_longitude: z.number(), lat_step_deg: z.number(), lon_step_deg: z.number() })
          .passthrough()
          .nullable()
          .optional(),
        // Both are null for a point outside North Carolina (status "unsupported").
        weather: z
          .object({
            supported: z.boolean(),
            status: z.string(),
            source: z.string(),
            freshness: z.string(),
            reason: z.string().nullable().optional(),
            // The place whose committed NASA record covers this point's grid cell.
            location_id: z.string().nullable().optional(),
          })
          .passthrough()
          .nullable()
          .optional(),
        guidance: z
          .object({ supported: z.boolean(), status: z.string(), region: z.string().nullable(), reason: z.string().nullable().optional() })
          .passthrough()
          .nullable()
          .optional(),
        notes: z.array(z.string()).default([]),
      })
      .passthrough(),
  })
  .passthrough();
export type LocationResolveResponse = z.infer<typeof LocationResolveResponse>;
