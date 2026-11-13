import type { Plan } from "../../api/schema";
import { monthDay } from "../../data/format";

/*
  Two-season calendar (card 2.6). One shared time axis from Sep 1 to Jul 1, one row per
  plan, planting markers aligned. Positions are drawing only; no metric is computed here.
  A calendar of planned operations: colors do not show measured ground cover (playbook p.41).
*/

const AXIS_START = { m: 9, d: 1 };
const DAYS = 303; // Sep 1 → Jul 1 (non-leap)
const MONTHS = ["Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"];
const MONTH_LEN = [30, 31, 30, 31, 31, 28, 31, 30, 31, 30];

function dayIndex(md: string): number {
  const m = Number(md.slice(0, 2));
  const d = Number(md.slice(3, 5));
  const order = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7];
  const mi = order.indexOf(m);
  if (mi < 0) return 0;
  let idx = 0;
  for (let i = 0; i < mi; i++) idx += MONTH_LEN[i]!;
  return Math.min(DAYS, Math.max(0, idx + d - AXIS_START.d));
}

const W = 640;
const LABEL_W = 0;
const x = (md: string) => LABEL_W + (dayIndex(md) / DAYS) * (W - LABEL_W);

export function Timeline({ rows }: { rows: Array<{ name: string; plan: Plan | null }> }) {
  return (
    <figure className="timeline" aria-labelledby="timeline-caption">
      <div className="timeline-scroll">
        <div className="timeline-grid">
          {rows.map(({ name, plan }) => {
            if (!plan || !plan.sequence) {
              return (
                <div className="tl-row" key={name}>
                  <div className="tl-label">
                    <strong>{name}</strong>
                    <span>{plan?.reason ? "Not evaluated yet: dates not sourced" : "Not available yet"}</span>
                  </div>
                  <div className="tl-track" />
                </div>
              );
            }
            const w = plan.sequence.winter;
            const harvest = plan.sequence.prev_harvest;
            const plant = plan.sequence.next_plant;
            const living =
              w.type === "cover" ? { from: w.seed, to: w.terminate, kind: "cover" } : w.type === "winter_grain" ? { from: w.plant, to: w.harvest, kind: "wheat" } : null;
            const text =
              w.type === "cover"
                ? `Rye ${monthDay(w.seed)}–${monthDay(w.terminate)} · ${plan.sequence.next_crop_id === "field_corn" ? "corn" : "soybeans"} ${monthDay(plant)}`
                : w.type === "winter_grain"
                  ? `Wheat ${monthDay(w.plant)}–${monthDay(w.harvest)} · soybeans ${monthDay(plant)}`
                  : `No planted cover · ${plan.sequence.next_crop_id === "field_corn" ? "corn" : "soybeans"} ${monthDay(plant)}`;
            return (
              <div className="tl-row" key={name}>
                <div className="tl-label">
                  <strong>{name}</strong>
                  <span>{text}</span>
                </div>
                <svg className="tl-track" viewBox={`0 0 ${W} 28`} preserveAspectRatio="none" role="img" aria-label={`${name}: ${text}`}>
                  <rect className="tl-fallow" x={x(harvest)} y={10} width={Math.max(0, x(plant) - x(harvest))} height={8} rx={2} />
                  {living ? (
                    <rect className={`tl-living tl-${living.kind}`} x={x(living.from)} y={6} width={Math.max(0, x(living.to) - x(living.from))} height={16} rx={3} />
                  ) : null}
                  <line className="tl-harvest" x1={x(harvest)} x2={x(harvest)} y1={4} y2={24} />
                  <circle className="tl-plant" cx={x(plant)} cy={14} r={5} />
                </svg>
              </div>
            );
          })}
          <div className="tl-row tl-axis-row" aria-hidden="true">
            <div className="tl-label" />
            <div className="tl-axis">
              {MONTHS.map((m, i) => (
                <span key={m} style={{ left: `${(MONTH_LEN.slice(0, i).reduce((a, b) => a + b, 0) / DAYS) * 100}%` }}>
                  {m}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
      <figcaption id="timeline-caption" className="timeline-caption">
        Calendar of planned operations, harvest to planting. Colors show planned dates, not measured ground cover.
        <span className="tl-key">
          <span className="tl-key-fallow" /> no planted cover (residue may remain) <span className="tl-key-cover" /> living rye{" "}
          <span className="tl-key-wheat" /> wheat <span className="tl-key-plant" /> planting
        </span>
      </figcaption>
    </figure>
  );
}
