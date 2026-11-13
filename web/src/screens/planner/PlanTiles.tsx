import type { CardKey } from "../../content/strategies";
import type { CardVM } from "../../view/build";
import { StatusPill } from "../../ui/components";
import { Roll } from "../../ui/Roll";

/*
  The three plans as number tiles across the top of the dashboard: one number each, with
  the sentence that explains it. Picking a tile picks the plan everywhere on the page.
*/
export function PlanTiles({ cards, selected, onSelect }: { cards: CardVM[]; selected: CardKey; onSelect: (k: CardKey) => void }) {
  // Display scaling only: the largest backend value sets the longest bar.
  const axisMax = Math.max(0, ...cards.map((c) => c.legs.find((l) => l.selected)?.soilMm ?? 0));
  return (
    <ol className="db-tiles" aria-label="The three plans">
      {cards.map((c) => {
        const leg = c.legs.find((l) => l.selected);
        const on = c.key === selected;
        return (
          <li key={c.key}>
            <button type="button" className={`db-tile${on ? " is-selected" : ""}`} aria-pressed={on} onClick={() => onSelect(c.key)}>
              <span className="db-tile-name">{c.content.name}</span>
              {leg?.available && leg.soilMm !== null ? (
                <span className="db-tile-fact">
                  <span className="db-tile-num">
                    <Roll value={leg.soilMm.toFixed(0)} />
                    <span className="db-tile-unit"> mm</span>
                  </span>
                  <span className="db-tile-cap">winter rain with nothing growing</span>
                  <span className="ws-bar" aria-hidden="true">
                    <span style={{ width: `${axisMax > 0 ? Math.max(1.5, (leg.soilMm / axisMax) * 100) : 0}%` }} />
                  </span>
                </span>
              ) : (
                <span className="db-tile-fact">
                  <span className="db-tile-num db-tile-na">Not evaluated yet</span>
                </span>
              )}
              <span className="db-tile-pills">
                {leg?.check.applies ? (
                  <StatusPill kind="check">
                    Check soil moisture in {leg.check.count} of {leg.check.denominator} springs
                  </StatusPill>
                ) : null}
                {c.priorityFits.map((f) => (
                  <StatusPill key={f.priority} kind={f.fit === "matches" ? "ok" : f.fit === "partly" ? "unavailable" : "check"}>
                    <span className="visually-hidden">{f.fit === "matches" ? "Matches" : f.fit === "partly" ? "Partly matches" : "Trade-off"}: </span>
                    {f.label}
                  </StatusPill>
                ))}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
