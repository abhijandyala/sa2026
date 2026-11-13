import type { CardKey, Leg } from "../content/strategies";
import { placeById } from "../content/locations";
import { PAGES, type AppState, type Emphasis, type Page, type Priority } from "./model";

/*
  Shareable links (cards 0.7 and 8.2). The hash holds view choices only: card, year,
  winter, rye date, priorities, emphasis and the summary. Never farm details. Invalid parts are ignored, so an old or
  broken link opens the sample (handbook p.14).
*/

export interface UrlView {
  card?: CardKey;
  year?: number;
  leg?: Leg;
  ryeEnd?: string;
  priorities?: Priority[];
  emphasis?: Emphasis;
  summary?: boolean;
  placeId?: string;
  page?: Page;
}

const CARDS: CardKey[] = ["current", "cover", "grain"];
const PRIORITIES: Priority[] = ["soil", "income", "water"];

export function toHash(s: AppState): string {
  const p = new URLSearchParams();
  p.set("s", s.card);
  if (s.year !== null) p.set("y", String(s.year));
  if (s.leg !== 1) p.set("l", String(s.leg));
  if (s.ryeEnd !== null) p.set("r", s.ryeEnd);
  if (s.priorities.length) p.set("p", s.priorities.join(","));
  if (s.emphasis !== "buffer") p.set("e", s.emphasis);
  if (s.summaryOpen) p.set("v", "summary");
  if (s.page !== "overview") p.set("pg", s.page);
  // Listed places only; typed coordinates stay out of links (they can point at a real field).
  if (s.placeId !== "union" && placeById(s.placeId)) p.set("loc", s.placeId);
  return "#" + p.toString();
}

export function fromHash(hash: string, validYears: ReadonlySet<number>, validRyeEnds: ReadonlySet<string> = new Set()): UrlView {
  const p = new URLSearchParams(hash.replace(/^#/, ""));
  const out: UrlView = {};
  const s = p.get("s");
  if (s && (CARDS as string[]).includes(s)) out.card = s as CardKey;
  const y = Number(p.get("y"));
  if (p.has("y") && Number.isInteger(y) && validYears.has(y)) out.year = y;
  if (p.get("l") === "2") out.leg = 2;
  const r = p.get("r");
  if (r && /^\d{2}-\d{2}$/.test(r) && validRyeEnds.has(r)) out.ryeEnd = r;
  const pr = (p.get("p") ?? "").split(",").filter((x): x is Priority => (PRIORITIES as string[]).includes(x));
  if (pr.length) out.priorities = [...new Set(pr)].slice(0, 2);
  const e = p.get("e");
  if (e === "cover" || e === "buffer") out.emphasis = e;
  if (p.get("v") === "summary") out.summary = true;
  const loc = p.get("loc");
  if (loc && placeById(loc)) out.placeId = loc;
  const pg = p.get("pg");
  if (pg && (PAGES as string[]).includes(pg)) out.page = pg as Page;
  return out;
}

export function applyUrlView(state: AppState, view: UrlView): AppState {
  return {
    ...state,
    card: view.card ?? state.card,
    year: view.year ?? state.year,
    leg: view.leg ?? state.leg,
    ryeEnd: view.ryeEnd ?? state.ryeEnd,
    priorities: view.priorities ?? state.priorities,
    emphasis: view.emphasis ?? state.emphasis,
    summaryOpen: view.summary ?? state.summaryOpen,
    placeId: view.placeId ?? state.placeId,
    page: view.page ?? state.page,
    ryeOpen: view.page ? view.page === "rye" : state.ryeOpen,
  };
}
