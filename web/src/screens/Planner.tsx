import { useEffect, useMemo, useReducer, useRef } from "react";
import { APP_NAME, TAGLINE, TASK_TITLE } from "../config";
import type { Bundle, PlantingEvent, Strategy } from "../data/schema";
import { historicalWindow, mm, plannedDate, springs, wetness } from "../data/format";
import { initialState, reducer } from "../state/model";
import { applyUrlView, fromHash, toHash } from "../state/url";
import { Banner, Button, StatusPill, StrategyCardShell, YearTile } from "../ui/components";

/*
  Layout B shell (decided Nov 12): header, years strip, 3D band capped near 40% of the
  viewport, three strategy cards below, evidence drawer. This is the Phase 0 frame that
  later phases fill in; numbers come straight from the bundle, never recomputed here.
*/

function headlineEvent(s: Strategy): PlantingEvent {
  return s.events.find((e) => e.id === s.headlineEventId) ?? s.events[0]!;
}

export function Planner({ bundle, synthetic }: { bundle: Bundle; synthetic: boolean }) {
  const validYears = useMemo(() => new Set(bundle.strategies[0]!.events[0]!.years.map((y) => y.year)), [bundle]);
  const [state, dispatch] = useReducer(reducer, bundle, (b) =>
    applyUrlView(initialState(b), fromHash(window.location.hash, validYears)),
  );
  const evidenceBtn = useRef<HTMLButtonElement>(null);
  const stripRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const next = toHash(state);
    if (next !== window.location.hash) history.replaceState(null, "", next);
  }, [state]);

  const selected = bundle.strategies.find((s) => s.id === state.selectedStrategy)!;
  const event = headlineEvent(selected);
  const year = state.selectedYear ?? event.summary.typicalYear;
  const yearRow = event.years.find((y) => y.year === year) ?? null;

  // Keep the selected year visible when the strip scrolls sideways on a phone.
  useEffect(() => {
    const strip = stripRef.current;
    const tile = strip?.querySelector<HTMLElement>(".year-tile.is-selected");
    if (!strip || !tile || strip.scrollWidth <= strip.clientWidth) return;
    strip.scrollLeft = tile.offsetLeft - strip.clientWidth / 2 + tile.offsetWidth / 2;
  }, [year, event.id]);

  return (
    <div className="planner">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">{APP_NAME}</span>
        </div>
        <div className="header-title">
          <h1>{TASK_TITLE}</h1>
          <p className="header-tagline">{TAGLINE}</p>
        </div>
        <div className="header-status">
          <span className="location">
            {bundle.plan.locationLabel} · {bundle.plan.isExample ? "Sample field" : "Your field"}
          </span>
          {synthetic ? (
            <StatusPill kind="synthetic">Synthetic test data</StatusPill>
          ) : (
            <StatusPill kind="saved">Saved NASA record · retrieved {bundle.manifest.retrievedAt.slice(0, 10)}</StatusPill>
          )}
          <Button variant="quiet" onClick={() => dispatch({ type: "reset" })}>
            Reset example
          </Button>
        </div>
      </header>

      {synthetic ? (
        <Banner kind="synthetic">
          <strong>Synthetic test data, not for judging.</strong> Every number on this screen is invented to test the layout. Real
          NASA weather appears when the saved record is added.
        </Banner>
      ) : null}

      <section className="strip" aria-labelledby="strip-title">
        <div className="strip-head">
          <h2 id="strip-title" className="strip-title">
            Past springs, {bundle.manifest.range.start.slice(0, 4)}–{bundle.manifest.range.end.slice(0, 4)}
          </h2>
          <p className="strip-context">
            Viewing: {event.windowDays} days before {event.label.toLowerCase()} ({plannedDate(event.plantingDate)})
          </p>
        </div>
        <div className="strip-tiles" role="group" aria-label="Choose a past spring to replay" ref={stripRef}>
          {event.years.map((y) => (
            <YearTile
              key={y.year}
              year={y.year}
              pctRank={y.pctRank}
              complete={y.complete}
              selected={y.year === year}
              marker={
                y.year === event.summary.typicalYear
                  ? "typical"
                  : y.year === event.summary.dryReplayYear
                    ? "dry-replay"
                    : undefined
              }
              onSelect={() => dispatch({ type: "selectYear", year: y.year })}
              description={y.complete ? `${mm(y.rainMm)}${y.dry ? ", among the driest 20%" : ""}` : "no complete record"}
            />
          ))}
        </div>
        <p className="strip-summary" aria-live="polite">
          {yearRow ? (
            yearRow.complete ? (
              <>
                <strong>Spring {yearRow.year}</strong> · {mm(yearRow.rainMm)} in the {event.windowDays} days before{" "}
                {plannedDate(event.plantingDate)} ({historicalWindow(yearRow.window)})
                {yearRow.dry ? " · among the driest 20% here" : ""} · modeled soil wetness {wetness(yearRow.soilWetRoot)} ·
                regional estimate
              </>
            ) : (
              <>
                <strong>Spring {yearRow.year}</strong> · Incomplete: {yearRow.expectedDays - yearRow.validDays} missing days.
                Not compared.
              </>
            )
          ) : (
            "Not enough complete years to compare."
          )}
        </p>
      </section>

      <section className="world-band" aria-label="Farm view">
        <div className="world-placeholder">
          <p className="marker">Illustration of your plan</p>
          <p>3D farm world goes here (Phase 4): three field strips, seasons, and the selected spring's weather.</p>
        </div>
      </section>

      <section className="cards" aria-label="Three winter plans">
        {bundle.strategies.map((s, i) => {
          const e = headlineEvent(s);
          const sum = e.summary;
          const count = sum.ruleApplies ? sum.flagged : sum.dryCount;
          const yr = e.years.find((y) => y.year === year);
          const flaggedThisYear = Boolean(yr?.flag);
          return (
            <StrategyCardShell
              key={s.id}
              index={i + 1}
              name={s.name}
              subtitle={s.subtitle}
              selected={s.id === state.selectedStrategy}
              tone={flaggedThisYear ? "check" : "default"}
              headline={sum.labelsWithheld ? "Not enough years" : springs(count, sum.completeYears)}
              secondary={
                sum.ruleApplies
                  ? "dry window and under 14 days between rye and planting"
                  : `had a dry ${e.label.toLowerCase()} window`
              }
              metric={
                s.metrics.gapDays !== null && s.metrics.livingCoverDays !== null
                  ? `${s.metrics.gapDays} days before planting · ${s.metrics.livingCoverDays} planned days with living rye`
                  : s.metrics.gapDays !== null
                    ? `${s.metrics.gapDays} days between wheat harvest and planting`
                    : "Rye timing does not apply"
              }
              status={
                flaggedThisYear ? (
                  <StatusPill kind="check">Check field moisture</StatusPill>
                ) : yr && !yr.complete ? (
                  <StatusPill kind="unavailable">Weather unavailable this year</StatusPill>
                ) : null
              }
              actions={
                <>
                  <Button
                    variant={s.id === state.selectedStrategy ? "primary" : "secondary"}
                    onClick={() => dispatch({ type: "selectStrategy", id: s.id })}
                    aria-pressed={s.id === state.selectedStrategy}
                  >
                    {s.id === state.selectedStrategy ? "Selected" : "Select"}
                  </Button>
                  <Button
                    ref={s.id === state.selectedStrategy ? evidenceBtn : undefined}
                    onClick={() => {
                      dispatch({ type: "selectStrategy", id: s.id });
                      dispatch({ type: "openEvidence" });
                    }}
                  >
                    Show evidence
                  </Button>
                </>
              }
            />
          );
        })}
      </section>
    </div>
  );
}
