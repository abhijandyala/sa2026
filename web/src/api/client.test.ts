import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { createClient, latestOnly } from "./client";
import { CompareResponse, SensitivityResponse, YearsResponse } from "./schema";

const dir = join(dirname(fileURLToPath(import.meta.url)), "../../public/data/sample");
const file = (n: string) => readFileSync(join(dir, `${n}.json`), "utf8");
const ok = (body: string) => ({ ok: true, status: 200, text: async () => body, headers: { get: () => "application/json" } });

function sampleFetch(overrides: Record<string, () => Promise<unknown>> = {}) {
  return async (url: string) => {
    for (const [k, f] of Object.entries(overrides)) if (url.includes(k)) return f() as never;
    const name = url.split("/").pop()!.replace(".json", "");
    return ok(file(name));
  };
}

describe("saved sample", () => {
  it("loads all three files as saved data", async () => {
    const c = createClient({ sampleBase: "/s", timeoutMs: 1000, fetchImpl: sampleFetch() });
    const r = await c.loadSample();
    expect(r.years).toMatchObject({ ok: true, origin: "saved" });
    expect(r.compare).toMatchObject({ ok: true, origin: "saved" });
    expect(r.sensitivity).toMatchObject({ ok: true, origin: "saved" });
  });

  it("treats a host's HTML fallback page as not found", async () => {
    const c = createClient({
      sampleBase: "/s",
      timeoutMs: 1000,
      fetchImpl: sampleFetch({ years: async () => ({ ok: true, status: 200, text: async () => "<!doctype html>", headers: { get: () => "text/html" } }) }),
    });
    expect((await c.loadSample()).years).toMatchObject({ ok: false, kind: "not-found" });
  });

  it("reports a format mismatch with the field that failed", async () => {
    const broken = JSON.stringify({ ...JSON.parse(file("compare")), plans: [] });
    const c = createClient({ sampleBase: "/s", timeoutMs: 1000, fetchImpl: sampleFetch({ compare: async () => ok(broken) }) });
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
    expect(await c.compare([], "union_county_sample")).toMatchObject({ ok: false, kind: "offline" });
  });

  it("posts plans and marks the answer live", async () => {
    let body = "";
    const f = async (_u: string, init?: { body?: string }) => {
      body = init?.body ?? "";
      return ok(file("compare"));
    };
    const c = createClient({ sampleBase: "/s", apiBase: "https://api.example", timeoutMs: 1000, fetchImpl: f });
    const r = await c.compare([], "union_county_sample");
    expect(r).toMatchObject({ ok: true, origin: "live" });
    expect(JSON.parse(body)).toEqual({ location_id: "union_county_sample", plans: [] });
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
    expect(byId.get("rye_12d")!.calendar.termination_gap_days).toBe(12);
    expect(byId.get("rye_19d")!.calendar.termination_gap_days).toBe(19);
    expect(byId.get("rye_12d")!.calendar.living_cover_days_planned - byId.get("rye_19d")!.calendar.living_cover_days_planned).toBe(7);
  });

  it("the rye check never applies to the no-cover plan", () => {
    const nc = compare.plans.find((p) => p.plan_id === "no_cover")!;
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
