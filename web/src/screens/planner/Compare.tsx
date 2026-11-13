import { useState } from "react";
import type { CardKey } from "../../content/strategies";
import type { CardVM } from "../../view/build";
import { WinterCell } from "./WinterCell";
import { WinterZoom } from "./WinterZoom";

/*
  Compare page: the three plans side by side, as pictures (redesigned Nov 13).
  Each cell is one winter of one plan: a rain glass with the backend's number, then the
  field seen from the side with the season running left to right. Blue rain marks the
  stretches with nothing growing. Each winter is its own row and the two are never added.
  The glasses share one scale, so their fill levels can be compared.
*/
export function Compare({
  cards,
  selected,
  selectedYear,
  onSelect,
  onOpen,
  onPickYear,
  onWhy,
}: {
  cards: CardVM[];
  selected: CardKey;
  selectedYear: number | null;
  onSelect: (k: CardKey) => void;
  onOpen: (k: CardKey) => void;
  onPickYear: (year: number, leg: 1 | 2, card: CardKey) => void;
  onWhy: (kind: "rain" | "check", leg: 1 | 2, card: CardKey) => void;
}) {
  // Display scaling only: the largest backend value fills its glass to the top.
  const axisMax = Math.max(0, ...cards.flatMap((c) => c.legs.map((l) => l.soilMm ?? 0)));
  const winters = [0, 1];
  // The picture that is open large, and where its small version sits on screen.
  const [zoom, setZoom] = useState<{ card: CardKey; leg: number; from: DOMRect } | null>(null);
  const zoomCard = zoom ? cards.find((c) => c.key === zoom.card) : undefined;
  const zoomLeg = zoom ? zoomCard?.legs[zoom.leg] : undefined;
  return (
    <section className="db-card cmp" aria-labelledby="cmp-title">
      <header className="db-card-head">
        <h2 id="cmp-title">Winter rain with nothing growing, by plan</h2>
        <p className="cmp-key" aria-hidden="true">
          <span className="cmp-key-rain" /> rain with nothing growing
          <span className="cmp-key-live" /> crop or cover growing
          <span className="cmp-key-note">Illustration of planned dates</span>
        </p>
      </header>

      <div className="cmp-grid" role="table" aria-label="Plans by winter">
        <div className="cmp-row cmp-head" role="row">
          <span role="columnheader" className="cmp-corner" />
          {cards.map((c) => (
            <div key={c.key} role="columnheader" className={`cmp-plan${c.key === selected ? " is-selected" : ""}`}>
              <button type="button" className="cmp-plan-pick" aria-pressed={c.key === selected} onClick={() => onSelect(c.key)}>
                {c.content.name}
              </button>
              <button type="button" className="cmp-plan-open" onClick={() => onOpen(c.key)} aria-label={`Open the plan: ${c.content.name}`}>
                Open plan
                <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                  <path d="M4.5 2.5L8 6l-3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          ))}
        </div>
        {winters.map((w) => (
          <div className="cmp-row" role="row" key={w}>
            <div role="rowheader" className="cmp-winter">
              <span className="cmp-winter-name">Winter {w + 1}</span>
              <span className="cmp-winter-sub">{w === 0 ? "after corn" : "after soybeans"}</span>
            </div>
            {cards.map((c) => (
              <div role="cell" key={c.key} className={`cmp-cell${c.key === selected ? " is-selected" : ""}`}>
                <WinterCell
                  planName={c.content.name}
                  onZoom={(from) => setZoom({ card: c.key, leg: w, from })}
                  leg={c.legs[w]!}
                  axisMax={axisMax}
                  selectedYear={selectedYear}
                  onPickYear={(year, leg) => onPickYear(year, leg, c.key)}
                  onWhy={(kind, leg) => onWhy(kind, leg, c.key)}
                />
              </div>
            ))}
          </div>
        ))}
      </div>
      {zoom && zoomCard && zoomLeg ? (
        <WinterZoom planName={zoomCard.content.name} leg={zoomLeg} axisMax={axisMax} from={zoom.from} onClose={() => setZoom(null)} />
      ) : null}
    </section>
  );
}
