// Writes web/public/data/sample/{years,compare,sensitivity}.json in the SHAPE of Rahul's
// draft API examples (backend branch, docs/api/examples/). The weather is SYNTHETIC and
// every file says "draft": true, so the UI shows a draft-data banner. When the backend
// generates real output (its Phase 10), those files replace these with the same names.
//
// Field names follow the draft examples exactly. Additions the frontend needs are kept
// in clearly named blocks and listed for Rahul in web/docs/api-requests.md:
//   - compare.spring_windows: per-year spring results for each planting window
//   - plans[].spring_window_id: which window a plan's planting falls in
//   - spring_windows[].eras.dry_spring: earlier vs recent for dry windows (no rule needed)
//   - plans[].winter.per_season: per-year winter rain without cover (for the replay line)
//
// Rules mirrored from the backend phase cards (Phases 2–5):
//   spring window = [plant − 30d, plant − 1d]; winter window = [prev_harvest, next_plant)
//   living cover = [seed, terminate); dry = bottom 20% of complete windows, ties count as dry
//   rank 1 = driest; cr_tt_03 fires when gap < 14 AND (dry OR grower concern)
//   eras 1981–2000 vs 2006–2025, ≥ 15 of 20 evaluable, "similar" when |Δ| < 10 pp

import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "data", "sample");

function mulberry32(seed) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(20261115);

const DAY = 86400000;
const ms = (iso) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
const iso = (t) => new Date(t).toISOString().slice(0, 10);
const add = (d, n) => iso(ms(d) + n * DAY);
const diff = (a, b) => Math.round((ms(b) - ms(a)) / DAY);
const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  const n = s.length;
  return n === 0 ? null : n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
};
const r1 = (x) => Math.round(x * 10) / 10;
const r2 = (x) => Math.round(x * 100) / 100;

// ---------------------------------------------------------------- synthetic daily weather
// Starts 1981-01-01 like the real snapshot, so the 1981 winter is unavailable.
const FIRST = "1981-01-01";
const LAST = "2025-06-30";
const daily = new Map();
let soil = 0.6;
let wetness = 1;
for (let t = ms(FIRST); t <= ms(LAST); t += DAY) {
  const d = iso(t);
  if (d.endsWith("-01-01")) wetness = 0.45 + rand() * 1.0;
  const doy = (t - ms(d.slice(0, 4) + "-01-01")) / DAY;
  const season = 0.85 + 0.25 * Math.sin(((doy - 80) / 365) * 2 * Math.PI);
  const wet = rand() < 0.3 * wetness * season;
  const mm = wet ? r1(-Math.log(1 - rand()) * 9.5 * wetness) : 0;
  soil = Math.min(0.95, Math.max(0.15, soil * 0.982 + mm * 0.0045 + 0.002));
  daily.set(d, { mm, root: r2(soil), top: r2(Math.min(0.98, soil * 0.92 + mm * 0.01)) });
}
const rain = (d) => daily.get(d)?.mm ?? null;

// ---------------------------------------------------------------- plans (draft sample dates)
const YEARS = Array.from({ length: 2025 - 1981 + 1 }, (_, i) => 1981 + i);
const ERA = { earlier: [1981, 2000], recent: [2006, 2025] };
const MIN_ERA = 15;

const PLANS = [
  { plan_id: "no_cover", label: "No planted winter cover", prev: "09-20", winter: { type: "none" }, plant: "05-12", window: "soy_full_season" },
  { plan_id: "rye_12d", label: "Cereal rye, terminated 12 days before soybean", prev: "09-20", winter: { type: "cover", crop_id: "cereal_rye", seed: "10-01", terminate: "04-30" }, plant: "05-12", window: "soy_full_season" },
  { plan_id: "rye_19d", label: "Cereal rye, terminated 19 days before soybean", prev: "09-20", winter: { type: "cover", crop_id: "cereal_rye", seed: "10-01", terminate: "04-23" }, plant: "05-12", window: "soy_full_season" },
  { plan_id: "wheat_double_crop", label: "Winter wheat for grain, then double-crop soybean", prev: "09-20", winter: { type: "winter_grain", crop_id: "winter_wheat", plant: "10-25", harvest: "06-10" }, plant: "06-15", window: "soy_double_crop" },
];

// ---------------------------------------------------------------- spring windows
function springWindow(id, plantMD, label) {
  const years = YEARS.map((y) => {
    const plant = `${y}-${plantMD}`;
    const start = add(plant, -30);
    let total = 0, valid = 0, top = 0, root = 0;
    for (let i = 0; i < 30; i++) {
      const rec = daily.get(add(start, i));
      if (rec) { total += rec.mm; valid++; top += rec.top; root += rec.root; }
    }
    const complete = valid === 30;
    return {
      year: y,
      start, end: add(plant, -1),
      total_mm: complete ? r1(total) : null,
      status: complete ? "complete" : valid ? "partial" : "unavailable",
      rank: null, of: null, percentile: null, is_dry: null,
      gwettop_window_mean: complete ? r2(top / 30) : null,
      gwetroot_window_mean: complete ? r2(root / 30) : null,
    };
  });
  const ok = years.filter((y) => y.status === "complete");
  const sorted = [...ok].sort((a, b) => a.total_mm - b.total_mm || a.year - b.year);
  const cutoffIdx = Math.max(0, Math.ceil(0.2 * sorted.length) - 1);
  const cutoff = sorted[cutoffIdx].total_mm;
  sorted.forEach((y, i) => {
    y.rank = i + 1;
    y.of = sorted.length;
    y.percentile = r1(((i + 1) / sorted.length) * 100);
    y.is_dry = y.total_mm <= cutoff;
  });
  const med = median(ok.map((y) => y.total_mm));
  const typical = [...ok].sort((a, b) => Math.abs(a.total_mm - med) - Math.abs(b.total_mm - med) || a.year - b.year)[0].year;
  const dryReplay = ok.filter((y) => y.is_dry).sort((a, b) => b.total_mm - a.total_mm || a.year - b.year)[0].year;
  const wettest = [...ok].sort((a, b) => b.total_mm - a.total_mm || a.year - b.year)[0].year;
  return {
    id, label, plant: plantMD,
    start: add(`2001-${plantMD}`, -30).slice(5), end: add(`2001-${plantMD}`, -1).slice(5),
    threshold: { value: cutoff, unit: "mm", method: "bottom 20% of eligible 30-day windows; ties at cutoff count as dry", reference_span: "1981-2025", status: "complete" },
    median_mm: r1(med),
    dry_count: ok.filter((y) => y.is_dry).length,
    denominator: ok.length,
    shortcuts: { typical, dry: dryReplay, wet: wettest },
    years,
    eras: { dry_spring: eraCompare(years, (y) => y.status === "complete", (y) => y.is_dry) },
  };
}

function eraCompare(rows, eligible, counts) {
  const part = ([a, b]) => {
    const ys = rows.filter((r) => r.year >= a && r.year <= b && eligible(r));
    const count = ys.filter(counts).length;
    return { count, denominator: ys.length, pct: ys.length ? r1((count / ys.length) * 100) : null };
  };
  const earlier = part(ERA.earlier);
  const recent = part(ERA.recent);
  const enough = earlier.denominator >= MIN_ERA && recent.denominator >= MIN_ERA;
  const diff_pp = enough ? r1(recent.pct - earlier.pct) : null;
  const result = !enough ? "insufficient_data" : Math.abs(diff_pp) < 10 ? "similar" : diff_pp > 0 ? "more_frequent_recent" : "less_frequent_recent";
  return { earlier, recent, diff_pp, result, caveat: "Descriptive comparison of two periods; not a trend, cause, or forecast." };
}

const WINDOWS = {
  soy_full_season: springWindow("soy_full_season", "05-12", "30 days before full-season soybean planting"),
  soy_double_crop: springWindow("soy_double_crop", "06-15", "30 days before double-crop soybean planting"),
};

// ---------------------------------------------------------------- per plan
function coverInterval(p, y) {
  if (p.winter.type === "cover") return [`${y - 1}-${p.winter.seed}`, `${y}-${p.winter.terminate}`];
  if (p.winter.type === "winter_grain") return [`${y - 1}-${p.winter.plant}`, `${y}-${p.winter.harvest}`];
  return null;
}

function buildPlan(p, { concern = false } = {}) {
  const w = WINDOWS[p.window];
  const exampleYear = 2007;
  const winterStart = `${exampleYear - 1}-${p.prev}`;
  const plant = `${exampleYear}-${p.plant}`;
  const cov = coverInterval(p, exampleYear);
  const windowDays = diff(winterStart, plant);
  const living = cov ? diff(cov[0], cov[1]) : 0;
  const gap = p.winter.type === "cover" ? diff(cov[1], plant) : p.winter.type === "winter_grain" ? diff(cov[1], plant) : null;

  const perSeason = YEARS.map((y) => {
    const s = `${y - 1}-${p.prev}`;
    const e = `${y}-${p.plant}`;
    const c = coverInterval(p, y);
    let total = 0, valid = 0, n = 0;
    for (let d = s; d < e; d = add(d, 1)) {
      n++;
      const mm = rain(d);
      if (mm === null) continue;
      valid++;
      const covered = c && d >= c[0] && d < c[1];
      if (!covered) total += mm;
    }
    return { year: y, rain_mm_without_cover: valid === n ? r1(total) : null, status: valid === n ? "complete" : valid ? "partial" : "unavailable" };
  });
  const winterOk = perSeason.filter((s) => s.status === "complete");

  const plan = {
    plan_id: p.plan_id,
    label: p.label,
    sequence: { previous_crop_id: "field_corn", prev_harvest: p.prev, winter: p.winter, next_crop_id: "soybean", next_plant: p.plant },
    spring_window_id: p.window,
    calendar: {
      living_cover_days_planned: living,
      days_without_planned_cover: windowDays - living,
      termination_gap_days: p.winter.type === "cover" ? gap : null,
      harvest_to_plant_days: p.winter.type === "winter_grain" ? gap : null,
      establishment: p.winter.type === "none" ? "inapplicable" : "uncertain",
    },
    winter: {
      status: "complete",
      per_season_median: { rain_mm_without_cover: r1(median(winterOk.map((s) => s.rain_mm_without_cover))), heavy_rain_days_without_cover: null },
      eligible_seasons: winterOk.length,
      segments: p.winter.type === "none" ? ["no_planned_cover"] : ["before_establishment", "living_cover", "after_termination"],
      per_season: perSeason,
    },
    spring_checks: [],
    other_checks: [],
    eras: {},
  };

  if (p.winter.type === "cover") {
    const qualifying = w.years.filter((y) => y.status === "complete" && gap < 14 && (y.is_dry || concern)).map((y) => y.year);
    const count = qualifying.length;
    plan.spring_checks.push({
      check_id: "rye_soy_short_gap_moisture",
      rule_ids: ["cr_tt_03"],
      label: gap < 14 ? "Would have prompted a field-moisture check" : "Gap is 14 days or more; short-gap check clears",
      fires_when: "gap < 14 days AND (dry replay OR grower low-moisture concern)",
      count, denominator: w.denominator, pct: r1((count / w.denominator) * 100),
      qualifying_years: qualifying,
      skipped_years: [],
      source: { title: "NC State Soybean Production Guide: Rotational Considerations", url: "https://content.ces.ncsu.edu/north-carolina-soybean-production-guide/rotational-considerations" },
    });
    plan.other_checks.push({ rule_id: "cr_tt_04", verdict: "manual_check", reason: "Applies only if insect pest spillover is a concern; grower input not provided" });
    plan.eras.rye_soy_short_gap_moisture = eraCompare(w.years, (y) => y.status === "complete", (y) => qualifying.includes(y.year));
  } else {
    plan.spring_checks.push({
      check_id: "rye_soy_short_gap_moisture", rule_ids: ["cr_tt_03"], status: "inapplicable",
      label: "Rye timing check does not apply to this plan", count: null, denominator: null, pct: null, qualifying_years: [], skipped_years: [],
    });
  }

  if (p.winter.type === "none") {
    plan.residue_context = { status: "unknown", note: "Corn residue may remain; not measured" };
    plan.other_checks.push({ rule_id: "sb_pw_01", verdict: "preferred", reason: "May 12 is inside the Apr 20–May 20 full-season window" });
  }
  if (p.winter.type === "cover") {
    plan.other_checks.push({ rule_id: "sb_pw_01", verdict: "preferred", reason: "May 12 is inside the Apr 20–May 20 full-season window" });
  }
  if (p.winter.type === "winter_grain") {
    plan.status = "partial";
    plan.other_checks.push(
      { rule_id: "ww_timing", verdict: "unknown", status: "unavailable", reason: "catalog_missing: wheat planting and harvest windows are not yet sourced" },
      { rule_id: "sb_pw_03", verdict: "caution", reason: "Planting past the third week of May; NC State reports yield declines" },
      { rule_id: "ww_rc_01", verdict: "caution", reason: "Wheat after corn: check head scab risk" },
    );
    plan._frontend_note = "Frontend-only draft plan. Backend wheat path is unavailable until the wheat catalog rows land (backend Phase 12).";
  }
  return plan;
}

const plans = PLANS.map((p) => buildPlan(p));
const meta = (id) => ({ plan_version: "pv_sample", catalog_version: "v1", snapshot_hash: "sha256:SYNTHETIC", request_id: id, draft: true });

const compare = {
  meta: meta("req_cmp_sample"),
  request_echo: { location_id: "union_county_sample", plan_ids: plans.map((p) => p.plan_id) },
  thresholds: {
    heavy_rain: { value: null, unit: "mm", method: "PENDING handbook definition", reference_span: "1981-2025", status: "unknown" },
    dry_spring: { ...WINDOWS.soy_full_season.threshold, window: `${WINDOWS.soy_full_season.start}..${WINDOWS.soy_full_season.end}` },
  },
  shared_eligible_years: { spring: WINDOWS.soy_full_season.denominator, winter: plans[0].winter.eligible_seasons },
  plans,
  spring_window: { start: WINDOWS.soy_full_season.start, end: WINDOWS.soy_full_season.end, note: "Same for no_cover and the rye plans because the planting date matches; rye date edits do not change it" },
  spring_windows: WINDOWS,
};

const years = {
  meta: { ...meta("req_years_sample"), plan_version: null },
  location: { id: "union_county_sample", label: "Union County, NC (sample)", grid: { lat: 34.98, lon: -80.55, source: "NASA POWER daily (synthetic sample values)", note: "Historical NASA estimates for the regional grid near the field" } },
  years: YEARS.map((y) => ({
    year: y,
    spring: "complete",
    winter: y === 1981 ? "unavailable" : "complete",
    full_season: y === 1981 ? "partial" : "complete",
    reason: y === 1981 ? "Series starts 1981-01-01; prior fall not covered" : null,
  })),
  shortcuts: WINDOWS.soy_full_season.shortcuts,
  eras: { earlier: { start: 1981, end: 2000 }, recent: { start: 2006, end: 2025 }, excluded_from_eras: [2001, 2002, 2003, 2004, 2005] },
};

const rye = PLANS.find((p) => p.plan_id === "rye_12d");
const sw = WINDOWS.soy_full_season;
const points = [];
for (let t = "2007-03-01"; t <= "2007-05-11"; t = add(t, 1)) {
  const md = t.slice(5);
  const plan = buildPlan({ ...rye, plan_id: "sweep", winter: { ...rye.winter, terminate: md } });
  points.push({
    terminate: md,
    gap_days: plan.calendar.termination_gap_days,
    living_cover_days_planned: plan.calendar.living_cover_days_planned,
    rain_mm_without_cover_median: plan.winter.per_season_median.rain_mm_without_cover,
    checks_count: plan.spring_checks[0].count,
  });
}
const sensitivity = {
  meta: meta("req_sens_sample"),
  base_plan_id: "rye_12d",
  varied: "terminate",
  fixed: { next_plant: rye.plant, seed: rye.winter.seed },
  check_id: "rye_soy_short_gap_moisture",
  denominator: sw.denominator,
  points,
};

mkdirSync(OUT, { recursive: true });
for (const [name, body] of Object.entries({ years, compare, sensitivity })) {
  writeFileSync(join(OUT, `${name}.json`), JSON.stringify(body, null, 1) + "\n");
}
const p12 = plans.find((p) => p.plan_id === "rye_12d");
console.log(
  `sample written to ${OUT}\n` +
    `soy window: ${sw.denominator} years, cutoff ${sw.threshold.value} mm, dry ${sw.dry_count}, typical ${sw.shortcuts.typical}, dry replay ${sw.shortcuts.dry}\n` +
    `rye_12d check ${p12.spring_checks[0].count}/${p12.spring_checks[0].denominator}; winter rain without cover: ` +
    plans.map((p) => `${p.plan_id} ${p.winter.per_season_median.rain_mm_without_cover} mm`).join(", "),
);
