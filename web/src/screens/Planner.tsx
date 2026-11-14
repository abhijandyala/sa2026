import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { APP_NAME } from "../config";
import { cardByKey, SOURCES, type CardKey, type Leg } from "../content/strategies";
import type { Client } from "../api/client";
import { sameForm, sampleForm } from "../state/form";
import { hasPendingEdits, initialState, reducer, type Page } from "../state/model";
import { applyUrlView, fromHash, toHash } from "../state/url";
import { useReplay, type ApplyOutcome, type Loaded } from "../state/useData";
import { buildView, validYears } from "../view/build";
import { Banner, Button, Segmented } from "../ui/components";
import { G } from "../ui/Glossary";
import { EvidenceDrawer } from "./planner/EvidenceDrawer";
import { FarmFormDrawer } from "./planner/FarmFormDrawer";
import { PlanDetail } from "./planner/PlanDetail";
import { PlanTiles } from "./planner/PlanTiles";
import { navIcon, SideNav, TITLES } from "./planner/SideNav";
import { Compare } from "./planner/Compare";
import { FieldCalendar } from "./planner/FieldCalendar";
import { Springs } from "./planner/Springs";
import { FarmView } from "./planner/FarmView";
import { RyeDeepDive } from "./planner/RyeDeepDive";
import { PriorityPicker } from "./planner/PriorityPicker";
import { Tour, type TourStep } from "./planner/Tour";
import { ExtensionSummary } from "./planner/ExtensionSummary";
import { CUSTOM_ID, customPlace, LocationDrawer } from "./planner/LocationDrawer";
import { DatesOnly } from "./planner/DatesOnly";
import { placeById, SAMPLE_PLACE, type Place } from "../content/locations";
import type { LatLon } from "../api/client";
import type { PlaceState } from "../state/useData";

/*
  Layout B (decided Nov 12): header, weather control (years strip), 3D band capped near
  40% of the viewport, three strategy cards, then the calendar. The cards' counts must
  start above the fold at 1280×720 (playbook p.38).
*/

export function Planner({
  data,
  apply,
  applying,
  hasLiveApi,
  client,
  place,
  chooseLocation,
}: {
  client: Client;
  place: PlaceState;
  chooseLocation: (p: Place, form: ReturnType<typeof sampleForm>) => Promise<void>;
  data: Loaded;
  apply: (form: ReturnType<typeof sampleForm>) => Promise<ApplyOutcome>;
  applying: boolean;
  hasLiveApi: boolean;
}) {
  const sample = useMemo(() => sampleForm(data.compare), [data.compare]);
  const years = useMemo(() => validYears(data.compare), [data.compare]);
  const ryeEnds = useMemo(() => new Set((data.sensitivity?.points ?? []).map((p) => p.terminate)), [data.sensitivity]);
  const [state, dispatch] = useReducer(reducer, sample, (s) =>
    applyUrlView(initialState(s), fromHash(window.location.hash, years, ryeEnds)),
  );
  const ryeRef = useRef<HTMLElement>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [audit, setAudit] = useState(false);
  const formBtn = useRef<HTMLButtonElement>(null);
  const locationBtn = useRef<HTMLButtonElement>(null);
  const [custom, setCustom] = useState<LatLon | null>(null);
  const [evidenceFocus, setEvidenceFocus] = useState<"rain" | "check" | null>(null);
  const [tour, setTour] = useState<number | null>(null);
  const tourBtn = useRef<HTMLButtonElement>(null);

  // Everything behind the page as one file: the service's responses as received, plus view choices.
  const exportJson = () => {
    const payload = {
      exported_by: APP_NAME,
      note: "Responses exactly as this page received them. Fieldback computes none of these values.",
      origin: data.origin,
      place: { name: place.place.name, latitude: place.place.latitude, longitude: place.place.longitude, status: place.kind },
      view: { plan: state.card, winter: state.leg, spring: view.selectedYear?.year ?? null, rye_end: state.ryeEnd, priorities: state.priorities },
      years: data.years,
      compare: data.compare,
      sensitivity: data.sensitivity,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `fieldback-results-${data.compare.meta.request_id}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const evidenceBtn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const next = toHash(state);
    if (next !== window.location.hash) history.replaceState(null, "", next);
  }, [state]);

  // Switch the data when the chosen place changes (a click, a shared link or Reset).
  const target: Place = state.placeId === CUSTOM_ID && custom ? customPlace(custom) : (placeById(state.placeId) ?? SAMPLE_PLACE);
  useEffect(() => {
    if (target.sample && place.kind === "sample") return;
    void chooseLocation(target, state.applied);
    // Only a change of place triggers this; dates go through Apply dates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target.id, target.latitude, target.longitude]);
  const datesOnly = place.kind === "dates-only" || place.kind === "checking";
  const placeLabel = `${place.place.name}, NC`;
  const placeStatus =
    place.kind === "sample"
      ? sameForm(state.applied, state.sample)
        ? "Sample field"
        : "Your dates"
      : place.kind === "live"
        ? "Supported example area"
        : place.kind === "checking"
          ? "Checking…"
          : "Dates only";

  // Follow the link when only the hash changes (a pasted share link, Back/Forward).
  useEffect(() => {
    const onHash = () => dispatch({ type: "applyLink", view: fromHash(window.location.hash, years, ryeEnds) });
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [years, ryeEnds]);

  // Move focus to the rye timing panel when its page opens.
  useEffect(() => {
    if (state.ryeOpen) ryeRef.current?.focus({ preventScroll: true });
  }, [state.ryeOpen]);

  const view = useMemo(
    () =>
      buildView(data, {
        card: state.card,
        year: state.year,
        leg: state.leg,
        ryeEnd: state.ryeEnd,
        earlierRyeEnd: state.applied.ryeEndEarlier.slice(5),
        priorities: state.priorities,
        observation: { moisture: state.applied.moistureConcern, irrigation: state.applied.irrigation },
      }),
    [data, state.card, state.year, state.leg, state.ryeEnd, state.applied, state.priorities],
  );
  // The summary shows both winters, so it builds the same view once per winter (numbers match the planner).
  const legViews = useMemo(() => {
    if (!state.summaryOpen) return null;
    const base = {
      card: state.card,
      year: state.year,
      ryeEnd: state.ryeEnd,
      earlierRyeEnd: state.applied.ryeEndEarlier.slice(5),
      priorities: state.priorities,
      observation: { moisture: state.applied.moistureConcern, irrigation: state.applied.irrigation },
    };
    return { 1: buildView(data, { ...base, leg: 1 }), 2: buildView(data, { ...base, leg: 2 }) } as const;
  }, [data, state.summaryOpen, state.card, state.year, state.ryeEnd, state.applied, state.priorities]);
  const selectedCard = view.cards.find((c) => c.key === state.card) ?? view.cards[0]!;
  // The grower's earlier rye date, read from the backend's sweep (same plan, edited date).
  const earlierPoint = view.rye && view.rye.earlierIndex !== null ? view.rye.points[view.rye.earlierIndex]! : null;
  const pending = hasPendingEdits(state);
  const replay = useReplay(client, view.selectedYear?.year ?? null, cardByKey(state.card).legs[state.leg], data.origin);

  const onApply = async () => {
    const draft = state.draft ?? state.applied;
    const r = await apply(draft);
    if (r.ok) {
      dispatch({ type: "applied", form: draft });
      setNotice(null);
    } else {
      setNotice(r.message);
    }
  };

  // The walkthrough reads the numbers on screen; it adds none of its own.
  const coverCard = view.cards.find((c) => c.key === "cover");
  const coverCheck = coverCard?.legs.find((l) => l.check.applies && l.check.count !== null)?.check;
  const tourSteps: TourStep[] = [
    {
      target: ".fb-stage-wrap",
      title: "One field, three winter plans",
      body: "Left: what you do now, crop residue with nothing growing. Middle: cereal rye as a winter cover. Right: a wheat crop. Press the play button to watch them from September to June.",
      onEnter: () => dispatch({ type: "setPage", page: "overview" }),
    },
    {
      target: ".fb-springs",
      title: "Every spring NASA recorded here",
      body: `Each bar is the rain in the 30 days before planting, one bar per year since 1981. We just jumped to ${view.shortcuts.dry ?? "a dry spring"}, one of the driest.`,
      onEnter: () => {
        dispatch({ type: "setPage", page: "springs" });
        if (view.shortcuts.dry !== null) dispatch({ type: "selectYear", year: view.shortcuts.dry });
      },
    },
    {
      target: ".cmp",
      title: "The plans side by side",
      body: coverCheck
        ? `Each dot is one past spring and each bar is winter rain with nothing growing. With rye, NC State would say check soil moisture before planting soybeans in ${coverCheck.count} of ${coverCheck.denominator} springs.`
        : "Each dot is one past spring and each bar is winter rain with nothing growing. The two winters are shown apart and never added.",
      onEnter: () => dispatch({ type: "setPage", page: "compare" }),
    },
    {
      target: ".db-nav-summary",
      title: "Take it to your Extension agent",
      body: "The Extension summary is a printable page with your dates, the three plans, what to discuss and every source. That is the end of the walkthrough.",
    },
  ];

  if (state.summaryOpen && legViews && !datesOnly) {
    return (
      <ExtensionSummary
        view={view}
        legViews={legViews}
        form={state.applied}
        priorities={state.priorities}
        planSource={sameForm(state.applied, state.sample) ? "sample" : "farmer"}
        placeLabel={placeLabel}
        onClose={() => dispatch({ type: "closeSummary" })}
      />
    );
  }

  const y = view.selectedYear;
  const springChip =
    y && y.status === "complete" && y.totalMm !== null
      ? { year: y.year, text: `${y.totalMm.toFixed(1)} mm of rain${y.isDry ? " · dry" : ""}`, dry: Boolean(y.isDry) }
      : null;
  const planSource = sameForm(state.applied, state.sample) ? "sample" : "farmer";

  const calendarRows = view.cards.map((c) => ({ key: c.key, name: c.content.name, plan: c.plan }));
  const page: Page = datesOnly ? "calendar" : state.page;
  const go = (p: Page) => {
    dispatch({ type: "setPage", page: p });
    window.scrollTo({ top: 0 });
  };
  const pickYear = (year: number, leg: 1 | 2, card?: CardKey) => {
    if (card && card !== state.card) dispatch({ type: "selectCard", card });
    if (leg !== state.leg) dispatch({ type: "selectLeg", leg });
    dispatch({ type: "selectYear", year });
  };
  const why = (kind: "rain" | "check", leg: 1 | 2, card?: CardKey) => {
    setEvidenceFocus(kind);
    if (card && card !== state.card) dispatch({ type: "selectCard", card });
    if (leg !== state.leg) dispatch({ type: "selectLeg", leg });
    dispatch({ type: "openEvidence" });
  };
  const planPick = (
    <div className="fb-plan-pick" role="group" aria-label="Plan to look at">
      {view.cards.map((c) => (
        <button
          key={c.key}
          type="button"
          className={c.key === state.card ? "is-on" : undefined}
          aria-pressed={c.key === state.card}
          onClick={() => dispatch({ type: "selectCard", card: c.key })}
        >
          {c.content.name}
        </button>
      ))}
    </div>
  );

  return (
    <div className={`db${audit ? " audit-on" : ""}`}>
      <SideNav page={page} only={datesOnly ? ["calendar"] : undefined} onGo={go} onSummary={datesOnly ? undefined : () => dispatch({ type: "openSummary" })}>
        <div className="db-side-foot">
          {view.dataKind === "draft" ? (
            <p className="db-draft" role="status">
              <span className="db-draft-dot" aria-hidden="true" />
              <span>
                <strong>Draft sample data</strong> · not for judging
              </span>
            </p>
          ) : null}
          <div className="db-links">
            <a href="?view=methods">
              {navIcon("M9 16A7 7 0 1 0 9 2a7 7 0 0 0 0 14zM7 7a2 2 0 1 1 3 1.700c-.600.400-1 .800-1 1.500M9 12.700v.100")}
              How it works
            </a>
            <a href="?view=credits">
              {navIcon("M3 5c0-1.100 2.700-2 6-2s6 .900 6 2-2.700 2-6 2-6-.900-6-2zM3 5v4c0 1.100 2.700 2 6 2s6-.900 6-2V5M3 9v4c0 1.100 2.700 2 6 2s6-.900 6-2V9")}
              Data and credits
            </a>
            <a href="?view=privacy">
              {navIcon("M9 2l5.500 2v4.500c0 3.500-2.300 6-5.500 7.500-3.200-1.500-5.500-4-5.500-7.500V4zM6.700 9l1.700 1.700 3-3.200")}
              Privacy and terms
            </a>
            <button type="button" role="switch" aria-checked={audit} className="db-switch" onClick={() => setAudit((v) => !v)}>
              {navIcon("M2.500 9.500V3.500a1 1 0 0 1 1-1h6l6 6-7 7zM6 6v.100")}
              Source tags
              <span className="db-switch-track" aria-hidden="true">
                <span />
              </span>
            </button>
            <button
              type="button"
              onClick={() => {
                dispatch({ type: "reset" });
                setNotice(null);
              }}
            >
              {navIcon("M3.500 9a5.500 5.500 0 1 0 1.700-4M3 2.500V5.500h3")}
              Reset the example
            </button>
          </div>
        </div>
      </SideNav>

      <div className="db-body">
        <header className="db-top">
          <div className="db-crumbs">
            <button
              ref={locationBtn}
              type="button"
              className="fb-place"
              onClick={() => dispatch({ type: "openLocation" })}
              aria-label={`Place: ${placeLabel}, ${placeStatus}. Change place`}
            >
              {placeLabel}
              {placeStatus === "Sample field" ? null : <span className="fb-place-status"> · {placeStatus}</span>}
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
            {datesOnly || page === "compare" || page === "plan" || page === "rye" || page === "calendar" ? null : (
              <Segmented
                label="Which winter"
                value={String(view.leg) as "1" | "2"}
                onChange={(v) => dispatch({ type: "selectLeg", leg: Number(v) as Leg })}
                options={[
                  { value: "1", label: "Winter after corn" },
                  { value: "2", label: "Winter after soybeans" },
                ]}
              />
            )}
            {datesOnly ? null : (
              <Button ref={tourBtn} onClick={() => setTour(0)}>
                Walk me through it
              </Button>
            )}
            {pending ? <span className="pending-note">Edited, not applied</span> : null}
            <Button ref={formBtn} variant="primary" onClick={() => dispatch({ type: "openForm" })}>
              Edit farm dates
            </Button>
          </div>
        </header>

        <main className="db-main">
          {notice && !state.formOpen ? (
            <Banner kind="info">
              {notice}{" "}
              <button type="button" className="link-button" onClick={() => setNotice(null)}>
                Dismiss
              </button>
            </Banner>
          ) : null}
          {place.kind === "live" ? (
            <Banner kind="info">
              <strong>Supported example area: {placeLabel}.</strong> Weather from NASA POWER for this place's grid cell
              {place.cell ? `, centered ${place.cell.lat.toFixed(2)}, ${place.cell.lon.toFixed(2)}` : ""}, from the live service. {place.guidanceNote ?? ""}
            </Banner>
          ) : null}

          <div className="db-page" key={datesOnly ? "dates" : page}>
          {datesOnly ? (
            <>
              <DatesOnly
                place={place}
                onBack={() => dispatch({ type: "setPlace", placeId: SAMPLE_PLACE.id })}
                onChoose={() => dispatch({ type: "openLocation" })}
              />
              <FieldCalendar rows={calendarRows} />
            </>
          ) : page === "overview" ? (
            <>
              <PlanTiles cards={view.cards} selected={state.card} onSelect={(card) => dispatch({ type: "selectCard", card })} />
              <section className="db-card db-fields fb-stage-wrap" aria-labelledby="fields-title">
                <header className="db-card-head">
                  <div>
                    <h2 id="fields-title">Your field through the season</h2>
                  </div>
                  <div className="db-next">
                    <Button onClick={() => go("compare")}>Compare the plans</Button>
                    <Button onClick={() => go("springs")}>See past springs</Button>
                  </div>
                </header>
                <FarmView
                  strips={view.strips}
                  spring={springChip}
                  onSelectCard={(card) => dispatch({ type: "selectCard", card })}
                  onSpring={() => go("springs")}
                />
              </section>
            </>
          ) : page === "springs" ? (
            <Springs
              view={view}
              onSelect={(year) => dispatch({ type: "selectYear", year })}
              stage={
                <FarmView
                  replay
                  strips={view.strips}
                  spring={null}
                  onSelectCard={(card) => dispatch({ type: "selectCard", card })}
                  onSpring={() => {}}
                />
              }
            />
          ) : page === "compare" ? (
            <Compare
              cards={view.cards}
              selected={state.card}
              selectedYear={view.selectedYear?.year ?? null}
              onSelect={(card) => dispatch({ type: "selectCard", card })}
              onOpen={(card) => {
                dispatch({ type: "selectCard", card });
                go("plan");
              }}
              onPickYear={pickYear}
              onWhy={why}
            />
          ) : page === "plan" ? (
            <div className="db-plan-row">
              <PlanDetail
                card={selectedCard}
                earlier={
                  selectedCard.key === "cover" && earlierPoint && view.rye
                    ? { terminate: earlierPoint.terminate, gap: earlierPoint.gap_days, count: earlierPoint.checks_count, denominator: view.rye.denominator }
                    : null
                }
                planSource={planSource}
                axisMax={Math.max(0, ...view.cards.flatMap((c) => c.legs.map((l) => l.soilMm ?? 0)))}
                selectedYear={view.selectedYear?.year ?? null}
                onPickYear={(year, leg) => pickYear(year, leg)}
                onWhy={(kind, leg) => why(kind, leg)}
                onAdjust={selectedCard.key === "cover" && view.rye ? () => dispatch({ type: "openRye" }) : undefined}
                onEvidence={() => {
                  setEvidenceFocus(null);
                  dispatch({ type: "openEvidence" });
                }}
                evidenceRef={evidenceBtn}
                toolbar={
                  <div className="fb-plan-tabs">
                    {planPick}
                    <PriorityPicker priorities={state.priorities} onToggle={(priority) => dispatch({ type: "togglePriority", priority })} />
                  </div>
                }
              />
            </div>
          ) : page === "rye" ? (
            view.rye ? (
              <RyeDeepDive
                ref={ryeRef}
                rye={view.rye}
                plan={view.cards.find((c) => c.key === "cover")?.legs[0]?.plan ?? null}
                springs={view.cards.find((c) => c.key === "cover")?.legs[0]?.springs ?? []}
                axisMax={Math.max(0, ...view.cards.flatMap((c) => c.legs.map((l) => l.soilMm ?? 0)))}
                selectedYear={state.leg === 1 ? (view.selectedYear?.year ?? null) : null}
                onChoose={(md) => dispatch({ type: "setRyeEnd", md })}
                onClose={() => dispatch({ type: "closeRye" })}
              />
            ) : (
              <section className="db-card">
                <header className="db-card-head">
                  <h2>Rye timing is not available for these dates yet</h2>
                </header>
              </section>
            )
          ) : (
            <FieldCalendar
              rows={calendarRows}
              onOpen={(key) => {
                dispatch({ type: "selectCard", card: key as CardKey });
                go("plan");
              }}
              action={
                <Segmented
                  label="Which winter"
                  value={String(view.leg) as "1" | "2"}
                  onChange={(v) => dispatch({ type: "selectLeg", leg: Number(v) as Leg })}
                  options={[
                    { value: "1", label: "Winter after corn" },
                    { value: "2", label: "Winter after soybeans" },
                  ]}
                />
              }
            />
          )}

          </div>

          <p className="db-foot">
            Past weather from{" "}
            <a href={SOURCES["nasa-power"].url} target="_blank" rel="noreferrer">
              NASA POWER
            </a>
            , guidance from{" "}
            <a href={SOURCES["ncs-soy-4"].url} target="_blank" rel="noreferrer">
              NC State Extension
            </a>
            . A replay to talk over with your <G id="extension">Extension agent</G>, not a forecast.
          </p>
        </main>
      </div>

      {tour !== null && !datesOnly && !state.evidenceOpen && !state.formOpen && !state.locationOpen ? (
        <Tour
          steps={tourSteps}
          index={tour}
          onIndex={setTour}
          onClose={() => {
            setTour(null);
            tourBtn.current?.focus();
          }}
        />
      ) : null}

      <LocationDrawer
        open={state.locationOpen}
        placeId={state.placeId}
        custom={custom}
        hasLiveApi={hasLiveApi}
        samplePoint={view.grid}
        resolved={(place.kind === "live" || place.kind === "dates-only") && place.cell ? { placeId: state.placeId, cell: place.cell } : null}
        onChoose={(placeId, point) => {
          if (point) setCustom(point);
          dispatch({ type: "setPlace", placeId });
        }}
        onClose={() => dispatch({ type: "closeLocation" })}
        returnFocusRef={locationBtn}
      />
      <FarmFormDrawer
        open={state.formOpen}
        draft={state.draft ?? state.applied}
        pending={pending}
        applying={applying}
        hasLiveApi={hasLiveApi}
        message={notice}
        onEdit={(patch) => dispatch({ type: "editDraft", patch })}
        onApply={onApply}
        onDiscard={() => {
          dispatch({ type: "discardDraft" });
          setNotice(null);
        }}
        onClose={() => dispatch({ type: "closeForm" })}
        returnFocusRef={formBtn}
      />
      <EvidenceDrawer
        open={state.evidenceOpen && !datesOnly}
        focus={evidenceFocus}
        onExport={exportJson}
        view={view}
        card={selectedCard}
        form={state.applied}
        replay={replay}
        priorities={state.priorities}
        emphasis={state.emphasis}
        onClose={() => dispatch({ type: "closeEvidence" })}
        returnFocusRef={evidenceBtn}
      />
    </div>
  );
}
