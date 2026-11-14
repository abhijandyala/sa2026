import type { ReactNode } from "react";
import type { LegSummaryVM } from "../../view/build";
import { Src } from "../../ui/components";
import { Roll } from "../../ui/Roll";
import { WinterPicture } from "./WinterPicture";

/*
  One winter of one plan, the same on the Compare page and the Plan page: a rain glass
  with the backend's number, the field seen from the side (click to open it large), and,
  where it applies, the soil-moisture check with one dot per past spring.
*/
const sentence = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

export function WinterCell({
  planName,
  onZoom,
  leg,
  axisMax,
  selectedYear,
  onPickYear,
  onWhy,
  caption,
}: {
  /** A short line shown right under the picture (the Plan page puts the winter's dates here). */
  caption?: ReactNode;
  planName: string;
  onZoom: (from: DOMRect) => void;
  leg: LegSummaryVM;
  axisMax: number;
  selectedYear: number | null;
  onPickYear: (year: number, leg: 1 | 2) => void;
  onWhy: (kind: "rain" | "check", leg: 1 | 2) => void;
}) {
  if (!leg.available) {
    // The service gave this plan's dates but no winter figure (wheat): draw the field, state the gap.
    if (leg.plan?.sequence) {
      return (
        <>
          <div className="cmp-fact">
            <span className="cmp-glass is-missing" aria-hidden="true" />
            <span className="cmp-none">No rain figure</span>
          </div>
          <WinterPicture plan={leg.plan} onOpen={onZoom} openLabel={`Open the large picture: ${planName}, winter ${leg.leg}`} />
          {caption}
          {leg.reason ? <p className="cmp-na-why">{sentence(leg.reason)}</p> : null}
        </>
      );
    }
    return (
      <div className="cmp-na">
        <p className="cmp-na-title">Not evaluated yet</p>
        {leg.reason ? <p className="cmp-na-why">{sentence(leg.reason)}</p> : null}
      </div>
    );
  }
  const fill = leg.soilMm === null || axisMax <= 0 ? 0 : Math.max(0, Math.min(1, leg.soilMm / axisMax));
  const flagged = new Set(leg.checkYears);
  const { count, denominator } = leg.check;
  return (
    <>
      <div className="cmp-fact">
        <span className={`cmp-glass has-tip${leg.soilMm === null ? " is-missing" : ""}`} data-tip="Fuller means more rain with nothing growing" aria-hidden="true">
          <span style={{ height: `${fill * 100}%` }} />
        </span>
        {leg.soilMm === null ? (
          <span className="cmp-none">Not available</span>
        ) : (
          <button
            type="button"
            className="why-link cmp-value"
            onClick={() => onWhy("rain", leg.leg)}
            aria-label={`${leg.soilMm.toFixed(0)} millimeters of winter rain with nothing growing, ${leg.title}. How this was worked out`}
          >
            <Roll value={leg.soilMm.toFixed(0)} className="cmp-num" />
            <span className="cmp-unit"> mm</span>
          </button>
        )}
        <Src k={["nasa", "calculated"]} />
      </div>

      {leg.plan ? <WinterPicture plan={leg.plan} onOpen={onZoom} openLabel={`Open the large picture: ${planName}, winter ${leg.leg}`} /> : null}
      {caption}

      {leg.check.applies ? (
        <div className="cmp-check">
          <button
            type="button"
            className="why-link cmp-check-text"
            onClick={() => onWhy("check", leg.leg)}
            aria-label={
              count === null || denominator === null
                ? `Check soil moisture before planting, ${leg.title}. How this was worked out`
                : `Check soil moisture in ${count} of ${denominator} past springs, ${leg.title}. How this was worked out`
            }
          >
            <span className="ws-dot is-check" aria-hidden="true" />
            <span>
              {count === null || denominator === null ? (
                "Check soil moisture before planting"
              ) : (
                <>
                  Check soil moisture in{" "}
                  <strong className="tabular">
                    {count} of {denominator}
                  </strong>{" "}
                  springs
                </>
              )}
            </span>
          </button>
          <Src k={["nasa", "ncstate", "calculated"]} />
          {/* One dot per past spring: a picture of the count above and a pointer shortcut to replay that spring. */}
          <div className="cmp-strip" aria-hidden="true">
            {leg.springs.map((s) => (
              <button
                key={s.year}
                type="button"
                tabIndex={-1}
                className={`ws-dot has-tip${flagged.has(s.year) ? " is-check" : ""}${s.complete ? "" : " is-missing"}${s.year === selectedYear && leg.selected ? " is-selected" : ""}`}
                data-tip={`Spring ${s.year}${flagged.has(s.year) ? ": check soil moisture" : ""}`}
                onClick={() => onPickYear(s.year, leg.leg)}
              />
            ))}
          </div>
        </div>
      ) : null}
    </>
  );
}
