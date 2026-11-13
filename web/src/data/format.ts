/*
  Display formatting only. No calculation lives here (handbook p.4): totals, ranks,
  flags and counts arrive from Rahul's data already computed.
  Dates are parsed as plain calendar dates (no time zones), so Apr 30 never shifts.
*/

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parts(iso: string): { y: number; m: number; d: number } {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) throw new Error(`Not an ISO date: ${iso}`);
  return { y: Number(match[1]), m: Number(match[2]), d: Number(match[3]) };
}

/** Planned crop calendar date. No year, so it never reads like historical weather (playbook p.36). */
export function plannedDate(iso: string): string {
  const { m, d } = parts(iso);
  return `${MONTHS[m - 1]} ${d}`;
}

/** A plan date in the backend's MM-DD form, e.g. "05-12" → "May 12". */
export function monthDay(md: string): string {
  const match = /^(\d{2})-(\d{2})$/.exec(md);
  if (!match) throw new Error(`Not an MM-DD date: ${md}`);
  return `${MONTHS[Number(match[1]) - 1]} ${Number(match[2])}`;
}

/** Historical weather date, always with its year (playbook p.36). */
export function historicalDate(iso: string): string {
  const { y, m, d } = parts(iso);
  return `${MONTHS[m - 1]} ${d}, ${y}`;
}

/** "Apr 12–May 11, 2012" for a historical window inside one year. */
export function historicalWindow([start, end]: readonly [string, string]): string {
  const a = parts(start);
  const b = parts(end);
  if (a.y !== b.y) return `${historicalDate(start)}–${historicalDate(end)}`;
  return `${MONTHS[a.m - 1]} ${a.d}–${MONTHS[b.m - 1]} ${b.d}, ${b.y}`;
}

/** Rainfall always in mm with one decimal (playbook p.36). Null means missing, never zero. */
export function mm(value: number | null): string {
  if (value === null) return "Not available";
  return `${value.toFixed(1)} mm`;
}

export function days(n: number | null, singular = "day", plural = "days"): string {
  if (n === null) return "—";
  return `${n} ${Math.abs(n) === 1 ? singular : plural}`;
}

/** "8 of 45 springs". Always shows N; never a bare percentage. */
export function springs(count: number | null, of: number): string {
  if (count === null) return "Not compared";
  return `${count} of ${of} ${of === 1 ? "spring" : "springs"}`;
}

/** Modeled root-zone wetness, a 0 to 1 fraction. */
export function wetness(value: number | null): string {
  if (value === null) return "Not available";
  return value.toFixed(2);
}

/** Signed change with words, e.g. "7 more days" / "7 fewer days". */
export function change(delta: number, more: string, fewer: string): string {
  if (delta === 0) return "No change";
  return `${Math.abs(delta)} ${delta > 0 ? more : fewer}`;
}
