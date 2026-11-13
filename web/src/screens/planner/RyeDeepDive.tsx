import { forwardRef, useRef, type CSSProperties, type PointerEvent } from "react";
import type { Plan } from "../../api/schema";
import { monthDay } from "../../data/format";
import { seasonDay } from "../../scene/growth";
import type { LegSummaryVM, RyeVM, SweepPoint } from "../../view/build";
import { Button, SourceChip, Src } from "../../ui/components";
import { Roll } from "../../ui/Roll";
import { dayAtFraction, seasonPct, WinterPicture } from "./WinterPicture";

/*
  Rye timing (Phase 5, redesigned Nov 13): one field picture with the rye's end date as a
  stake you drag along the ground. As it moves, the rye ends there, the blue rain with
  nothing growing widens or narrows, and three tiles show the backend's values for that
  date: rain with nothing growing, springs to check soil moisture, days of living rye.
  Every value is a point from the backend's sensitivity sweep; the page only picks the
  point (playbook p.40, handbook p.12). The past springs' weather never changes here.
  The strip under the stake is amber over the dates where the check appears.
*/

export const RyeDeepDive = forwardRef<
  HTMLElement,
  {
    rye: RyeVM;
    /** The winter-cover plan for winter 1, already carrying the chosen end date. */
    plan: Plan | null;
    /** One entry per past spring, for the dots. */
    springs: LegSummaryVM["springs"];
    /** The largest rain value across all plans, so the glass matches the other pages. */
    axisMax: number;
    selectedYear: number | null;
    onChoose: (md: string | null) => void;
    onClose: () => void;
  }
>(function RyeDeepDive({ rye, plan, springs, axisMax, selectedYear, onChoose, onClose }, ref) {
  const { points, chosen, proposed, denominator } = rye;
  const dragging = useRef(false);
  const choose = (i: number) => {
    if (i !== rye.index) onChoose(i === rye.proposedIndex ? null : points[i]!.terminate);
  };
  const days = points.map((p) => seasonDay(p.terminate));
  const firstDay = days[0]!;
  const lastDay = days[days.length - 1]!;
  const day = days[rye.index]!;
  const plantDay = seasonDay(rye.plant);
  const boundary = rye.boundaryIndex !== null ? points[rye.boundaryIndex]! : null;
  // The guidance gap, read from the backend's own rule text ("gap < 14 days ...").
  const guideMatch = rye.rule.label.match(/gap\s*<\s*(\d+)\s*day/);
  const guideDays = guideMatch ? Number(guideMatch[1]) : (boundary?.gap_days ?? null);
  const short = rye.boundaryIndex !== null && rye.index > rye.boundaryIndex;

  const nearest = (d: number) => {
    let best = 0;
    days.forEach((v, i) => {
      if (Math.abs(v - d) < Math.abs(days[best]! - d)) best = i;
    });
    return best;
  };
  const fromPointer = (e: PointerEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    choose(nearest(dayAtFraction((e.clientX - r.left) / r.width)));
  };

  // Display only: which part of the strip is amber (dates where the backend's count is above zero).
  const span = Math.max(1, lastDay - firstDay);
  const stops: string[] = [];
  points.forEach((p, i) => {
    const on = (p.checks_count ?? 0) > 0;
    const from = ((days[i]! - 0.5 - firstDay) / span) * 100;
    const to = ((days[i]! + 0.5 - firstDay) / span) * 100;
    const color = on ? "var(--ry-warn)" : "var(--ry-clear)";
    stops.push(`${color} ${Math.max(0, from).toFixed(2)}%`, `${color} ${Math.min(100, to).toFixed(2)}%`);
  });

  const flagged = new Set(chosen.qualifying_years ?? []);
  const fill = chosen.rain_mm_without_cover_median === null || axisMax <= 0 ? 0 : Math.max(0, Math.min(1, chosen.rain_mm_without_cover_median / axisMax));
  const livingMax = Math.max(1, ...points.map((p) => p.living_cover_days_planned));
  const was = (text: string) => (rye.changed ? <p className="ry-was">Your plan, {monthDay(proposed.terminate)}: {text}</p> : null);
  const rain = (p: SweepPoint) => (p.rain_mm_without_cover_median === null ? "not available" : `${p.rain_mm_without_cover_median.toFixed(0)} mm`);

  const announce = `End rye ${monthDay(chosen.terminate)}: ${chosen.gap_days} days before soybean planting, ${chosen.living_cover_days_planned} planned days with living rye, ${
    chosen.checks_count ?? "an unknown number of"
  } of ${denominator} springs with a field-moisture check.`;

  const pct = seasonPct(day);
  const plantPct = seasonPct(plantDay);
  const overlay = (
    <div
      className="ry-layer"
      onPointerDown={(e) => {
        if ((e.target as HTMLElement).closest(".ry-range")) return;
        dragging.current = true;
        e.currentTarget.setPointerCapture(e.pointerId);
        fromPointer(e);
      }}
      onPointerMove={(e) => {
        if (dragging.current) fromPointer(e);
      }}
      onPointerUp={() => {
        dragging.current = false;
      }}
      onPointerCancel={() => {
        dragging.current = false;
      }}
    >
      {boundary && guideDays !== null ? (
        <span className="ry-guide" style={{ left: `${seasonPct(seasonDay(boundary.terminate) + 0.5)}%` }} aria-hidden="true">
          <span>{guideDays} days before planting</span>
        </span>
      ) : null}
      <span className={`ry-gap${short ? " is-short" : ""}`} style={{ left: `${pct}%`, width: `${Math.max(0, plantPct - pct)}%` }} aria-hidden="true">
        <span>{chosen.gap_days} days</span>
      </span>
      <span className="ry-line" style={{ left: `${pct}%` }} aria-hidden="true" />
      <span className="ry-flag" style={{ left: `${pct}%`, transform: `translateX(-${pct}%)` }} aria-hidden="true">
        End the rye <strong className="tabular">{monthDay(chosen.terminate)}</strong>
      </span>
      <input
        className="ry-range"
        type="range"
        aria-label="Date to end the rye"
        min={0}
        max={points.length - 1}
        step={1}
        value={rye.index}
        aria-valuetext={`${monthDay(chosen.terminate)}, ${chosen.gap_days} days before soybean planting`}
        onChange={(e) => choose(Number(e.target.value))}
        onKeyDown={(e) => {
          if (e.key === "PageUp" || e.key === "PageDown") {
            e.preventDefault();
            choose(Math.min(points.length - 1, Math.max(0, rye.index + (e.key === "PageUp" ? 7 : -7))));
          }
        }}
        style={
          {
            left: `calc(${seasonPct(firstDay)}% - 14px)`,
            width: `calc(${seasonPct(lastDay) - seasonPct(firstDay)}% + 28px)`,
            "--ry-zones": `linear-gradient(to right, ${stops.join(", ")})`,
          } as CSSProperties
        }
      />
    </div>
  );

  return (
    <section className="db-card ry" aria-labelledby="rye-title" ref={ref} tabIndex={-1}>
      <header className="db-card-head">
        <h2 id="rye-title">Drag the stake to change when the rye ends</h2>
        <p className="cmp-key" aria-hidden="true">
          <span className="cmp-key-rain" /> rain with nothing growing
          <span className="cmp-key-live" /> rye growing
          <span className="ry-key-warn" /> dates with a moisture check
        </p>
      </header>

      {plan?.sequence ? <WinterPicture plan={plan} large overlay={overlay} /> : null}

      <div className="ry-jumps" role="group" aria-label="Jump to a date">
        <Button className="btn btn-secondary btn-small" onClick={() => choose(rye.proposedIndex)} aria-pressed={rye.index === rye.proposedIndex}>
          Your plan · {monthDay(proposed.terminate)}
        </Button>
        {rye.earlierIndex !== null ? (
          <Button className="btn btn-secondary btn-small" onClick={() => choose(rye.earlierIndex!)} aria-pressed={rye.index === rye.earlierIndex}>
            Your earlier date · {monthDay(points[rye.earlierIndex]!.terminate)}
          </Button>
        ) : null}
        {boundary ? (
          <Button className="btn btn-secondary btn-small" onClick={() => choose(rye.boundaryIndex!)} aria-pressed={rye.index === rye.boundaryIndex}>
            {boundary.gap_days} days before planting · {monthDay(boundary.terminate)}
          </Button>
        ) : null}
        <Button variant="quiet" onClick={onClose}>
          Back to the plan
        </Button>
      </div>
      <p className="visually-hidden" aria-live="polite">
        {announce}
      </p>

      <div className="ry-tiles">
        <div className="ry-tile">
          <p className="ry-big">
            <span className={`cmp-glass${chosen.rain_mm_without_cover_median === null ? " is-missing" : ""}`} aria-hidden="true">
              <span style={{ height: `${fill * 100}%` }} />
            </span>
            {chosen.rain_mm_without_cover_median === null ? (
              <span className="ry-unit">Not available</span>
            ) : (
              <>
                <Roll value={chosen.rain_mm_without_cover_median.toFixed(0)} className="ry-num" />
                <span className="ry-unit">mm</span>
              </>
            )}
          </p>
          <p className="ry-label">
            Winter rain with nothing growing <Src k={["nasa", "calculated"]} />
          </p>
          {was(rain(proposed))}
        </div>

        <div className={`ry-tile${(chosen.checks_count ?? 0) > 0 ? " is-warn" : ""}`}>
          <div className="ry-check">
            <p className="ry-big">
              {chosen.checks_count === null ? (
                <span className="ry-unit">Not available</span>
              ) : (
                <>
                  <Roll value={String(chosen.checks_count)} className="ry-num" />
                  <span className="ry-unit">of {denominator}</span>
                </>
              )}
            </p>
            {springs.length ? (
              <div className="cmp-strip ry-dots" aria-hidden="true">
                {springs.map((sp) => (
                  <span
                    key={sp.year}
                    className={`ws-dot has-tip${flagged.has(sp.year) ? " is-check" : ""}${sp.complete ? "" : " is-missing"}${sp.year === selectedYear ? " is-selected" : ""}`}
                    data-tip={`Spring ${sp.year}${flagged.has(sp.year) ? ": check soil moisture" : ""}`}
                  />
                ))}
              </div>
            ) : null}
          </div>
          <p className="ry-label">
            Springs to check soil moisture <Src k={["nasa", "ncstate", "calculated"]} />
          </p>
          {was(`${proposed.checks_count ?? "not available"} of ${denominator}`)}
        </div>

        <div className="ry-tile">
          <p className="ry-big">
            <Roll value={String(chosen.living_cover_days_planned)} className="ry-num" />
            <span className="ry-unit">days</span>
          </p>
          <div className="ry-bar" aria-hidden="true">
            <span style={{ width: `${(chosen.living_cover_days_planned / livingMax) * 100}%` }} />
          </div>
          <p className="ry-label">
            Living rye, planned <Src k="calculated" />
          </p>
          {was(`${proposed.living_cover_days_planned} days`)}
        </div>
      </div>

      <p className="ry-rule">
        NC State: end the cover at least two weeks before planting soybeans when low soil moisture is a concern. Illustration of planned dates;
        past weather does not change.{" "}
        {rye.rule.source ? <SourceChip kind="ncstate" href={rye.rule.source.url} title={rye.rule.source.title} /> : null}
      </p>
    </section>
  );
});
