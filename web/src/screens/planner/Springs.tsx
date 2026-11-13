import { useEffect, useRef, type ReactNode } from "react";
import { historicalWindow, mm, wetness } from "../../data/format";
import type { ViewModel } from "../../view/build";
import { Roll } from "../../ui/Roll";
import { G } from "../../ui/Glossary";

/*
  Past springs, as pictures a grower already knows (Nov 13):
  - the fields on the 3D stage, under the chosen spring's rain;
  - three rain gauges for the springs worth a look (typical, dry, wet);
  - every spring since 1981 as one small gauge: fuller means more rain, a ring marks one
    of the driest. No bar chart. Picking a spring changes the weather only.
  Fill heights are the backend's totals scaled to the tallest; nothing is computed.
*/
export function Springs({ view, stage, onSelect }: { view: ViewModel; stage: ReactNode; onSelect: (year: number) => void }) {
  const rowRef = useRef<HTMLDivElement>(null);
  const keyboardMove = useRef(false);
  const { chart, shortcuts } = view;
  const y = view.selectedYear;
  const selected = y?.year ?? null;
  const tileByYear = new Map(view.tiles.map((t) => [t.year, t]));
  const barByYear = new Map(chart.bars.map((b) => [b.year, b]));
  const first = chart.bars[0]?.year;
  const last = chart.bars[chart.bars.length - 1]?.year;

  useEffect(() => {
    if (!keyboardMove.current) return;
    keyboardMove.current = false;
    rowRef.current?.querySelector<HTMLElement>(".sp-drop.is-selected")?.focus();
  }, [selected]);

  const move = (dir: number) => {
    const i = chart.bars.findIndex((b) => b.year === selected);
    const next = chart.bars[Math.min(chart.bars.length - 1, Math.max(0, i + dir))];
    if (next && next.year !== selected) {
      keyboardMove.current = true;
      onSelect(next.year);
    }
  };

  // Display scaling only: the backend's total as a share of the largest value on the chart.
  const frac = (v: number | null) => (v === null ? 0 : Math.max(0, Math.min(1, v / chart.axisMax)));

  const named: Array<{ id: string; label: string; year: number | null }> = [
    { id: "typical", label: "Typical", year: shortcuts.typical },
    { id: "dry", label: "Dry", year: shortcuts.dry },
    { id: "wet", label: "Wet", year: shortcuts.wet },
  ];
  const isNamed = named.some((n) => n.year !== null && n.year === selected);
  const gauges = [...named.filter((n) => n.year !== null), ...(selected !== null && !isNamed ? [{ id: "picked", label: "Picked", year: selected }] : [])];
  const era = view.windowEra;

  return (
    <section className="db-card fb-springs" aria-labelledby="springs-title">
      <header className="db-card-head">
        <h2 id="springs-title">
          {y ? `Spring ${y.year} on your field` : "Past springs"}
        </h2>
        <p className="sp-key">
          Rain in the 30 days before planting · a <G id="replay">replay</G>, not a forecast
        </p>
      </header>

      <div className="sp-hero">
        <div className="sp-stage">{stage}</div>

        <div className="sp-side">
          <div className="sp-gauges" role="group" aria-label="Springs worth a look">
            {gauges.map((n) => {
              const b = barByYear.get(n.year!);
              const on = n.year === selected;
              return (
                <button key={n.id} type="button" className={`sp-gauge${on ? " is-on" : ""}`} aria-pressed={on} onClick={() => onSelect(n.year!)}>
                  <span className="sp-tube" aria-hidden="true">
                    <span style={{ height: `${frac(b?.mm ?? null) * 100}%` }} />
                  </span>
                  <span className="sp-gauge-name">{n.label}</span>
                  <span className="sp-gauge-year tabular">{n.year}</span>
                  <span className="sp-gauge-mm tabular">{b && b.mm !== null ? mm(b.mm) : "No record"}</span>
                </button>
              );
            })}
          </div>

          {y && y.status === "complete" ? (
            <div className="sp-now" aria-live="polite">
              <p className="sp-fact">
                <Roll value={y.totalMm === null ? "0.0" : y.totalMm.toFixed(1)} className="sp-fact-num" />
                <span className="sp-fact-unit">mm of rain</span>
              </p>
              <p className="sp-fact-text">
                {historicalWindow(y.window)} · <G id="regional-estimate">regional estimate</G>
                {y.isDry && !view.labelsWithheld ? " · one of the driest here" : ""}
              </p>
              <div className="sp-meters">
                {y.rank !== null && y.of !== null && y.of > 1 && !view.labelsWithheld ? (
                  <div className="sp-meter">
                    <span className="sp-meter-label">
                      Rank {y.rank} of {y.of}
                    </span>
                    <span className="sp-meter-track sp-meter-rank" aria-hidden="true">
                      <span className="sp-meter-pin" style={{ left: `${((y.rank - 1) / (y.of - 1)) * 100}%` }} />
                    </span>
                    <span className="sp-meter-ends" aria-hidden="true">
                      <span>Driest</span>
                      <span>Wettest</span>
                    </span>
                  </div>
                ) : null}
                {y.wetnessRoot !== null ? (
                  <div className="sp-meter">
                    <span className="sp-meter-label">
                      <G id="soil-wetness">Modeled soil wetness</G> {wetness(y.wetnessRoot)}
                    </span>
                    <span className="sp-meter-track" aria-hidden="true">
                      <span className="sp-meter-fill" style={{ width: `${Math.max(0, Math.min(1, y.wetnessRoot)) * 100}%` }} />
                    </span>
                    <span className="sp-meter-ends" aria-hidden="true">
                      <span>Dry</span>
                      <span>Saturated</span>
                    </span>
                  </div>
                ) : null}
              </div>
            </div>
          ) : (
            <p className="sp-fact-text" aria-live="polite">
              {y ? "This spring's weather record is incomplete, so it is not compared." : "Not enough complete years to compare."}
            </p>
          )}
        </div>
      </div>

      {chart.bars.length ? (
        <div className="sp-all">
          <p className="sp-all-title">
            <span>
              Pick any spring to replay it <span className="sp-all-range">{first} to {last}</span>
            </span>
            <span className="sp-key">
              <span className="sp-drop-key" /> fuller is more rain
              <span className="sp-drop-key is-dry" /> {view.window?.dry_count != null ? `one of the ${view.window.dry_count} driest` : "a dry spring"}
            </span>
          </p>
          <div className="sp-drops-row">
            <button type="button" className="sp-step" aria-label="Earlier spring" disabled={selected === first} onClick={() => move(-1)}>
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                <path d="M9 2.5L4.5 7 9 11.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          <div
            className="sp-drops"
            role="group"
            aria-label="Past springs. Use the arrow keys to move between years."
            ref={rowRef}
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
            {chart.bars.map((b, i) => {
              const t = tileByYear.get(b.year);
              const edge = i < 3 ? " is-start" : i > chart.bars.length - 4 ? " is-end" : "";
              const showLabel = b.selected || b.year % 5 === 0 || b.year === first || b.year === last;
              return (
                <button
                  key={b.year}
                  type="button"
                  className={`sp-drop${b.selected ? " is-selected" : ""}${b.isDry ? " is-dry" : ""}${b.mm === null ? " is-missing" : ""}`}
                  aria-pressed={b.selected}
                  aria-label={`${b.year}: ${t?.description ?? (b.mm === null ? "no complete record" : mm(b.mm))}`}
                  tabIndex={b.selected || (selected === null && b.year === first) ? 0 : -1}
                  onClick={() => onSelect(b.year)}
                >
                  <span className={`sp-drop-tip${edge}`} aria-hidden="true">
                    {b.year}
                    {b.mm === null ? "" : ` · ${mm(b.mm)}`}
                  </span>
                  <span className="sp-drop-glass" aria-hidden="true">
                    <span style={{ height: `${frac(b.mm) * 100}%` }} />
                  </span>
                  <span className="sp-drop-year" aria-hidden="true">
                    {showLabel ? (b.selected ? b.year : `'${String(b.year).slice(2)}`) : ""}
                  </span>
                </button>
              );
            })}
          </div>
            <button type="button" className="sp-step" aria-label="Later spring" disabled={selected === last} onClick={() => move(1)}>
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                <path d="M5 2.5L9.5 7 5 11.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>
      ) : (
        <p className="sp-empty">This plan's weather for this winter is not evaluated yet. Pick another plan or winter.</p>
      )}

      {era ? (
        <div className="sp-eras-dots">
          {[era.earlier, era.recent].map((e) => (
            <div className="pd-era-row" key={e.label}>
              <span className="pd-era-label">{e.label}</span>
              <span className="pd-era-dots" aria-hidden="true">
                {Array.from({ length: e.denominator }, (_, i) => (
                  <span key={i} className={`ws-dot${i < e.count ? " is-dry-era" : ""}`} />
                ))}
              </span>
              <span className="tabular">
                {e.count} of {e.denominator} dry
              </span>
            </div>
          ))}
        </div>
      ) : null}
      {view.labelsWithheld && chart.bars.length ? (
        <p className="sp-note">Fewer than 15 springs have complete records, so typical, dry and rank labels are withheld.</p>
      ) : null}
    </section>
  );
}
