import type { CompareResponse, Plan, PlanInput } from "../api/schema";

/*
  The farm form (card 1.3). A rotation has two winters (legs, backend docs/api/presets.md):
  leg 1 corn → soybeans in the 2026–27 season, leg 2 soybeans → corn in 2027–28. Dates are
  entered as real calendar dates so native pickers work; the backend receives MM-DD.
  Validation here is only about the order of what the grower typed, so errors can sit
  beside the field (playbook p.39). Every agronomic rule stays in the backend.
*/

export type Tri = "yes" | "no" | "unknown";
export type SoilSource = "sample" | "farmer" | "usda" | "unknown";

export interface FarmForm {
  // Leg 1: corn → soybeans
  cornHarvest: string;
  soyPlant: string;
  ryeSeed: string;
  ryeEnd: string;
  /** A comparison date for the rye slider only; not sent as a separate plan. */
  ryeEndEarlier: string;
  wheatPlant: string;
  wheatHarvest: string;
  soyDoubleCropPlant: string;
  // Leg 2: soybeans → corn
  soyHarvest: string;
  rye2Seed: string;
  rye2End: string;
  cornPlant: string;
  // Field context
  moistureConcern: Tri;
  irrigation: Tri;
  soilSource: SoilSource;
  soilTexture: string;
}

export type FormErrors = Partial<Record<keyof FarmForm, string>>;

const SEASON: Record<1 | 2, [number, number]> = { 1: [2026, 2027], 2: [2027, 2028] };

/** MM-DD from the backend → a date in that leg's season (Jul–Dec in fall, Jan–Jun in spring). */
export function toSeasonDate(md: string, leg: 1 | 2 = 1): string {
  const month = Number(md.slice(0, 2));
  const [fall, spring] = SEASON[leg];
  return `${month >= 7 ? fall : spring}-${md}`;
}
const toMd = (iso: string) => iso.slice(5);

const LEG2_FIELDS: Array<keyof FarmForm> = ["soyHarvest", "rye2Seed", "rye2End", "cornPlant"];
const legOf = (k: keyof FarmForm): 1 | 2 => (LEG2_FIELDS.includes(k) ? 2 : 1);

export function sampleForm(compare: CompareResponse): FarmForm {
  const byId = new Map(compare.plans.map((p) => [p.plan_id, p]));
  const seq = (id: string) => byId.get(id)?.sequence;
  const cover = (p: Plan["sequence"]) => (p?.winter.type === "cover" ? p.winter : null);
  const grain = (p: Plan["sequence"]) => (p?.winter.type === "winter_grain" ? p.winter : null);
  const rye = seq("corn_soy__rye");
  const leg1 = rye ?? seq("corn_soy__no_cover");
  const rye2 = seq("soy_corn__rye");
  const leg2 = rye2 ?? seq("soy_corn__no_cover");
  const wheat = seq("corn_soy__wheat_dc");
  return {
    cornHarvest: toSeasonDate(leg1?.prev_harvest ?? "09-20"),
    soyPlant: toSeasonDate(leg1?.next_plant ?? "05-12"),
    ryeSeed: toSeasonDate(cover(rye)?.seed ?? "10-01"),
    ryeEnd: toSeasonDate(cover(rye)?.terminate ?? "04-30"),
    ryeEndEarlier: toSeasonDate("04-23"),
    // Wheat dates are the grower's to enter; sample values until the backend has wheat windows.
    wheatPlant: toSeasonDate(grain(wheat)?.plant ?? "10-25"),
    wheatHarvest: toSeasonDate(grain(wheat)?.harvest ?? "06-10"),
    soyDoubleCropPlant: toSeasonDate(wheat?.next_plant ?? "06-15"),
    soyHarvest: toSeasonDate(leg2?.prev_harvest ?? "10-15", 2),
    rye2Seed: toSeasonDate(cover(rye2)?.seed ?? "10-20", 2),
    rye2End: toSeasonDate(cover(rye2)?.terminate ?? "04-05", 2),
    cornPlant: toSeasonDate(leg2?.next_plant ?? "04-15", 2),
    moistureConcern: "unknown",
    irrigation: "unknown",
    soilSource: "sample",
    soilTexture: "",
  };
}

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
    "soyHarvest",
    "rye2Seed",
    "rye2End",
    "cornPlant",
  ];
  for (const k of dates) {
    const v = f[k];
    const [fall, spring] = SEASON[legOf(k)];
    if (!v) e[k] = "Enter a date.";
    else if (v < `${fall}-07-01` || v > `${spring}-06-30`) e[k] = `Choose a date between Jul 1, ${fall} and Jun 30, ${spring}.`;
  }
  if (Object.keys(e).length) return e;

  // Leg 1
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
  // Leg 2
  if (f.cornPlant <= f.soyHarvest) e.cornPlant = "Corn planting must come after the soybean harvest.";
  if (f.rye2Seed < f.soyHarvest) e.rye2Seed = "Sow rye on or after the soybean harvest.";
  if (f.rye2End <= f.rye2Seed || f.rye2End >= f.cornPlant) e.rye2End = "Choose a rye end date after seeding and before corn planting.";
  return e;
}

/** The plans the form describes, in the backend's request shape (presets.md IDs). */
export function toPlanInputs(f: FarmForm): PlanInput[] {
  const concern = { low_moisture_concern: f.moistureConcern };
  const leg1 = { ...concern, prev_harvest: toMd(f.cornHarvest) };
  const leg2 = { ...concern, prev_harvest: toMd(f.soyHarvest) };
  return [
    { ...leg1, plan_id: "corn_soy__no_cover", winter: { type: "none" }, next_plant: toMd(f.soyPlant) },
    {
      ...leg1,
      plan_id: "corn_soy__rye",
      winter: { type: "cover", crop_id: "cereal_rye", seed: toMd(f.ryeSeed), terminate: toMd(f.ryeEnd) },
      next_plant: toMd(f.soyPlant),
    },
    {
      ...leg1,
      plan_id: "corn_soy__wheat_dc",
      winter: { type: "winter_grain", crop_id: "winter_wheat", plant: toMd(f.wheatPlant), harvest: toMd(f.wheatHarvest) },
      next_plant: toMd(f.soyDoubleCropPlant),
    },
    { ...leg2, plan_id: "soy_corn__no_cover", winter: { type: "none" }, next_plant: toMd(f.cornPlant) },
    {
      ...leg2,
      plan_id: "soy_corn__rye",
      winter: { type: "cover", crop_id: "cereal_rye", seed: toMd(f.rye2Seed), terminate: toMd(f.rye2End) },
      next_plant: toMd(f.cornPlant),
    },
  ];
}

export const sameForm = (a: FarmForm, b: FarmForm) => JSON.stringify(a) === JSON.stringify(b);
