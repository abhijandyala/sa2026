import type { CompareResponse, PlanInput } from "../api/schema";

/*
  The farm form (card 1.3). Dates are entered for one planned season (fall 2026 to
  summer 2027) so native date pickers work; the backend receives MM-DD (its Plan model).
  Validation here is only about the order of what the grower typed, so errors can sit
  beside the field (playbook p.39). Every agronomic rule stays in the backend.
*/

export type Tri = "yes" | "no" | "unknown";
export type SoilSource = "sample" | "farmer" | "usda" | "unknown";

export interface FarmForm {
  cornHarvest: string;
  soyPlant: string;
  ryeSeed: string;
  ryeEnd: string;
  ryeEndEarlier: string;
  wheatPlant: string;
  wheatHarvest: string;
  soyDoubleCropPlant: string;
  moistureConcern: Tri;
  irrigation: Tri;
  soilSource: SoilSource;
  soilTexture: string;
}

export type FormErrors = Partial<Record<keyof FarmForm, string>>;

const FALL_YEAR = 2026;
const SPRING_YEAR = 2027;

/** MM-DD from the backend → a date in the planned season (Jul–Dec in fall, Jan–Jun in spring). */
export function toSeasonDate(md: string): string {
  const month = Number(md.slice(0, 2));
  return `${month >= 7 ? FALL_YEAR : SPRING_YEAR}-${md}`;
}
const toMd = (iso: string) => iso.slice(5);

export function sampleForm(compare: CompareResponse): FarmForm {
  const byId = new Map(compare.plans.map((p) => [p.plan_id, p]));
  const rye = byId.get("rye_12d")?.sequence;
  const rye19 = byId.get("rye_19d")?.sequence;
  const wheat = byId.get("wheat_double_crop")?.sequence;
  const any = compare.plans[0]!.sequence;
  const ryeW = rye?.winter.type === "cover" ? rye.winter : null;
  const rye19W = rye19?.winter.type === "cover" ? rye19.winter : null;
  const wheatW = wheat?.winter.type === "winter_grain" ? wheat.winter : null;
  return {
    cornHarvest: toSeasonDate(any.prev_harvest),
    soyPlant: toSeasonDate(rye?.next_plant ?? any.next_plant),
    ryeSeed: toSeasonDate(ryeW?.seed ?? "10-01"),
    ryeEnd: toSeasonDate(ryeW?.terminate ?? "04-30"),
    ryeEndEarlier: toSeasonDate(rye19W?.terminate ?? "04-23"),
    wheatPlant: toSeasonDate(wheatW?.plant ?? "10-25"),
    wheatHarvest: toSeasonDate(wheatW?.harvest ?? "06-10"),
    soyDoubleCropPlant: toSeasonDate(wheat?.next_plant ?? "06-15"),
    moistureConcern: "unknown",
    irrigation: "unknown",
    soilSource: "sample",
    soilTexture: "",
  };
}

const inSeason = (iso: string) => iso >= `${FALL_YEAR}-07-01` && iso <= `${SPRING_YEAR}-06-30`;

export function validateForm(f: FarmForm): FormErrors {
  const e: FormErrors = {};
  const dates: Array<keyof FarmForm> = [
    "cornHarvest",
    "soyPlant",
    "ryeSeed",
    "ryeEnd",
    "ryeEndEarlier",
    "wheatPlant",
    "wheatHarvest",
    "soyDoubleCropPlant",
  ];
  for (const k of dates) {
    const v = f[k];
    if (!v) e[k] = "Enter a date.";
    else if (!inSeason(v)) e[k] = `Choose a date between Jul 1, ${FALL_YEAR} and Jun 30, ${SPRING_YEAR}.`;
  }
  if (Object.keys(e).length) return e;

  if (f.soyPlant <= f.cornHarvest) e.soyPlant = "Soybean planting must come after the corn harvest.";
  if (f.ryeSeed < f.cornHarvest) e.ryeSeed = "Sow rye on or after the corn harvest.";
  for (const k of ["ryeEnd", "ryeEndEarlier"] as const) {
    if (f[k] <= f.ryeSeed || f[k] >= f.soyPlant) e[k] = "Choose a rye end date after seeding and before soybean planting for this comparison.";
  }
  if (!e.ryeEnd && !e.ryeEndEarlier && f.ryeEndEarlier > f.ryeEnd) {
    e.ryeEndEarlier = "The earlier end date should be on or before the proposed end date.";
  }
  if (f.wheatPlant < f.cornHarvest) e.wheatPlant = "Plant wheat on or after the corn harvest.";
  if (f.wheatHarvest <= f.wheatPlant) e.wheatHarvest = "Wheat harvest must come after wheat planting.";
  if (f.soyDoubleCropPlant <= f.wheatHarvest) e.soyDoubleCropPlant = "Plant double-crop soybeans after the wheat harvest.";
  return e;
}

/** The plans the form describes, in the backend's request shape. */
export function toPlanInputs(f: FarmForm): PlanInput[] {
  const base = { prev_harvest: toMd(f.cornHarvest), low_moisture_concern: f.moistureConcern };
  return [
    { ...base, plan_id: "no_cover", winter: { type: "none" }, next_plant: toMd(f.soyPlant) },
    { ...base, plan_id: "rye_12d", winter: { type: "cover", crop_id: "cereal_rye", seed: toMd(f.ryeSeed), terminate: toMd(f.ryeEnd) }, next_plant: toMd(f.soyPlant) },
    { ...base, plan_id: "rye_19d", winter: { type: "cover", crop_id: "cereal_rye", seed: toMd(f.ryeSeed), terminate: toMd(f.ryeEndEarlier) }, next_plant: toMd(f.soyPlant) },
    {
      ...base,
      plan_id: "wheat_double_crop",
      winter: { type: "winter_grain", crop_id: "winter_wheat", plant: toMd(f.wheatPlant), harvest: toMd(f.wheatHarvest) },
      next_plant: toMd(f.soyDoubleCropPlant),
    },
  ];
}

export const sameForm = (a: FarmForm, b: FarmForm) => JSON.stringify(a) === JSON.stringify(b);
