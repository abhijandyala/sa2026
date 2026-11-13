import type { CardKey, Leg, Priority } from "../content/strategies";
import type { FarmForm } from "./form";

/*
  What the user has selected (frontend handbook p.9, playbook p.38 and p.48).
  Enforced here and tested in model.test.ts:
  - opening evidence or the form, or changing priorities, never changes dates or the year;
  - picking a year changes weather only, never the plan;
  - form edits stay in a draft until applied;
  - reset restores everything, including field observation, priority and year.
*/

export type { Priority };
export type Emphasis = "cover" | "buffer";
/** One question per page (design strategy, Nov 13): the sidebar switches pages, it does not scroll. */
export type Page = "overview" | "springs" | "compare" | "plan" | "rye" | "calendar";
export const PAGES: Page[] = ["overview", "springs", "compare", "plan", "rye", "calendar"];

export interface AppState {
  sample: FarmForm;
  applied: FarmForm;
  draft: FarmForm | null;
  card: CardKey;
  year: number | null; // null = the window's typical year
  /** Which winter the page shows: 1 = corn → soybeans, 2 = soybeans → corn. */
  leg: Leg;
  /** Rye end date chosen on the slider, MM-DD. null = the plan's proposed date. */
  ryeEnd: string | null;
  ryeOpen: boolean;
  priorities: Priority[];
  emphasis: Emphasis;
  evidenceOpen: boolean;
  formOpen: boolean;
  /** The printable Extension summary (Phase 8) is showing instead of the planner. */
  summaryOpen: boolean;
  /** Which place's weather to use (Phase 9): a place ID, or "custom" for typed coordinates. */
  placeId: string;
  locationOpen: boolean;
  page: Page;
}

export type Action =
  | { type: "selectCard"; card: CardKey }
  | { type: "selectYear"; year: number | null }
  | { type: "selectLeg"; leg: Leg }
  | { type: "setRyeEnd"; md: string | null }
  | { type: "openRye" }
  | { type: "closeRye" }
  | { type: "openForm" }
  | { type: "closeForm" }
  | { type: "editDraft"; patch: Partial<FarmForm> }
  | { type: "applied"; form: FarmForm }
  | { type: "discardDraft" }
  | { type: "togglePriority"; priority: Priority }
  | { type: "setEmphasis"; emphasis: Emphasis }
  | { type: "openEvidence" }
  | { type: "closeEvidence" }
  | { type: "setPage"; page: Page }
  | { type: "setPlace"; placeId: string }
  | { type: "openLocation" }
  | { type: "closeLocation" }
  | { type: "openSummary" }
  | { type: "closeSummary" }
  | {
      type: "applyLink";
      view: {
        card?: CardKey;
        year?: number;
        leg?: Leg;
        ryeEnd?: string;
        priorities?: Priority[];
        emphasis?: Emphasis;
        summary?: boolean;
        placeId?: string;
        page?: Page;
      };
    }
  | { type: "reset" };

export const MAX_PRIORITIES = 2;

export function initialState(sample: FarmForm): AppState {
  return {
    sample,
    applied: sample,
    draft: null,
    card: "cover",
    year: null,
    leg: 1,
    ryeEnd: null,
    ryeOpen: false,
    priorities: [],
    emphasis: "buffer",
    evidenceOpen: false,
    formOpen: false,
    summaryOpen: false,
    placeId: "union",
    locationOpen: false,
    page: "overview",
  };
}

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "selectCard":
      // A different planting window can apply, so the year returns to that window's typical year.
      return { ...state, card: action.card, year: action.card === state.card ? state.year : null };
    case "selectYear":
      return { ...state, year: action.year };
    case "selectLeg":
      // Each winter has its own planting window, so the year returns to that window's typical year.
      return { ...state, leg: action.leg, year: action.leg === state.leg ? state.year : null };
    case "setRyeEnd":
      // Moving the rye date never changes the year, the soybean date or anything else.
      return { ...state, ryeEnd: action.md };
    case "openRye":
      // The rye slider is for the winter before soybeans (leg 1).
      return { ...state, ryeOpen: true, page: "rye", card: "cover", leg: 1, year: state.card === "cover" && state.leg === 1 ? state.year : null };
    case "closeRye":
      return { ...state, ryeOpen: false, page: state.page === "rye" ? "plan" : state.page };
    case "setPage":
      // The rye page is the rye slider: it looks at winter cover in the winter before soybeans.
      return action.page === "rye"
        ? { ...state, page: "rye", ryeOpen: true, card: "cover", leg: 1, year: state.card === "cover" && state.leg === 1 ? state.year : null }
        : { ...state, page: action.page, ryeOpen: false };
    case "openForm":
      return { ...state, formOpen: true, draft: state.draft ?? state.applied };
    case "closeForm":
      return { ...state, formOpen: false };
    case "editDraft":
      return { ...state, draft: { ...(state.draft ?? state.applied), ...action.patch } };
    case "applied":
      // New dates come with a new sweep, so the slider returns to the proposed date.
      return { ...state, applied: action.form, draft: null, formOpen: false, ryeEnd: null };
    case "discardDraft":
      return { ...state, draft: null, formOpen: false };
    case "togglePriority": {
      const has = state.priorities.includes(action.priority);
      if (has) return { ...state, priorities: state.priorities.filter((p) => p !== action.priority) };
      if (state.priorities.length >= MAX_PRIORITIES) return state;
      return { ...state, priorities: [...state.priorities, action.priority] };
    }
    case "setEmphasis":
      return { ...state, emphasis: action.emphasis };
    case "openEvidence":
      return { ...state, evidenceOpen: true };
    case "closeEvidence":
      return { ...state, evidenceOpen: false };
    case "setPlace":
      // A new place has its own weather record, so the year and rye date return to its defaults.
      return { ...state, placeId: action.placeId, locationOpen: false, year: null, ryeEnd: null, ryeOpen: false };
    case "openLocation":
      return { ...state, locationOpen: true };
    case "closeLocation":
      return { ...state, locationOpen: false };
    case "openSummary":
      // The summary shows the applied plan; drawers close so nothing hides it.
      return { ...state, summaryOpen: true, evidenceOpen: false, formOpen: false, ryeOpen: false };
    case "closeSummary":
      return { ...state, summaryOpen: false };
    case "applyLink": {
      // A shared link or Back/Forward: view choices only, never dates. A missing part means the default.
      const v = action.view;
      return {
        ...state,
        card: v.card ?? "cover",
        year: v.year ?? null,
        leg: v.leg ?? 1,
        ryeEnd: v.ryeEnd ?? null,
        priorities: v.priorities ?? [],
        emphasis: v.emphasis ?? "buffer",
        summaryOpen: v.summary ?? false,
        placeId: v.placeId ?? "union",
        page: v.page ?? "overview",
        ryeOpen: v.page === "rye",
      };
    }
    case "reset":
      return initialState(state.sample);
  }
}

export const hasPendingEdits = (s: AppState) => s.draft !== null && JSON.stringify(s.draft) !== JSON.stringify(s.applied);
