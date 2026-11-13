import type { LegSummaryVM } from "../../view/build";
import { Src } from "../../ui/components";
import { Roll } from "../../ui/Roll";

/*
  One winter of one plan as two pictures instead of a table row (design strategy, Nov 13):
  - a rain bar: how much winter rain falls while nothing is growing;
  - a dot grid: one dot per past spring, amber where the moisture check applies.
  The same two pictures are used on the Compare page and the Plan page, so a dot always
  means one spring and a blue bar always means rain. Values are the backend's; the bar
  length and the dot colors only display them.
*/
export function WinterStat({
  leg,
  axisMax,
  selectedYear,
  onPickYear,
  onWhy,
}: {
  leg: LegSummaryVM;
  /** The largest rain value shown on the page, so every bar shares one scale. */
  axisMax: number;
  selectedYear: number | null;
  onPickYear: (year: number, leg: 1 | 2) => void;
  onWhy: (kind: "rain" | "check", leg: 1 | 2) => void;
}) {
  if (!leg.available) {
    return (
      <div className="ws ws-na">
        <p className="ws-na-title">Not evaluated yet</p>
      </div>
    );
  }
  const flagged = new Set(leg.checkYears);
  const width = leg.soilMm === null || axisMax <= 0 ? 0 : Math.max(1.5, Math.min(100, (leg.soilMm / axisMax) * 100));
  return (
    <div className="ws">
      <div className="ws-row">
        <p className="ws-label">Rain with nothing growing</p>
        {leg.soilMm === null ? (
          <p className="ws-none">Not available</p>
        ) : (
          <>
            <button
              type="button"
              className="why-link ws-value"
              onClick={() => onWhy("rain", leg.leg)}
              aria-label={`${leg.soilMm.toFixed(0)} millimeters of winter rain with no living cover, ${leg.title}. How this was worked out`}
            >
              <Roll value={leg.soilMm.toFixed(0)} className="ws-num" />
              <span className="ws-unit"> mm</span>
            </button>
            <Src k={["nasa", "calculated"]} />
            <div className="ws-bar" aria-hidden="true">
              <span style={{ width: `${width}%` }} />
            </div>
          </>
        )}
      </div>

      {leg.check.applies ? (
        <div className="ws-row">
          <p className="ws-label">Springs to check soil moisture</p>
          <>
            <button
              type="button"
              className="why-link ws-value"
              onClick={() => onWhy("check", leg.leg)}
              aria-label={`Field moisture check in ${leg.check.count} of ${leg.check.denominator} springs, ${leg.title}. How this was worked out`}
            >
              <Roll value={String(leg.check.count)} className="ws-num" />
              <span className="ws-unit"> of {leg.check.denominator}</span>
            </button>
            <Src k={["nasa", "ncstate", "calculated"]} />
          </>
          {/* The dots are a picture of the count above and a pointer shortcut to replay a spring. */}
        <div className="ws-dots" aria-hidden="true">
          {leg.springs.map((s) => (
            <button
              key={s.year}
              type="button"
              tabIndex={-1}
              className={`ws-dot${flagged.has(s.year) ? " is-check" : ""}${s.dry ? " is-dry" : ""}${s.complete ? "" : " is-missing"}${s.year === selectedYear && leg.selected ? " is-selected" : ""}`}
              title={`${s.year}${flagged.has(s.year) ? ": check soil moisture" : s.dry ? ": a dry spring" : ""}`}
              onClick={() => onPickYear(s.year, leg.leg)}
            />
          ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function DotKey({ showCheck }: { showCheck: boolean }) {
  return (
    <p className="ws-key" aria-hidden="true">
      <span className="ws-dot" /> one past spring
      {showCheck ? (
        <>
          <span className="ws-dot is-check" /> check soil moisture
        </>
      ) : null}
      <span className="ws-dot is-dry" /> a dry spring
    </p>
  );
}
