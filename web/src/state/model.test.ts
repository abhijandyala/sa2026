import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { Bundle } from "../data/schema";
import { hasPendingEdits, initialState, reducer, type AppState } from "./model";
import { applyUrlView, fromHash, toHash } from "./url";

const bundle = Bundle.parse(
  JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../public/data/fixture-synthetic.json"), "utf8")),
);
const base = initialState(bundle);
const planOf = (s: AppState) => JSON.stringify(s.applied);

describe("state model", () => {
  it("opens on the sample with the rye card selected", () => {
    expect(base.applied).toEqual(bundle.plan);
    expect(base.selectedStrategy).toBe("protect-soil");
    expect(base.ryeEnd).toBe("2027-04-30");
  });

  it("opening and closing evidence keeps dates, year and rye date", () => {
    let s = reducer(base, { type: "selectYear", year: 2012 });
    s = reducer(s, { type: "setRyeEnd", date: "2027-04-23" });
    const open = reducer(s, { type: "openEvidence" });
    const closed = reducer(open, { type: "closeEvidence" });
    expect(closed.selectedYear).toBe(2012);
    expect(closed.ryeEnd).toBe("2027-04-23");
    expect(planOf(closed)).toBe(planOf(base));
  });

  it("picking a year never changes the plan (case E)", () => {
    const s = reducer(base, { type: "selectYear", year: 1986 });
    expect(planOf(s)).toBe(planOf(base));
    expect(s.ryeEnd).toBe(base.ryeEnd);
  });

  it("changing priorities changes nothing else (case J)", () => {
    const s = reducer(base, { type: "togglePriority", priority: "soil" });
    expect(s.priorities).toEqual(["soil"]);
    expect({ ...s, priorities: [] }).toEqual({ ...base, priorities: [] });
  });

  it("allows at most two priorities", () => {
    let s = reducer(base, { type: "togglePriority", priority: "soil" });
    s = reducer(s, { type: "togglePriority", priority: "income" });
    s = reducer(s, { type: "togglePriority", priority: "water" });
    expect(s.priorities).toEqual(["soil", "income"]);
  });

  it("date edits stay in a draft until applied", () => {
    const edited = reducer(base, { type: "editDraft", patch: { soyPlant: "2027-05-15" } });
    expect(edited.applied.soyPlant).toBe("2027-05-12");
    expect(hasPendingEdits(edited)).toBe(true);
    const applied = reducer(edited, { type: "applyDraft" });
    expect(applied.applied.soyPlant).toBe("2027-05-15");
    expect(hasPendingEdits(applied)).toBe(false);
  });

  it("clamps the rye end date to the supported range", () => {
    const early = reducer(base, { type: "setRyeEnd", date: "2026-01-01" });
    const late = reducer(base, { type: "setRyeEnd", date: "2027-06-01" });
    expect(early.ryeEnd).toBe(base.ryeEndRange[0]);
    expect(late.ryeEnd).toBe(base.ryeEndRange[1]);
  });

  it("reset restores everything including observation, priority and year", () => {
    let s = reducer(base, { type: "editDraft", patch: { moistureConcern: "yes" } });
    s = reducer(s, { type: "applyDraft" });
    s = reducer(s, { type: "selectYear", year: 2012 });
    s = reducer(s, { type: "togglePriority", priority: "income" });
    s = reducer(s, { type: "setRyeEnd", date: "2027-04-01" });
    s = reducer(s, { type: "openEvidence" });
    expect(reducer(s, { type: "reset" })).toEqual(base);
  });
});

describe("shareable links", () => {
  const years = new Set(bundle.strategies[1]!.events[0]!.years.map((y) => y.year));

  it("round-trips the view", () => {
    let s = reducer(base, { type: "selectYear", year: 2012 });
    s = reducer(s, { type: "setRyeEnd", date: "2027-04-23" });
    s = reducer(s, { type: "togglePriority", priority: "soil" });
    const restored = applyUrlView(base, fromHash(toHash(s), years));
    expect(restored.selectedYear).toBe(2012);
    expect(restored.ryeEnd).toBe("2027-04-23");
    expect(restored.priorities).toEqual(["soil"]);
  });

  it("ignores a broken or old link and opens the sample", () => {
    const view = fromHash("#s=nope&y=1850&r=yesterday&p=fast,cheap&e=loud", years);
    expect(view).toEqual({});
    expect(applyUrlView(base, view)).toEqual(base);
  });

  it("never puts farm details in the link", () => {
    expect(toHash(base)).not.toMatch(/union|soil=|irrigation|moisture/i);
  });
});
