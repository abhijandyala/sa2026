import { z } from "zod";

/*
  Proposed data contract between Rahul's pipeline (writer) and this frontend (reader).
  Mirrors the "Data contract changes" section of the scope-change doc. Field names are a
  proposal to agree at kickoff; change them here and the types follow.

  Rules the frontend relies on (playbook p.22, p.24, p.57–59):
  - rainfall is stored in mm, totals are summed before rounding;
  - a missing value is null and carries a reason; a valid zero stays 0;
  - every flag carries a reason code and a rule source ID;
  - the frontend never recomputes a total, rank, flag or count, it only formats them.
*/

const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "expected YYYY-MM-DD");
const isoDateTime = z.string().min(10);

export const TriState = z.enum(["yes", "no", "unknown"]);
export const SoilSource = z.enum(["farmer", "usda", "sample", "unknown"]);
export const Priority = z.enum(["soil", "income", "water"]);
export const StrategyId = z.enum(["current", "protect-soil", "earn-more"]);

export const SourceRef = z.object({
  id: z.string(),
  title: z.string(),
  publisher: z.string(),
  url: z.string().url(),
  checked: isoDate.optional(),
});

export const Manifest = z.object({
  synthetic: z.boolean(),
  dataset: z.string(),
  community: z.string().optional(),
  parameters: z.array(z.object({ name: z.string(), units: z.string(), description: z.string() })).min(1),
  point: z.object({ id: z.string(), label: z.string(), lat: z.number(), lon: z.number() }),
  range: z.object({ start: isoDate, end: isoDate }),
  timeStandard: z.string(),
  scaleNote: z.string(),
  retrievedAt: isoDateTime,
  queryUrl: z.string(),
  recreate: z.string(),
  checksum: z.string().optional(),
});

export const ReasonCode = z.enum([
  "dry_window_and_gap_under_14",
  "farmer_reported_dry_and_gap_under_14",
  "both_dry_window_and_farmer_report",
  "dry_window_no_rule",
  "incomplete_window",
  "not_applicable",
]);

export const YearWindow = z.object({
  year: z.number().int(),
  window: z.tuple([isoDate, isoDate]),
  rainMm: z.number().min(0).nullable(),
  validDays: z.number().int().min(0),
  expectedDays: z.number().int().min(1),
  complete: z.boolean(),
  pctRank: z.number().min(0).max(1).nullable(),
  dry: z.boolean().nullable(),
  soilWetRoot: z.number().min(0).max(1).nullable(),
  flag: z.boolean().nullable(),
  reason: ReasonCode.nullable(),
  rule: z.string().nullable(),
});

const HalfSummary = z.object({
  range: z.string(),
  complete: z.number().int(),
  dry: z.number().int(),
  flagged: z.number().int().nullable(),
});

export const EventSummary = z.object({
  completeYears: z.number().int(),
  excludedYears: z.number().int(),
  minCompleteYears: z.number().int(),
  labelsWithheld: z.boolean(),
  medianMm: z.number().nullable(),
  dryThresholdMm: z.number().nullable(),
  dryRule: z.string(),
  // Springs whose window was at or below the dry threshold (pure data, no agronomic rule).
  dryCount: z.number().int().nullable(),
  // Springs flagged by a sourced rule. Null when no sourced rule applies to this event.
  flagged: z.number().int().nullable(),
  ruleApplies: z.boolean(),
  earlier: HalfSummary,
  recent: HalfSummary,
  // Complete year nearest the median; ties go to the earliest year (playbook p.23).
  typicalYear: z.number().int().nullable(),
  // Playbook p.23: highest complete total at or below the 20th-percentile cutoff. Not the single driest year.
  dryReplayYear: z.number().int().nullable(),
  // Null when the dry replay would equal the typical value (no meaningful contrast, playbook p.59).
  contrastWithheld: z.boolean(),
});

export const PlantingEvent = z.object({
  id: z.string(),
  label: z.string(),
  crop: z.enum(["soybeans", "corn"]),
  plantingDate: isoDate,
  windowDays: z.number().int(),
  gapDays: z.number().int().nullable(),
  years: z.array(YearWindow),
  summary: EventSummary,
});

export const CropStep = z.object({
  crop: z.enum(["corn", "soybeans", "rye", "wheat", "clover", "vetch", "none"]),
  label: z.string(),
  start: isoDate,
  end: isoDate,
  role: z.enum(["cash", "cover", "fallow"]),
});

export const Claim = z.object({ text: z.string(), source: z.string().nullable() });

export const Feasibility = z.object({
  check: z.string(),
  result: z.enum(["pass", "fail", "unknown"]),
  message: z.string(),
  source: z.string().nullable(),
});

export const Strategy = z.object({
  id: StrategyId,
  name: z.string(),
  subtitle: z.string(),
  sequence: z.array(CropStep).min(1),
  headings: z.object({
    why: z.array(Claim),
    evidence: z.array(Claim),
    benefits: z.array(Claim),
    gaps: z.array(Claim),
    risks: z.array(Claim),
  }),
  matches: z.array(Priority),
  metrics: z.object({
    gapDays: z.number().int().nullable(),
    livingCoverDays: z.number().int().nullable(),
  }),
  events: z.array(PlantingEvent).min(1),
  headlineEventId: z.string(),
  feasibility: z.array(Feasibility),
});

export const CurvePoint = z.object({
  endDate: isoDate,
  livingCoverDays: z.number().int(),
  gapDays: z.number().int(),
  flagged: z.number().int(),
});

export const Curve = z.object({
  strategyId: StrategyId,
  eventId: z.string(),
  seedDate: isoDate,
  plantingDate: isoDate,
  proposedEnd: isoDate,
  earlierEnd: isoDate,
  completeYears: z.number().int(),
  points: z.array(CurvePoint).min(1),
});

export const FarmPlan = z.object({
  isExample: z.boolean(),
  locationId: z.string(),
  locationLabel: z.string(),
  cornHarvest: isoDate,
  soyPlant: isoDate,
  soyHarvest: isoDate,
  ryeSeed: isoDate,
  ryeEnd: isoDate,
  ryeEndEarlier: isoDate,
  wheatPlant: isoDate,
  wheatHarvest: isoDate,
  soyDoubleCropPlant: isoDate,
  cornPlant: isoDate,
  soilSource: SoilSource,
  soilTexture: z.string().nullable(),
  moistureConcern: TriState,
  irrigation: TriState,
  priorities: z.array(Priority),
});

export const Bundle = z.object({
  contractVersion: z.literal(1),
  manifest: Manifest,
  plan: FarmPlan,
  strategies: z.array(Strategy).length(3),
  curves: z.array(Curve),
  sources: z.array(SourceRef),
});

export type Bundle = z.infer<typeof Bundle>;
export type Manifest = z.infer<typeof Manifest>;
export type FarmPlan = z.infer<typeof FarmPlan>;
export type Strategy = z.infer<typeof Strategy>;
export type StrategyId = z.infer<typeof StrategyId>;
export type PlantingEvent = z.infer<typeof PlantingEvent>;
export type YearWindow = z.infer<typeof YearWindow>;
export type EventSummary = z.infer<typeof EventSummary>;
export type Curve = z.infer<typeof Curve>;
export type CurvePoint = z.infer<typeof CurvePoint>;
export type Priority = z.infer<typeof Priority>;
export type TriState = z.infer<typeof TriState>;
export type SoilSource = z.infer<typeof SoilSource>;
export type ReasonCode = z.infer<typeof ReasonCode>;
export type SourceRef = z.infer<typeof SourceRef>;
export type Feasibility = z.infer<typeof Feasibility>;
export type CropStep = z.infer<typeof CropStep>;
