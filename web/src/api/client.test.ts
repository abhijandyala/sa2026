import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { createClient, latestOnly } from "./client";
import { PLACES, SAMPLE_PLACE as UNION } from "../content/locations";
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
    const r = await c.loadSaved();
    expect(r.years).toMatchObject({ ok: true, origin: "saved" });
    expect(r.compare).toMatchObject({ ok: true, origin: "saved" });
    expect(r.sensitivity).toMatchObject({ ok: true, origin: "saved" });
    // Read through the adapter: the backend's own values, under the names the screens use.
    const rye = r.compare.ok ? r.compare.data.plans.find((p) => p.plan_id === "corn_soy__rye") : undefined;
    const raw = JSON.parse(real("union/compare.json")).plans.find((p: { plan_id: string }) => p.plan_id === "corn_soy__rye");
    expect(rye?.winter?.per_season_median.rain_mm_without_cover).toBe(raw.winter.per_season_median.rain_mm_outside_cover);
    expect(rye?.sequence?.winter).toEqual({ type: "cover", crop_id: "cereal_rye", seed: "10-01", terminate: "04-30" });
  });

  it("treats a host's HTML fallback page as not found", async () => {
    const c = createClient({
      sampleBase: "/s",
      timeoutMs: 1000,
      fetchImpl: sampleFetch({ "years/": async () => ({ ok: true, status: 200, text: async () => "<!doctype html>", headers: { get: () => "text/html" } }) }),
    });
    expect((await c.loadSaved()).years).toMatchObject({ ok: false, kind: "not-found" });
  });

  it("reports a format mismatch with the field that failed", async () => {
    const broken = JSON.stringify({ ...JSON.parse(real("union/compare.json")), plans: [] });
    const c = createClient({ sampleBase: "/s", timeoutMs: 1000, fetchImpl: sampleFetch({ "compare.json": async () => ok(broken) }) });
    const r = (await c.loadSaved()).compare;
    expect(r).toMatchObject({ ok: false, kind: "schema" });
    expect(!r.ok && r.detail).toMatch(/^plans/);
  });

  it("times out instead of spinning forever", async () => {
    const hang = (_u: string, init?: { signal?: AbortSignal }) =>
      new Promise<never>((_, reject) => init?.signal?.addEventListener("abort", () => reject(new Error("aborted"))));
    const c = createClient({ sampleBase: "/s", timeoutMs: 20, fetchImpl: hang });
    expect((await c.loadSaved()).years).toMatchObject({ ok: false, kind: "timeout" });
  });
});

describe("places", () => {
  const rye = {
    plan_id: "corn_soy__rye",
    previous_crop_id: "field_corn",
    next_crop_id: "soybean",
    prev_harvest: "09-20",
    next_plant: "05-20",
    winter: { type: "cover", crop_id: "cereal_rye", seed: "10-10", terminate: "05-01" },
    low_moisture_concern: "unknown",
  } as const;
  const backendRye = {
    plan_id: "corn_soy__rye",
    previous_crop_id: "field_corn",
    prev_harvest: "09-20",
    next_crop_id: "soybean",
    next_plant: "05-20",
    winter: { kind: "cover", crop_id: "cereal_rye", seed: "10-10", terminate: "05-01" },
    grower: { low_moisture_concern: null },
  };

  it("every county in the picker has its own saved record, with its own snapshot and cutoffs", async () => {
    const c = createClient({ sampleBase: "/s", timeoutMs: 1000, fetchImpl: sampleFetch() });
    const seen = new Map<string, string>();
    for (const p of PLACES) {
      const r = await c.loadSaved(p.id);
      expect([p.id, r.years.ok, r.compare.ok, r.sensitivity.ok]).toEqual([p.id, true, true, true]);
      if (!r.compare.ok || !r.years.ok) continue;
      const raw = JSON.parse(real(`${p.id}/compare.json`));
      expect(raw.weather_location.id).toBe(p.id);
      expect(r.compare.data.meta.snapshot_hash).toBe(raw.weather_location.snapshot_hash);
      expect(r.years.data.location.label).toContain(p.name);
      seen.set(p.id, r.compare.data.meta.snapshot_hash);
    }
    // Wayne and Johnston share one NASA grid cell (the backend says so); every other county has its own.
    expect(JSON.parse(real("wayne/compare.json")).weather_location.shares_snapshot_with).toBe("johnston");
    expect(new Set(seen.values()).size).toBe(PLACES.length - 1);
  });

  it("reads a season's daily detail from the chosen county's folder", async () => {
    const urls: string[] = [];
    const c = createClient({ sampleBase: "/s", timeoutMs: 1000, fetchImpl: async (u: string) => (urls.push(u), ok(real(u.replace(/^\/s\//, "")))) });
    const r = await c.replay(1986, "corn_soy__rye", { origin: "saved", placeId: "pitt" });
    expect(urls).toEqual(["/s/pitt/replay/corn_soy__rye/1986.json"]);
    expect(r).toMatchObject({ ok: true, origin: "saved" });
    expect(r.ok && (r.data as { weather_location?: { id: string } }).weather_location?.id).toBe("pitt");
  });

  it("asks the live service for the edited plan itself at the chosen place, by id or by a point in the body", async () => {
    const calls: Array<{ url: string; method?: string; body: unknown }> = [];
    const f = async (u: string, init?: { method?: string; body?: string }) => {
      calls.push({ url: u, method: init?.method, body: init?.body ? JSON.parse(init.body) : undefined });
      return ok(real(u.includes("sensitivity") ? "pitt/sensitivity.json" : "pitt/replay/corn_soy__rye/1986.json"));
    };
    const c = createClient({ sampleBase: "/s", apiBase: "https://api.example/", timeoutMs: 1000, fetchImpl: f });
    expect(await c.replay(1986, "corn_soy__rye", { origin: "live", plan: rye, place: { id: "pitt", latitude: 35.59, longitude: -77.37 } })).toMatchObject({ ok: true, origin: "live" });
    expect(await c.sensitivity(rye, { latitude: 35.6, longitude: -77.4 })).toMatchObject({ ok: true, origin: "live" });
    expect(calls).toEqual([
      { url: "https://api.example/v1/seasons/1986/replay", method: "POST", body: { plan: backendRye, location_id: "pitt" } },
      { url: "https://api.example/v1/plans/sensitivity", method: "POST", body: { plan: backendRye, location: { latitude: 35.6, longitude: -77.4 } } },
    ]);
    // A typed point never appears in a URL.
    expect(calls.every((k) => !/35\.6|77\.4/.test(k.url))).toBe(true);
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
    const calls: string[] = [];
    const f = async (u: string, init?: { body?: string }) => {
      calls.push(u);
      body = init?.body ?? "";
      return ok(real("union/compare.json"));
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
    const r = await c.compare([plan], { latitude: 34.98, longitude: -80.55 });
    expect(r).toMatchObject({ ok: true, origin: "live" });
    // One call: the answer carries each planting date's typical, dry and wet springs itself.
    expect(calls).toEqual(["https://api.example/v1/plans/compare"]);
    // The backend's CompareRequest: {location: {latitude, longitude}, plans} with its own plan fields,
    // and no soil lookup (an outside call the screens do not read).
    expect(JSON.parse(body)).toEqual({
      include_soil: false,
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
    expect(r.ok && r.data.location.weather?.supported).toBe(false);
    expect(r.ok && r.data.location.guidance?.region).toBe("coastal_plain");
  });

  it("reads the backend's answer for a point outside North Carolina, where weather and guidance are null", async () => {
    const answer = { location: { status: "unsupported", code: "unsupported_location", latitude: 40.7, longitude: -74, bounds: { in_nc: false }, grid_cell: null, cell_id: null, weather: null, guidance: null, notes: [] } };
    const c = createClient({ sampleBase: "/s", apiBase: "https://api.example", timeoutMs: 1000, fetchImpl: async () => ok(JSON.stringify(answer)) });
    const r = await c.resolveLocation({ latitude: 40.7, longitude: -74 });
    expect(r.ok && r.data.location.bounds?.in_nc).toBe(false);
    expect(r.ok && r.data.location.weather).toBeNull();
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
