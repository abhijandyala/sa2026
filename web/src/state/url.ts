import type { CardKey } from "../content/strategies";
import type { AppState, Emphasis, Priority } from "./model";

/*
  Shareable links (cards 0.7 and 8.2). The hash holds view choices only: card, year,
  priorities, emphasis. Never farm details. Invalid parts are ignored, so an old or
  broken link opens the sample (handbook p.14).
*/

export interface UrlView {
  card?: CardKey;
  year?: number;
  ryeEnd?: string;
  priorities?: Priority[];
  emphasis?: Emphasis;
}

const CARDS: CardKey[] = ["current", "cover", "grain"];
const PRIORITIES: Priority[] = ["soil", "income", "water"];

export function toHash(s: AppState): string {
  const p = new URLSearchParams();
  p.set("s", s.card);
  if (s.year !== null) p.set("y", String(s.year));
  if (s.ryeEnd !== null) p.set("r", s.ryeEnd);
  if (s.priorities.length) p.set("p", s.priorities.join(","));
  if (s.emphasis !== "buffer") p.set("e", s.emphasis);
  return "#" + p.toString();
}

export function fromHash(hash: string, validYears: ReadonlySet<number>, validRyeEnds: ReadonlySet<string> = new Set()): UrlView {
  const p = new URLSearchParams(hash.replace(/^#/, ""));
  const out: UrlView = {};
  const s = p.get("s");
  if (s && (CARDS as string[]).includes(s)) out.card = s as CardKey;
  const y = Number(p.get("y"));
  if (p.has("y") && Number.isInteger(y) && validYears.has(y)) out.year = y;
  const r = p.get("r");
  if (r && /^\d{2}-\d{2}$/.test(r) && validRyeEnds.has(r)) out.ryeEnd = r;
  const pr = (p.get("p") ?? "").split(",").filter((x): x is Priority => (PRIORITIES as string[]).includes(x));
  if (pr.length) out.priorities = [...new Set(pr)].slice(0, 2);
  const e = p.get("e");
  if (e === "cover" || e === "buffer") out.emphasis = e;
  return out;
}

export function applyUrlView(state: AppState, view: UrlView): AppState {
  return {
    ...state,
    card: view.card ?? state.card,
    year: view.year ?? state.year,
    ryeEnd: view.ryeEnd ?? state.ryeEnd,
    priorities: view.priorities ?? state.priorities,
    emphasis: view.emphasis ?? state.emphasis,
  };
}
