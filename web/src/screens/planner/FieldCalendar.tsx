import type { ReactNode } from "react";
import type { Plan } from "../../api/schema";
import { monthDay, reasonText } from "../../data/format";
import { MONTH_TICKS, SEASON_DAYS, seasonDay } from "../../scene/growth";
import { seasonPct, WinterPicture } from "./WinterPicture";

/*
  The Calendar page (card 2.6, redesigned Nov 13): when each field job happens.
  One row per plan on a shared month grid, September to June:
  - the field seen from the side, as a full-width strip (the same picture as the Compare page);
  - under it, every planned job as a dated chip in its month, with a pin at the exact day.
  Planned dates only: nothing is measured or computed, and it works without weather data.
*/

type JobKind = "harvest" | "seed" | "end" | "plant";
interface Job {
  kind: JobKind;
  md: string;
  day: number;
  label: string;
}
const CROP: Record<string, string> = { field_corn: "corn", soybean: "soybeans", cereal_rye: "rye", winter_wheat: "wheat" };

function jobsOf(plan: Plan): Job[] {
  const seq = plan.sequence;
  if (!seq) return [];
  const crop = (id: string) => CROP[id] ?? "crop";
  const job = (kind: JobKind, md: string, label: string): Job => ({ kind, md, day: seasonDay(md), label });
  const out = [job("harvest", seq.prev_harvest, `Harvest ${crop(seq.previous_crop_id)}`)];
  const w = seq.winter;
  if (w.type === "cover") {
    out.push(job("seed", w.seed, `Seed ${crop(w.crop_id)}`), job("end", w.terminate, `End the ${crop(w.crop_id)}`));
  } else if (w.type === "winter_grain") {
    out.push(job("seed", w.plant, `Plant ${crop(w.crop_id)}`), job("harvest", w.harvest, `Harvest ${crop(w.crop_id)}`));
  }
  out.push(job("plant", seq.next_plant, `Plant ${crop(seq.next_crop_id)}`));
  return out.sort((a, b) => a.day - b.day);
}

/** Month columns that line up with the picture: a sliver at each edge, then one column per month by its length. */
const EDGE = seasonPct(0);
const MONTH_COLS = MONTH_TICKS.map((m, i) => (MONTH_TICKS[i + 1]?.day ?? SEASON_DAYS - 1) - m.day);
const COLS = `${EDGE}fr ${MONTH_COLS.map((len) => `${((len / (SEASON_DAYS - 1)) * (100 - EDGE * 2)).toFixed(3)}fr`).join(" ")} ${EDGE}fr`;
/** The same width cut into single days, so a chip can start on its own date. */
const DAY_COLS = `${EDGE}fr repeat(${SEASON_DAYS - 1}, ${((100 - EDGE * 2) / (SEASON_DAYS - 1)).toFixed(4)}fr) ${EDGE}fr`;
/** A chip is about a month wide. */
const CHIP_DAYS = 31;

/**
 * Where each chip starts, in season days: on its own date when there is room, otherwise
 * pushed just far enough that chips sit side by side. The pin above always marks the exact date.
 */
function placeChips(jobs: Job[]): number[] {
  const starts: number[] = [];
  jobs.forEach((j, i) => {
    starts.push(i === 0 ? j.day : Math.max(j.day, starts[i - 1]! + CHIP_DAYS + 1));
  });
  const last = SEASON_DAYS - 1 - CHIP_DAYS;
  for (let i = starts.length - 1; i >= 0; i--) {
    const limit = i === starts.length - 1 ? last : starts[i + 1]! - CHIP_DAYS - 1;
    if (starts[i]! > limit) starts[i] = Math.max(0, limit);
  }
  return starts;
}

export interface CalendarRow {
  key: string;
  name: string;
  plan: Plan | null;
}

export function FieldCalendar({
  rows,
  action,
  onOpen,
}: {
  rows: CalendarRow[];
  /** A control for the card's top right (the winter switch). */
  action?: ReactNode;
  onOpen?: (key: string) => void;
}) {
  return (
    <section className="db-card cal" aria-labelledby="calendar-title">
      <header className="db-card-head">
        <h2 id="calendar-title">Field jobs, month by month</h2>
        {action}
      </header>

      <div className="cal-grid">
        <div className="cal-row cal-head" aria-hidden="true">
          <span />
          <div className="cal-months" style={{ gridTemplateColumns: COLS }}>
            <span />
            {MONTH_TICKS.map((m) => (
              <span key={m.name} className="cal-month">
                {m.name}
              </span>
            ))}
            <span />
          </div>
        </div>

        {rows.map((row) => {
          const jobs = row.plan?.sequence ? jobsOf(row.plan) : [];
          const starts = placeChips(jobs);
          return (
            <div className="cal-row" key={row.key}>
              <div className="cal-name">
                <strong>{row.name}</strong>
                {onOpen ? (
                  <button type="button" className="cmp-plan-open cal-open" onClick={() => onOpen(row.key)} aria-label={`Open the plan: ${row.name}`}>
                    Open plan
                    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                      <path d="M4.5 2.5L8 6l-3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                ) : null}
              </div>
              {row.plan?.sequence ? (
                <div className="cal-track">
                  <WinterPicture plan={row.plan} wide />
                  <div className="cal-pins" aria-hidden="true">
                    {jobs.map((j) => (
                      <span key={j.kind + j.md} className={`cal-pin is-${j.kind}`} style={{ left: `${seasonPct(j.day)}%` }} />
                    ))}
                  </div>
                  <ol className="cal-jobs" style={{ gridTemplateColumns: DAY_COLS }} aria-label={`${row.name}: planned jobs`}>
                    {jobs.map((j, i) => (
                      <li key={j.kind + j.md} className={`cal-job is-${j.kind}`} style={{ gridColumn: `${starts[i]! + 2} / span ${CHIP_DAYS}`, gridRow: 1 }}>
                        <span className="cal-job-date tabular">{monthDay(j.md)}</span>
                        <span className="cal-job-name">{j.label}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              ) : (
                <div className="cal-track">
                  <div className="cmp-na">
                    <p className="cmp-na-title">Not evaluated yet</p>
                    {row.plan?.reason ? <p className="cmp-na-why">{reasonText(row.plan.reason)}</p> : null}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <p className="cal-note">
        <span className="cmp-key-rain" /> rain with nothing growing <span className="cmp-key-live" /> crop or cover growing
        <span className="cmp-key-note">Planned dates, drawn as an illustration. Not measured ground cover.</span>
      </p>
    </section>
  );
}
