/*
  Plain definitions for the terms the challenge asks teams to explain (card 6.6).
  Shown as tap-to-open terms on the planner and as a list on the Methods page.
*/

export type TermId =
  | "cover-crop"
  | "living-cover"
  | "residue"
  | "end-cover"
  | "double-crop"
  | "soil-wetness"
  | "driest-20"
  | "rank"
  | "regional-estimate"
  | "replay"
  | "extension";

export const GLOSSARY: Record<TermId, { term: string; definition: string }> = {
  "cover-crop": {
    term: "Cover crop",
    definition: "A crop planted to protect and build the soil between cash crops, not to sell. Cereal rye is a common winter cover before soybeans.",
  },
  "living-cover": {
    term: "Living cover",
    definition: "Days when a planted crop is growing on the field. Here it is planned from seeding to ending dates, not measured.",
  },
  residue: {
    term: "Crop residue",
    definition: "Stalks and leaves left on the surface after harvest or after a cover crop ends. It still shields some soil, but it is not living cover.",
  },
  "end-cover": {
    term: "Ending the cover crop",
    definition: "Killing the cover crop before planting the next crop (often called termination). After it ends it stops using soil water.",
  },
  "double-crop": {
    term: "Double-crop soybeans",
    definition: "Soybeans planted right after a winter grain such as wheat is harvested, usually in June, so the land yields two crops in one year.",
  },
  "soil-wetness": {
    term: "Modeled soil wetness",
    definition:
      "NASA POWER's root-zone soil wetness, a 0 to 1 value from a weather model (MERRA-2) for the area around the grid point. 0 is dry, 1 is saturated. It is not a reading from your field.",
  },
  "driest-20": {
    term: "Driest 20%",
    definition: "Springs whose 30-day rainfall before planting was at or below the 20th percentile of all complete springs here. A label for comparing past years, not a drought declaration.",
  },
  rank: {
    term: "Rank",
    definition: "Where a spring's 30-day rainfall falls among all complete springs for the same dates. 1 is the driest.",
  },
  "regional-estimate": {
    term: "Regional estimate",
    definition: "NASA POWER values describe a grid cell roughly 50 km across, not one farm. Local storms can make a field wetter or drier than the estimate.",
  },
  replay: {
    term: "Historical replay",
    definition: "Running this year's planned dates against the weather of a past year. It shows how a plan would have fared; it does not forecast next spring.",
  },
  extension: {
    term: "Extension agent",
    definition: "A local adviser from NC State Extension (the county Cooperative Extension office) who helps growers with crop decisions.",
  },
};
