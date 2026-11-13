import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { CompareResponse } from "../api/schema";
import { validYears } from "../view/build";
import { sampleForm, toPlanInputs, validateForm } from "./form";
import { hasPendingEdits, initialState, reducer, type AppState } from "./model";
import { applyUrlView, fromHash, toHash } from "./url";

const compare = CompareResponse.parse(
  JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../public/data/sample/compare.json"), "utf8")),
);
const sample = sampleForm(compare);
const base = initialState(sample);
const plan = (s: AppState) => JSON.stringify(s.applied);

describe("state model", () => {
  it("opens on the sample with the cover card selected", () => {
    expect(base.applied).toEqual(sample);
    expect(base.card).toBe("cover");
    expect(base.year).toBeNull();
  });

  it("opening and closing evidence keeps the year and the plan", () => {
    let s = reducer(base, { type: "selectYear", year: 2012 });
    s = reducer(reducer(s, { type: "openEvidence" }), { type: "closeEvidence" });
    expect(s.year).toBe(2012);
    expect(plan(s)).toBe(plan(base));
  });

  it("picking a year never changes the plan (case E)", () => {
    const s = reducer(base, { type: "selectYear", year: 1986 });
    expect(plan(s)).toBe(plan(base));
  });

  it("changing priorities changes nothing else (case J)", () => {
    const s = reducer(base, { type: "togglePriority", priority: "soil" });
    expect({ ...s, priorities: [] }).toEqual(base);
  });

  it("allows at most two priorities", () => {
    let s = reducer(base, { type: "togglePriority", priority: "soil" });
    s = reducer(s, { type: "togglePriority", priority: "income" });
    s = reducer(s, { type: "togglePriority", priority: "water" });
    expect(s.priorities).toEqual(["soil", "income"]);
  });

  it("form edits stay in a draft until applied", () => {
    let s = reducer(base, { type: "openForm" });
    s = reducer(s, { type: "editDraft", patch: { soyPlant: "2027-05-18" } });
    expect(s.applied.soyPlant).toBe("2027-05-12");
    expect(hasPendingEdits(s)).toBe(true);
    s = reducer(s, { type: "applied", form: s.draft! });
    expect(s.applied.soyPlant).toBe("2027-05-18");
    expect(s.formOpen).toBe(false);
    expect(hasPendingEdits(s)).toBe(false);
  });

  it("switching cards resets the year to that window's typical year", () => {
    let s = reducer(base, { type: "selectYear", year: 2012 });
    s = reducer(s, { type: "selectCard", card: "grain" });
    expect(s.year).toBeNull();
  });

  it("reset restores everything, including the field observation", () => {
    let s = reducer(base, { type: "openForm" });
    s = reducer(s, { type: "editDraft", patch: { moistureConcern: "yes" } });
    s = reducer(s, { type: "applied", form: s.draft! });
    s = reducer(s, { type: "selectYear", year: 2012 });
    s = reducer(s, { type: "togglePriority", priority: "income" });
    s = reducer(s, { type: "openEvidence" });
    expect(reducer(s, { type: "reset" })).toEqual(base);
  });
});

describe("farm form", () => {
  it("reads the sample dates from the backend plans", () => {
    expect(sample).toMatchObject({
      cornHarvest: "2026-09-20",
      ryeSeed: "2026-10-01",
      ryeEnd: "2027-04-30",
      ryeEndEarlier: "2027-04-23",
      soyPlant: "2027-05-12",
      moistureConcern: "unknown",
    });
    expect(validateForm(sample)).toEqual({});
  });

  it("puts the rye-order error on the rye field", () => {
    const e = validateForm({ ...sample, ryeEnd: "2027-05-20" });
    expect(e.ryeEnd).toBe("Choose a rye end date after seeding and before soybean planting for this comparison.");
    expect(Object.keys(e)).toEqual(["ryeEnd"]);
  });

  it("requires every date and keeps them inside the season", () => {
    expect(validateForm({ ...sample, wheatHarvest: "" }).wheatHarvest).toBe("Enter a date.");
    expect(validateForm({ ...sample, soyPlant: "2028-05-12" }).soyPlant).toMatch(/^Choose a date between/);
  });

  it("checks the wheat sequence", () => {
    expect(validateForm({ ...sample, soyDoubleCropPlant: "2027-06-01" }).soyDoubleCropPlant).toBe(
      "Plant double-crop soybeans after the wheat harvest.",
    );
  });

  it("sends MM-DD and the grower's concern to the backend, never a guessed value", () => {
    const inputs = toPlanInputs({ ...sample, moistureConcern: "unknown" });
    const rye = inputs.find((p) => p.plan_id === "rye_12d")!;
    expect(rye).toMatchObject({ prev_harvest: "09-20", next_plant: "05-12", low_moisture_concern: "unknown" });
    expect(rye.winter).toEqual({ type: "cover", crop_id: "cereal_rye", seed: "10-01", terminate: "04-30" });
  });
});

describe("shareable links", () => {
  const years = validYears(compare);

  it("round-trips the view", () => {
    let s = reducer(base, { type: "selectYear", year: 2012 });
    s = reducer(s, { type: "togglePriority", priority: "soil" });
    s = reducer(s, { type: "selectCard", card: "current" });
    s = reducer(s, { type: "selectYear", year: 1999 });
    const restored = applyUrlView(base, fromHash(toHash(s), years));
    expect(restored).toMatchObject({ card: "current", year: 1999, priorities: ["soil"] });
  });

  it("ignores a broken or old link and opens the sample", () => {
    const view = fromHash("#s=protect-soil&y=1850&p=fast&e=loud", years);
    expect(view).toEqual({});
    expect(applyUrlView(base, view)).toEqual(base);
  });

  it("never puts farm details in the link", () => {
    expect(toHash(base)).not.toMatch(/union|harvest|moisture|irrigation|soil=/i);
  });
});
