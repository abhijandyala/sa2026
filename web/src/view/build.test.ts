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
