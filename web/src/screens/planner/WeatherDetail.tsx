import { useEffect, useRef } from "react";
import { historicalDate, historicalWindow, mm, monthDay, wetness as fmtWet } from "../../data/format";
import type { ReplayState } from "../../state/useData";
import type { ViewModel } from "../../view/build";

/*
  Past springs in detail (cards 3.3 and 3.4). Hand-drawn SVG from the design tokens:
  - every complete spring as a bar on one fixed axis, zero baseline, labeled median and
    dry cutoff (playbook p.42, handbook p.11), with a table version and a text summary;
  - the selected spring day by day, from the backend's replay;
  - modeled soil wetness for every spring, labeled as modeled, not a field measurement.
  Missing values are gaps with a note, never zero-height bars.
*/

export function WeatherDetail({
  view,
  replay,
  onSelectYear,
}: {
  view: ViewModel;
  replay: ReplayState;
  onSelectYear: (year: number) => void;
}) {
  const plant = view.window ? monthDay(view.window.plant) : "planting";
  return (
    <section className="detail" aria-labelledby="detail-title">
      <div className="detail-head">
        <h2 id="detail-title" className="section-title">
          Past springs in detail
        </h2>
        <p className="detail-sub">
          Historical replay · {view.windowLabel} ({plant}) · regional estimate near {view.locationLabel.replace(/\s*\(sample\)$/i, "")} ·
          NASA POWER
        </p>
      </div>
      <div className="detail-grid">
        <div className="detail-main">
          <RainfallChart view={view} onSelectYear={onSelectYear} />
          <DailyRain replay={replay} />
        </div>
        <WetnessPanel view={view} replay={replay} />
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- rainfall by year */

const CW = 900;
const CH = 240;
const M = { l: 44, r: 12, t: 14, b: 30 };

function RainfallChart({ view, onSelectYear }: { view: ViewModel; onSelectYear: (y: number) => void }) {
  const { chart, selectedYear } = view;
  const n = chart.bars.length;
  const scrollRef = useRef<HTMLDivElement>(null);
  const selIndex = chart.bars.findIndex((b) => b.selected);

  // On a phone the chart scrolls sideways; keep the selected spring in view.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || el.scrollWidth <= el.clientWidth || selIndex < 0) return;
    const frac = (M.l + ((selIndex + 0.5) / n) * (CW - M.l - M.r)) / CW;
    el.scrollLeft = frac * el.scrollWidth - el.clientWidth / 2;
  }, [selIndex, n]);
  if (!n) {
    return <p className="chart-empty">Year-by-year rainfall is not available from the service yet.</p>;
  }
  const pw = CW - M.l - M.r;
  const ph = CH - M.t - M.b;
  const slot = pw / n;
  const bw = Math.max(4, slot * 0.72);
  const y = (v: number) => M.t + ph - (v / chart.axisMax) * ph;
  const ticks = Array.from({ length: Math.round(chart.axisMax / chart.axisStep) + 1 }, (_, i) => i * chart.axisStep);
  const first = chart.bars[0]!.year;
  const sel = chart.bars.find((b) => b.selected);

  const summary = selectedYear
    ? selectedYear.status !== "complete"
      ? `Spring ${selectedYear.year} has no complete record for this window, so it is left out.`
      : `Spring ${selectedYear.year}: ${mm(selectedYear.totalMm)}` +
        (view.labelsWithheld
          ? ". Relative labels are withheld because fewer than 15 springs have complete records."
          : `, rank ${selectedYear.rank} of ${selectedYear.of} (1 = driest)${selectedYear.isDry ? ", at or below the dry cutoff" : ""}. ` +
            `Median ${mm(chart.medianMm)}; dry cutoff ${mm(chart.cutoffMm)} (driest 20% of complete springs).`)
    : "No spring selected.";

  return (
    <figure className="chart" aria-labelledby="rain-chart-title">
      <figcaption>
        <h3 id="rain-chart-title" className="chart-title">
          Rainfall in the 30 days before planting (mm)
        </h3>
      </figcaption>
      <div className="chart-scroll" ref={scrollRef}>
      <svg
        className="chart-svg"
        viewBox={`0 0 ${CW} ${CH}`}
        role="img"
        aria-label={`Bar chart of rainfall in the 30 days before planting for each spring. ${summary}`}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line className="chart-grid" x1={M.l} x2={CW - M.r} y1={y(t)} y2={y(t)} />
            <text className="chart-tick" x={M.l - 6} y={y(t) + 4} textAnchor="end">
              {t}
            </text>
          </g>
        ))}
        {chart.bars.map((b, i) => {
          const x = M.l + i * slot + (slot - bw) / 2;
          const label = (b.year - first) % 5 === 0 || b.selected;
          return (
            <g key={b.year} className="chart-bar-group" onClick={() => onSelectYear(b.year)}>
              <rect className="chart-hit" x={M.l + i * slot} y={M.t} width={slot} height={ph} />
              {b.mm === null ? (
                <text className="chart-missing" x={x + bw / 2} y={y(0) - 4} textAnchor="middle">
                  ×
                </text>
              ) : (
                <rect
                  className={`chart-bar${b.selected ? " is-selected" : ""}`}
                  x={x}
                  y={y(b.mm)}
                  width={bw}
                  height={Math.max(b.mm > 0 ? 1 : 0, y(0) - y(b.mm))}
                  rx={1.5}
                />
              )}
              {label ? (
                <text className={`chart-year${b.selected ? " is-selected" : ""}`} x={x + bw / 2} y={CH - 10} textAnchor="middle">
                  {b.selected ? b.year : `’${String(b.year).slice(2)}`}
                </text>
              ) : null}
            </g>
          );
        })}
        <line className="chart-axis" x1={M.l} x2={CW - M.r} y1={y(0)} y2={y(0)} />
        {chart.medianMm !== null ? (
          <g>
            <line className="chart-median" x1={M.l} x2={CW - M.r} y1={y(chart.medianMm)} y2={y(chart.medianMm)} />
            <text className="chart-ref" x={CW - M.r} y={y(chart.medianMm) - 5} textAnchor="end">
              Median {chart.medianMm.toFixed(1)} mm
            </text>
          </g>
        ) : null}
        {chart.cutoffMm !== null ? (
          <g>
            <line className="chart-cutoff" x1={M.l} x2={CW - M.r} y1={y(chart.cutoffMm)} y2={y(chart.cutoffMm)} />
            <text className="chart-ref chart-ref-cutoff" x={M.l + 6} y={y(chart.cutoffMm) - 5}>
              Dry cutoff {chart.cutoffMm.toFixed(1)} mm (driest 20%)
            </text>
          </g>
        ) : null}
        {sel && sel.mm !== null ? (
          <text className="chart-value" x={M.l + chart.bars.indexOf(sel) * slot + slot / 2} y={y(sel.mm) - 6} textAnchor="middle">
            {sel.mm.toFixed(1)}
          </text>
        ) : null}
      </svg>
      </div>
      <p className="chart-summary" aria-live="polite">
        {summary}
        {chart.excluded.length ? ` Left out for incomplete records: ${chart.excluded.join(", ")} (shown as ×).` : ""}
      </p>
      <details className="chart-table">
        <summary>Show the numbers as a table</summary>
        <div className="table-scroll">
          <table>
            <caption className="visually-hidden">Rainfall in the 30 days before planting, by spring</caption>
            <thead>
              <tr>
                <th scope="col">Spring</th>
                <th scope="col">Dates</th>
                <th scope="col">Rain (mm)</th>
                <th scope="col">Rank (1 = driest)</th>
                <th scope="col">Driest 20%</th>
                <th scope="col">Soil wetness (modeled)</th>
              </tr>
            </thead>
            <tbody>
              {(view.window?.years ?? []).map((r) => (
                <tr key={r.year} aria-current={r.year === selectedYear?.year ? "true" : undefined}>
                  <th scope="row">{r.year}</th>
                  <td>{historicalWindow([r.start, r.end])}</td>
                  <td className="num">{r.status === "complete" ? r.total_mm?.toFixed(1) : "Not complete"}</td>
                  <td className="num">{view.labelsWithheld || r.rank === null ? "—" : r.rank}</td>
                  <td>{view.labelsWithheld || r.is_dry === null ? "—" : r.is_dry ? "Yes" : "No"}</td>
                  <td className="num">{fmtWet(r.gwetroot_window_mean)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

/* ---------------------------------------------------------------- the selected spring, day by day */

const DW = 900;
const DH = 170;
const DM = { l: 44, r: 44, t: 12, b: 26 };

function DailyRain({ replay }: { replay: ReplayState }) {
  if (replay.status === "idle") return null;
  if (replay.status === "loading") {
    return (
      <div className="daily daily-loading" aria-busy="true">
        Loading daily values for {replay.year}…
      </div>
    );
  }
  if (replay.status === "error") {
    return (
      <div className="daily daily-error" role="status">
        Daily values for {replay.year} are not available right now. The yearly comparison above still applies.
      </div>
    );
  }
  const r = replay.data;
  const days = r.daily;
  if (!days.length) return null;
  const valid = days.filter((d) => d.precip_mm !== null).length;
  const peak = Math.max(10, ...days.map((d) => d.precip_mm ?? 0));
  const step = peak <= 20 ? 5 : peak <= 50 ? 10 : 25;
  const top = Math.ceil(peak / step) * step;
  const pw = DW - DM.l - DM.r;
  const ph = DH - DM.t - DM.b;
  const slot = pw / days.length;
  const bw = slot * 0.7;
  const y = (v: number) => DM.t + ph - (v / top) * ph;
  const yw = (v: number) => DM.t + ph - v * ph;
  const wetPts = days
    .map((d, i) => (d.gwetroot == null ? null : `${DM.l + i * slot + slot / 2},${yw(d.gwetroot)}`))
    .filter(Boolean)
    .join(" ");
  const ticks = Array.from({ length: top / step + 1 }, (_, i) => i * step);
  const win = r.dates.spring_window;

  return (
    <figure className="daily" aria-labelledby="daily-title">
      <figcaption className="daily-head">
        <h3 id="daily-title" className="chart-title">
          Spring {r.year}, day by day
        </h3>
        <p className="daily-sub">
          {historicalWindow([win.start, win.end])} · total {mm(r.spring.total_mm)} · {valid} of {days.length} days with a value
        </p>
      </figcaption>
      <div className="chart-scroll">
      <svg
        className="chart-svg"
        viewBox={`0 0 ${DW} ${DH}`}
        role="img"
        aria-label={`Daily rain from ${historicalDate(win.start)} to ${historicalDate(win.end)}, total ${mm(r.spring.total_mm)}. Line: modeled root-zone soil wetness from 0 to 1.`}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line className="chart-grid" x1={DM.l} x2={DW - DM.r} y1={y(t)} y2={y(t)} />
            <text className="chart-tick" x={DM.l - 6} y={y(t) + 4} textAnchor="end">
              {t}
            </text>
          </g>
        ))}
        {[0, 0.5, 1].map((t) => (
          <text key={t} className="chart-tick chart-tick-wet" x={DW - DM.r + 6} y={yw(t) + 4}>
            {t}
          </text>
        ))}
        {days.map((d, i) => {
          const x = DM.l + i * slot + (slot - bw) / 2;
          const last = days.length - 1;
          const showDate = i === 0 || i === last || (i % 7 === 0 && last - i >= 4);
          return (
            <g key={d.date}>
              {d.precip_mm === null ? (
                <text className="chart-missing" x={x + bw / 2} y={y(0) - 4} textAnchor="middle">
                  ×
                </text>
              ) : d.precip_mm > 0 ? (
                <rect className="chart-bar daily-bar" x={x} y={y(d.precip_mm)} width={bw} height={y(0) - y(d.precip_mm)} rx={1} />
              ) : null}
              {showDate ? (
                <text className="chart-year" x={x + bw / 2} y={DH - 8} textAnchor="middle">
                  {monthDay(d.date.slice(5))}
                </text>
              ) : null}
            </g>
          );
        })}
        <line className="chart-axis" x1={DM.l} x2={DW - DM.r} y1={y(0)} y2={y(0)} />
        {wetPts ? <polyline className="daily-wet" points={wetPts} /> : null}
      </svg>
      </div>
      <p className="daily-key">
        <span className="key-item">
          <span className="key-bar" /> Daily rain (mm, left axis)
        </span>
        <span className="key-item">
          <span className="key-line" /> Modeled root-zone soil wetness (0 dry to 1 saturated, right axis)
        </span>
        {r.daily_scope === "spring_window" ? <span className="key-item">Sample shows the 30-day window only</span> : null}
      </p>
      {r.checks_triggered.length ? (
        <p className="daily-check">
          <strong>Why the check appeared:</strong> {r.checks_triggered.map((c) => c.reason).join("; ")}.
        </p>
      ) : null}
    </figure>
  );
}

/* ---------------------------------------------------------------- soil wetness, every spring */

const WW = 320;
const WH = 64;

function WetnessPanel({ view, replay }: { view: ViewModel; replay: ReplayState }) {
  const { wetness, selectedYear } = view;
  const x = (v: number) => 12 + v * (WW - 24);
  const label = replay.status === "ready" ? replay.data.wetness.label : "modeled";
  return (
    <aside className="wetness" aria-labelledby="wet-title">
      <h3 id="wet-title" className="chart-title">
        Soil wetness, {label}
      </h3>
      <p className="wet-value">
        {selectedYear ? (
          wetness.selected === null ? (
            <>Not available for {selectedYear.year}.</>
          ) : (
            <>
              <strong className="tabular">{fmtWet(wetness.selected)}</strong> in spring {selectedYear.year}
            </>
          )
        ) : (
          "No spring selected."
        )}
      </p>
      {wetness.points.length ? (
        <svg className="wet-svg" viewBox={`0 0 ${WW} ${WH}`} role="img" aria-label={`Root-zone soil wetness for ${wetness.points.length} springs on a scale from 0, dry, to 1, saturated.`}>
          <line className="chart-axis" x1={12} x2={WW - 12} y1={32} y2={32} />
          {wetness.points
            .filter((p) => !p.selected)
            .map((p) => (
              <circle key={p.year} className="wet-dot" cx={x(p.value)} cy={32} r={4} />
            ))}
          {wetness.points
            .filter((p) => p.selected)
            .map((p) => (
              <g key={p.year}>
                <circle className="wet-dot is-selected" cx={x(p.value)} cy={32} r={7} />
                <text className="chart-value" x={x(p.value)} y={16} textAnchor="middle">
                  {p.year}
                </text>
              </g>
            ))}
          <text className="chart-tick" x={12} y={56}>
            0 dry
          </text>
          <text className="chart-tick" x={WW - 12} y={56} textAnchor="end">
            1 saturated
          </text>
        </svg>
      ) : null}
      <p className="wet-note">
        Each dot is one spring's average over the same 30 days. Root-zone wetness from NASA POWER (MERRA-2 model), a regional
        estimate, not a reading from your field.
      </p>
      {wetness.missingYears.length ? <p className="wet-note">Not available for {wetness.missingYears.join(", ")}.</p> : null}
      <p className="wet-note">
        <strong>Satellite and model vs. your field:</strong> these values describe the region around the grid point. A soil check in
        your own field tells you what your seedbed is like this year.
      </p>
    </aside>
  );
}
