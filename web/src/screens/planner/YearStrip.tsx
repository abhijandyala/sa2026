import { useEffect, useRef } from "react";
import { historicalWindow, mm, monthDay, wetness } from "../../data/format";
import type { ViewModel } from "../../view/build";
import { YearTile } from "../../ui/components";

/*
  The weather control (cards 1.2 and 3.1). Changing the year changes weather only.
  Arrow keys move along the strip; the selected year stays in view on a phone.
*/
export function YearStrip({ view, onSelect }: { view: ViewModel; onSelect: (year: number) => void }) {
  const stripRef = useRef<HTMLDivElement>(null);
  const keyboardMove = useRef(false);
  const selected = view.selectedYear?.year ?? null;
  const first = view.tiles[0]?.year;
  const last = view.tiles[view.tiles.length - 1]?.year;

  useEffect(() => {
    const strip = stripRef.current;
    const tile = strip?.querySelector<HTMLElement>(".year-tile.is-selected");
    if (keyboardMove.current) {
      keyboardMove.current = false;
      tile?.focus();
    }
    if (!strip || !tile || strip.scrollWidth <= strip.clientWidth) return;
    strip.scrollLeft = tile.offsetLeft - strip.clientWidth / 2 + tile.offsetWidth / 2;
  }, [selected, view.window?.id]);

  const move = (dir: number) => {
    const i = view.tiles.findIndex((t) => t.year === selected);
    const next = view.tiles[Math.min(view.tiles.length - 1, Math.max(0, i + dir))];
    if (next && next.year !== selected) {
      keyboardMove.current = true;
      onSelect(next.year);
    }
  };

  const y = view.selectedYear;
  const plant = view.window ? monthDay(view.window.plant) : "planting";

  return (
    <section className="strip" aria-labelledby="strip-title">
      <div className="strip-head">
        <div>
          <h2 id="strip-title" className="strip-title">
            Change the weather: pick a past spring
          </h2>
          <p className="strip-context">
            {view.windowLabel} ({plant}) · {first}–{last} · historical replay, not a forecast
          </p>
        </div>
        <div className="strip-shortcuts" role="group" aria-label="Jump to a year">
          {view.shortcuts.typical !== null ? (
            <button type="button" className="btn btn-secondary btn-small" onClick={() => onSelect(view.shortcuts.typical!)}>
              Typical spring ({view.shortcuts.typical})
            </button>
          ) : null}
          {view.shortcuts.dry !== null ? (
            <button type="button" className="btn btn-secondary btn-small" onClick={() => onSelect(view.shortcuts.dry!)}>
              Dry spring ({view.shortcuts.dry})
            </button>
          ) : null}
        </div>
      </div>

      {view.tiles.length ? (
        <div
          className="strip-tiles"
          role="group"
          aria-label="Past springs. Use the arrow keys to move between years."
          ref={stripRef}
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
          {view.tiles.map((t) => (
            <YearTile
              key={t.year}
              year={t.year}
              pctRank={t.percentile === null ? null : t.percentile / 100}
              complete={t.status === "complete"}
              selected={t.selected}
              marker={t.marker === "dry" ? "dry-replay" : t.marker}
              onSelect={() => onSelect(t.year)}
              description={t.description}
            />
          ))}
        </div>
      ) : (
        <p className="strip-empty">Year-by-year results are not available from the service yet. Plan comparisons below still work.</p>
      )}

      <div className="strip-foot">
        <p className="strip-summary" aria-live="polite">
          {y ? (
            y.status === "complete" ? (
              <>
                <strong>Spring {y.year}</strong> · {y.totalMm === 0 ? "0.0 mm (no rain)" : mm(y.totalMm)} in the 30 days before {plant} (
                {historicalWindow(y.window)}) · regional estimate
                {view.labelsWithheld ? null : (
                  <>
                    {y.isDry ? " · one of the driest 20% on record here" : ""} · rank {y.rank} of {y.of} (1 = driest)
                  </>
                )}{" "}
                · modeled soil wetness {y.wetnessRoot === null ? "not available" : wetness(y.wetnessRoot)}
              </>
            ) : y.status === "partial" ? (
              <>
                <strong>Spring {y.year}</strong> · Incomplete weather record for this window, so it is not compared.
              </>
            ) : (
              <>
                <strong>Spring {y.year}</strong> · No weather record for this window. Plan dates can still be compared.
              </>
            )
          ) : (
            "Not enough complete years to compare."
          )}
        </p>
        {view.labelsWithheld && view.tiles.length ? (
          <p className="strip-dry">Fewer than 15 springs have complete records, so typical, dry and rank labels are withheld.</p>
        ) : view.contrastWithheld && view.tiles.length ? (
          <p className="strip-dry">These springs offer no meaningful dry contrast, so no dry replay year is marked.</p>
        ) : null}
        {view.window && view.window.dry_count !== null && !view.labelsWithheld ? (
          <p className="strip-dry tabular">
            Dry windows (driest 20%): {view.window.dry_count} of {view.window.denominator} springs
            {view.windowEra ? (
              <>
                {" "}
                · {view.windowEra.earlier.label}: {view.windowEra.earlier.count} of {view.windowEra.earlier.denominator} ·{" "}
                {view.windowEra.recent.label}: {view.windowEra.recent.count} of {view.windowEra.recent.denominator}
              </>
            ) : null}
          </p>
        ) : null}
        <p className="strip-legend" aria-hidden="true">
          <span className="legend-swatch legend-dry" /> paler = drier <span className="legend-mark legend-typical" /> typical{" "}
          <span className="legend-mark legend-dryrep" /> dry replay
        </p>
      </div>
    </section>
  );
}
