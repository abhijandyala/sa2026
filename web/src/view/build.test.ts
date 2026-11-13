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
const rye12 = compare.plans.find((p) => p.plan_id === "corn_soy__rye")!;
const cornWin = compare.spring_windows!.corn_planting!;

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

  it("shows both winters' rain without cover on every card, from the backend, never added", () => {
    for (const k of ["current", "cover", "grain"]) {
      for (const l of card(k).legs) {
        const p = compare.plans.find((pl) => pl.plan_id === l.planId)!;
        expect(l.soilMm).toBe(p.winter ? p.winter.per_season_median.rain_mm_without_cover : null);
      }
    }
    expect(card("current").legs[0]!.soilMm!).toBeGreaterThan(card("cover").legs[0]!.soilMm!);
    expect(card("current").legs[1]!.soilMm!).toBeGreaterThan(card("cover").legs[1]!.soilMm!);
  });

  it("says the moisture check does not apply where there is no cover crop to end before soybeans", () => {
    expect(card("current").check).toEqual({ applies: false, count: null, denominator: null });
    expect(card("cover").legs[1]!.check.applies).toBe(false);
  });

  it("shows the wheat winter as not evaluated, with the backend's reason and no numbers", () => {
    const g = card("grain");
    expect(g.legs[0]).toMatchObject({ available: false, soilMm: null, check: { count: null } });
    expect(g.legs[0]!.reason).toMatch(/^Wheat planting and harvest windows/);
    expect(g.missing).toBe(true);
    expect(g.legs[1]).toMatchObject({ available: true, planId: "soy_corn__no_cover" });
  });

  it("shows dry planting windows as weather context, per planting window", () => {
    expect(v.windowEra).toMatchObject({ earlier: { count: soy.eras.dry_spring.earlier.count }, recent: { count: soy.eras.dry_spring.recent.count } });
    expect(card("current").era?.measure).toBe("Dry planting windows");
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

  it("winter 2 follows its own corn planting window and plans", () => {
    const w2 = buildView(data, { card: "cover", year: null, leg: 2 });
    expect(w2.window?.id).toBe("corn_planting");
    expect(w2.selectedYear?.year).toBe(cornWin.shortcuts.typical);
    const cover = w2.cards.find((c) => c.key === "cover")!;
    expect(cover.plan?.plan_id).toBe("soy_corn__rye");
    expect(cover.metrics[0]).toBe("10 days before corn planting");
    expect(cover.checks.map((c) => c.rule_id)).toContain("cr_tt_01");
    expect(w2.strips.map((s) => s.plan?.plan_id)).toEqual(["soy_corn__no_cover", "soy_corn__rye", "soy_corn__no_cover"]);
  });

  it("the grain card on winter 1 has no weather window to show", () => {
    const g = buildView(data, { card: "grain", year: null, leg: 1 });
    expect(g.window).toBeNull();
    expect(g.tiles).toEqual([]);
  });

  it("shows a plan the service did not send as not available instead of inventing numbers", () => {
    const without = { ...data, compare: { ...compare, plans: compare.plans.filter((p) => p.plan_id !== "corn_soy__wheat_dc") } };
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
    expect(v.shortcuts).toEqual({ typical: null, dry: null, wet: null });
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
    expect(v.strips[2]!.weather.totalMm).toBeNull(); // wheat winter not evaluated yet
    const w2 = buildView(data, { card: "cover", year: 2014, leg: 2 });
    expect(w2.strips[1]!.weather.totalMm).toBe(cornWin.years.find((y) => y.year === 2014)!.total_mm);
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
    const r = buildView(data, { card: "cover", year: 2014, earlierRyeEnd: "04-23" }).rye!;
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
    expect(cover.plan!.sequence!.winter).toMatchObject({ terminate: "04-23" });
    expect(cover.legs[0]).toMatchObject({ soilMm: p.rain_mm_without_cover_median, check: { count: p.checks_count } });
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
    expect(v.strips[1]!.plan!.sequence!.winter).toMatchObject({ terminate: "04-10" });
  });

  it("says the per-year mark is not available when the sweep lacks qualifying years", () => {
    const thin = { ...data, sensitivity: { ...sensitivity, points: sensitivity.points.map(({ qualifying_years: _q, eras: _e, ...p }) => p) } };
    const cover = buildView(thin, { card: "cover", year: 2014, ryeEnd: "04-10" }).cards.find((c) => c.key === "cover")!;
    expect(cover.status).toEqual({ kind: "unavailable", text: "This spring's check is not available for this date" });
    expect(cover.era).toBeNull();
  });
});

describe("priorities and field observations (Phase 7)", () => {
  const numbers = (v: ReturnType<typeof buildView>) =>
    v.cards.map((c) => [c.key, c.legs.map((l) => [l.soilMm, l.check.count, l.check.denominator]), c.era?.earlier.count, c.era?.recent.count]);

  it("never changes a number or the card order (case J)", () => {
    const plain = buildView(data, { card: "cover", year: 2014 });
    const picked = buildView(data, { card: "cover", year: 2014, priorities: ["soil", "water"] });
    expect(numbers(picked)).toEqual(numbers(plain));
    expect(picked.cards.map((c) => c.key)).toEqual(["current", "cover", "grain"]);
  });

  it("badges each plan with a sourced reason, warnings included", () => {
    const v = buildView(data, { card: "cover", year: 2014, priorities: ["water", "soil"] });
    const fits = Object.fromEntries(v.cards.map((c) => [c.key, c.priorityFits.map((f) => [f.priority, f.fit])]));
    expect(fits).toEqual({
      current: [["soil", "tradeoff"], ["water", "matches"]],
      cover: [["soil", "matches"], ["water", "tradeoff"]],
      grain: [["soil", "partly"]],
    });
    const coverWater = v.cards[1]!.priorityFits.find((f) => f.priority === "water")!;
    expect(coverWater.detail).toBe("Check field moisture in 9 of 45 springs (corn → soy).");
    expect(coverWater.reason.source).toBe("ncs-soy-4");
    expect(v.cards[2]!.priorityFits[0]!.detail).toMatch(/not evaluated yet/);
  });

  it("shows no badges until a priority is chosen", () => {
    expect(buildView(data, { card: "cover", year: 2014 }).cards.every((c) => c.priorityFits.length === 0)).toBe(true);
  });

  it("a reported moisture concern shows the 14-day guidance with the plan's own gap", () => {
    const v = buildView(data, { card: "cover", year: 1981, observation: { moisture: "yes", irrigation: "unknown" } });
    const cover = v.cards.find((c) => c.key === "cover")!;
    expect(cover.observations).toEqual([
      expect.objectContaining({ kind: "reported", text: expect.stringContaining("this plan ends it 12 days before") }),
    ]);
    // Only where the NC State moisture check applies.
    expect(v.cards.find((c) => c.key === "current")!.observations).toEqual([]);
  });

  it("unknown invites a field check; removing the observation returns the prior notes (case 3)", () => {
    const unknown = buildView(data, { card: "cover", year: 1981, observation: { moisture: "unknown", irrigation: "no" } });
    expect(unknown.cards[1]!.observations.map((o) => o.kind)).toEqual(["unknown"]);
    const no = buildView(data, { card: "cover", year: 1981, observation: { moisture: "no", irrigation: "no" } });
    expect(no.cards[1]!.observations).toEqual([]);
    expect(numbers(no)).toEqual(numbers(unknown));
  });

  it("irrigation is context only", () => {
    const v = buildView(data, { card: "cover", year: 1981, observation: { moisture: "no", irrigation: "yes" } });
    expect(v.cards[1]!.observations).toEqual([expect.objectContaining({ kind: "context", text: expect.stringMatching(/does not change/) })]);
  });
});
