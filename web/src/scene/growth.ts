import type { Plan } from "../api/schema";

/*
  What each field shows on a given day of the planned season (cards 4.2, 4.3).
  This is an ILLUSTRATION of planned dates: heights are schematic stages, never
  measured or modeled crop growth (playbook p.41). Pure functions, tested.

  Season axis: day 0 = Sep 1, last day = Jun 30 (303 days), matching the 2D calendar.
*/

export const SEASON_DAYS = 303;
const ORDER = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6];
const LEN = [30, 31, 30, 31, 31, 28, 31, 30, 31, 30];
const NAMES = ["Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun"];

/** "05-12" → day of the season (Sep 1 = 0). Dates outside Sep–Jun clamp to the ends. */
export function seasonDay(md: string): number {
  const m = Number(md.slice(0, 2));
  const d = Number(md.slice(3, 5));
  const i = ORDER.indexOf(m);
  if (i < 0) return m === 7 || m === 8 ? (m === 7 ? SEASON_DAYS : 0) : 0;
  let idx = 0;
  for (let k = 0; k < i; k++) idx += LEN[k]!;
  return Math.min(SEASON_DAYS, Math.max(0, idx + d - 1));
}

/** Day of the season → "Apr 20". */
export function seasonLabel(day: number): string {
  let rest = Math.min(SEASON_DAYS - 1, Math.max(0, Math.round(day)));
  for (let k = 0; k < LEN.length; k++) {
    if (rest < LEN[k]!) return `${NAMES[k]} ${rest + 1}`;
    rest -= LEN[k]!;
  }
  return "Jun 30";
}

/** Month boundaries for the scrubber's labels. */
export const MONTH_TICKS = NAMES.map((name, k) => ({ name, day: LEN.slice(0, k).reduce((a, b) => a + b, 0) }));

export interface FieldState {
  corn: { show: boolean; h: number };
  cover: { show: boolean; h: number; ended: boolean };
  wheat: { show: boolean; h: number; ripe: number };
  soy: { show: boolean; h: number };
  /** 0..1 how much crop residue is drawn on the surface. */
  residue: number;
  /** True while the day is inside the 30-day window before this field's planting. */
  inSpringWindow: boolean;
  /** "Living cover", "Residue only", … for the text description. */
  label: string;
}

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));

export function fieldStateAt(plan: Plan, day: number): FieldState {
  const seq = plan.sequence;
  const harvest = seasonDay(seq.prev_harvest);
  const plant = seasonDay(seq.next_plant);
  const w = seq.winter;
  const emergence = plant + 7;

  const corn = { show: day < harvest, h: 1 };
  const soy = { show: day >= emergence, h: 0.12 + 0.68 * clamp01((day - emergence) / 50) };
  const cover = { show: false, h: 0, ended: false };
  const wheat = { show: false, h: 0, ripe: 0 };
  let residue = day >= harvest ? 1 : 0;
  let label = day < harvest ? "Corn before harvest" : "Corn residue, no living cover";

  if (w.type === "cover") {
    const seed = seasonDay(w.seed);
    const end = seasonDay(w.terminate);
    if (day >= seed && day < end) {
      cover.show = true;
      cover.h = 0.15 + 0.85 * Math.pow(clamp01((day - seed) / Math.max(1, end - seed)), 1.6);
      residue = 0.5;
      label = "Living rye (planned)";
    } else if (day >= end) {
      cover.show = true;
      cover.ended = true;
      cover.h = 0.28;
      residue = 1;
      label = "Rye ended; residue on the surface";
    }
  } else if (w.type === "winter_grain") {
    const start = seasonDay(w.plant);
    const end = seasonDay(w.harvest);
    if (day >= start && day < end) {
      const p = clamp01((day - start) / Math.max(1, end - start));
      wheat.show = true;
      wheat.h = 0.1 + 0.9 * Math.pow(p, 1.4);
      wheat.ripe = clamp01((p - 0.72) / 0.28);
      residue = 0.5;
      label = wheat.ripe > 0.5 ? "Wheat ripening (planned)" : "Living wheat (planned)";
    } else if (day >= end) {
      residue = 1;
      label = "Wheat harvested; stubble on the surface";
    }
  }

  if (soy.show) label = `${label.split(";")[0]}; soybeans up`;
  else if (day >= plant) label = `${label.split(";")[0]}; soybeans planted`;

  return {
    corn,
    cover,
    wheat,
    soy,
    residue,
    inSpringWindow: day >= plant - 30 && day < plant,
    label,
  };
}
