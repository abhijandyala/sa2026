import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { APP_NAME, TAGLINE, TASK_TITLE } from "../config";
import { CARDS, cardByKey } from "../content/strategies";
import type { Client } from "../api/client";
import { sameForm, sampleForm } from "../state/form";
import { hasPendingEdits, initialState, reducer } from "../state/model";
import { applyUrlView, fromHash, toHash } from "../state/url";
import { useReplay, type ApplyOutcome, type Loaded } from "../state/useData";
import { buildView, validYears } from "../view/build";
import { Banner, Button, StatusPill } from "../ui/components";
import { EvidenceDrawer } from "./planner/EvidenceDrawer";
import { FarmFormDrawer } from "./planner/FarmFormDrawer";
import { StrategyCard } from "./planner/StrategyCard";
import { Timeline } from "./planner/Timeline";
import { YearStrip } from "./planner/YearStrip";
import { WeatherDetail } from "./planner/WeatherDetail";
import { FarmView } from "./planner/FarmView";

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
}: {
  client: Client;
  data: Loaded;
  apply: (form: ReturnType<typeof sampleForm>) => Promise<ApplyOutcome>;
  applying: boolean;
  hasLiveApi: boolean;
}) {
  const sample = useMemo(() => sampleForm(data.compare), [data.compare]);
  const years = useMemo(() => validYears(data.compare), [data.compare]);
  const [state, dispatch] = useReducer(reducer, sample, (s) => applyUrlView(initialState(s), fromHash(window.location.hash, years)));
  const [notice, setNotice] = useState<string | null>(null);
  const formBtn = useRef<HTMLButtonElement>(null);
  const evidenceBtn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const next = toHash(state);
    if (next !== window.location.hash) history.replaceState(null, "", next);
  }, [state]);

  // Follow the link when only the hash changes (a pasted share link, Back/Forward).
  useEffect(() => {
    const onHash = () => dispatch({ type: "applyLink", view: fromHash(window.location.hash, years) });
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [years]);

  const view = useMemo(() => buildView(data, { card: state.card, year: state.year }), [data, state.card, state.year]);
  const selectedCard = view.cards.find((c) => c.key === state.card) ?? view.cards[0]!;
  const rye19 = data.compare.plans.find((p) => p.plan_id === "rye_19d") ?? null;
  const rye19Check = rye19?.spring_checks.find((c) => c.check_id === "rye_soy_short_gap_moisture");
  const pending = hasPendingEdits(state);
  const replay = useReplay(client, view.selectedYear?.year ?? null, cardByKey(state.card).planId, data.origin);

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

  const status =
    view.dataKind === "live" ? (
      <StatusPill kind="live">Live results for your dates</StatusPill>
    ) : view.dataKind === "draft" ? (
      <StatusPill kind="synthetic">Draft sample data</StatusPill>
    ) : (
      <StatusPill kind="saved">Saved NASA record</StatusPill>
    );

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
            {view.locationLabel.replace(/\s*\(sample\)$/i, "")} · {sameForm(state.applied, state.sample) ? "Sample field" : "Your dates"}
          </span>
          {status}
        </div>
        <nav className="header-actions" aria-label="Plan actions">
          <span className="control-label">Change the plan:</span>
          <Button ref={formBtn} variant="primary" onClick={() => dispatch({ type: "openForm" })}>
            Edit farm dates
          </Button>
          {pending ? <span className="pending-note">Edited, not applied</span> : null}
          <Button ref={evidenceBtn} onClick={() => dispatch({ type: "openEvidence" })}>
            Show evidence
          </Button>
          <Button
            variant="quiet"
            onClick={() => {
              dispatch({ type: "reset" });
              setNotice(null);
            }}
          >
            Reset example
          </Button>
        </nav>
      </header>

      {view.dataKind === "draft" ? (
        <Banner kind="synthetic">
          <strong>Draft sample data, not for judging.</strong> Synthetic weather shaped like the Field Shift service's output.
          Real NASA results replace it when the service publishes them.
        </Banner>
      ) : null}
      {notice && !state.formOpen ? (
        <Banner kind="info">
          {notice}{" "}
          <button type="button" className="link-button" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </Banner>
      ) : null}

      <YearStrip view={view} onSelect={(year) => dispatch({ type: "selectYear", year })} />

      <FarmView strips={view.strips} onSelectCard={(card) => dispatch({ type: "selectCard", card })} />

      <section className="cards" aria-label="Three winter plans">
        {view.cards.map((c, i) => (
          <StrategyCard
            key={c.key}
            card={c}
            index={i + 1}
            selected={c.key === state.card}
            earlier={
              c.key === "cover" && rye19 && rye19Check
                ? { plan: rye19, count: rye19Check.count, denominator: rye19Check.denominator }
                : null
            }
            onSelect={() => dispatch({ type: "selectCard", card: c.key })}
            onEvidence={() => {
              dispatch({ type: "selectCard", card: c.key });
              dispatch({ type: "openEvidence" });
            }}
          />
        ))}
      </section>

      <WeatherDetail view={view} replay={replay} onSelectYear={(year) => dispatch({ type: "selectYear", year })} />

      <section className="calendar" aria-labelledby="calendar-title">
        <h2 id="calendar-title" className="section-title">
          The plans on one calendar
        </h2>
        <Timeline
          rows={CARDS.map((c) => ({ name: c.name, plan: data.compare.plans.find((p) => p.plan_id === c.planId) ?? null }))}
        />
      </section>

      <footer className="planner-foot">
        <p>
          {APP_NAME} supports a conversation with your Extension agent. It replays past weather; it does not forecast next spring
          or measure your field.
        </p>
      </footer>

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
        open={state.evidenceOpen}
        view={view}
        card={selectedCard}
        form={state.applied}
        onClose={() => dispatch({ type: "closeEvidence" })}
        returnFocusRef={evidenceBtn}
      />
    </div>
  );
}
