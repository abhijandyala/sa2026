// Generates public/data/fixture-synthetic.json: SYNTHETIC test data shaped like the
// agreed data contract (src/data/schema.ts). It lets the frontend be built before
// Rahul's real NASA POWER bundle exists. Every value here is invented and the
// manifest says so; the UI shows a "Synthetic test data" banner while it is loaded.
//
// It also acts as a reference implementation of the contract's rules for Rahul:
// 30-day window ending the day before planting, nearest-rank 20th percentile,
// typical = nearest the median (earliest on ties), dry replay = highest complete
// total at or below the cutoff, minimum 15 complete years, zero is valid, null is missing.

import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const OUT = join(here, "..", "public", "data", "fixture-synthetic.json");

// ---------- deterministic randomness ----------
function mulberry32(seed) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(20261114);

// ---------- date helpers (UTC, no time zones) ----------
const DAY = 86400000;
const toMs = (iso) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
const toIso = (ms) => new Date(ms).toISOString().slice(0, 10);
const addDays = (iso, n) => toIso(toMs(iso) + n * DAY);
const diffDays = (a, b) => Math.round((toMs(b) - toMs(a)) / DAY);
const withYear = (iso, year) => `${year}${iso.slice(4)}`;

// ---------- the sample farm plan (fictional, Union County) ----------
const plan = {
  isExample: true,
  locationId: "union-nc",
  locationLabel: "Union County, NC",
  cornHarvest: "2026-10-05",
  ryeSeed: "2026-10-14",
  ryeEnd: "2027-04-30",
  ryeEndEarlier: "2027-04-23",
  soyPlant: "2027-05-12",
  soyHarvest: "2027-10-20",
  wheatPlant: "2026-10-25",
  wheatHarvest: "2027-06-10",
  soyDoubleCropPlant: "2027-06-15",
  cornPlant: "2028-04-15",
  soilSource: "sample",
  soilTexture: "Sandy loam (sample profile)",
  moistureConcern: "unknown",
  irrigation: "unknown",
  priorities: [],
};
const secondCoverSeed = "2027-10-25";
const secondCoverEnd = "2028-03-30";

const FIRST_YEAR = 1981;
const LAST_YEAR = 2025;
const SPLIT_LAST_EARLIER = 2002;
const WINDOW = 30;
const MIN_COMPLETE = 15;
const DRY_PCT = 0.2;
const GAP_RULE_DAYS = 14;

// ---------- synthetic daily weather per year ----------
// One continuous Mar 1 – Jun 30 series per year so overlapping windows agree.
const weather = {};
for (let y = FIRST_YEAR; y <= LAST_YEAR; y++) {
  const wetness = 0.55 + rand() * 0.9; // year-to-year variation
  const days = {};
  let soil = 0.55 + rand() * 0.15;
  for (let d = toMs(`${y}-03-01`); d <= toMs(`${y}-06-30`); d += DAY) {
    const wet = rand() < 0.3 * wetness;
    const mm = wet ? Math.round(-Math.log(1 - rand()) * 9 * wetness * 10) / 10 : 0;
    soil = Math.min(0.95, Math.max(0.12, soil * 0.985 + mm * 0.004));
    days[toIso(d)] = { mm, soil: Math.round(soil * 1000) / 1000 };
  }
  weather[y] = days;
}
// Case D / K fixtures: two missing rain days in 1994's May window, missing soil wetness in 2008.
weather[1994]["1994-04-20"].mm = null;
weather[1994]["1994-04-21"].mm = null;
for (const k of Object.keys(weather[2008])) weather[2008][k].soil = null;

// ---------- per-event computation ----------
function percentileNearestRank(sorted, p) {
  const idx = Math.max(0, Math.ceil(p * sorted.length) - 1);
  return sorted[idx];
}

function buildEvent({ id, label, crop, plantingDate, gapDays, ruleApplies }) {
  const md = plantingDate.slice(4); // "-05-12"
  const years = [];
  for (let y = FIRST_YEAR; y <= LAST_YEAR; y++) {
    const plant = `${y}${md}`;
    const start = addDays(plant, -WINDOW);
    const end = addDays(plant, -1);
    let total = 0;
    let valid = 0;
    let soilSum = 0;
    let soilN = 0;
    for (let i = 0; i < WINDOW; i++) {
      const rec = weather[y][addDays(start, i)];
      if (rec && rec.mm !== null && rec.mm >= 0) {
        total += rec.mm;
        valid += 1;
      }
      if (rec && rec.soil !== null) {
        soilSum += rec.soil;
        soilN += 1;
      }
    }
    const complete = valid === WINDOW;
    years.push({
      year: y,
      window: [start, end],
      rainMm: complete ? Math.round(total * 10) / 10 : null,
      validDays: valid,
      expectedDays: WINDOW,
      complete,
      pctRank: null,
      dry: null,
      soilWetRoot: soilN === WINDOW ? Math.round((soilSum / soilN) * 100) / 100 : null,
      flag: null,
      reason: null,
      rule: null,
    });
  }

  const completeYears = years.filter((y) => y.complete);
  const sorted = completeYears.map((y) => y.rainMm).sort((a, b) => a - b);
  const labelsWithheld = completeYears.length < MIN_COMPLETE;
  const threshold = labelsWithheld ? null : percentileNearestRank(sorted, DRY_PCT);
  const median = labelsWithheld
    ? null
    : sorted.length % 2
      ? sorted[(sorted.length - 1) / 2]
      : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;

  for (const y of years) {
    if (!y.complete) {
      y.reason = "incomplete_window";
      continue;
    }
    if (!labelsWithheld) {
      y.pctRank = Math.round((sorted.filter((v) => v <= y.rainMm).length / sorted.length) * 1000) / 1000;
      y.dry = y.rainMm <= threshold;
    }
    if (ruleApplies) {
      const short = gapDays !== null && gapDays < GAP_RULE_DAYS;
      y.flag = Boolean(y.dry && short);
      y.reason = y.flag ? "dry_window_and_gap_under_14" : null;
      y.rule = y.flag ? "ncs-soy-4" : null;
    } else if (y.dry) {
      y.reason = "dry_window_no_rule";
    }
  }

  let typicalYear = null;
  let dryReplayYear = null;
  if (!labelsWithheld) {
    typicalYear = [...completeYears].sort(
      (a, b) => Math.abs(a.rainMm - median) - Math.abs(b.rainMm - median) || a.year - b.year,
    )[0].year;
    const atOrBelow = completeYears.filter((y) => y.rainMm <= threshold);
    const top = Math.max(...atOrBelow.map((y) => y.rainMm));
    dryReplayYear = atOrBelow.filter((y) => y.rainMm === top).sort((a, b) => a.year - b.year)[0].year;
  }
  const typicalMm = completeYears.find((y) => y.year === typicalYear)?.rainMm;
  const dryMm = completeYears.find((y) => y.year === dryReplayYear)?.rainMm;

  const half = (from, to) => {
    const ys = completeYears.filter((y) => y.year >= from && y.year <= to);
    return {
      range: `${from}–${to}`,
      complete: ys.length,
      dry: ys.filter((y) => y.dry).length,
      flagged: ruleApplies ? ys.filter((y) => y.flag).length : null,
    };
  };

  return {
    id,
    label,
    crop,
    plantingDate,
    windowDays: WINDOW,
    gapDays,
    years,
    summary: {
      completeYears: completeYears.length,
      excludedYears: years.length - completeYears.length,
      minCompleteYears: MIN_COMPLETE,
      labelsWithheld,
      medianMm: median === null ? null : Math.round(median * 10) / 10,
      dryThresholdMm: threshold,
      dryRule: "At or below the 20th percentile (nearest rank) of complete years",
      dryCount: labelsWithheld ? null : completeYears.filter((y) => y.dry).length,
      flagged: ruleApplies ? completeYears.filter((y) => y.flag).length : null,
      ruleApplies,
      earlier: half(FIRST_YEAR, SPLIT_LAST_EARLIER),
      recent: half(SPLIT_LAST_EARLIER + 1, LAST_YEAR),
      typicalYear,
      dryReplayYear,
      contrastWithheld: typicalMm !== undefined && typicalMm === dryMm,
    },
  };
}

const soyMayGap = diffDays(plan.ryeEnd, plan.soyPlant); // 12
const events = {
  currentSoy: buildEvent({ id: "soy-may", label: "Soybean planting", crop: "soybeans", plantingDate: plan.soyPlant, gapDays: null, ruleApplies: false }),
  currentCorn: buildEvent({ id: "corn-apr", label: "Corn planting", crop: "corn", plantingDate: plan.cornPlant, gapDays: null, ruleApplies: false }),
  ryeSoy: buildEvent({ id: "soy-may", label: "Soybean planting after rye", crop: "soybeans", plantingDate: plan.soyPlant, gapDays: soyMayGap, ruleApplies: true }),
  coverCorn: buildEvent({ id: "corn-apr", label: "Corn planting after rye", crop: "corn", plantingDate: plan.cornPlant, gapDays: diffDays(secondCoverEnd, plan.cornPlant), ruleApplies: false }),
  wheatSoy: buildEvent({ id: "soy-jun", label: "June soybean planting after wheat", crop: "soybeans", plantingDate: plan.soyDoubleCropPlant, gapDays: diffDays(plan.wheatHarvest, plan.soyDoubleCropPlant), ruleApplies: false }),
  wheatCorn: buildEvent({ id: "corn-apr", label: "Corn planting", crop: "corn", plantingDate: plan.cornPlant, gapDays: null, ruleApplies: false }),
};

// ---------- trade-off curve for the rye end date ----------
const ryeEvent = events.ryeSoy;
const dryCompleteYears = ryeEvent.years.filter((y) => y.complete && y.dry).length;
const points = [];
for (let end = addDays(plan.ryeSeed, 1); toMs(end) < toMs(plan.soyPlant); end = addDays(end, 1)) {
  const gap = diffDays(end, plan.soyPlant);
  points.push({
    endDate: end,
    livingCoverDays: diffDays(plan.ryeSeed, end),
    gapDays: gap,
    flagged: gap < GAP_RULE_DAYS ? dryCompleteYears : 0,
  });
}

// ---------- strategies ----------
const C = (text, source = null) => ({ text, source });
const strategies = [
  {
    id: "current",
    name: "What you do now",
    subtitle: "No planted winter cover · crop residue may remain",
    sequence: [
      { crop: "corn", label: "Corn", start: "2026-04-15", end: plan.cornHarvest, role: "cash" },
      { crop: "none", label: "No planted winter cover", start: plan.cornHarvest, end: plan.soyPlant, role: "fallow" },
      { crop: "soybeans", label: "Soybeans", start: plan.soyPlant, end: plan.soyHarvest, role: "cash" },
      { crop: "none", label: "No planted winter cover", start: plan.soyHarvest, end: plan.cornPlant, role: "fallow" },
      { crop: "corn", label: "Corn", start: plan.cornPlant, end: "2028-10-05", role: "cash" },
    ],
    headings: {
      why: [C("The plan the other two are compared against. Same corn and soybean dates; only the winters change.")],
      evidence: [C("Each spring since 1981 replayed for the same planting dates.", "nasa-power")],
      benefits: [C("No cover-crop seed, planting or termination work.", "ncs-soy-4")],
      gaps: [C("Erosion depends on residue, slope and storms, which this app does not measure.")],
      risks: [C("Without living cover, soil has less protection through fall and winter.", "ncs-cover")],
    },
    matches: ["water"],
    metrics: { gapDays: null, livingCoverDays: null },
    events: [events.currentSoy, events.currentCorn],
    headlineEventId: "soy-may",
    feasibility: [
      { check: "soybean_optimum_window", result: "pass", message: "May 12 is inside NC State's Apr 20–May 20 optimum soybean planting period.", source: "ncs-soy-5" },
    ],
  },
  {
    id: "protect-soil",
    name: "Protect the soil",
    subtitle: "Cereal rye before soybeans, rye again before corn",
    sequence: [
      { crop: "corn", label: "Corn", start: "2026-04-15", end: plan.cornHarvest, role: "cash" },
      { crop: "rye", label: "Cereal rye", start: plan.ryeSeed, end: plan.ryeEnd, role: "cover" },
      { crop: "soybeans", label: "Soybeans", start: plan.soyPlant, end: plan.soyHarvest, role: "cash" },
      { crop: "rye", label: "Cereal rye", start: secondCoverSeed, end: secondCoverEnd, role: "cover" },
      { crop: "corn", label: "Corn", start: plan.cornPlant, end: "2028-10-05", role: "cash" },
    ],
    headings: {
      why: [
        C("Cereal rye is one of the most popular cover crops planted before soybeans.", "ncs-soy-4"),
        C("Rye gives some of the strongest erosion protection through fall and winter.", "ncs-cover"),
      ],
      evidence: [
        C("If low soil moisture is a concern, NC State suggests ending the cover at least two weeks before soybean planting.", "ncs-soy-4"),
        C("Each spring since 1981 replayed with NASA rainfall for this location.", "nasa-power"),
      ],
      benefits: [
        C("Can suppress weeds and, with no-till, help conserve soil moisture later in the season.", "ncs-soy-4"),
        C("Small grains can be planted after soybean harvest, so the second winter is covered too.", "ncs-cover"),
      ],
      gaps: [
        C("Actual rye growth and residue depend on your field and are not measured here."),
        C("A moisture rule for corn planting after a cover crop has not been sourced yet."),
      ],
      risks: [
        C("A living cover uses soil moisture. In a dry spring it can leave the seedbed too dry.", "ncs-soy-4"),
        C("Grass covers can tie up soil nitrogen as they break down, which matters before corn.", "ncs-cover"),
        C("Extra seed, planting and termination work.", "ncs-soy-4"),
      ],
    },
    matches: ["soil"],
    metrics: { gapDays: soyMayGap, livingCoverDays: diffDays(plan.ryeSeed, plan.ryeEnd) },
    events: [events.ryeSoy, events.coverCorn],
    headlineEventId: "soy-may",
    feasibility: [
      { check: "legume_window", result: "fail", message: "Your soybeans come off Oct 20, after the Oct 1 crimson clover window for the Piedmont. Rye is used instead.", source: "ncs-cover" },
      { check: "soybean_optimum_window", result: "pass", message: "May 12 is inside NC State's Apr 20–May 20 optimum soybean planting period.", source: "ncs-soy-5" },
    ],
  },
  {
    id: "earn-more",
    name: "Earn more",
    subtitle: "Wheat for grain, then June soybeans",
    sequence: [
      { crop: "corn", label: "Corn", start: "2026-04-15", end: plan.cornHarvest, role: "cash" },
      { crop: "wheat", label: "Wheat for grain", start: plan.wheatPlant, end: plan.wheatHarvest, role: "cash" },
      { crop: "soybeans", label: "Soybeans (June)", start: plan.soyDoubleCropPlant, end: "2027-11-05", role: "cash" },
      { crop: "none", label: "No planted winter cover", start: "2027-11-05", end: plan.cornPlant, role: "fallow" },
      { crop: "corn", label: "Corn", start: plan.cornPlant, end: "2028-10-05", role: "cash" },
    ],
    headings: {
      why: [C("Adds a third crop to sell from the same land over two years.")],
      evidence: [
        C("NC State reports lower yields for soybeans planted in June than in the Apr 20–May 20 window.", "ncs-soy-5"),
        C("Each June planting window since 1981 replayed with NASA rainfall.", "nasa-power"),
      ],
      benefits: [C("Grain income from the wheat crop."), C("Wheat covers the soil through the first winter.", "ncs-cover")],
      gaps: [
        C("Wheat planting and harvest dates are sample values until an NC State small-grain source is linked."),
        C("Prices and costs are not included."),
      ],
      risks: [
        C("June-planted soybeans yield less.", "ncs-soy-5"),
        C("A dry seedbed right after wheat harvest."),
        C("Little time between wheat harvest and soybean planting."),
      ],
    },
    matches: ["income"],
    metrics: { gapDays: diffDays(plan.wheatHarvest, plan.soyDoubleCropPlant), livingCoverDays: null },
    events: [events.wheatSoy, events.wheatCorn],
    headlineEventId: "soy-jun",
    feasibility: [
      { check: "soybean_optimum_window", result: "fail", message: "June 15 is after NC State's Apr 20–May 20 optimum period. Expect lower yields.", source: "ncs-soy-5" },
    ],
  },
];

const bundle = {
  contractVersion: 1,
  manifest: {
    synthetic: true,
    dataset: "SYNTHETIC TEST DATA shaped like NASA POWER Daily (not real weather)",
    community: "AG",
    parameters: [
      { name: "PRECTOTCORR", units: "mm/day", description: "Precipitation corrected (synthetic values)" },
      { name: "GWETROOT", units: "0-1", description: "Root zone soil wetness (synthetic values)" },
    ],
    point: { id: "union-nc", label: "Reference point near Monroe, Union County, NC", lat: 34.98, lon: -80.55 },
    range: { start: `${FIRST_YEAR}-03-01`, end: `${LAST_YEAR}-06-30` },
    timeStandard: "LST",
    scaleNote: "Regional grid estimate, not a farm gauge (synthetic fixture).",
    retrievedAt: "2026-11-12T00:00:00Z",
    queryUrl: "n/a (generated by web/scripts/make-fixture.mjs)",
    recreate: "cd web && npm run fixture",
  },
  plan,
  strategies,
  curves: [
    {
      strategyId: "protect-soil",
      eventId: "soy-may",
      seedDate: plan.ryeSeed,
      plantingDate: plan.soyPlant,
      proposedEnd: plan.ryeEnd,
      earlierEnd: plan.ryeEndEarlier,
      completeYears: ryeEvent.summary.completeYears,
      points,
    },
  ],
  sources: [
    { id: "ncs-soy-4", title: "NC Soybean Production Guide, ch. 4: Soil Health, Tillage, Cover Crops, and Crop Rotation", publisher: "NC State Extension", url: "https://content.ces.ncsu.edu/north-carolina-soybean-production-guide/rotational-considerations", checked: "2026-11-12" },
    { id: "ncs-soy-5", title: "NC Soybean Production Guide, ch. 5: Planting Decisions", publisher: "NC State Extension", url: "https://content.ces.ncsu.edu/north-carolina-soybean-production-guide/soybean-planting-decisions", checked: "2026-11-12" },
    { id: "ncs-cover", title: "Winter Annual Cover Crops", publisher: "NC State Extension", url: "https://content.ces.ncsu.edu/winter-annual-cover-crops", checked: "2026-11-12" },
    { id: "nasa-power", title: "NASA POWER Daily API", publisher: "NASA Langley Research Center", url: "https://power.larc.nasa.gov/docs/services/api/temporal/daily/" },
    { id: "nasa-power-faq", title: "NASA POWER data FAQ and spatial scale", publisher: "NASA Langley Research Center", url: "https://power.larc.nasa.gov/docs/faqs/data/" },
  ],
};

mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, JSON.stringify(bundle, null, 2) + "\n");
const s = ryeEvent.summary;
console.log(
  `wrote ${OUT}\n` +
    `protect-soil soy-may: ${s.completeYears} complete, ${s.excludedYears} excluded, dry ${s.dryCount}, flagged ${s.flagged}, ` +
    `typical ${s.typicalYear}, dry replay ${s.dryReplayYear}, median ${s.medianMm} mm, threshold ${s.dryThresholdMm} mm`,
);
