/*
  The three cards and their five headings (the challenge asks for why, evidence,
  benefits, gaps and risks for each strategy). Every factual line cites a source that
  was checked against the NC State page on Nov 12, 2026, or is marked as a gap.

  Card keys map to the backend's stable plan IDs (Rahul, Nov 12). Display names are
  the frontend's choice; "Add a grain crop" replaces "Earn more" because the backend
  does no economics.
*/

export type CardKey = "current" | "cover" | "grain";

export interface Claim {
  text: string;
  source: SourceId | null;
}

export interface CardContent {
  key: CardKey;
  planId: string;
  earlierPlanId?: string;
  name: string;
  subtitle: string;
  headings: { why: Claim[]; evidence: Claim[]; benefits: Claim[]; gaps: Claim[]; risks: Claim[] };
}

export type SourceId = "ncs-soy-4" | "ncs-soy-5" | "ncs-cover" | "nasa-power" | "sare-rye" | "ncs-scab";

export const SOURCES: Record<SourceId, { title: string; publisher: string; url: string; kind: "ncstate" | "nasa" | "other" }> = {
  "ncs-soy-4": {
    title: "NC Soybean Production Guide, ch. 4: Soil Health, Tillage, Cover Crops, and Crop Rotation",
    publisher: "NC State Extension",
    url: "https://content.ces.ncsu.edu/north-carolina-soybean-production-guide/rotational-considerations",
    kind: "ncstate",
  },
  "ncs-soy-5": {
    title: "NC Soybean Production Guide, ch. 5: Planting Decisions",
    publisher: "NC State Extension",
    url: "https://content.ces.ncsu.edu/north-carolina-soybean-production-guide/soybean-planting-decisions",
    kind: "ncstate",
  },
  "ncs-cover": {
    title: "Winter Annual Cover Crops (AG-439-58)",
    publisher: "NC State Extension",
    url: "https://content.ces.ncsu.edu/winter-annual-cover-crops",
    kind: "ncstate",
  },
  "ncs-scab": {
    title: "Planting to Reduce Head Scab Risk",
    publisher: "NC State Extension",
    url: "https://smallgrains.ces.ncsu.edu/news/planting-to-reduce-head-scab-risk/",
    kind: "ncstate",
  },
  "sare-rye": {
    title: "Cereal Rye (Managing Cover Crops Profitably, 3rd ed.)",
    publisher: "SARE",
    url: "https://www.sare.org/publications/managing-cover-crops-profitably/nonlegume-cover-crops/cereal-rye/",
    kind: "other",
  },
  "nasa-power": {
    title: "NASA POWER Daily API",
    publisher: "NASA Langley Research Center",
    url: "https://power.larc.nasa.gov/docs/services/api/temporal/daily/",
    kind: "nasa",
  },
};

const c = (text: string, source: SourceId | null = null): Claim => ({ text, source });

export const CARDS: CardContent[] = [
  {
    key: "current",
    planId: "no_cover",
    name: "What you do now",
    subtitle: "No planted winter cover · crop residue may remain",
    headings: {
      why: [c("The plan the other two are compared against. Same corn harvest and soybean dates; only the winter changes.")],
      evidence: [c("Every spring since 1981 replayed for the same planting date with NASA rainfall for this area.", "nasa-power")],
      benefits: [c("No cover-crop seed, planting or termination work.", "ncs-soy-4")],
      gaps: [c("Residue cover, slope and storm intensity decide real erosion; this tool does not measure them.")],
      risks: [c("Without living cover, soil has less protection through fall and winter.", "ncs-cover")],
    },
  },
  {
    key: "cover",
    planId: "rye_12d",
    earlierPlanId: "rye_19d",
    name: "Add winter cover",
    subtitle: "Cereal rye after corn, ended before soybeans",
    headings: {
      why: [
        c("Cereal rye is one of the most popular cover crops planted before soybeans.", "ncs-soy-4"),
        c("Rye gives some of the strongest erosion protection through fall and winter.", "ncs-cover"),
      ],
      evidence: [
        c("If low soil moisture is a concern, NC State suggests ending the cover at least two weeks before soybean planting.", "ncs-soy-4"),
        c("Every spring since 1981 replayed with NASA rainfall for this area.", "nasa-power"),
      ],
      benefits: [
        c("Can suppress weeds and, with no-till, help conserve soil moisture later in the season.", "ncs-soy-4"),
        c("Scavenges leftover nitrogen and can be seeded late after corn.", "sare-rye"),
      ],
      gaps: [
        c("Days with living rye are planned from dates; actual establishment and growth are not measured."),
        c("The second winter (soybeans to corn) is not evaluated in this version."),
      ],
      risks: [
        c("A living cover uses soil moisture. In a dry spring it can leave the seedbed too dry before planting.", "ncs-soy-4"),
        c("Extra seed, planting and termination work.", "ncs-soy-4"),
      ],
    },
  },
  {
    key: "grain",
    planId: "wheat_double_crop",
    name: "Add a grain crop",
    subtitle: "Winter wheat for grain, then June soybeans",
    headings: {
      why: [c("Adds a third harvested crop to the same land over two years.")],
      evidence: [
        c("NC State reports lower yields for soybeans planted in June than in the Apr 20–May 20 window.", "ncs-soy-5"),
        c("Every June planting window since 1981 replayed with NASA rainfall for this area.", "nasa-power"),
      ],
      benefits: [c("Wheat keeps the soil covered through the first winter.", "ncs-cover")],
      gaps: [
        c("Wheat planting and harvest windows are not yet sourced, so the timing check shows unknown."),
        c("Prices, costs and profit are not part of this tool."),
      ],
      risks: [
        c("June-planted soybeans yield less.", "ncs-soy-5"),
        c("Wheat after corn: check head scab risk.", "ncs-scab"),
        c("Little time between wheat harvest and soybean planting."),
      ],
    },
  },
];

export const cardByKey = (k: CardKey) => CARDS.find((c) => c.key === k)!;
