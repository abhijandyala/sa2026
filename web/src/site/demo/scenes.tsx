import { useMemo, useRef, useState } from "react";
import { buildView, type ViewModel } from "../../view/build";
import { Compare } from "../../screens/planner/Compare";
import { FieldCalendar } from "../../screens/planner/FieldCalendar";
import { PlanDetail } from "../../screens/planner/PlanDetail";
import { SideNav, TITLES } from "../../screens/planner/SideNav";
import { RyeDeepDive } from "../../screens/planner/RyeDeepDive";
import { Springs } from "../../screens/planner/Springs";
import { WinterPicture } from "../../screens/planner/WinterPicture";
import type { CardKey } from "../../content/strategies";
import { SAMPLE_PLACE } from "../../content/locations";
import type { Page } from "../../state/model";
import type { SiteData } from "../useSiteData";
import { DemoPlayer, type DemoStep } from "./DemoPlayer";

/*
  The recordings on the marketing pages. Each scene is a real planner screen with its own
  small state, plus a script for the pointer. Nothing here draws a fake screenshot.
*/

const noop = () => {};
const axisOf = (view: ViewModel) => Math.max(0, ...view.cards.flatMap((c) => c.legs.map((l) => l.soilMm ?? 0)));

export interface SceneProps {
  data: SiteData;
  chrome?: boolean;
  play?: "visible" | "hover";
}

/**
  The whole planner in one recording: the app's own sidebar and top bar, and the pointer
  clicking from page to page. Every screen is the page's real component on the saved record;
  the clicks on the sidebar are what change the page. (The Overview page's 3D field is left
  out of the loop: it is heavy to run inside a scaled recording.)
*/
export function TourScene({ data, chrome, play }: SceneProps) {
  const [page, setPage] = useState<Page>("compare");
  const [card, setCard] = useState<CardKey>("current");
  const [year, setYear] = useState<number | null>(null);
  const [end, setEnd] = useState<string | null>(null);
  const [run, setRun] = useState(0);
  const main = useRef<HTMLElement>(null);
  const view = useMemo(() => buildView(data, { card, year, leg: 1, ryeEnd: end }), [data, card, year, end]);
  const rye = view.rye;
  const cover = view.cards.find((c) => c.key === "cover");
  const leg = cover?.legs[0];
  if (!rye || !cover || !leg) return null;
  const axisMax = axisOf(view);
  const rows = view.cards.map((c) => ({ key: c.key, name: c.content.name, plan: c.plan }));

  // The rye drag: one backend point per step, back to early April and then home to the last date that clears.
  const from = rye.proposedIndex;
  const early = Math.max(0, from - 24);
  const settle = rye.boundaryIndex ?? Math.max(0, from - 2);
  const drag = (a: number, b: number, start: number, each: number): DemoStep[] => {
    const out: DemoStep[] = [];
    const dir = a < b ? 1 : -1;
    for (let i = a, k = 0; i !== b + dir; i += dir, k++) {
      const md = rye.points[i]!.terminate;
      out.push({ at: start + k * each, run: () => setEnd(i === from ? null : md) });
    }
    return out;
  };
  const nav = (n: number) => `.db-nav button:nth-child(${n})`;
  const springs = leg.springs.length;
  const steps: DemoStep[] = [
    { at: 500, say: "One page per question. Start by comparing the three plans" },
    { at: 1400, to: { sel: ".cmp-row:nth-child(2) .cmp-cell:nth-of-type(2) .wp-frame", fx: 0.45, fy: 0.4 }, act: "hover", say: "Blue rain falls where nothing is growing" },
    { at: 4000, to: { sel: ".cmp-row:nth-child(2) .cmp-cell:nth-of-type(3) .wp-frame", fx: 0.55, fy: 0.45 }, act: "hover", say: "With rye, the ground is covered for most of the winter" },
    { at: 6600, to: { sel: ".cmp-check-text", fx: 0.3 }, say: `One dot per past spring, ${springs} in all. Amber means check soil moisture first` },
    { at: 9400, to: nav(2), act: "click", say: "Past springs: every spring since 1981 as a rain glass" },
    { at: 11400, to: ".sp-gauge:nth-child(2)", act: "click", say: "Replay a dry spring. Only the weather changes" },
    { at: 14400, to: nav(5), act: "click", say: "Rye timing: drag the day the rye ends" },
    { at: 16000, to: ".ry-line", follow: ".ry-line" },
    ...drag(from, early, 17000, 90),
    { at: 17600, say: "Earlier: fewer springs to check, more rain on bare ground" },
    ...drag(early, settle, 20200, 90),
    { at: 22300, say: "Two weeks before planting, the check clears in every spring" },
    { at: 24300, follow: "", to: nav(6), act: "click", say: "Calendar: every field job on its day" },
    { at: 26000, to: { sel: ".cal-row:nth-child(3) .cal-job:nth-child(3)", fy: 0.5 }, say: "Seeding, ending the rye and planting, for each plan" },
    { at: 28600, to: nav(4), act: "click", run: () => setCard("cover"), say: "Plan detail: both winters, and what to check before you plant" },
    // The plan page is taller than the window: scroll it, as a reader would, to the cards underneath.
    { at: 31000, run: () => main.current?.scrollTo({ top: main.current.scrollHeight, behavior: "smooth" }) },
    { at: 32000, to: { sel: ".pd-row", fx: 0.18, fy: 0.35 } },
    { at: 33800, to: ".db-summary", say: "Then print a summary for your Extension agent" },
  ];
  return (
    <DemoPlayer
      title={`Fieldback · ${TITLES[page]}`}
      width={1400}
      height={800}
      duration={36500}
      steps={steps}
      chrome={chrome}
      play={play}
      onLoop={() => {
        setPage("compare");
        setCard("current");
        setYear(null);
        setEnd(null);
        setRun((n) => n + 1);
      }}
    >
      <div className="db demo-db" key={run}>
        <SideNav page={page} onGo={setPage} onSummary={noop} />
        <div className="db-body">
          <header className="db-top">
            <div className="db-crumbs">
              <button type="button" className="fb-place">
                {SAMPLE_PLACE.name}, NC
                <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
                  <path d="M2 3.5l3 3 3-3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
              <span className="db-crumb-sep" aria-hidden="true">
                /
              </span>
              <h1>{TITLES[page]}</h1>
            </div>
            <div className="db-top-actions">
              <button type="button" className="btn btn-primary">
                Edit farm dates
              </button>
            </div>
          </header>
          <main className="db-main" ref={main}>
            <div className="db-page" key={page}>
              {page === "springs" ? (
                <Springs view={view} onSelect={setYear} stage={<div className="demo-stage-field">{leg.plan?.sequence ? <WinterPicture plan={leg.plan} large /> : null}</div>} />
              ) : page === "rye" ? (
                <RyeDeepDive rye={rye} plan={leg.plan} springs={leg.springs} axisMax={axisMax} selectedYear={null} onChoose={noop} onClose={noop} />
              ) : page === "calendar" ? (
                <FieldCalendar rows={rows} />
              ) : page === "plan" ? (
                <div className="db-plan-row">
                  <PlanDetail card={cover} axisMax={axisMax} earlier={null} planSource="sample" selectedYear={null} onPickYear={noop} onWhy={noop} onEvidence={noop} />
                </div>
              ) : (
                <Compare cards={view.cards} selected={card} selectedYear={null} onSelect={setCard} onOpen={noop} onPickYear={noop} onWhy={noop} />
              )}
            </div>
          </main>
        </div>
      </div>
    </DemoPlayer>
  );
}

/** Compare plans: point at the fields, pick a plan, read the check. */
export function CompareScene({ data, chrome, play }: SceneProps) {
  const [card, setCard] = useState<CardKey>("current");
  const [run, setRun] = useState(0);
  const view = useMemo(() => buildView(data, { card, year: null, leg: 1 }), [data, card]);
  const steps: DemoStep[] = [
    { at: 600, say: "Three winter plans, side by side" },
    { at: 1400, to: { sel: ".cmp-row:nth-child(2) .cmp-cell:nth-of-type(2) .wp-frame", fx: 0.45, fy: 0.4 }, act: "hover", say: "Blue rain falls where nothing is growing" },
    { at: 4200, to: { sel: ".cmp-row:nth-child(2) .cmp-cell:nth-of-type(3) .wp-frame", fx: 0.55, fy: 0.45 }, act: "hover", say: "Rye covers the ground for most of the winter" },
    { at: 7000, to: ".cmp-head .cmp-plan:nth-of-type(2) .cmp-plan-pick", act: "click", say: "Pick the plan to look at" },
    { at: 9200, to: { sel: ".cmp-check-text", fx: 0.3 }, say: "One dot per past spring: amber means check the soil first" },
    { at: 12200, to: { sel: ".cmp-row:nth-child(3) .cmp-cell:nth-of-type(3) .wp-frame", fx: 0.5, fy: 0.45 }, act: "hover", say: "Each winter is replayed on its own" },
  ];
  return (
    <DemoPlayer
      title="Fieldback · Compare plans"
      width={1180}
      height={720}
      duration={15500}
      steps={steps}
      chrome={chrome}
      play={play}
      onLoop={() => {
        setCard("current");
        setRun((n) => n + 1);
      }}
    >
      <div className="demo-app" key={run}>
        <Compare cards={view.cards} selected={card} selectedYear={null} onSelect={setCard} onOpen={noop} onPickYear={noop} onWhy={noop} />
      </div>
    </DemoPlayer>
  );
}

/** Rye timing: drag the stake earlier and watch the numbers move. */
export function RyeScene({ data, chrome, play }: SceneProps) {
  const [end, setEnd] = useState<string | null>(null);
  const [run, setRun] = useState(0);
  const view = useMemo(() => buildView(data, { card: "cover", year: null, leg: 1, ryeEnd: end }), [data, end]);
  const rye = view.rye;
  const cover = view.cards.find((c) => c.key === "cover")?.legs[0];
  if (!rye || !cover) return null;
  // The drag: one backend point per step, from the plan's date back to an early-April date and part of the way home.
  const from = rye.proposedIndex;
  const early = Math.max(0, from - 24);
  const settle = rye.boundaryIndex ?? Math.max(0, from - 2);
  const drag = (a: number, b: number, start: number, each: number): DemoStep[] => {
    const out: DemoStep[] = [];
    const dir = a < b ? 1 : -1;
    for (let i = a, k = 0; i !== b + dir; i += dir, k++) {
      const md = rye.points[i]!.terminate;
      out.push({ at: start + k * each, run: () => setEnd(i === from ? null : md) });
    }
    return out;
  };
  const steps: DemoStep[] = [
    { at: 500, say: "The stake marks the day the rye ends" },
    { at: 1300, to: ".ry-line", follow: ".ry-line", say: "Drag it earlier" },
    ...drag(from, early, 2300, 110),
    { at: 5400, say: "More days before planting, and no springs to check" },
    { at: 7600, say: "But more rain falls with nothing growing" },
    ...drag(early, settle, 9000, 110),
    { at: 12000, say: "Two weeks before planting is where the check clears" },
    { at: 13200, follow: "", to: { sel: ".ry-tiles .ry-tile:nth-child(2)", fx: 0.3, fy: 0.4 } },
  ];
  return (
    <DemoPlayer
      title="Fieldback · Rye timing"
      width={1180}
      height={700}
      duration={16000}
      steps={steps}
      chrome={chrome}
      play={play}
      onLoop={() => {
        setEnd(null);
        setRun((n) => n + 1);
      }}
    >
      <div className="demo-app" key={run}>
        <RyeDeepDive rye={rye} plan={cover.plan} springs={cover.springs} axisMax={axisOf(view)} selectedYear={null} onChoose={noop} onClose={noop} />
      </div>
    </DemoPlayer>
  );
}

/** Past springs: pick the dry spring, then the wet one. */
export function SpringsScene({ data, chrome, play }: SceneProps) {
  const [year, setYear] = useState<number | null>(null);
  const [run, setRun] = useState(0);
  const view = useMemo(() => buildView(data, { card: "cover", year, leg: 1 }), [data, year]);
  const plan = view.cards.find((c) => c.key === "cover")?.legs[0]?.plan ?? null;
  const steps: DemoStep[] = [
    { at: 500, say: "Every spring NASA has on record, as a rain glass" },
    { at: 1600, to: ".sp-gauge:nth-child(2)", act: "click", say: "Replay a dry spring" },
    { at: 5000, to: ".sp-gauge:nth-child(3)", act: "click", say: "Then a wet one" },
    { at: 8400, to: ".sp-drop:nth-child(34)", act: "click", say: "Or pick any year from the row" },
    { at: 11600, to: ".sp-step:last-child", act: "click" },
    { at: 12300, to: ".sp-step:last-child", act: "click", say: "Only the weather changes. Your dates stay put." },
  ];
  return (
    <DemoPlayer
      title="Fieldback · Past springs"
      width={1180}
      height={700}
      duration={15000}
      steps={steps}
      chrome={chrome}
      play={play}
      onLoop={() => {
        setYear(null);
        setRun((n) => n + 1);
      }}
    >
      <div className="demo-app" key={run}>
        <Springs view={view} onSelect={setYear} stage={<div className="demo-stage-field">{plan?.sequence ? <WinterPicture plan={plan} large /> : null}</div>} />
      </div>
    </DemoPlayer>
  );
}

/** Calendar: both winters, every job on its day. */
export function CalendarScene({ data, chrome, play }: SceneProps) {
  const [leg, setLeg] = useState<1 | 2>(1);
  const [run, setRun] = useState(0);
  const view = useMemo(() => buildView(data, { card: "cover", year: null, leg }), [data, leg]);
  const rows = view.cards.map((c) => ({ key: c.key, name: c.content.name, plan: c.plan }));
  const steps: DemoStep[] = [
    { at: 500, say: "Each plan's jobs, on the day they happen" },
    { at: 1500, to: { sel: ".cal-row:nth-child(3) .cal-job:nth-child(2)", fy: 0.5 }, say: "Seed the rye after the corn comes off" },
    { at: 4300, to: { sel: ".cal-row:nth-child(3) .cal-job:nth-child(3)", fy: 0.5 }, say: "End it before the soybeans go in" },
    { at: 7200, to: ".cal .segmented button:nth-child(2)", act: "click", run: () => setLeg(2), say: "Then the winter after soybeans" },
    { at: 10200, to: { sel: ".cal-row:nth-child(3) .wp-frame", fx: 0.5, fy: 0.5 }, act: "hover" },
  ];
  return (
    <DemoPlayer
      title="Fieldback · Calendar"
      width={1180}
      height={690}
      duration={13000}
      steps={steps}
      chrome={chrome}
      play={play}
      onLoop={() => {
        setLeg(1);
        setRun((n) => n + 1);
      }}
    >
      <div className="demo-app" key={run}>
        <FieldCalendar
          rows={rows}
          action={
            <div className="segmented" role="group" aria-label="Which winter">
              <button type="button" role="radio" className="segmented-option" aria-checked={leg === 1}>
                Winter after corn
              </button>
              <button type="button" role="radio" className="segmented-option" aria-checked={leg === 2}>
                Winter after soybeans
              </button>
            </div>
          }
        />
      </div>
    </DemoPlayer>
  );
}
