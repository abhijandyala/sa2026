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
  it("reads the sample dates for both winters from the backend plans", () => {
    expect(sample).toMatchObject({
      soyHarvest: "2027-10-15",
      rye2Seed: "2027-10-20",
      rye2End: "2028-04-05",
      cornPlant: "2028-04-15",
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
    expect(inputs.map((p) => p.plan_id)).toEqual([
      "corn_soy__no_cover",
      "corn_soy__rye",
      "corn_soy__wheat_dc",
      "soy_corn__no_cover",
      "soy_corn__rye",
    ]);
    const rye = inputs.find((p) => p.plan_id === "corn_soy__rye")!;
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

describe("winters", () => {
  it("choosing winter 2 keeps the plan and resets the year to that window's typical year", () => {
    const s = reducer(reducer(base, { type: "selectYear", year: 2014 }), { type: "selectLeg", leg: 2 });
    expect(s).toMatchObject({ leg: 2, year: null });
    expect(s.applied).toEqual(base.applied);
  });

  it("checks the order of winter 2's dates", () => {
    expect(validateForm({ ...sample, rye2End: "2028-04-20" }).rye2End).toBe("Choose a rye end date after seeding and before corn planting.");
    expect(validateForm({ ...sample, cornPlant: "2027-10-01" }).cornPlant).toBe("Corn planting must come after the soybean harvest.");
  });

  it("the rye slider opens on winter 1", () => {
    const s = reducer(reducer(base, { type: "selectLeg", leg: 2 }), { type: "openRye" });
    expect(s.leg).toBe(1);
  });

  it("keeps the winter in a shared link", () => {
    const s = reducer(base, { type: "selectLeg", leg: 2 });
    expect(toHash(s)).toMatch(/l=2/);
    expect(fromHash(toHash(s), validYears(compare)).leg).toBe(2);
  });
});

describe("following a link in an open tab", () => {
  it("applies the link's view and keeps the dates", () => {
    let s = reducer(base, { type: "openForm" });
    s = reducer(s, { type: "editDraft", patch: { soyPlant: "2027-05-18" } });
    s = reducer(s, { type: "applied", form: s.draft! });
    s = reducer(s, { type: "applyLink", view: { card: "grain", year: 2014 } });
    expect(s).toMatchObject({ card: "grain", year: 2014 });
    expect(s.applied.soyPlant).toBe("2027-05-18");
  });

  it("treats missing parts as the defaults", () => {
    const s = reducer({ ...base, card: "grain", year: 2014, priorities: ["soil"] }, { type: "applyLink", view: {} });
    expect(s).toMatchObject({ card: "cover", year: null, priorities: [] });
  });
});

describe("rye end date", () => {
  it("moving the date keeps the year, the plan and the card", () => {
    let s = reducer(base, { type: "selectYear", year: 2014 });
    s = reducer(s, { type: "setRyeEnd", md: "04-23" });
    expect(s).toMatchObject({ ryeEnd: "04-23", year: 2014, card: "cover" });
    expect(s.applied).toEqual(base.applied);
  });

  it("opening the deep-dive selects the cover plan", () => {
    const s = reducer(reducer(base, { type: "selectCard", card: "grain" }), { type: "openRye" });
    expect(s).toMatchObject({ ryeOpen: true, card: "cover" });
  });

  it("applying new dates returns the slider to the proposed date", () => {
    let s = reducer(base, { type: "setRyeEnd", md: "04-10" });
    s = reducer(reducer(s, { type: "openForm" }), { type: "applied", form: { ...sample, soyPlant: "2027-05-18" } });
    expect(s.ryeEnd).toBeNull();
  });

  it("reset clears the chosen date and closes the deep-dive", () => {
    const s = reducer(reducer(base, { type: "openRye" }), { type: "setRyeEnd", md: "04-10" });
    expect(reducer(s, { type: "reset" })).toEqual(base);
  });

  it("round-trips in a link and ignores a date outside the sweep", () => {
    const s = reducer(base, { type: "setRyeEnd", md: "04-23" });
    const ok = fromHash(toHash(s), validYears(compare), new Set(["04-23", "04-30"]));
    expect(ok.ryeEnd).toBe("04-23");
    expect(fromHash("#s=cover&r=12-25", validYears(compare), new Set(["04-23"])).ryeEnd).toBeUndefined();
  });
});

describe("Extension summary state (Phase 8)", () => {
  it("opens over closed drawers, survives a link and resets", () => {
    const s0 = { ...initialState(sampleForm(compare)), evidenceOpen: true };
    const s1 = reducer(s0, { type: "openSummary" });
    expect(s1).toMatchObject({ summaryOpen: true, evidenceOpen: false, formOpen: false });
    expect(toHash(s1)).toMatch(/v=summary/);
    expect(fromHash(toHash(s1), new Set())).toMatchObject({ summary: true });
    expect(reducer(s1, { type: "closeSummary" }).summaryOpen).toBe(false);
    expect(reducer(s1, { type: "reset" }).summaryOpen).toBe(false);
  });
});

describe("place (Phase 9)", () => {
  const base = initialState(sampleForm(compare));
  it("defaults to the Union County sample and keeps it out of links", () => {
    expect(base.placeId).toBe("union");
    expect(toHash(base)).not.toMatch(/loc=/);
  });

  it("a listed county goes in the link; typed coordinates never do", () => {
    const county = reducer({ ...base, year: 2014, ryeEnd: "04-23" }, { type: "setPlace", placeId: "johnston" });
    expect(county).toMatchObject({ placeId: "johnston", year: null, ryeEnd: null, locationOpen: false });
    expect(fromHash(toHash(county), new Set())).toMatchObject({ placeId: "johnston" });
    const typed = reducer(base, { type: "setPlace", placeId: "custom" });
    expect(toHash(typed)).not.toMatch(/loc=/);
  });

  it("ignores unknown places in a link and reset returns to the sample", () => {
    expect(fromHash("#loc=atlantis", new Set()).placeId).toBeUndefined();
    expect(reducer(reducer(base, { type: "setPlace", placeId: "pitt" }), { type: "reset" }).placeId).toBe("union");
  });
});

describe("pages (one question per page)", () => {
  const base = initialState(sampleForm(compare));
  it("starts on the overview and keeps it out of links", () => {
    expect(base.page).toBe("overview");
    expect(toHash(base)).not.toMatch(/pg=/);
  });
  it("a page goes in the link and comes back from it", () => {
    const s = reducer(base, { type: "setPage", page: "compare" });
    expect(fromHash(toHash(s), new Set())).toMatchObject({ page: "compare" });
    expect(fromHash("#pg=nowhere", new Set()).page).toBeUndefined();
  });
  it("the rye page is the rye slider: winter cover, the winter before soybeans", () => {
    const s = reducer({ ...base, card: "current", leg: 2 }, { type: "setPage", page: "rye" });
    expect(s).toMatchObject({ page: "rye", ryeOpen: true, card: "cover", leg: 1 });
    expect(reducer(s, { type: "closeRye" })).toMatchObject({ page: "plan", ryeOpen: false });
    expect(reducer(base, { type: "openRye" }).page).toBe("rye");
  });
});
