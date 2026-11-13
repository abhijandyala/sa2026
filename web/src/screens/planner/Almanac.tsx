import { useEffect, useRef } from "react";
import { historicalWindow, mm, monthDay, wetness } from "../../data/format";
import type { ViewModel } from "../../view/build";
import { Src } from "../../ui/components";
import { G } from "../../ui/Glossary";

/*
  The weather control as an almanac (design direction B): one bar per spring, the dry
  cutoff from the response, the earlier and recent eras underneath, and the selected
  spring called out. Changing the year changes weather only. Arrow keys move between
  years. Bar heights are the backend's totals scaled to the chart; nothing is computed.
*/

/** Height of the dot and year label under each bar, in px (matches .alm-bar in CSS). */
const BELOW = 24;

const yearsOf = (label: string): [number, number] | null => {
  const m = label.match(/(\d{4})\D+(\d{4})/);
  return m ? [Number(m[1]), Number(m[2])] : null;
};

export function Almanac({ view, onSelect }: { view: ViewModel; onSelect: (year: number) => void }) {
  const barsRef = useRef<HTMLDivElement>(null);
  const keyboardMove = useRef(false);
  const selected = view.selectedYear?.year ?? null;
  const { chart } = view;
  const tileByYear = new Map(view.tiles.map((t) => [t.year, t]));
  const first = chart.bars[0]?.year;
  const last = chart.bars[chart.bars.length - 1]?.year;
  const plant = view.window ? monthDay(view.window.plant) : "planting";

  useEffect(() => {
    if (!keyboardMove.current) return;
    keyboardMove.current = false;
    barsRef.current?.querySelector<HTMLElement>(".alm-bar.is-selected")?.focus();
  }, [selected]);

  const move = (dir: number) => {
    const i = chart.bars.findIndex((b) => b.year === selected);
    const next = chart.bars[Math.min(chart.bars.length - 1, Math.max(0, i + dir))];
    if (next && next.year !== selected) {
      keyboardMove.current = true;
      onSelect(next.year);
    }
  };

  // Display scaling only: the backend's total as a share of the chart's axis.
  const frac = (v: number) => Math.max(0, Math.min(1, v / chart.axisMax));
  const y = view.selectedYear;

  // Era rails under the bars, sized by how many springs each covers.
  const earlier = yearsOf(view.eraSpans.earlier);
  const recent = yearsOf(view.eraSpans.recent);
  const inSpan = (s: [number, number] | null) => (s ? chart.bars.filter((b) => b.year >= s[0] && b.year <= s[1]).length : 0);
  const nEarlier = inSpan(earlier);
  const nRecent = inSpan(recent);
  const nGap = Math.max(0, chart.bars.length - nEarlier - nRecent);
  const era = view.windowEra;

  const shortcut = (label: string, year: number | null) =>
    year === null ? null : (
      <button
        type="button"
        className={`btn btn-secondary btn-small${year === selected ? " is-current" : ""}`}
        aria-pressed={year === selected}
        onClick={() => onSelect(year)}
      >
        {label} {year}
      </button>
    );

  return (
    <section className="almanac" aria-labelledby="alm-title">
      <div className="alm-head">
        <div className="alm-title-row">
          <h2 id="alm-title" className="alm-title">
            Pick a past spring
          </h2>
          <p className="alm-key" aria-hidden="true">
            <span className="alm-key-dot" />{" "}
            {view.window?.dry_count != null
              ? `${view.window.dry_count} driest of ${view.window.denominator}`
              : "dry spring"}
            {chart.cutoffMm !== null ? (
              <>
                <span className="alm-key-line" /> cutoff {mm(chart.cutoffMm)}
              </>
            ) : null}
          </p>
        </div>
        <p className="alm-context">
          30 days before {plant} · {first}–{last} · <G id="replay">historical replay</G>
        </p>
      </div>

      <div className="alm-callout" aria-live="polite">
        {y ? (
          y.status === "complete" ? (
            <>
              <p className="alm-year">
                <span className="alm-year-label">Spring {y.year}</span>
                <span className="alm-mm tabular">{y.totalMm === 0 ? "0.0 mm" : mm(y.totalMm)}</span>
                <Src k="nasa" />
              </p>
              <p className="alm-facts tabular">
                {historicalWindow(y.window)} · <G id="regional-estimate">regional estimate</G>
                {view.labelsWithheld ? null : (
                  <>
                    {" "}
                    · <G id="rank">rank</G> {y.rank} of {y.of} (1 = driest)
                  </>
                )}{" "}
                · <G id="soil-wetness">modeled soil wetness</G> {y.wetnessRoot === null ? "not available" : wetness(y.wetnessRoot)}
              </p>
              {y.isDry && !view.labelsWithheld ? (
                <p className="alm-dry">
                  One of the <G id="driest-20">driest 20%</G> of springs on record here
                </p>
              ) : null}
            </>
          ) : (
            <p className="alm-facts">
              <strong>Spring {y.year}</strong> ·{" "}
              {y.status === "partial" ? "Incomplete weather record for this window, so it is not compared." : "No weather record for this window."}
            </p>
          )
        ) : (
          <p className="alm-facts">Not enough complete years to compare.</p>
        )}
      </div>

      {chart.bars.length ? (
        <div className="alm-chart">
          <div
            className="alm-bars"
            role="group"
            aria-label="Past springs. Use the arrow keys to move between years."
            ref={barsRef}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") {
                e.preventDefault();
                move(1);
              } else if (e.key === "ArrowLeft") {
                e.preventDefault();
                move(-1);
              }
            }}
          >
            {chart.cutoffMm !== null ? (
              <div className="alm-cutoff" style={{ bottom: `calc(${BELOW}px + (100% - ${BELOW}px) * ${frac(chart.cutoffMm)})` }} aria-hidden="true">
              </div>
            ) : null}
            {chart.bars.map((b) => {
              const t = tileByYear.get(b.year);
              const label = String(b.year).slice(2);
              const nearSelected = selected !== null && Math.abs(b.year - selected) === 1;
              const showLabel = b.selected || ((b.year % 5 === 0 || b.year === first || b.year === last) && !nearSelected);
              return (
                <button
                  key={b.year}
                  type="button"
                  className={`alm-bar${b.selected ? " is-selected" : ""}${b.isDry ? " is-dry" : ""}${b.mm === null ? " is-missing" : ""}`}
                  aria-pressed={b.selected}
                  aria-label={`${b.year}: ${t?.description ?? (b.mm === null ? "no complete record" : mm(b.mm))}`}
                  tabIndex={b.selected || (selected === null && b.year === first) ? 0 : -1}
                  onClick={() => onSelect(b.year)}
                >
                  <span className="alm-track">
                    <span className="alm-fill" style={{ height: b.mm === null ? "100%" : `${frac(b.mm) * 100}%` }} />
                  </span>
                  <span className="alm-dot" aria-hidden="true" />
                  <span className="alm-label" aria-hidden="true">
                    {showLabel ? `'${label}` : ""}
                  </span>
                </button>
              );
            })}
          </div>
          {era && nEarlier && nRecent ? (
            <div className="alm-eras tabular" aria-label="Dry springs by era">
              <span style={{ flexGrow: nEarlier }}>
                {era.earlier.label}: <strong>{era.earlier.count} of {era.earlier.denominator}</strong> dry
              </span>
              {nGap ? <span className="alm-era-gap" style={{ flexGrow: nGap }} aria-hidden="true" /> : null}
              <span style={{ flexGrow: nRecent }}>
                {era.recent.label}: <strong>{era.recent.count} of {era.recent.denominator}</strong>
                {era.result === "similar" ? " · similar" : ""}
              </span>
            </div>
          ) : null}
        </div>
      ) : (
        <p className="strip-empty">
          This plan's weather for this winter is not evaluated yet. Pick another plan or winter; the comparisons below still work.
        </p>
      )}

      <div className="alm-foot">
        <div className="alm-shortcuts" role="group" aria-label="Jump to a spring">
          {shortcut("Typical", view.shortcuts.typical)}
          {shortcut("Dry", view.shortcuts.dry)}
          {shortcut("Wet", view.shortcuts.wet)}
        </div>
      </div>
      {view.labelsWithheld && chart.bars.length ? (
        <p className="strip-dry">Fewer than 15 springs have complete records, so typical, dry and rank labels are withheld.</p>
      ) : null}
    </section>
  );
}
