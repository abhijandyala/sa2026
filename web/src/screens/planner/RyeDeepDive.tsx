import { forwardRef } from "react";
import { monthDay } from "../../data/format";
import type { Emphasis } from "../../state/model";
import type { RyeVM, SweepPoint } from "../../view/build";
import { Button, Segmented, Slider, SourceChip, Src, StatusPill, type SourceKind } from "../../ui/components";
import { G } from "../../ui/Glossary";

/*
  The rye deep-dive (Phase 5): drag the end date and see exactly what moves.
  Every value is a point from the backend's sensitivity sweep; the panel only picks the
  point and shows differences between two backend values (playbook p.40 "show the delta",
  handbook p.12). The spring weather never changes here.
*/

interface Metric {
  key: "checks" | "gap" | "living" | "rain";
  label: string;
  value: (p: SweepPoint, denom: number) => string;
  raw: (p: SweepPoint) => number | null;
  unit: string;
  more: string;
  fewer: string;
}

const METRICS: Record<Metric["key"], Metric> = {
  checks: {
    key: "checks",
    label: "Springs that would have needed a field-moisture check",
    value: (p, d) => (p.checks_count === null ? "—" : `${p.checks_count} of ${d}`),
    raw: (p) => p.checks_count,
    unit: "springs",
    more: "more springs",
    fewer: "fewer springs",
  },
  gap: {
    key: "gap",
    label: "Days before soybean planting",
    value: (p) => `${p.gap_days}`,
    raw: (p) => p.gap_days,
    unit: "days",
    more: "more days before planting",
    fewer: "fewer days before planting",
  },
  living: {
    key: "living",
    label: "Planned days with living rye",
    value: (p) => `${p.living_cover_days_planned}`,
    raw: (p) => p.living_cover_days_planned,
    unit: "days",
    more: "more planned days with living rye",
    fewer: "fewer planned days with living rye",
  },
  rain: {
    key: "rain",
    label: "Median winter rain on ground with no living cover",
    value: (p) => (p.rain_mm_without_cover_median === null ? "—" : `${p.rain_mm_without_cover_median.toFixed(1)} mm`),
    raw: (p) => p.rain_mm_without_cover_median,
    unit: "mm",
    more: "mm more rain on uncovered ground",
    fewer: "mm less rain on uncovered ground",
  },
};

const SRC: Record<Metric["key"], SourceKind[]> = {
  checks: ["nasa", "ncstate", "calculated"],
  gap: ["calculated"],
  living: ["calculated"],
  rain: ["nasa", "calculated"],
};

const ORDER: Record<Emphasis, Metric["key"][]> = {
  buffer: ["checks", "gap", "living", "rain"],
  cover: ["living", "rain", "checks", "gap"],
};

function delta(m: Metric, from: SweepPoint, to: SweepPoint): string | null {
  const a = m.raw(from);
  const b = m.raw(to);
  if (a === null || b === null) return null;
  const d = Math.round((b - a) * 10) / 10;
  if (d === 0) return "No change";
  const n = m.key === "rain" ? Math.abs(d).toFixed(1) : String(Math.abs(d));
  return `${n} ${d > 0 ? m.more : m.fewer}`;
}

export const RyeDeepDive = forwardRef<HTMLElement, {
  rye: RyeVM;
  emphasis: Emphasis;
  onEmphasis: (e: Emphasis) => void;
  onChoose: (md: string | null) => void;
  onClose: () => void;
}>(function RyeDeepDive({ rye, emphasis, onEmphasis, onChoose, onClose }, ref) {
  const { points, chosen, proposed, denominator } = rye;
  const choose = (i: number) => onChoose(i === rye.proposedIndex ? null : points[i]!.terminate);
  const keys = ORDER[emphasis];
  const boundary = rye.boundaryIndex !== null ? points[rye.boundaryIndex]! : null;
  const plant = monthDay(rye.plant);

  const note =
    rye.index === rye.proposedIndex
      ? "This is your proposed date."
      : rye.earlierIndex === rye.index
        ? "Same as the earlier date you entered."
        : `Compared with your proposed date, ${monthDay(proposed.terminate)}.`;

  const announce = `End rye ${monthDay(chosen.terminate)}: ${chosen.gap_days} days before soybean planting, ${chosen.living_cover_days_planned} planned days with living rye, ${
    chosen.checks_count ?? "an unknown number of"
  } of ${denominator} springs with a field-moisture check.`;

  return (
    <section className="rye" aria-labelledby="rye-title" ref={ref} tabIndex={-1}>
      <header className="rye-head">
        <div>
          <h2 id="rye-title" className="section-title">
            Adjust rye timing
          </h2>
          <p className="rye-sub">
            Rye sown {monthDay(rye.seed)}, soybeans planted {plant}. Moving the date you <G id="end-cover">end the cover crop</G>{" "}
            changes the gap and the days of <G id="living-cover">living rye</G>; the past springs' weather stays the same.
          </p>
        </div>
        <div className="rye-head-actions">
          <Segmented
            label="What matters most"
            value={emphasis}
            onChange={onEmphasis}
            options={[
              { value: "buffer", label: "More time before planting" },
              { value: "cover", label: "More living cover" },
            ]}
          />
          <Button variant="quiet" onClick={onClose}>
            Close
          </Button>
        </div>
      </header>

      <div className="rye-grid">
        <div className="rye-controls">
          <Slider
            id="rye-end"
            label={`End the rye cover: ${monthDay(chosen.terminate)}`}
            min={0}
            max={points.length - 1}
            value={rye.index}
            onChange={choose}
            valueText={`${monthDay(chosen.terminate)}, ${chosen.gap_days} days before soybean planting, ${chosen.living_cover_days_planned} planned days with living rye`}
            boundary={rye.boundaryIndex !== null ? { at: rye.boundaryIndex + 0.5, label: "14 days" } : undefined}
          />
          <div className="rye-jumps" role="group" aria-label="Jump to a date">
            <Button className="btn btn-secondary btn-small" onClick={() => choose(rye.proposedIndex)} aria-pressed={rye.index === rye.proposedIndex}>
              Proposed ({monthDay(proposed.terminate)})
            </Button>
            {rye.earlierIndex !== null ? (
              <Button className="btn btn-secondary btn-small" onClick={() => choose(rye.earlierIndex!)} aria-pressed={rye.index === rye.earlierIndex}>
                Earlier ({monthDay(points[rye.earlierIndex]!.terminate)})
              </Button>
            ) : null}
            {boundary ? (
              <Button className="btn btn-secondary btn-small" onClick={() => choose(rye.boundaryIndex!)} aria-pressed={rye.index === rye.boundaryIndex}>
                Last date with 14+ days ({monthDay(boundary.terminate)})
              </Button>
            ) : null}
          </div>
          <p className="rye-note">{note}</p>
          <p className="visually-hidden" aria-live="polite">
            {announce}
          </p>
        </div>

        <dl className="rye-metrics">
          {keys.map((k, i) => {
            const m = METRICS[k];
            const d = rye.changed ? delta(m, proposed, chosen) : null;
            return (
              <div key={k} className={`rye-metric${i < 2 ? " is-lead" : ""}`}>
                <dt>{m.label}</dt>
                <dd>
                  {rye.changed ? (
                    <>
                      <span className="rye-from tabular">{m.value(proposed, denominator)}</span>
                      <span aria-hidden="true"> → </span>
                      <span className="visually-hidden"> changes to </span>
                    </>
                  ) : null}
                  <strong className="tabular">{m.value(chosen, denominator)}</strong>
                  <Src k={SRC[k]} />
                  {d ? <span className="rye-delta">{d}</span> : null}
                </dd>
              </div>
            );
          })}
        </dl>
      </div>

      <div className="rye-year">
        {rye.thisYear ? (
          rye.thisYear.flagged === null ? (
            <StatusPill kind="unavailable">Spring {rye.thisYear.year}: not available for this date</StatusPill>
          ) : rye.thisYear.flagged ? (
            <StatusPill kind="check">Spring {rye.thisYear.year}: check field moisture</StatusPill>
          ) : (
            <span className="rye-year-clear">Spring {rye.thisYear.year}: no field-moisture check at this date</span>
          )
        ) : null}
        {rye.era ? (
          <span className="rye-era tabular">
            Checks by period: {rye.era.earlier.label} {rye.era.earlier.count} of {rye.era.earlier.denominator} ·{" "}
            {rye.era.recent.label} {rye.era.recent.count} of {rye.era.recent.denominator}
          </span>
        ) : (
          <span className="rye-era">Checks by period: not available for this date</span>
        )}
      </div>

      <TradeoffCurve rye={rye} onChoose={choose} />

      <p className="rye-rule">
        The check follows NC State's guidance: end the cover at least 2 weeks before soybean planting if low soil moisture is a concern.
        It fires when {rye.rule.label.replace("AND", "and").replace("OR", "or")}.{" "}
        {rye.rule.source ? <SourceChip kind="ncstate" href={rye.rule.source.url} title={rye.rule.source.title} /> : null}
      </p>
    </section>
  );
});

/* ---------------------------------------------------------------- trade-off curve */

const W = 900;
const TOP_H = 120;
const BOT_H = 70;
const M = { l: 52, r: 16, t: 14, gap: 26, b: 28 };

function TradeoffCurve({ rye, onChoose }: { rye: RyeVM; onChoose: (i: number) => void }) {
  const { points, denominator } = rye;
  const n = points.length;
  const H = M.t + TOP_H + M.gap + BOT_H + M.b;
  const x = (i: number) => M.l + (i / Math.max(1, n - 1)) * (W - M.l - M.r);
  const rains = points.map((p) => p.rain_mm_without_cover_median).filter((v): v is number => v !== null);
  const rainMax = Math.max(10, ...rains);
  const rStep = rainMax <= 100 ? 25 : rainMax <= 250 ? 50 : 100;
  const rTop = Math.ceil(rainMax / rStep) * rStep;
  const yr = (v: number) => M.t + TOP_H - (v / rTop) * TOP_H;
  const b0 = M.t + TOP_H + M.gap;
  const yc = (v: number) => b0 + BOT_H - (v / Math.max(1, denominator)) * BOT_H;
  const rainPath = points
    .map((p, i) => (p.rain_mm_without_cover_median === null ? null : `${x(i)},${yr(p.rain_mm_without_cover_median)}`))
    .filter(Boolean)
    .join(" ");
  const stepPath = points
    .map((p, i) => {
      const v = p.checks_count ?? 0;
      return i === 0 ? `M${x(i)},${yc(v)}` : `H${x(i)}V${yc(v)}`;
    })
    .join("");
  const ticksX = points.map((p, i) => ({ p, i })).filter(({ p }) => p.terminate.endsWith("-01") || p.terminate.endsWith("-15"));
  const cx = x(rye.index);
  const bx = rye.boundaryIndex !== null ? (x(rye.boundaryIndex) + x(Math.min(n - 1, rye.boundaryIndex + 1))) / 2 : null;
  const first = points[0]!;
  const last = points[n - 1]!;

  return (
    <figure className="curve" aria-labelledby="curve-title">
      <figcaption>
        <h3 id="curve-title" className="chart-title">
          The trade-off across every end date
        </h3>
      </figcaption>
      <div className="chart-scroll">
        <svg
          className="chart-svg"
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`Two charts sharing end dates from ${monthDay(first.terminate)} to ${monthDay(last.terminate)}. Top: median winter rain on ground with no living cover. Bottom: springs with a field-moisture check, out of ${denominator}.`}
          onClick={(e) => {
            const svg = e.currentTarget;
            const r = svg.getBoundingClientRect();
            const px = ((e.clientX - r.left) / r.width) * W;
            const i = Math.round(((px - M.l) / (W - M.l - M.r)) * (n - 1));
            if (i >= 0 && i < n) onChoose(i);
          }}
        >
          <text className="curve-panel" x={M.l} y={M.t - 2}>
            Winter rain on ground with no living cover (median mm)
          </text>
          {[0, rTop / 2, rTop].map((t) => (
            <g key={`r${t}`}>
              <line className="chart-grid" x1={M.l} x2={W - M.r} y1={yr(t)} y2={yr(t)} />
              <text className="chart-tick" x={M.l - 6} y={yr(t) + 4} textAnchor="end">
                {t}
              </text>
            </g>
          ))}
          <polyline className="curve-rain" points={rainPath} />

          <text className="curve-panel" x={M.l} y={b0 - 6}>
            Springs with a field-moisture check (of {denominator})
          </text>
          {[0, denominator].map((t) => (
            <g key={`c${t}`}>
              <line className="chart-grid" x1={M.l} x2={W - M.r} y1={yc(t)} y2={yc(t)} />
              <text className="chart-tick" x={M.l - 6} y={yc(t) + 4} textAnchor="end">
                {t}
              </text>
            </g>
          ))}
          <path className="curve-step" d={stepPath} />

          {ticksX.map(({ p, i }) => (
            <text key={p.terminate} className="chart-year" x={x(i)} y={H - 8} textAnchor="middle">
              {monthDay(p.terminate)}
            </text>
          ))}

          {bx !== null ? (
            <g>
              <line className="curve-boundary" x1={bx} x2={bx} y1={M.t} y2={b0 + BOT_H} />
              <text className="chart-ref chart-ref-check" x={bx + 6} y={M.t + 14}>
                14 days before planting
              </text>
            </g>
          ) : null}
          <line className="curve-chosen" x1={cx} x2={cx} y1={M.t} y2={b0 + BOT_H} />
          {rye.chosen.rain_mm_without_cover_median !== null ? (
            <circle className="curve-dot" cx={cx} cy={yr(rye.chosen.rain_mm_without_cover_median)} r={5} />
          ) : null}
          <circle className="curve-dot" cx={cx} cy={yc(rye.chosen.checks_count ?? 0)} r={5} />
        </svg>
      </div>
      <p className="chart-summary">
        Ending rye on or before {rye.boundaryIndex !== null ? monthDay(points[rye.boundaryIndex]!.terminate) : "the 14-day date"} keeps at
        least 14 days before planting, so the check stays clear in every spring; later dates would have needed it in{" "}
        {points[n - 1]!.checks_count ?? "—"} of {denominator}. Median winter rain on uncovered ground is{" "}
        {first.rain_mm_without_cover_median?.toFixed(1) ?? "—"} mm if rye ends {monthDay(first.terminate)} and{" "}
        {last.rain_mm_without_cover_median?.toFixed(1) ?? "—"} mm if it ends {monthDay(last.terminate)}. Click the chart to pick a
        date.
      </p>
    </figure>
  );
}
