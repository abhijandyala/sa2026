// Writes web/public/data/sample/ in the SHAPE of Rahul's draft API examples
// (backend branch: docs/api/examples/ and docs/api/presets.md, Nov 12 2026).
// The weather is SYNTHETIC and every file says "draft": true, so the UI shows a
// draft-data banner. The backend's generated output (its Phase 10) replaces these
// files with the same names.
//
// Presets are rotations with two legs; each leg is its own plan, tested against every
// spring on its own, and the legs are never summed:
//   current_practice: corn_soy__no_cover + soy_corn__no_cover
//   winter_cover:     corn_soy__rye      + soy_corn__rye
//   add_grain_crop:   corn_soy__wheat_dc + soy_corn__no_cover
// corn_soy__wheat_dc is "unavailable: catalog_missing" until the wheat rows land.
// Sample dates follow presets.md and are flagged dates_assumed.
//
// Frontend additions the drafts do not carry yet (see web/docs/api-requests.md):
//   compare.spring_windows (per-year results per window), plans[].spring_window_id,
//   spring_windows[].eras.dry_spring, plans[].winter.per_season,
//   sensitivity.points[].qualifying_years and .eras.
//
// Rules mirrored from the backend phase cards: spring window = [plant − 30d, plant − 1d];
// winter window = [prev_harvest, next_plant); living cover = [seed, terminate);
// dry = bottom 20% of complete windows, ties count as dry; rank 1 = driest;
// cr_tt_03 fires when gap < 14 AND (dry OR grower concern);
// eras 1981–2000 vs 2006–2025, ≥ 15 of 20 evaluable, "similar" when |Δ| < 10 pp.

import { mkdirSync, rmSync, writeFileSync } from "node:fs";
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
const daily = new Map();
let soil = 0.6;
let wetness = 1;
for (let t = ms("1981-01-01"); t <= ms("2025-06-30"); t += DAY) {
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

const YEARS = Array.from({ length: 2025 - 1981 + 1 }, (_, i) => 1981 + i);
const ERA = { earlier: [1981, 2000], recent: [2006, 2025] };
const MIN_ERA = 15;

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

// ---------------------------------------------------------------- spring windows (one per planting date)
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
      year: y, start, end: add(plant, -1),
      total_mm: complete ? r1(total) : null,
      status: complete ? "complete" : valid ? "partial" : "unavailable",
      rank: null, of: null, percentile: null, is_dry: null,
      gwettop_window_mean: complete ? r2(top / 30) : null,
      gwetroot_window_mean: complete ? r2(root / 30) : null,
    };
  });
  const ok = years.filter((y) => y.status === "complete");
  const sorted = [...ok].sort((a, b) => a.total_mm - b.total_mm || a.year - b.year);
  const cutoff = sorted[Math.max(0, Math.ceil(0.2 * sorted.length) - 1)].total_mm;
  sorted.forEach((y, i) => {
    y.rank = i + 1;
    y.of = sorted.length;
    y.percentile = r1(((i + 1) / sorted.length) * 100);
    y.is_dry = y.total_mm <= cutoff;
  });
  const med = median(ok.map((y) => y.total_mm));
  const typical = [...ok].sort((a, b) => Math.abs(a.total_mm - med) - Math.abs(b.total_mm - med) || a.year - b.year)[0].year;
  const dry = ok.filter((y) => y.is_dry).sort((a, b) => b.total_mm - a.total_mm || a.year - b.year)[0].year;
  const wet = [...ok].sort((a, b) => b.total_mm - a.total_mm || a.year - b.year)[0].year;
  const s = add(`2001-${plantMD}`, -30).slice(5);
  const e = add(`2001-${plantMD}`, -1).slice(5);
  return {
    id, label, plant: plantMD, start: s, end: e,
    threshold: { value: cutoff, unit: "mm", method: "bottom 20% of eligible 30-day windows; ties at cutoff count as dry", window: `${s}..${e}`, reference_span: "1981-2025", status: "complete" },
    median_mm: r1(med),
    dry_count: ok.filter((y) => y.is_dry).length,
    denominator: ok.length,
    shortcuts: { typical, dry, wet },
    years,
    eras: { dry_spring: eraCompare(years, (y) => y.status === "complete", (y) => y.is_dry) },
  };
}

const WINDOWS = {
  soy_full_season: springWindow("soy_full_season", "05-12", "30 days before soybean planting"),
  corn_planting: springWindow("corn_planting", "04-15", "30 days before corn planting"),
};

// ---------------------------------------------------------------- plans (presets.md, dates assumed)
const SOURCE_SOY4 = { title: "NC State Soybean Production Guide: Rotational Considerations", url: "https://content.ces.ncsu.edu/north-carolina-soybean-production-guide/rotational-considerations" };

const PLANS = [
  { plan_id: "corn_soy__no_cover", rotation_id: "current_practice", leg: 1, label: "No planted winter cover before soybean", prev_crop: "field_corn", prev: "09-20", winter: { type: "none" }, next_crop: "soybean", plant: "05-12", window: "soy_full_season" },
  { plan_id: "corn_soy__rye", rotation_id: "winter_cover", leg: 1, label: "Cereal rye before soybean", prev_crop: "field_corn", prev: "09-20", winter: { type: "cover", crop_id: "cereal_rye", seed: "10-01", terminate: "04-30" }, next_crop: "soybean", plant: "05-12", window: "soy_full_season", moistureRule: true },
  { plan_id: "soy_corn__no_cover", rotation_id: "current_practice", leg: 2, label: "No planted winter cover before corn", prev_crop: "soybean", prev: "10-15", winter: { type: "none" }, next_crop: "field_corn", plant: "04-15", window: "corn_planting" },
  { plan_id: "soy_corn__rye", rotation_id: "winter_cover", leg: 2, label: "Cereal rye before corn", prev_crop: "soybean", prev: "10-15", winter: { type: "cover", crop_id: "cereal_rye", seed: "10-20", terminate: "04-05" }, next_crop: "field_corn", plant: "04-15", window: "corn_planting" },
];

const ROTATIONS = [
  { rotation_id: "current_practice", label: "Current practice", legs: [{ leg: 1, plan_id: "corn_soy__no_cover" }, { leg: 2, plan_id: "soy_corn__no_cover" }] },
  { rotation_id: "winter_cover", label: "Winter cover", legs: [{ leg: 1, plan_id: "corn_soy__rye" }, { leg: 2, plan_id: "soy_corn__rye" }] },
  { rotation_id: "add_grain_crop", label: "Add a grain crop", legs: [{ leg: 1, plan_id: "corn_soy__wheat_dc" }, { leg: 2, plan_id: "soy_corn__no_cover" }] },
];

function coverInterval(p, y) {
  if (p.winter.type !== "cover") return null;
  const seedYear = Number(p.winter.seed.slice(0, 2)) >= 7 ? y - 1 : y;
  return [`${seedYear}-${p.winter.seed}`, `${y}-${p.winter.terminate}`];
}

const OTHER_CHECKS = {
  corn_soy__no_cover: [{ rule_id: "sb_pw_01", verdict: "preferred", reason: "May 12 is inside the Apr 20–May 20 full-season soybean window" }],
  corn_soy__rye: [
    { rule_id: "sb_pw_01", verdict: "preferred", reason: "May 12 is inside the Apr 20–May 20 full-season soybean window" },
    { rule_id: "cr_tt_04", verdict: "manual_check", reason: "Applies only if insect pest spillover is a concern; grower input not provided" },
  ],
  soy_corn__no_cover: [
    { rule_id: "fc_pw_01", verdict: "manual_check", reason: "Plant corn once soil is at or above 55 F; no soil temperature input. Conflicts with fc_pw_02 (50 F)" },
    { rule_id: "fc_pw_02", verdict: "manual_check", reason: "Below 50 F soil temperature is a germination concern; no soil temperature input. Conflicts with fc_pw_01 (55 F)" },
    { rule_id: "fc_wt_03", verdict: "manual_check", reason: "Choose hybrid and date so silking avoids July 1–20" },
  ],
  soy_corn__rye: [
    { rule_id: "cr_tt_01", verdict: "preferred", reason: "Gap 10 days is within 7–14 days before corn" },
    { rule_id: "cr_nut_01", verdict: "manual_check", reason: "Corn after rye: plan the nitrogen rate, rye can tie up nitrogen" },
    { rule_id: "fc_nut_02", verdict: "acceptable", reason: "Starter fertilizer can speed early growth in no-till corn after a small grain cover" },
    { rule_id: "fc_pw_01", verdict: "manual_check", reason: "Plant corn once soil is at or above 55 F; no soil temperature input. Conflicts with fc_pw_02 (50 F)" },
    { rule_id: "fc_pw_02", verdict: "manual_check", reason: "Below 50 F soil temperature is a germination concern; no soil temperature input. Conflicts with fc_pw_01 (55 F)" },
    { rule_id: "fc_wt_03", verdict: "manual_check", reason: "Choose hybrid and date so silking avoids July 1–20" },
  ],
};

function buildPlan(p, { concern = false } = {}) {
  const w = WINDOWS[p.window];
  const ex = 2007;
  const winterStart = `${ex - 1}-${p.prev}`;
  const plant = `${ex}-${p.plant}`;
  const cov = coverInterval(p, ex);
  const living = cov ? diff(cov[0], cov[1]) : 0;
  const gap = cov ? diff(cov[1], plant) : null;

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
      if (!(c && d >= c[0] && d < c[1])) total += mm;
    }
    return { year: y, rain_mm_without_cover: valid === n ? r1(total) : null, status: valid === n ? "complete" : valid ? "partial" : "unavailable" };
  });
  const winterOk = perSeason.filter((s) => s.status === "complete");

  const plan = {
    plan_id: p.plan_id,
    rotation_id: p.rotation_id,
    leg: p.leg,
    label: p.label,
    editable: ["prev_harvest", ...(p.winter.type === "cover" ? ["winter.seed", "winter.terminate"] : []), "next_plant"],
    dates_assumed: true,
    sequence: { previous_crop_id: p.prev_crop, prev_harvest: p.prev, winter: p.winter, next_crop_id: p.next_crop, next_plant: p.plant },
    spring_window: { start: w.start, end: w.end },
    spring_window_id: p.window,
    calendar: {
      living_cover_days_planned: living,
      days_without_planned_cover: diff(winterStart, plant) - living,
      termination_gap_days: gap,
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
    other_checks: OTHER_CHECKS[p.plan_id] ?? [],
    eras: {},
  };

  if (p.moistureRule) {
    const qualifying = w.years.filter((y) => y.status === "complete" && gap < 14 && (y.is_dry || concern)).map((y) => y.year);
    plan.spring_checks.push({
      check_id: "rye_soy_short_gap_moisture",
      rule_ids: ["cr_tt_03"],
      label: gap < 14 ? "Would have prompted a field-moisture check" : "Gap is 14 days or more; short-gap check clears",
      fires_when: "gap < 14 days AND (dry replay OR grower low-moisture concern)",
      count: qualifying.length,
      denominator: w.denominator,
      pct: r1((qualifying.length / w.denominator) * 100),
      qualifying_years: qualifying,
      skipped_years: [],
      source: SOURCE_SOY4,
    });
    plan.eras.rye_soy_short_gap_moisture = eraCompare(w.years, (y) => y.status === "complete", (y) => qualifying.includes(y.year));
  }
  if (p.winter.type === "none") {
    plan.residue_context = { status: "unknown", note: `${p.prev_crop === "soybean" ? "Soybean" : "Corn"} residue may remain; not measured` };
  }
  return plan;
}

const plans = PLANS.map((p) => buildPlan(p));
plans.splice(2, 0, {
  plan_id: "corn_soy__wheat_dc",
  rotation_id: "add_grain_crop",
  leg: 1,
  label: "Winter wheat for grain, then double-crop soybean",
  status: "unavailable",
  reason: "catalog_missing: wheat planting and harvest windows and the double-crop soybean window are not yet sourced",
  spring_checks: [],
  other_checks: [
    { rule_id: "ww_rc_01", verdict: "caution", reason: "Wheat after corn: check head scab risk" },
    { rule_id: "sb_rc_03", verdict: "caution", reason: "Double-crop soybeans: maturity groups under 4 need a caution" },
  ],
  eras: {},
});

const meta = (id) => ({ plan_version: "pv_sample", catalog_version: "v1", snapshot_hash: "sha256:SYNTHETIC", request_id: id, draft: true });

const compare = {
  meta: meta("req_cmp_sample"),
  request_echo: { location_id: "union_county_sample", rotation_ids: ROTATIONS.map((r) => r.rotation_id) },
  thresholds: {
    heavy_rain: { value: null, unit: "mm", method: "PENDING handbook definition", reference_span: "1981-2025", status: "unknown" },
    dry_spring: WINDOWS.soy_full_season.threshold,
  },
  shared_eligible_years: { spring: WINDOWS.soy_full_season.denominator, winter: plans[0].winter.eligible_seasons },
  plans,
  spring_window: { note: "Per plan. Leg 1 plans share 04-12..05-11; leg 2 plans share 03-16..04-14. Termination edits never change it; planting-date edits do." },
  rotations: ROTATIONS,
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

// ---------------------------------------------------------------- sensitivity sweep for corn_soy__rye
const rye = PLANS.find((p) => p.plan_id === "corn_soy__rye");
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
    qualifying_years: plan.spring_checks[0].qualifying_years, // REQUESTED
    eras: plan.eras.rye_soy_short_gap_moisture, // REQUESTED
  });
}
const sensitivity = {
  meta: meta("req_sens_sample"),
  base_plan_id: "corn_soy__rye",
  varied: "terminate",
  fixed: { next_plant: rye.plant, seed: rye.winter.seed },
  check_id: "rye_soy_short_gap_moisture",
  denominator: sw.denominator,
  points,
};

// ---------------------------------------------------------------- write
rmSync(join(OUT, "replay"), { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
for (const [name, body] of Object.entries({ years, compare, sensitivity })) {
  writeFileSync(join(OUT, `${name}.json`), JSON.stringify(body, null, 1) + "\n");
}

// Replay (GET /v1/seasons/{year}/replay?plan=). `daily` is trimmed to the 30-day spring
// window to keep the static sample small; `daily_scope` says so.
let replayFiles = 0;
for (const p of PLANS) {
  const built = plans.find((x) => x.plan_id === p.plan_id);
  const w = WINDOWS[p.window];
  const check = built.spring_checks.find((c) => c.check_id === "rye_soy_short_gap_moisture");
  mkdirSync(join(OUT, "replay", p.plan_id), { recursive: true });
  for (const y of w.years) {
    const cov = coverInterval(p, y.year);
    const days = [];
    for (let d = y.start; d <= y.end; d = add(d, 1)) {
      const rec = daily.get(d);
      const covered = cov && d >= cov[0] && d < cov[1];
      days.push({
        date: d,
        precip_mm: rec ? rec.mm : null,
        status: rec ? "complete" : "unavailable",
        gwettop: rec ? rec.top : null,
        gwetroot: rec ? rec.root : null,
        cover_status: p.winter.type === "none" ? "no_planned_cover" : covered ? "planned_living_cover" : "terminated",
        segment: p.winter.type === "none" ? "no_planned_cover" : covered ? "living_cover" : "after_termination",
      });
    }
    const triggered = check && check.qualifying_years.includes(y.year)
      ? [{ check_id: check.check_id, rule_ids: check.rule_ids, reason: `Gap ${built.calendar.termination_gap_days} days < 14 and spring window ranked dry (${y.total_mm} mm <= ${w.threshold.value} mm cutoff)` }]
      : [];
    const body = {
      meta: meta(`req_rep_${p.plan_id}_${y.year}`),
      year: y.year,
      plan_id: p.plan_id,
      dates: {
        prev_harvest: `${y.year - 1}-${p.prev}`,
        ...(cov ? { seed: cov[0], terminate: cov[1] } : {}),
        next_plant: `${y.year}-${p.plant}`,
        spring_window: { start: y.start, end: y.end },
      },
      coverage: { winter: y.year === 1981 ? "unavailable" : "complete", spring: y.status },
      spring: { total_mm: y.total_mm, rank: y.rank, of: y.of, percentile: y.percentile, is_dry: y.is_dry, status: y.status },
      wetness: { gwettop_window_mean: y.gwettop_window_mean, gwetroot_window_mean: y.gwetroot_window_mean, unit: "fraction (0-1)", label: "modeled", status: y.gwetroot_window_mean === null ? "unavailable" : "complete" },
      checks_triggered: triggered,
      key_rain_days: days.filter((d) => (d.precip_mm ?? 0) >= 20).map((d) => ({ date: d.date, precip_mm: d.precip_mm, segment: d.segment, heavy: null })),
      daily_scope: "spring_window",
      daily: days,
    };
    writeFileSync(join(OUT, "replay", p.plan_id, `${y.year}.json`), JSON.stringify(body) + "\n");
    replayFiles++;
  }
}

const p12 = plans.find((p) => p.plan_id === "corn_soy__rye");
console.log(
  `sample written to ${OUT} (${replayFiles} replay files)\n` +
    `soy window: cutoff ${sw.threshold.value} mm, dry ${sw.dry_count}/${sw.denominator}, typical ${sw.shortcuts.typical}, dry replay ${sw.shortcuts.dry}\n` +
    `corn window: cutoff ${WINDOWS.corn_planting.threshold.value} mm, typical ${WINDOWS.corn_planting.shortcuts.typical}, dry replay ${WINDOWS.corn_planting.shortcuts.dry}\n` +
    `corn_soy__rye check ${p12.spring_checks[0].count}/${p12.spring_checks[0].denominator}; winter rain without cover: ` +
    plans.filter((p) => p.winter).map((p) => `${p.plan_id} ${p.winter.per_season_median.rain_mm_without_cover} mm (gap ${p.calendar.termination_gap_days})`).join(", "),
);
