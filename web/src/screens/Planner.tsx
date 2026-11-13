import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { APP_NAME, TAGLINE, TASK_TITLE } from "../config";
import { cardByKey, type Leg } from "../content/strategies";
import type { Client } from "../api/client";
import { sameForm, sampleForm } from "../state/form";
import { hasPendingEdits, initialState, reducer } from "../state/model";
import { applyUrlView, fromHash, toHash } from "../state/url";
import { useReplay, type ApplyOutcome, type Loaded } from "../state/useData";
import { buildView, validYears } from "../view/build";
import { Banner, Button, Segmented, StatusPill } from "../ui/components";
import { G } from "../ui/Glossary";
import { EvidenceDrawer } from "./planner/EvidenceDrawer";
import { FarmFormDrawer } from "./planner/FarmFormDrawer";
import { StrategyCard } from "./planner/StrategyCard";
import { Timeline } from "./planner/Timeline";
import { Almanac } from "./planner/Almanac";
import { WeatherDetail } from "./planner/WeatherDetail";
import { FarmView } from "./planner/FarmView";
import { RyeDeepDive } from "./planner/RyeDeepDive";
import { PriorityPicker } from "./planner/PriorityPicker";

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
  const ryeEnds = useMemo(() => new Set((data.sensitivity?.points ?? []).map((p) => p.terminate)), [data.sensitivity]);
  const [state, dispatch] = useReducer(reducer, sample, (s) =>
    applyUrlView(initialState(s), fromHash(window.location.hash, years, ryeEnds)),
  );
  const ryeRef = useRef<HTMLElement>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [audit, setAudit] = useState(false);
  const formBtn = useRef<HTMLButtonElement>(null);
  const evidenceBtn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const next = toHash(state);
    if (next !== window.location.hash) history.replaceState(null, "", next);
  }, [state]);

  // Follow the link when only the hash changes (a pasted share link, Back/Forward).
  useEffect(() => {
    const onHash = () => dispatch({ type: "applyLink", view: fromHash(window.location.hash, years, ryeEnds) });
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [years, ryeEnds]);

  // Bring the deep-dive into view and move focus to it when it opens.
  useEffect(() => {
    if (!state.ryeOpen) return;
    // Show the 3D view and the slider together, so dragging visibly moves the rye field.
    const band = document.querySelector<HTMLElement>(".world-band");
    (band ?? ryeRef.current)?.scrollIntoView({ block: "start" });
    ryeRef.current?.focus({ preventScroll: true });
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

  const status =
    view.dataKind === "live" ? (
      <StatusPill kind="live">Live results for your dates</StatusPill>
    ) : view.dataKind === "draft" ? (
      <StatusPill kind="synthetic">Draft sample data</StatusPill>
    ) : (
      <StatusPill kind="saved">Saved NASA record</StatusPill>
    );

  return (
    <div className={`planner${audit ? " audit-on" : ""}`}>
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
          <Button
            variant="quiet"
            className="btn btn-quiet header-link-small"
            onClick={() => {
              dispatch({ type: "reset" });
              setNotice(null);
            }}
          >
            Reset example
          </Button>
          <a className="header-link header-link-small" href="?view=methods">
            How it works
          </a>
        </div>
        <nav className="header-actions" aria-label="Plan actions">
          <Segmented
            label="Which winter"
            value={String(view.leg) as "1" | "2"}
            onChange={(v) => dispatch({ type: "selectLeg", leg: Number(v) as Leg })}
            options={[
              { value: "1", label: "Winter 1: corn → soy" },
              { value: "2", label: "Winter 2: soy → corn" },
            ]}
          />
          <PriorityPicker priorities={state.priorities} onToggle={(priority) => dispatch({ type: "togglePriority", priority })} />
          <span className="header-actions-gap" aria-hidden="true" />
          <Button variant="quiet" className="btn btn-quiet btn-small" aria-pressed={audit} onClick={() => setAudit((a) => !a)}>
            {audit ? "Hide sources" : "Show sources"}
          </Button>
          <Button ref={formBtn} variant="primary" onClick={() => dispatch({ type: "openForm" })}>
            Edit farm dates
          </Button>
          {pending ? <span className="pending-note">Edited, not applied</span> : null}
          <Button ref={evidenceBtn} onClick={() => dispatch({ type: "openEvidence" })}>
            Show evidence
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

      <div className="hero">
        <FarmView strips={view.strips} onSelectCard={(card) => dispatch({ type: "selectCard", card })} />
        <Almanac view={view} onSelect={(year) => dispatch({ type: "selectYear", year })} />
      </div>

      {state.ryeOpen && view.rye ? (
        <RyeDeepDive
          ref={ryeRef}
          rye={view.rye}
          emphasis={state.emphasis}
          onEmphasis={(emphasis) => dispatch({ type: "setEmphasis", emphasis })}
          onChoose={(md) => dispatch({ type: "setRyeEnd", md })}
          onClose={() => dispatch({ type: "closeRye" })}
        />
      ) : null}

      <section className="cards" aria-label="Three winter plans">
        {view.cards.map((c, i) => (
          <StrategyCard
            key={c.key}
            card={c}
            index={i + 1}
            selected={c.key === state.card}
            earlier={
              c.key === "cover" && state.leg === 1 && earlierPoint && view.rye
                ? { terminate: earlierPoint.terminate, gap: earlierPoint.gap_days, count: earlierPoint.checks_count, denominator: view.rye.denominator }
                : null
            }
            onSelect={() => dispatch({ type: "selectCard", card: c.key })}
            onAdjust={c.key === "cover" && view.rye ? () => dispatch({ type: "openRye" }) : undefined}
            planSource={sameForm(state.applied, state.sample) ? "sample" : "farmer"}
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
          rows={view.cards.map((c) => ({ name: c.content.name, plan: c.plan }))}
        />
      </section>

      <footer className="planner-foot">
        <p>
          {APP_NAME} supports a conversation with your <G id="extension">Extension agent</G>. It replays past weather; it does not
          forecast next spring or measure your field. <a href="?view=credits">Data and credits</a>
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
        replay={replay}
        priorities={state.priorities}
        emphasis={state.emphasis}
        onClose={() => dispatch({ type: "closeEvidence" })}
        returnFocusRef={evidenceBtn}
      />
    </div>
  );
}
