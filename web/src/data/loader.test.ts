import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { loadBundle, loadPreferred } from "./loader";
import { Bundle } from "./schema";

const fixturePath = join(dirname(fileURLToPath(import.meta.url)), "../../public/data/fixture-synthetic.json");
const fixtureText = readFileSync(fixturePath, "utf8");
const fixture = Bundle.parse(JSON.parse(fixtureText));

const respond = (status: number, body = "") => async () => ({ ok: status >= 200 && status < 300, status, text: async () => body });

describe("loader", () => {
  it("accepts the fixture and marks it synthetic", async () => {
    const r = await loadBundle("x", { timeoutMs: 1000, fetchImpl: respond(200, fixtureText) });
    expect(r.status).toBe("ok");
    expect(r.status === "ok" && r.origin).toBe("fixture");
  });

  it("reports a schema problem instead of rendering bad data", async () => {
    const broken = JSON.stringify({ ...JSON.parse(fixtureText), strategies: [] });
    const r = await loadBundle("x", { timeoutMs: 1000, fetchImpl: respond(200, broken) });
    expect(r).toMatchObject({ status: "error", kind: "schema" });
  });

  it("reports invalid JSON", async () => {
    const r = await loadBundle("x", { timeoutMs: 1000, fetchImpl: respond(200, "{nope") });
    expect(r).toMatchObject({ status: "error", kind: "parse" });
  });

  it("surfaces a location mismatch", async () => {
    const r = await loadBundle("x", { timeoutMs: 1000, expectedLocationId: "wake-nc", fetchImpl: respond(200, fixtureText) });
    expect(r).toMatchObject({ status: "error", kind: "mismatch" });
  });

  it("times out instead of spinning forever", async () => {
    const hang = (_u: string, init?: { signal?: AbortSignal }) =>
      new Promise<never>((_, reject) => init?.signal?.addEventListener("abort", () => reject(new Error("aborted"))));
    const r = await loadBundle("x", { timeoutMs: 20, fetchImpl: hang });
    expect(r).toMatchObject({ status: "error", kind: "timeout" });
  });

  it("falls back to the fixture only when the real file is missing", async () => {
    const calls: string[] = [];
    const f = async (u: string) => {
      calls.push(u);
      return u === "real" ? { ok: false, status: 404, text: async () => "" } : { ok: true, status: 200, text: async () => fixtureText };
    };
    const r = await loadPreferred("real", "fixture", { timeoutMs: 1000, fetchImpl: f });
    expect(calls).toEqual(["real", "fixture"]);
    expect(r.status).toBe("ok");
  });

  it("treats a single-page-app HTML fallback as not found and uses the fixture", async () => {
    const f = async (u: string) =>
      u === "real"
        ? { ok: true, status: 200, text: async () => "<!doctype html><html></html>", headers: { get: () => "text/html" } }
        : { ok: true, status: 200, text: async () => fixtureText };
    const r = await loadPreferred("real", "fixture", { timeoutMs: 1000, fetchImpl: f });
    expect(r).toMatchObject({ status: "ok", origin: "fixture" });
  });

  it("does not hide a broken real file behind the fixture", async () => {
    const f = async (u: string) => (u === "real" ? { ok: true, status: 200, text: async () => "{}" } : { ok: true, status: 200, text: async () => fixtureText });
    const r = await loadPreferred("real", "fixture", { timeoutMs: 1000, fetchImpl: f });
    expect(r).toMatchObject({ status: "error", kind: "schema" });
  });
});

// Contract invariants Rahul's real bundle must also satisfy (scope doc test cases E–L).
describe("fixture contract invariants", () => {
  const events = fixture.strategies.flatMap((s) => s.events);

  it("zero rain stays a number and missing stays null", () => {
    for (const e of events) {
      for (const y of e.years) {
        if (y.complete) expect(y.rainMm).not.toBeNull();
        else expect(y.rainMm).toBeNull();
      }
    }
  });

  it("earlier and recent halves add up to the totals (case G)", () => {
    for (const e of events) {
      const s = e.summary;
      expect(s.earlier.complete + s.recent.complete).toBe(s.completeYears);
      expect(s.earlier.dry + s.recent.dry).toBe(s.dryCount);
      if (s.flagged !== null) expect((s.earlier.flagged ?? 0) + (s.recent.flagged ?? 0)).toBe(s.flagged);
    }
  });

  it("every flag carries a reason and a rule source", () => {
    for (const e of events) for (const y of e.years) if (y.flag) expect(y.reason && y.rule).toBeTruthy();
  });

  it("the baseline never gets a rye timing flag", () => {
    const current = fixture.strategies.find((s) => s.id === "current")!;
    for (const e of current.events) {
      expect(e.summary.ruleApplies).toBe(false);
      for (const y of e.years) expect(y.flag).toBeNull();
    }
  });

  it("moving the rye end date earlier never increases the flagged count (case F)", () => {
    const pts = fixture.curves[0]!.points;
    for (let i = 1; i < pts.length; i++) {
      expect(pts[i]!.gapDays).toBe(pts[i - 1]!.gapDays - 1);
      expect(pts[i]!.livingCoverDays).toBe(pts[i - 1]!.livingCoverDays + 1);
      expect(pts[i]!.flagged).toBeGreaterThanOrEqual(pts[i - 1]!.flagged);
    }
  });

  it("every source chip points at a listed source", () => {
    const ids = new Set(fixture.sources.map((s) => s.id));
    for (const s of fixture.strategies) {
      for (const list of Object.values(s.headings)) for (const c of list) if (c.source) expect(ids.has(c.source)).toBe(true);
      for (const f of s.feasibility) if (f.source) expect(ids.has(f.source)).toBe(true);
    }
  });

  it("the illustrative 12-day and 19-day gaps match the plan dates (cases A–C)", () => {
    const pts = fixture.curves[0]!.points;
    expect(pts.find((p) => p.endDate === fixture.plan.ryeEnd)?.gapDays).toBe(12);
    expect(pts.find((p) => p.endDate === fixture.plan.ryeEndEarlier)?.gapDays).toBe(19);
  });
});
