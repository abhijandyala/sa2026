import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { adaptCompare, adaptReplay, adaptSensitivity, BackendCompare, BackendRotations, BackendSensitivity, BackendYears, SavedWetness, shortcutsByPlant, windowId } from "./adapt";
import { ReplayResponse } from "./schema";

/*
  The adapter against Rahul's real responses (public/data/nasa, saved from the backend
  branch). Every expectation compares an adapted value with the raw value it came from,
  so the adapter can be shown to rename and select, never to compute.
*/
const dir = join(dirname(fileURLToPath(import.meta.url)), "../../public/data/nasa");
const read = (rel: string) => JSON.parse(readFileSync(join(dir, rel), "utf8"));
const raw = BackendCompare.parse(read("compare.json"));
const extras = {
  rotations: BackendRotations.parse(read("rotations.json")),
  wetness: SavedWetness.parse(read("wetness.json")),
  shortcuts: shortcutsByPlant([BackendYears.parse(read("years/corn_soy__rye.json")), BackendYears.parse(read("years/soy_corn__rye.json"))]),
};
const view = adaptCompare(raw, extras);
const rawPlan = (id: string) => raw.plans.find((p) => p.plan_id === id)!;
const plan = (id: string) => view.plans.find((p) => p.plan_id === id)!;

describe("compare, adapted", () => {
  it("keeps every plan and each winter's own median, never a sum", () => {
    expect(view.plans.map((p) => p.plan_id)).toEqual(raw.plans.map((p) => p.plan_id));
    for (const id of ["corn_soy__no_cover", "corn_soy__rye", "soy_corn__no_cover", "soy_corn__rye"]) {
      expect(plan(id).winter!.per_season_median.rain_mm_without_cover).toBe(rawPlan(id).winter!.per_season_median.rain_mm_outside_cover);
      expect(plan(id).calendar!.termination_gap_days).toBe(rawPlan(id).calendar!.termination_gap_days);
    }
  });

  it("reads the dates from the backend's plan block (winter.kind)", () => {
    expect(plan("corn_soy__no_cover").sequence).toMatchObject({ prev_harvest: "09-20", next_plant: "05-12", winter: { type: "none" } });
    expect(plan("soy_corn__rye").sequence!.winter).toEqual({ type: "cover", crop_id: "cereal_rye", seed: "10-20", terminate: "04-05" });
  });

  it("leaves the wheat plan unavailable, with the backend's reason", () => {
    const wheat = plan("corn_soy__wheat_dc");
    expect(wheat.status).toBe("unavailable");
    expect(wheat.reason).toBe(rawPlan("corn_soy__wheat_dc").reason);
    expect(wheat.sequence).toBeUndefined();
  });

  it("gives each planting date its own window, cutoff and 45 springs", () => {
    const soy = view.spring_windows![windowId("05-12")]!;
    const corn = view.spring_windows![windowId("04-15")]!;
    expect(soy.threshold.value).toBe(raw.thresholds.dry_spring["05-12"]!.value);
    expect(corn.threshold.value).toBe(raw.thresholds.dry_spring["04-15"]!.value);
    expect(soy.years).toHaveLength(45);
    expect(soy.dry_count).toBe(rawPlan("corn_soy__rye").spring!.dry_seasons);
    expect(soy.years.filter((y) => y.is_dry).length).toBe(soy.dry_count);
    const season = rawPlan("corn_soy__rye").seasons.find((s) => s.year === 2001)!;
    expect(soy.years.find((y) => y.year === 2001)).toMatchObject({ total_mm: season.spring_total_mm, rank: season.spring_rank, is_dry: true, start: "2001-04-12", end: "2001-05-11" });
  });

  it("takes shortcut years and wetness from where the backend puts them", () => {
    const soy = view.spring_windows![windowId("05-12")]!;
    expect(soy.shortcuts).toEqual(read("years/corn_soy__rye.json").shortcuts);
    expect(view.spring_windows![windowId("04-15")]!.shortcuts).toEqual(read("years/soy_corn__rye.json").shortcuts);
    const replay = read("replay/corn_soy__no_cover/2014.json");
    expect(soy.years.find((y) => y.year === 2014)!.gwetroot_window_mean).toBe(replay.wetness.gwetroot_window_mean);
  });

  it("without the extras, shortcut years and wetness stay unknown, not guessed", () => {
    const bare = adaptCompare(raw);
    const soy = bare.spring_windows![windowId("05-12")]!;
    expect(soy.shortcuts).toEqual({ typical: null, dry: null, wet: null });
    expect(soy.years.every((y) => y.gwetroot_window_mean === null)).toBe(true);
    expect(bare.rotations).toEqual([]);
  });

  it("carries the moisture check and the two-period counts unchanged", () => {
    const check = plan("corn_soy__rye").spring_checks.find((c) => c.check_id === "rye_soy_short_gap_moisture")!;
    const rawCheck = rawPlan("corn_soy__rye").spring_checks.find((c) => c.check_id === "rye_soy_short_gap_moisture")!;
    expect([check.count, check.denominator, check.qualifying_years]).toEqual([rawCheck.count, rawCheck.denominator, rawCheck.qualifying_years]);
    const era = plan("corn_soy__rye").eras["rye_soy_short_gap_moisture"]!;
    const rawEra = rawPlan("corn_soy__rye").eras["rye_soy_short_gap_moisture"]!;
    expect([era.earlier.count, era.earlier.denominator, era.recent.count, era.recent.denominator]).toEqual([
      rawEra.earlier.events,
      rawEra.earlier.evaluable,
      rawEra.recent.events,
      rawEra.recent.evaluable,
    ]);
  });

  it("turns a rule with no verdict into unknown or manual check, never a pass", () => {
    const none = raw.plans.flatMap((p) => p.other_checks.map((c, i) => ({ id: p.plan_id, i, c }))).filter((x) => x.c.verdict === null);
    expect(none.length).toBeGreaterThan(0);
    for (const x of none) expect(["unknown", "manual_check"]).toContain(plan(x.id).other_checks[x.i]!.verdict);
  });

  it("names the rotations by leg", () => {
    expect(view.rotations.find((r) => r.rotation_id === "winter_cover")!.legs).toEqual([
      { leg: 1, plan_id: "corn_soy__rye" },
      { leg: 2, plan_id: "soy_corn__rye" },
    ]);
  });
});

describe("rye sweep, adapted", () => {
  const rawSweep = BackendSensitivity.parse(read("sensitivity.json"));
  const sweep = adaptSensitivity(rawSweep);

  it("keeps each point's values under the screens' names", () => {
    expect(sweep.points).toHaveLength(rawSweep.points.length);
    const i = rawSweep.points.findIndex((p) => p.terminate === "04-30");
    expect(sweep.points[i]).toMatchObject({ gap_days: 12, rain_mm_without_cover_median: rawSweep.points[i]!.rain_outside_cover_mm_median, checks_count: 9 });
  });

  it("names the flagged springs only when the count is the whole dry list or zero", () => {
    for (const p of sweep.points) {
      if (p.checks_count === 0) expect(p.qualifying_years).toEqual([]);
      else if (p.checks_count === rawSweep.dry_years!.length) expect(p.qualifying_years).toEqual(rawSweep.dry_years);
      else expect(p.qualifying_years).toBeUndefined();
    }
    expect(sweep.points.find((p) => p.gap_days === 14)!.checks_count).toBe(0);
    expect(sweep.points.find((p) => p.gap_days === 13)!.checks_count).toBe(9);
  });
});

describe("season replay, adapted", () => {
  it("lists only the 30 days of the planting window", () => {
    const real = ReplayResponse.parse(read("replay/corn_soy__rye/2008.json"));
    const r = adaptReplay(real);
    expect(real.daily.length).toBeGreaterThan(200);
    expect(r.daily).toHaveLength(30);
    expect(r.daily[0]!.date).toBe(real.dates.spring_window.start);
    expect(r.daily[29]!.date).toBe(real.dates.spring_window.end);
    expect(r.spring.total_mm).toBe(real.spring.total_mm);
  });
});
