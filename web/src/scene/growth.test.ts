import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { CompareResponse } from "../api/schema";
import { fieldStateAt, SEASON_DAYS, seasonDay, seasonLabel } from "./growth";

const compare = CompareResponse.parse(
  JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../public/data/sample/compare.json"), "utf8")),
);
const plan = (id: string) => compare.plans.find((p) => p.plan_id === id)!;

describe("season axis", () => {
  it("maps dates onto Sep 1 … Jun 30", () => {
    expect(seasonDay("09-01")).toBe(0);
    expect(seasonDay("06-30")).toBe(SEASON_DAYS - 1);
    expect(seasonLabel(seasonDay("05-12"))).toBe("May 12");
    expect(seasonLabel(seasonDay("04-30"))).toBe("Apr 30");
  });
  it("orders fall before spring", () => {
    expect(seasonDay("10-01")).toBeLessThan(seasonDay("01-15"));
    expect(seasonDay("04-23")).toBeLessThan(seasonDay("04-30"));
  });
});

describe("what each field shows", () => {
  const jan = seasonDay("01-15");

  it("in winter: residue only without cover, living rye, living wheat", () => {
    expect(fieldStateAt(plan("no_cover"), jan)).toMatchObject({ cover: { show: false }, wheat: { show: false }, residue: 1 });
    expect(fieldStateAt(plan("rye_12d"), jan)).toMatchObject({ cover: { show: true, ended: false } });
    expect(fieldStateAt(plan("wheat_double_crop"), jan)).toMatchObject({ wheat: { show: true } });
  });

  it("ends rye on its date and keeps soybeans until after planting", () => {
    const rye = plan("rye_12d");
    expect(fieldStateAt(rye, seasonDay("04-29")).cover.ended).toBe(false);
    expect(fieldStateAt(rye, seasonDay("04-30")).cover.ended).toBe(true);
    expect(fieldStateAt(rye, seasonDay("05-12")).soy.show).toBe(false);
    expect(fieldStateAt(rye, seasonDay("05-25")).soy.show).toBe(true);
  });

  it("marks the 30-day window before each field's own planting", () => {
    expect(fieldStateAt(plan("rye_12d"), seasonDay("04-12")).inSpringWindow).toBe(true);
    expect(fieldStateAt(plan("rye_12d"), seasonDay("05-12")).inSpringWindow).toBe(false);
    expect(fieldStateAt(plan("wheat_double_crop"), seasonDay("05-20")).inSpringWindow).toBe(true);
    expect(fieldStateAt(plan("wheat_double_crop"), seasonDay("04-20")).inSpringWindow).toBe(false);
  });

  it("shows corn only before its harvest", () => {
    expect(fieldStateAt(plan("no_cover"), seasonDay("09-10")).corn.show).toBe(true);
    expect(fieldStateAt(plan("no_cover"), seasonDay("09-25")).corn.show).toBe(false);
  });

  it("never draws a stage taller than 1", () => {
    for (const id of ["no_cover", "rye_12d", "wheat_double_crop"]) {
      for (let d = 0; d < SEASON_DAYS; d += 3) {
        const s = fieldStateAt(plan(id), d);
        for (const v of [s.cover.h, s.wheat.h, s.soy.h]) expect(v).toBeLessThanOrEqual(1);
      }
    }
  });
});
