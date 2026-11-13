import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { CompareResponse, SensitivityResponse, YearsResponse } from "../api/schema";
import { buildView } from "./build";

const dir = join(dirname(fileURLToPath(import.meta.url)), "../../public/data/sample");
const read = (n: string) => JSON.parse(readFileSync(join(dir, `${n}.json`), "utf8"));
const years = YearsResponse.parse(read("years"));
const compare = CompareResponse.parse(read("compare"));
const sensitivity = SensitivityResponse.parse(read("sensitivity"));
const data = { years, compare, sensitivity, origin: "saved" as const };
const soy = compare.spring_windows!.soy_full_season!;
const rye12 = compare.plans.find((p) => p.plan_id === "rye_12d")!;

describe("view model", () => {
  const v = buildView(data, { card: "cover", year: null });
  const card = (k: string) => v.cards.find((c) => c.key === k)!;

  it("marks draft data so the banner shows", () => {
    expect(v.dataKind).toBe("draft");
    expect(buildView({ ...data, origin: "live" }, { card: "cover", year: null }).dataKind).toBe("live");
  });

  it("opens on the window's typical year", () => {
    expect(v.selectedYear?.year).toBe(soy.shortcuts.typical);
    expect(v.tiles.filter((t) => t.selected)).toHaveLength(1);
  });

  it("uses the backend's check count for the cover card, unchanged", () => {
    const check = rye12.spring_checks[0]!;
    expect(card("cover").check).toEqual({ applies: true, count: check.count, denominator: check.denominator });
    expect(card("cover").era?.measure).toBe("Springs with a field-moisture check");
  });

  it("leads every card with the backend's winter rain without cover, unchanged", () => {
    for (const k of ["current", "cover", "grain"]) {
      const p = compare.plans.find((pl) => pl.plan_id === card(k).content.planId)!;
      expect(card(k).soil.mm).toBe(p.winter.per_season_median.rain_mm_without_cover);
    }
    expect(card("current").soil.mm!).toBeGreaterThan(card("cover").soil.mm!);
  });

  it("says the moisture check does not apply where there is no cover crop to end", () => {
    expect(card("current").check).toEqual({ applies: false, count: null, denominator: null });
    expect(card("grain").check.applies).toBe(false);
  });

  it("shows dry planting windows as weather context, per planting window", () => {
    expect(v.windowEra).toMatchObject({ earlier: { count: soy.eras.dry_spring.earlier.count }, recent: { count: soy.eras.dry_spring.recent.count } });
    expect(card("current").era?.measure).toBe("Dry planting windows");
    const june = compare.spring_windows!.soy_double_crop!;
    expect(card("grain").era?.earlier.count).toBe(june.eras.dry_spring.earlier.count);
  });

  it("shows the check only in a year the backend listed", () => {
    const flagged = rye12.spring_checks[0]!.qualifying_years[0]!;
    const clear = soy.years.find((y) => !y.is_dry)!.year;
    expect(buildView(data, { card: "cover", year: flagged }).cards.find((c) => c.key === "cover")!.status).toEqual({
      kind: "check",
      text: "Check field moisture",
    });
    expect(buildView(data, { card: "cover", year: clear }).cards.find((c) => c.key === "cover")!.status).toBeNull();
  });

  it("never gives the no-cover card a rye check, only a dry-window note", () => {
    const dryYear = soy.years.find((y) => y.is_dry)!.year;
    const s = buildView(data, { card: "current", year: dryYear }).cards.find((c) => c.key === "current")!.status;
    expect(s?.kind).toBe("dry");
  });

  it("follows the grain card to its own June window", () => {
    const g = buildView(data, { card: "grain", year: null });
    expect(g.window?.id).toBe("soy_double_crop");
    expect(g.windowLabel).toMatch(/double-crop/);
  });

  it("shows a missing plan as not available instead of inventing numbers", () => {
    const without = { ...data, compare: { ...compare, plans: compare.plans.filter((p) => p.plan_id !== "wheat_double_crop") } };
    const g = buildView(without, { card: "cover", year: null }).cards.find((c) => c.key === "grain")!;
    expect(g.missing).toBe(true);
    expect(g.soil.mm).toBeNull();
    expect(g.check.count).toBeNull();
  });

  it("passes the heavy-rain threshold through without a value of its own", () => {
    expect(v.thresholds.heavy_rain.value).toBeNull();
    expect(v.thresholds.heavy_rain.status).toBe("unknown");
  });
});

// Weather states (card 3.5). Each is built from the sample by changing only what the
// backend would send in that situation.
describe("weather states", () => {
  const withWindow = (patch: (w: typeof soy) => typeof soy) => ({
    ...data,
    compare: { ...compare, spring_windows: { ...compare.spring_windows!, soy_full_season: patch(structuredClone(soy)) } },
  });

  it("keeps a valid zero as 0.0 mm, not missing", () => {
    const d = withWindow((w) => ({ ...w, years: w.years.map((y) => (y.year === 1990 ? { ...y, total_mm: 0 } : y)) }));
    const v = buildView(d, { card: "cover", year: 1990 });
    expect(v.selectedYear).toMatchObject({ status: "complete", totalMm: 0 });
    expect(v.tiles.find((t) => t.year === 1990)!.description).toBe("0.0 mm, no rain");
    expect(v.chart.bars.find((b) => b.year === 1990)!.mm).toBe(0);
  });

  it("shows an incomplete year as not compared, never as dry or zero", () => {
    const d = withWindow((w) => ({
      ...w,
      years: w.years.map((y) => (y.year === 1994 ? { ...y, status: "partial", total_mm: null, rank: null, percentile: null, is_dry: null } : y)),
    }));
    const v = buildView(d, { card: "cover", year: 1994 });
    expect(v.tiles.find((t) => t.year === 1994)!.description).toBe("incomplete record, not compared");
    expect(v.chart.bars.find((b) => b.year === 1994)!.mm).toBeNull();
    expect(v.chart.excluded).toEqual([1994]);
    expect(v.cards.find((c) => c.key === "cover")!.status).toEqual({ kind: "unavailable", text: "Weather unavailable for this year" });
  });

  it("withholds every relative label with fewer than 15 complete years", () => {
    const d = withWindow((w) => ({
      ...w,
      years: w.years.map((y, i) => (i < 31 ? { ...y, status: "unavailable", total_mm: null } : y)),
    }));
    const v = buildView(d, { card: "cover", year: 2020 });
    expect(v.labelsWithheld).toBe(true);
    expect(v.shortcuts).toEqual({ typical: null, dry: null });
    expect(v.tiles.every((t) => t.marker === undefined && t.isDry === null && t.percentile === null)).toBe(true);
    expect(v.chart.medianMm).toBeNull();
    expect(v.chart.cutoffMm).toBeNull();
    expect(v.windowEra).toBeNull();
    expect(v.selectedYear).toMatchObject({ rank: null, isDry: null });
  });

  it("withholds the dry contrast when the backend sends no dry replay year", () => {
    const d = withWindow((w) => ({ ...w, shortcuts: { ...w.shortcuts, dry: null } }));
    const v = buildView(d, { card: "cover", year: null });
    expect(v.contrastWithheld).toBe(true);
    expect(v.shortcuts.dry).toBeNull();
    expect(v.labelsWithheld).toBe(false);
  });

  it("keeps rain when modeled wetness is missing (case K)", () => {
    const d = withWindow((w) => ({ ...w, years: w.years.map((y) => (y.year === 2008 ? { ...y, gwetroot_window_mean: null } : y)) }));
    const v = buildView(d, { card: "cover", year: 2008 });
    expect(v.selectedYear?.totalMm).not.toBeNull();
    expect(v.selectedYear?.wetnessRoot).toBeNull();
    expect(v.wetness.selected).toBeNull();
    expect(v.wetness.missingYears).toEqual([2008]);
  });

  it("gives the chart a fixed, clean axis per planting window", () => {
    const a = buildView(data, { card: "cover", year: 1990 }).chart;
    const b = buildView(data, { card: "cover", year: 2014 }).chart;
    expect(a.axisMax).toBe(b.axisMax);
    expect(a.axisMax % a.axisStep).toBe(0);
    expect(Math.max(...a.bars.map((x) => x.mm ?? 0))).toBeLessThanOrEqual(a.axisMax);
  });
});

describe("3D field strips", () => {
  it("gives every field its own planting window's selected spring", () => {
    const v = buildView(data, { card: "cover", year: 2014 });
    expect(v.strips.map((s) => s.key)).toEqual(["current", "cover", "grain"]);
    const june = compare.spring_windows!.soy_double_crop!.years.find((y) => y.year === 2014)!;
    expect(v.strips[2]!.weather.totalMm).toBe(june.total_mm);
    expect(v.strips[1]!.weather.totalMm).toBe(soy.years.find((y) => y.year === 2014)!.total_mm);
    expect(v.strips[1]!.selected).toBe(true);
  });
  it("carries the card's status so the field flag matches the card", () => {
    const flagged = rye12.spring_checks[0]!.qualifying_years[0]!;
    const v = buildView(data, { card: "cover", year: flagged });
    expect(v.strips[1]!.status).toEqual(v.cards[1]!.status);
  });
});

describe("rye slider", () => {
  const point = (md: string) => sensitivity.points.find((p) => p.terminate === md)!;

  it("starts on the proposed date and finds the earlier date and the 14-day boundary", () => {
    const r = buildView(data, { card: "cover", year: 2014 }).rye!;
    expect(r.chosen.terminate).toBe("04-30");
    expect(r.changed).toBe(false);
    expect(r.points[r.earlierIndex!]!.terminate).toBe("04-23");
    expect(r.points[r.boundaryIndex!]!.gap_days).toBe(14);
    expect(r.points[r.boundaryIndex! + 1]!.gap_days).toBe(13);
  });

  it("moves the cover card to the chosen date using the sweep's values only", () => {
    const v = buildView(data, { card: "cover", year: 2014, ryeEnd: "04-23" });
    const cover = v.cards.find((c) => c.key === "cover")!;
    const p = point("04-23");
    expect(v.rye!.changed).toBe(true);
    expect(cover.check).toEqual({ applies: true, count: p.checks_count, denominator: sensitivity.denominator });
    expect(cover.soil.mm).toBe(p.rain_mm_without_cover_median);
    expect(cover.metrics).toEqual([`${p.gap_days} days before soybean planting`, `${p.living_cover_days_planned} planned days with living rye`]);
    expect(cover.plan!.sequence.winter).toMatchObject({ terminate: "04-23" });
  });

  it("clears the check in a dry spring once the gap reaches 14 days (case C)", () => {
    const dry = rye12.spring_checks[0]!.qualifying_years[0]!;
    const before = buildView(data, { card: "cover", year: dry }).cards.find((c) => c.key === "cover")!;
    const after = buildView(data, { card: "cover", year: dry, ryeEnd: "04-23" }).cards.find((c) => c.key === "cover")!;
    expect(before.status?.kind).toBe("check");
    expect(after.status).toBeNull();
  });

  it("keeps the spring rainfall, rank and the other cards unchanged", () => {
    const a = buildView(data, { card: "cover", year: 2014 });
    const b = buildView(data, { card: "cover", year: 2014, ryeEnd: "04-10" });
    expect(b.selectedYear).toEqual(a.selectedYear);
    expect(b.chart).toEqual(a.chart);
    expect(b.cards.filter((c) => c.key !== "cover")).toEqual(a.cards.filter((c) => c.key !== "cover"));
  });

  it("the 3D field and its plan follow the chosen date", () => {
    const v = buildView(data, { card: "cover", year: 2014, ryeEnd: "04-10" });
    expect(v.strips[1]!.plan!.sequence.winter).toMatchObject({ terminate: "04-10" });
  });

  it("says the per-year mark is not available when the sweep lacks qualifying years", () => {
    const thin = { ...data, sensitivity: { ...sensitivity, points: sensitivity.points.map(({ qualifying_years: _q, eras: _e, ...p }) => p) } };
    const cover = buildView(thin, { card: "cover", year: 2014, ryeEnd: "04-10" }).cards.find((c) => c.key === "cover")!;
    expect(cover.status).toEqual({ kind: "unavailable", text: "This spring's check is not available for this date" });
    expect(cover.era).toBeNull();
  });
});
