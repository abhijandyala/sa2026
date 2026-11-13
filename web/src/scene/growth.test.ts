import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { CompareResponse } from "../api/schema";
import { fieldStateAt, SEASON_DAYS, seasonDay, seasonLabel, type FieldState } from "./growth";

const compare = CompareResponse.parse(
  JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../public/data/sample/compare.json"), "utf8")),
);
const plan = (id: string) => compare.plans.find((p) => p.plan_id === id)!;
const at = (id: string, md: string): FieldState => fieldStateAt(plan(id), seasonDay(md))!;

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

describe("winter 1: corn → soybeans", () => {
  it("in winter: residue only without cover, living rye with cover", () => {
    expect(at("corn_soy__no_cover", "01-15")).toMatchObject({ cover: { show: false }, residue: 1 });
    expect(at("corn_soy__rye", "01-15")).toMatchObject({ cover: { show: true, ended: false } });
  });

  it("ends rye on its date and shows soybeans only after planting", () => {
    expect(at("corn_soy__rye", "04-29").cover.ended).toBe(false);
    expect(at("corn_soy__rye", "04-30").cover.ended).toBe(true);
    expect(at("corn_soy__rye", "05-12").soy.show).toBe(false);
    expect(at("corn_soy__rye", "05-25")).toMatchObject({ soy: { show: true, mature: false } });
  });

  it("shows mature corn only before its harvest", () => {
    expect(at("corn_soy__no_cover", "09-10").corn).toMatchObject({ show: true, mature: true });
    expect(at("corn_soy__no_cover", "09-25").corn.show).toBe(false);
  });

  it("marks the 30 days before planting", () => {
    expect(at("corn_soy__rye", "04-12").inSpringWindow).toBe(true);
    expect(at("corn_soy__rye", "05-12").inSpringWindow).toBe(false);
  });
});

describe("winter 2: soybeans → corn", () => {
  it("shows mature soybeans before their Oct 15 harvest, then residue", () => {
    expect(at("soy_corn__no_cover", "10-01").soy).toMatchObject({ show: true, mature: true });
    expect(at("soy_corn__no_cover", "11-01")).toMatchObject({ soy: { show: false }, residue: 1 });
    expect(at("soy_corn__no_cover", "11-01").label).toBe("Soybean residue, no living cover");
  });

  it("ends rye Apr 5 and brings corn up after the Apr 15 planting", () => {
    expect(at("soy_corn__rye", "04-04").cover.ended).toBe(false);
    expect(at("soy_corn__rye", "04-05").cover.ended).toBe(true);
    expect(at("soy_corn__rye", "04-20").corn.show).toBe(false);
    expect(at("soy_corn__rye", "05-10").corn).toMatchObject({ show: true, mature: false });
    expect(at("soy_corn__rye", "05-10").label).toMatch(/corn up$/);
  });

  it("marks its own window before corn planting", () => {
    expect(at("soy_corn__rye", "03-20").inSpringWindow).toBe(true);
    expect(at("soy_corn__rye", "04-20").inSpringWindow).toBe(false);
  });
});

describe("plans the backend cannot evaluate yet", () => {
  it("draws nothing for a plan without dates (wheat until sourced)", () => {
    expect(fieldStateAt(plan("corn_soy__wheat_dc"), seasonDay("01-15"))).toBeNull();
  });
});

it("never draws a stage taller than 1", () => {
  for (const p of compare.plans) {
    for (let d = 0; d < SEASON_DAYS; d += 3) {
      const s = fieldStateAt(p, d);
      if (s) for (const v of [s.cover.h, s.wheat.h, s.soy.h, s.corn.h]) expect(v).toBeLessThanOrEqual(1);
    }
  }
});
