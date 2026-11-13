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

export type Leg = 1 | 2;

export interface CardContent {
  key: CardKey;
  /** Backend rotation ID (docs/api/presets.md). */
  rotationId: string;
  /** Each leg is its own plan: leg 1 = corn → soybeans, leg 2 = soybeans → corn. */
  legs: Record<Leg, string>;
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
    rotationId: "current_practice",
    legs: { 1: "corn_soy__no_cover", 2: "soy_corn__no_cover" },
    name: "What you do now",
    subtitle: "No planted winter cover · residue may remain",
    headings: {
      why: [c("The rotation the other two are compared against. Same harvest and planting dates; only the winters change.")],
      evidence: [c("Every spring since 1981 replayed for the same planting date with NASA rainfall for this area.", "nasa-power")],
      benefits: [c("No cover-crop seed, planting or termination work.", "ncs-soy-4")],
      gaps: [c("Residue cover, slope and storm intensity decide real erosion; this tool does not measure them.")],
      risks: [c("Without living cover, soil has less protection through fall and winter.", "ncs-cover")],
    },
  },
  {
    key: "cover",
    rotationId: "winter_cover",
    legs: { 1: "corn_soy__rye", 2: "soy_corn__rye" },
    name: "Add winter cover",
    subtitle: "Cereal rye in both winters",
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
        c("Small grains can be planted after soybean harvest, so the second winter is covered too.", "ncs-cover"),
      ],
      gaps: [
        c("Days with living rye are planned from dates; actual establishment and growth are not measured."),
        c("The field-moisture check comes from soybean guidance, so it applies to the winter before soybeans only."),
      ],
      risks: [
        c("A living cover uses soil moisture. In a dry spring it can leave the seedbed too dry before planting.", "ncs-soy-4"),
        c("Before corn, rye can tie up soil nitrogen as it breaks down, so plan the nitrogen rate.", "ncs-cover"),
        c("Extra seed, planting and termination work.", "ncs-soy-4"),
      ],
    },
  },
  {
    key: "grain",
    rotationId: "add_grain_crop",
    legs: { 1: "corn_soy__wheat_dc", 2: "soy_corn__no_cover" },
    name: "Add a grain crop",
    subtitle: "Wheat for grain, then June soybeans",
    headings: {
      why: [c("Adds a third harvested crop to the same land over two years.")],
      evidence: [
        c("NC State reports lower yields for soybeans planted in June than in the Apr 20–May 20 window.", "ncs-soy-5"),
      ],
      benefits: [c("Wheat keeps the soil covered through the first winter.", "ncs-cover")],
      gaps: [
        c("The wheat winter is not evaluated yet: wheat planting and harvest windows are not sourced."),
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

/*
  Priorities (Phase 7.1). The grower picks up to two; the card order and every number
  stay the same. A badge says how a plan relates to the priority, with a sourced reason:
  "matches", "partly" (one winter only) or "trade-off". Plans with nothing sourced to say
  get no badge.
  "Keep spring moisture" replaces "Save water": the tool measures no water saving.
*/
export type Priority = "soil" | "income" | "water";

export const PRIORITY_INFO: Record<Priority, { label: string; short: string }> = {
  soil: { label: "Protect the soil", short: "Protect soil" },
  income: { label: "Add a grain harvest", short: "Grain harvest" },
  water: { label: "Keep spring soil moisture", short: "Spring moisture" },
};

export const PRIORITY_ORDER: Priority[] = ["soil", "water", "income"];

export type PriorityFit = "matches" | "partly" | "tradeoff";

export const PRIORITY_FIT: Record<CardKey, Partial<Record<Priority, { fit: PriorityFit; reason: Claim }>>> = {
  current: {
    soil: { fit: "tradeoff", reason: c("Without living cover, soil has less protection through fall and winter.", "ncs-cover") },
    water: { fit: "matches", reason: c("No cover crop is using soil moisture before planting.", "ncs-soy-4") },
  },
  cover: {
    soil: { fit: "matches", reason: c("Rye gives some of the strongest erosion protection through fall and winter.", "ncs-cover") },
    water: { fit: "tradeoff", reason: c("A living cover uses soil moisture before planting.", "ncs-soy-4") },
  },
  grain: {
    soil: {
      fit: "partly",
      reason: c("Wheat keeps the soil covered through the first winter; the second winter has no planted cover.", "ncs-cover"),
    },
    income: { fit: "matches", reason: c("Adds a wheat harvest to the same land over two years.") },
  },
};
