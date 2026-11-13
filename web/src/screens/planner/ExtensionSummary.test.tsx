import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { CompareResponse, SensitivityResponse, YearsResponse } from "../../api/schema";
import { sampleForm } from "../../state/form";
import { buildView, type Selection } from "../../view/build";
import { ExtensionSummary } from "./ExtensionSummary";

const dir = join(dirname(fileURLToPath(import.meta.url)), "../../../public/data/sample");
const read = (n: string) => JSON.parse(readFileSync(join(dir, `${n}.json`), "utf8"));
const data = {
  years: YearsResponse.parse(read("years")),
  compare: CompareResponse.parse(read("compare")),
  sensitivity: SensitivityResponse.parse(read("sensitivity")),
  origin: "saved" as const,
};
const form = sampleForm(data.compare);

function show(sel: Partial<Selection> = {}) {
  const base: Selection = { card: "cover", year: 2014, observation: { moisture: "yes", irrigation: "unknown" }, ...sel };
  const legViews = { 1: buildView(data, { ...base, leg: 1 }), 2: buildView(data, { ...base, leg: 2 }) } as const;
  render(
    <ExtensionSummary
      view={legViews[1]}
      legViews={legViews}
      form={{ ...form, moistureConcern: "yes" }}
      priorities={base.priorities ?? []}
      planSource="sample"
      onClose={() => {}}
    />,
  );
  return legViews;
}

describe("Extension summary", () => {
  it("shows both winters with the planner's numbers, never added", () => {
    const v = show();
    const plan = screen.getAllByRole("heading", { name: "2. Add winter cover" })[0]!.closest(".xs-plan") as HTMLElement;
    const rows = within(plan).getAllByRole("row");
    const cover = v[1].cards.find((c) => c.key === "cover")!;
    expect(rows[1]).toHaveTextContent(`${cover.legs[0]!.soilMm!.toFixed(1)} mm`);
    expect(rows[1]).toHaveTextContent(`${cover.legs[0]!.check.count} of ${cover.legs[0]!.check.denominator}`);
    expect(rows[2]).toHaveTextContent(`${cover.legs[1]!.soilMm!.toFixed(1)} mm`);
    expect(screen.queryByText(/74\.6 mm/)).toBeNull(); // 46.3 + 28.3 would be a sum
  });

  it("lists a rule shared by several plans once, naming each plan", () => {
    show();
    const items = screen.getAllByText(/Plant corn once soil is at or above 55 F/);
    expect(items).toHaveLength(1);
    expect(items[0]!.closest("li")).toHaveTextContent(/What you do now, Add winter cover, Add a grain crop/);
  });

  it("puts what the grower reported first, with its source", () => {
    show();
    const first = screen.getByRole("heading", { name: "To discuss with your agent" }).nextElementSibling!.querySelector("li")!;
    expect(first).toHaveTextContent(/^You reported: You reported a field moisture concern/);
    expect(first.querySelector(".xs-ref")).not.toBeNull();
  });

  it("states the disclaimer and numbers every cited source", () => {
    show({ priorities: ["soil"] });
    expect(screen.getAllByText(/Not a forecast or a field measurement/)).toHaveLength(2);
    const sources = screen.getByRole("heading", { name: "Sources" }).nextElementSibling!;
    expect(within(sources as HTMLElement).getAllByRole("listitem")[0]).toHaveTextContent("NASA POWER");
    const cited = new Set([...document.querySelectorAll(".xs-ref")].map((e) => e.textContent));
    expect(within(sources as HTMLElement).getAllByRole("listitem")).toHaveLength(cited.size);
  });
});
