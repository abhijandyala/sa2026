import { change, days, historicalDate, historicalWindow, mm, plannedDate, springs, wetness } from "./format";

describe("dates", () => {
  it("planned dates have no year so they never look like weather history", () => {
    expect(plannedDate("2027-04-30")).toBe("Apr 30");
  });
  it("historical dates always carry the year", () => {
    expect(historicalDate("2012-04-12")).toBe("Apr 12, 2012");
  });
  it("formats a window inside one year", () => {
    expect(historicalWindow(["2012-04-12", "2012-05-11"])).toBe("Apr 12–May 11, 2012");
  });
  it("does not shift dates across time zones", () => {
    expect(plannedDate("2027-05-01")).toBe("May 1");
    expect(plannedDate("2028-02-29")).toBe("Feb 29");
  });
  it("rejects non-ISO input", () => {
    expect(() => plannedDate("04/30/2027")).toThrow();
  });
});

describe("rainfall", () => {
  it("shows one decimal in mm", () => {
    expect(mm(31.44)).toBe("31.4 mm");
  });
  it("keeps a valid zero as zero", () => {
    expect(mm(0)).toBe("0.0 mm");
  });
  it("shows missing as not available, never zero", () => {
    expect(mm(null)).toBe("Not available");
  });
});

describe("counts and changes", () => {
  it("always shows N with the count", () => {
    expect(springs(8, 45)).toBe("8 of 45 springs");
    expect(springs(null, 45)).toBe("Not compared");
  });
  it("pluralizes days", () => {
    expect(days(1)).toBe("1 day");
    expect(days(12)).toBe("12 days");
    expect(days(null)).toBe("—");
  });
  it("describes both directions of a change", () => {
    expect(change(7, "more days before planting", "fewer days before planting")).toBe("7 more days before planting");
    expect(change(-7, "more planned days with living rye", "fewer planned days with living rye")).toBe(
      "7 fewer planned days with living rye",
    );
    expect(change(0, "a", "b")).toBe("No change");
  });
  it("formats wetness as a fraction", () => {
    expect(wetness(0.412)).toBe("0.41");
    expect(wetness(null)).toBe("Not available");
  });
});
