import type { Priority, StrategyId } from "../data/schema";
import type { AppState, Emphasis } from "./model";

/*
  Shareable links (scope change 17, card 0.7 and 8.2). The hash holds only view choices:
  strategy, year, rye end date, priorities, emphasis. Never farm details.
  Anything invalid is ignored, so an old or broken link opens the sample (handbook p.14).
*/

export interface UrlView {
  strategy?: StrategyId;
  year?: number;
  ryeEnd?: string;
  priorities?: Priority[];
  emphasis?: Emphasis;
}

const STRATEGIES: StrategyId[] = ["current", "protect-soil", "earn-more"];
const PRIORITIES: Priority[] = ["soil", "income", "water"];

export function toHash(s: AppState): string {
  const p = new URLSearchParams();
  p.set("s", s.selectedStrategy);
  if (s.selectedYear !== null) p.set("y", String(s.selectedYear));
  if (s.ryeEnd !== s.sample.ryeEnd) p.set("r", s.ryeEnd);
  if (s.priorities.length) p.set("p", s.priorities.join(","));
  if (s.emphasis !== "buffer") p.set("e", s.emphasis);
  return "#" + p.toString();
}

export function fromHash(hash: string, validYears: ReadonlySet<number>): UrlView {
  const p = new URLSearchParams(hash.replace(/^#/, ""));
  const out: UrlView = {};
  const s = p.get("s");
  if (s && (STRATEGIES as string[]).includes(s)) out.strategy = s as StrategyId;
  const y = Number(p.get("y"));
  if (Number.isInteger(y) && validYears.has(y)) out.year = y;
  const r = p.get("r");
  if (r && /^\d{4}-\d{2}-\d{2}$/.test(r)) out.ryeEnd = r;
  const pr = (p.get("p") ?? "").split(",").filter((x): x is Priority => (PRIORITIES as string[]).includes(x));
  if (pr.length) out.priorities = [...new Set(pr)].slice(0, 2);
  const e = p.get("e");
  if (e === "cover" || e === "buffer") out.emphasis = e;
  return out;
}

export function applyUrlView(state: AppState, view: UrlView): AppState {
  const next = { ...state };
  if (view.strategy) next.selectedStrategy = view.strategy;
  if (view.year !== undefined) next.selectedYear = view.year;
  if (view.ryeEnd) {
    const [lo, hi] = state.ryeEndRange;
    if (view.ryeEnd >= lo && view.ryeEnd <= hi) next.ryeEnd = view.ryeEnd;
  }
  if (view.priorities) next.priorities = view.priorities;
  if (view.emphasis) next.emphasis = view.emphasis;
  return next;
}
