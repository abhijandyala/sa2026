import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { createClient, latestOnly } from "./client";
import { SAMPLE_PLACE as UNION } from "../content/locations";
import { CompareResponse, SensitivityResponse, YearsResponse } from "./schema";

const dir = join(dirname(fileURLToPath(import.meta.url)), "../../public/data/sample");
const file = (n: string) => readFileSync(join(dir, `${n}.json`), "utf8");
const ok = (body: string) => ({ ok: true, status: 200, text: async () => body, headers: { get: () => "application/json" } });

// The saved NASA record: Rahul's real responses, as the site loads them.
const nasa = join(dirname(fileURLToPath(import.meta.url)), "../../public/data/nasa");
const real = (rel: string) => readFileSync(join(nasa, rel), "utf8");

function sampleFetch(overrides: Record<string, () => Promise<unknown>> = {}) {
  return async (url: string) => {
    for (const [k, f] of Object.entries(overrides)) if (url.includes(k)) return f() as never;
    return ok(real(url.replace(/^\/s\//, "")));
  };
}

describe("saved sample", () => {
  it("loads all three files as saved data", async () => {
    const c = createClient({ sampleBase: "/s", timeoutMs: 1000, fetchImpl: sampleFetch() });
    const r = await c.loadSample();
    expect(r.years).toMatchObject({ ok: true, origin: "saved" });
    expect(r.compare).toMatchObject({ ok: true, origin: "saved" });
    expect(r.sensitivity).toMatchObject({ ok: true, origin: "saved" });
    // Read through the adapter: the backend's own values, under the names the screens use.
    const rye = r.compare.ok ? r.compare.data.plans.find((p) => p.plan_id === "corn_soy__rye") : undefined;
    const raw = JSON.parse(real("compare.json")).plans.find((p: { plan_id: string }) => p.plan_id === "corn_soy__rye");
    expect(rye?.winter?.per_season_median.rain_mm_without_cover).toBe(raw.winter.per_season_median.rain_mm_outside_cover);
    expect(rye?.sequence?.winter).toEqual({ type: "cover", crop_id: "cereal_rye", seed: "10-01", terminate: "04-30" });
  });

  it("treats a host's HTML fallback page as not found", async () => {
    const c = createClient({
      sampleBase: "/s",
      timeoutMs: 1000,
      fetchImpl: sampleFetch({ "years/": async () => ({ ok: true, status: 200, text: async () => "<!doctype html>", headers: { get: () => "text/html" } }) }),
    });
    expect((await c.loadSample()).years).toMatchObject({ ok: false, kind: "not-found" });
  });

  it("reports a format mismatch with the field that failed", async () => {
    const broken = JSON.stringify({ ...JSON.parse(real("compare.json")), plans: [] });
    const c = createClient({ sampleBase: "/s", timeoutMs: 1000, fetchImpl: sampleFetch({ "compare.json": async () => ok(broken) }) });
    const r = (await c.loadSample()).compare;
    expect(r).toMatchObject({ ok: false, kind: "schema" });
    expect(!r.ok && r.detail).toMatch(/^plans/);
  });

  it("times out instead of spinning forever", async () => {
    const hang = (_u: string, init?: { signal?: AbortSignal }) =>
      new Promise<never>((_, reject) => init?.signal?.addEventListener("abort", () => reject(new Error("aborted"))));
    const c = createClient({ sampleBase: "/s", timeoutMs: 20, fetchImpl: hang });
    expect((await c.loadSample()).years).toMatchObject({ ok: false, kind: "timeout" });
  });
});

describe("live recompute", () => {
  it("says plainly when no live service is configured", async () => {
    const c = createClient({ sampleBase: "/s", timeoutMs: 1000, fetchImpl: sampleFetch() });
    expect(c.hasLiveApi).toBe(false);
    expect(await c.compare([], UNION)).toMatchObject({ ok: false, kind: "offline" });
    expect(await c.resolveLocation(UNION)).toMatchObject({ ok: false, kind: "offline" });
  });

  it("posts plans and marks the answer live", async () => {
    let body = "";
    const f = async (u: string, init?: { body?: string }) => {
      if (u.includes("/v1/years")) return ok(real(`years/${new URL(u).searchParams.get("plan")}.json`));
      body = init?.body ?? "";
      return ok(real("compare.json"));
    };
    const c = createClient({ sampleBase: "/s", apiBase: "https://api.example", timeoutMs: 1000, fetchImpl: f });
    const plan = {
      plan_id: "corn_soy__rye",
      previous_crop_id: "field_corn",
      next_crop_id: "soybean",
      prev_harvest: "09-20",
      next_plant: "05-12",
      winter: { type: "cover", crop_id: "cereal_rye", seed: "10-01", terminate: "04-23" },
      low_moisture_concern: "unknown",
    } as const;
    const r = await c.compare([plan], UNION);
    expect(r).toMatchObject({ ok: true, origin: "live" });
    // The backend's CompareRequest: {location: {latitude, longitude}, plans} with its own plan fields.
    expect(JSON.parse(body)).toEqual({
      location: { latitude: 34.98, longitude: -80.55 },
      plans: [
        {
          plan_id: "corn_soy__rye",
          previous_crop_id: "field_corn",
          prev_harvest: "09-20",
          next_crop_id: "soybean",
          next_plant: "05-12",
          winter: { kind: "cover", crop_id: "cereal_rye", seed: "10-01", terminate: "04-23" },
          grower: { low_moisture_concern: null },
        },
      ],
    });
  });

  it("resolves a place with the backend's lat/lon body and reads weather and guidance support", async () => {
    let body = "";
    const answer = {
      meta: {},
      location: {
        status: "partial",
        latitude: 35.52,
        longitude: -78.37,
        bounds: { in_nc: true },
        cell_id: "cell_+35.500_-78.125",
        weather: { supported: false, status: "unavailable", source: "none", freshness: "unavailable", reason: "offline mode" },
        guidance: { supported: true, status: "complete", region: "coastal_plain" },
        notes: [],
      },
    };
    const f = async (_u: string, init?: { body?: string }) => {
      body = init?.body ?? "";
      return ok(JSON.stringify(answer));
    };
    const c = createClient({ sampleBase: "/s", apiBase: "https://api.example", timeoutMs: 1000, fetchImpl: f });
    const r = await c.resolveLocation({ latitude: 35.52, longitude: -78.37 });
    expect(JSON.parse(body)).toEqual({ lat: 35.52, lon: -78.37, fetch_history: true });
    expect(r.ok && r.data.location.weather.supported).toBe(false);
    expect(r.ok && r.data.location.guidance.region).toBe("coastal_plain");
  });

  it("keeps only the newest answer", () => {
    const order = latestOnly();
    const a = order.next();
    const b = order.next();
    expect(order.isLatest(a)).toBe(false);
    expect(order.isLatest(b)).toBe(true);
  });
});

// Invariants the backend's real output must also satisfy. If one fails on real data,
// raise it in docs/handoff.md rather than patching the UI.
describe("sample contract invariants", () => {
  const compare = CompareResponse.parse(JSON.parse(file("compare")));
  const years = YearsResponse.parse(JSON.parse(file("years")));
  const sens = SensitivityResponse.parse(JSON.parse(file("sensitivity")));
  const soy = compare.spring_windows!.soy_full_season!;

  it("every response is marked draft until the backend replaces it", () => {
    expect(compare.meta.draft && years.meta.draft && sens.meta.draft).toBe(true);
  });

  it("eras exclude 2001–2005 and each era has at most 20 seasons", () => {
    expect(years.eras.excluded_from_eras).toEqual([2001, 2002, 2003, 2004, 2005]);
    for (const e of [soy.eras.dry_spring, ...compare.plans.flatMap((p) => Object.values(p.eras))]) {
      expect(e.earlier.denominator).toBeLessThanOrEqual(20);
      expect(e.recent.denominator).toBeLessThanOrEqual(20);
      expect(e.earlier.count + e.recent.count).toBeLessThanOrEqual(soy.dry_count!);
    }
  });

  it("a real zero stays a number and missing stays null", () => {
    for (const w of Object.values(compare.spring_windows!)) {
      for (const y of w.years) expect(y.status === "complete" ? y.total_mm !== null : y.total_mm === null).toBe(true);
    }
  });

  it("the 12-day and 19-day plans match the sample dates (cases A–C)", () => {
    const byId = new Map(compare.plans.map((p) => [p.plan_id, p]));
    expect(byId.get("corn_soy__rye")!.calendar!.termination_gap_days).toBe(12);
    const p19 = sens.points.find((p) => p.terminate === "04-23")!;
    const p12 = sens.points.find((p) => p.terminate === "04-30")!;
    expect(p19.gap_days).toBe(19);
    expect(p12.living_cover_days_planned - p19.living_cover_days_planned).toBe(7);
  });

  it("rotations follow presets.md: two legs each, wheat leg 1 unavailable", () => {
    expect(compare.rotations.map((r) => [r.rotation_id, r.legs.map((l) => l.plan_id)])).toEqual([
      ["current_practice", ["corn_soy__no_cover", "soy_corn__no_cover"]],
      ["winter_cover", ["corn_soy__rye", "soy_corn__rye"]],
      ["add_grain_crop", ["corn_soy__wheat_dc", "soy_corn__no_cover"]],
    ]);
    const wheat = compare.plans.find((p) => p.plan_id === "corn_soy__wheat_dc")!;
    expect(wheat.status).toBe("unavailable");
    expect(wheat.reason).toMatch(/^catalog_missing/);
    for (const p of compare.plans) expect(p.leg === 1 || p.leg === 2).toBe(true);
  });

  it("each leg has its own spring window and denominators", () => {
    const rye2 = compare.plans.find((p) => p.plan_id === "soy_corn__rye")!;
    expect(rye2.spring_window).toEqual({ start: "03-16", end: "04-14" });
    expect(rye2.calendar).toMatchObject({ termination_gap_days: 10, living_cover_days_planned: 167 });
    expect(compare.spring_windows!.corn_planting!.denominator).toBe(45);
  });

  it("the rye check never applies to the no-cover plan", () => {
    const nc = compare.plans.find((p) => p.plan_id === "corn_soy__no_cover")!;
    expect(nc.spring_checks.every((c) => c.status === "inapplicable" && c.count === null)).toBe(true);
  });

  it("the sensitivity curve steps at 14 days by exactly the dry-year count (case F)", () => {
    for (const p of sens.points) expect(p.checks_count).toBe(p.gap_days < 14 ? soy.dry_count : 0);
    for (let i = 1; i < sens.points.length; i++) {
      expect(sens.points[i]!.gap_days).toBe(sens.points[i - 1]!.gap_days - 1);
      expect(sens.points[i]!.living_cover_days_planned).toBe(sens.points[i - 1]!.living_cover_days_planned + 1);
    }
  });
});
