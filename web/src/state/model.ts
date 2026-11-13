import type { Bundle, FarmPlan, Priority, StrategyId } from "../data/schema";

/*
  One place for what the user has selected (frontend handbook p.9, playbook p.38 and p.48).
  Rules enforced here and tested in model.test.ts:
  - opening evidence, help or changing priorities never changes dates or the year;
  - picking a year changes weather only, never the plan;
  - editing dates goes to a draft until applied;
  - reset restores everything, including field observation, priority and year.
*/

export type CameraPreset = "overview" | StrategyId | "cutaway";
export type Emphasis = "cover" | "buffer";

export interface AppState {
  sample: FarmPlan;
  applied: FarmPlan;
  draft: FarmPlan | null;
  selectedStrategy: StrategyId;
  selectedYear: number | null; // null = the event's typical year
  ryeEnd: string;
  ryeEndRange: readonly [string, string];
  priorities: Priority[];
  emphasis: Emphasis;
  evidenceOpen: boolean;
  camera: CameraPreset;
}

export type Action =
  | { type: "selectStrategy"; id: StrategyId }
  | { type: "selectYear"; year: number | null }
  | { type: "setRyeEnd"; date: string }
  | { type: "editDraft"; patch: Partial<FarmPlan> }
  | { type: "applyDraft" }
  | { type: "discardDraft" }
  | { type: "togglePriority"; priority: Priority }
  | { type: "setEmphasis"; emphasis: Emphasis }
  | { type: "openEvidence" }
  | { type: "closeEvidence" }
  | { type: "setCamera"; camera: CameraPreset }
  | { type: "reset" };

export const MAX_PRIORITIES = 2;

export function initialState(bundle: Bundle): AppState {
  const curve = bundle.curves.find((c) => c.strategyId === "protect-soil");
  const first = curve?.points[0]?.endDate ?? bundle.plan.ryeEnd;
  const last = curve?.points[curve.points.length - 1]?.endDate ?? bundle.plan.ryeEnd;
  return {
    sample: bundle.plan,
    applied: bundle.plan,
    draft: null,
    selectedStrategy: "protect-soil",
    selectedYear: null,
    ryeEnd: bundle.plan.ryeEnd,
    ryeEndRange: [first, last],
    priorities: [...bundle.plan.priorities],
    emphasis: "buffer",
    evidenceOpen: false,
    camera: "overview",
  };
}

const clampDate = (iso: string, [lo, hi]: readonly [string, string]) => (iso < lo ? lo : iso > hi ? hi : iso);

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "selectStrategy":
      return { ...state, selectedStrategy: action.id, selectedYear: null };
    case "selectYear":
      return { ...state, selectedYear: action.year };
    case "setRyeEnd":
      return { ...state, ryeEnd: clampDate(action.date, state.ryeEndRange) };
    case "editDraft":
      return { ...state, draft: { ...(state.draft ?? state.applied), ...action.patch } };
    case "applyDraft":
      return state.draft ? { ...state, applied: state.draft, draft: null } : state;
    case "discardDraft":
      return { ...state, draft: null };
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
    case "setCamera":
      return { ...state, camera: action.camera };
    case "reset":
      return {
        ...state,
        applied: state.sample,
        draft: null,
        selectedStrategy: "protect-soil",
        selectedYear: null,
        ryeEnd: state.sample.ryeEnd,
        priorities: [...state.sample.priorities],
        emphasis: "buffer",
        evidenceOpen: false,
        camera: "overview",
      };
  }
}

/** True when the form shows edits that the results do not reflect yet. */
export const hasPendingEdits = (s: AppState) =>
  s.draft !== null && JSON.stringify(s.draft) !== JSON.stringify(s.applied);
