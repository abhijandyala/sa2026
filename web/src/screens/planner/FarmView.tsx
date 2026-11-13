import { Component, lazy, Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import type { CardKey } from "../../content/strategies";
import { fieldStateAt, MONTH_TICKS, SEASON_DAYS, seasonDay, seasonLabel } from "../../scene/growth";
import type { CameraPreset, ScenePalette } from "../../scene/FarmWorld";
import type { StripVM } from "../../view/build";
import { Button, Segmented, StatusPill } from "../../ui/components";

/*
  The farm view around the 3D scene (cards 4.1, 4.3, 4.7, 4.8):
  - the 3D code loads in its own file after the planner is on screen;
  - a season scrubber with play and pause, synced to the plan dates;
  - camera presets the demo mode can use later;
  - plain-text labels and a text description, so nothing depends on seeing the 3D;
  - fallbacks: no WebGL, reduced motion (still frame, no camera moves), and phones
    (tap to load). Everything shown in 3D is also in the cards and the 2D calendar.
*/

const FarmWorld = lazy(() => import("../../scene/FarmWorld"));

const DEFAULT_DAY = seasonDay("01-15");

function hasWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return Boolean(c.getContext("webgl2") ?? c.getContext("webgl"));
  } catch {
    return false;
  }
}

function useMedia(query: string): boolean {
  const [match, setMatch] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const on = () => setMatch(m.matches);
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [query]);
  return match;
}

function readPalette(): ScenePalette {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
  return {
    cover: "#4E8F5F",
    coverEnded: "#B49A62",
    wheat: "#D2AE4E",
    wheatGreen: "#6E9E52",
    corn: "#C4A15C",
    cornGreen: "#5C9A44",
    soy: "#5E8C3A",
    soyMature: "#A88B4A",
    residue: "#D8C69A",
    rain: v("--rain", "#285A76"),
    action: v("--action", "#164B38"),
    check: "#D9822B",
    water: "#3D7FA6",
  };
}

class SceneBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export function FarmView({
  strips,
  onSelectCard,
}: {
  strips: StripVM[];
  onSelectCard: (k: CardKey) => void;
}) {
  const reducedMotion = useMedia("(prefers-reduced-motion: reduce)");
  const narrow = useMedia("(max-width: 860px)");
  const dark = useMedia("(prefers-color-scheme: dark)");
  const webgl = useMemo(hasWebGL, []);
  const [day, setDay] = useState(DEFAULT_DAY);
  const [playing, setPlaying] = useState(false);
  const [preset, setPreset] = useState<CameraPreset>("overview");
  const [mounted, setMounted] = useState(false);
  const [tapped, setTapped] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const palette = useMemo(readPalette, [dark]);

  // Mount the 3D only after the planner has painted (card 4.1).
  useEffect(() => {
    const id = window.setTimeout(() => setMounted(true), 50);
    return () => window.clearTimeout(id);
  }, []);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      setDay((d) => {
        if (d >= SEASON_DAYS - 1) {
          setPlaying(false);
          return d;
        }
        return d + 2;
      });
    }, 60);
    return () => window.clearInterval(id);
  }, [playing]);

  const states = strips.map((s) => (s.plan ? fieldStateAt(s.plan, day) : null));
  const description = strips
    .map((s, i) => `${s.name}: ${states[i]?.label ?? "not evaluated yet"}${s.status?.kind === "check" ? ", check field moisture" : ""}`)
    .join(". ");
  const show3d = webgl && mounted && (!narrow || tapped);

  let canvas: ReactNode;
  if (!webgl) {
    canvas = (
      <div className="world-fallback">
        <p className="marker">Illustration of your plan</p>
        <p>This device cannot show the 3D view. The cards and the calendar below show the same plans and dates.</p>
      </div>
    );
  } else if (narrow && !tapped) {
    canvas = (
      <div className="world-fallback">
        <p className="marker">Illustration of your plan</p>
        <p>Three fields through the season, with the selected spring's rain.</p>
        <Button variant="primary" onClick={() => setTapped(true)}>
          Show 3D farm view
        </Button>
      </div>
    );
  } else if (!show3d) {
    canvas = <div className="world-fallback" aria-busy="true">Loading 3D view…</div>;
  } else {
    canvas = (
      <SceneBoundary
        fallback={
          <div className="world-fallback">
            <p>The 3D view could not start on this device. The cards and calendar below show the same plans.</p>
          </div>
        }
      >
        <Suspense fallback={<div className="world-fallback" aria-busy="true">Loading 3D view…</div>}>
          <FarmWorld
            strips={strips}
            day={day}
            preset={preset}
            animate={!reducedMotion}
            palette={palette}
            onSelect={onSelectCard}
          />
        </Suspense>
      </SceneBoundary>
    );
  }

  const selectedIndex = strips.findIndex((s) => s.selected);

  return (
    <section className={`world-band${expanded ? " is-expanded" : ""}`} aria-labelledby="world-title">
      <h2 id="world-title" className="visually-hidden">
        Farm view
      </h2>
      <div className="world-stage">
        {canvas}
        {show3d ? (
          <ol className={`world-labels preset-${preset}`} aria-hidden="true">
            {strips.map((s, i) => (
              <li
                key={s.key}
                className={s.selected ? "is-selected" : undefined}
                hidden={preset !== "overview" && i !== selectedIndex}
              >
                <strong>{s.name}</strong>
                <span>{states[i]?.label ?? "Not evaluated yet"}</span>
                {s.status?.kind === "check" ? <StatusPill kind="check">Check field moisture</StatusPill> : null}
              </li>
            ))}
          </ol>
        ) : null}
        <p className="world-tag">Illustration of your plan</p>
        <p className="visually-hidden" aria-live="polite">
          {seasonLabel(day)}. {description}.
        </p>
      </div>

      <div className="world-controls">
        <Button
          variant="secondary"
          className="btn btn-secondary btn-small"
          onClick={() => {
            if (day >= SEASON_DAYS - 1) setDay(0);
            setPlaying((p) => !p);
          }}
          aria-pressed={playing}
        >
          {playing ? "Pause" : "Play the seasons"}
        </Button>
        <div className="scrubber">
          <label htmlFor="season-day" className="scrubber-label">
            <span className="tabular">{seasonLabel(day)}</span>
            <span className="visually-hidden"> in the planned season</span>
          </label>
          <input
            id="season-day"
            type="range"
            min={0}
            max={SEASON_DAYS - 1}
            value={day}
            aria-valuetext={`${seasonLabel(day)}. ${description}`}
            onChange={(e) => {
              setPlaying(false);
              setDay(Number(e.target.value));
            }}
          />
          <div className="scrubber-ticks" aria-hidden="true">
            {MONTH_TICKS.map((m) => (
              <span key={m.name} style={{ left: `${(m.day / (SEASON_DAYS - 1)) * 100}%` }}>
                {m.name}
              </span>
            ))}
          </div>
        </div>
        <Segmented
          label="Camera"
          value={preset}
          onChange={setPreset}
          options={[
            { value: "overview", label: "All fields" },
            { value: "field", label: "One field" },
            { value: "cutaway", label: "Soil" },
          ]}
        />
        <Button className="btn btn-quiet btn-small" onClick={() => setExpanded((e) => !e)} aria-pressed={expanded}>
          {expanded ? "Smaller" : "Enlarge"}
        </Button>
      </div>
      <p className="world-legend">
        Illustration: planned dates, the selected spring's NASA rain (only in each field's 30 days before planting) and modeled soil
        wetness (topsoil color, blue water line). Plant heights are stages, not measurements.
      </p>
    </section>
  );
}
