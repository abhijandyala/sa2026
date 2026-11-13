import { Component, lazy, Suspense, useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import type { CardKey } from "../../content/strategies";
import { fieldStateAt, MONTH_TICKS, SEASON_DAYS, seasonDay, seasonLabel } from "../../scene/growth";
import type { CameraPreset, ScenePalette } from "../../scene/FarmWorld";
import type { StripVM } from "../../view/build";
import { Segmented } from "../../ui/components";

/*
  The hero: three fields on one stage, with each plan's answer sitting on the picture.
  - the 3D code loads in its own file after the page is on screen;
  - the season plays from September to mid-winter once when it opens, then waits;
  - plain-text labels and a spoken description, so nothing depends on seeing the 3D;
  - fallbacks: no WebGL, and reduced motion (still frame, no camera drift).
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

/** Illustration colors. The selection frame uses the theme's accent. */
function readPalette(): ScenePalette {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
  return {
    cover: "#4FB56F",
    coverEnded: "#B9A36B",
    wheat: "#D2AE4E",
    wheatGreen: "#6E9E52",
    corn: "#C4A15C",
    cornGreen: "#5C9A44",
    soy: "#5E8C3A",
    soyMature: "#A88B4A",
    residue: "#E3D3A8",
    rain: v("--rain", "#0B6E86"),
    action: v("--action", "#004656"),
    accent: v("--accent", "#2ADCEB"),
    check: "#E08A1E",
    water: "#2AA8C4",
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
  spring,
  onSelectCard,
  onSpring,
  replay = false,
}: {
  strips: StripVM[];
  /** The spring being replayed, shown as a chip on the stage. */
  spring: { year: number; text: string; dry: boolean } | null;
  onSelectCard: (k: CardKey) => void;
  onSpring: () => void;
  /** Past springs page: hold the scene inside the 30 days before planting, where the replayed rain falls. */
  replay?: boolean;
}) {
  const reducedMotion = useMedia("(prefers-reduced-motion: reduce)");
  const webgl = useMemo(hasWebGL, []);
  const [day, setDay] = useState(reducedMotion ? DEFAULT_DAY : 0);
  const [playing, setPlaying] = useState(false);
  const [intro, setIntro] = useState(!reducedMotion);
  const [preset, setPreset] = useState<CameraPreset>("overview");
  const [mounted, setMounted] = useState(false);
  const palette = useMemo(readPalette, []);

  // Mount the 3D only after the page has painted.
  useEffect(() => {
    const id = window.setTimeout(() => setMounted(true), 50);
    return () => window.clearTimeout(id);
  }, []);

  // Opening move: the season runs from September to mid-winter once, so the fields visibly differ.
  useEffect(() => {
    if (!intro || !mounted || replay) return;
    const id = window.setInterval(() => {
      setDay((d) => {
        if (d >= DEFAULT_DAY) {
          setIntro(false);
          return DEFAULT_DAY;
        }
        return Math.min(DEFAULT_DAY, d + 3);
      });
    }, 36);
    return () => window.clearInterval(id);
  }, [intro, mounted]);

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

  // In replay mode the date sits 12 days before the selected plan's planting date.
  const plantMd = (strips.find((s) => s.selected) ?? strips[0])?.plan?.sequence?.next_plant ?? strips.find((s) => s.plan?.sequence)?.plan?.sequence?.next_plant;
  const shown = replay && plantMd ? Math.max(0, seasonDay(plantMd) - 12) : day;
  const states = strips.map((s) => (s.plan ? fieldStateAt(s.plan, shown) : null));
  const description = strips
    .map((s, i) => `${s.name}: ${states[i]?.label ?? "not evaluated yet"}${s.status?.kind === "check" ? ", check field moisture" : ""}`)
    .join(". ");
  const show3d = webgl && mounted;
  const selectedIndex = strips.findIndex((s) => s.selected);
  const selectedStrip = strips[selectedIndex] ?? null;
  const selectedState = selectedIndex >= 0 ? states[selectedIndex] : null;
  const stop = () => {
    setIntro(false);
    setPlaying(false);
  };

  const loading = (
    <div className="fb-stage-fallback" aria-busy="true">
      <span className="sk-fields" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span>Loading the 3D fields…</span>
    </div>
  );

  let canvas: ReactNode;
  if (!webgl) {
    canvas = (
      <div className="fb-stage-fallback">
        <p>This device cannot show the 3D fields. The cards here and the calendar below show the same plans and dates.</p>
      </div>
    );
  } else if (!show3d) {
    canvas = loading;
  } else {
    canvas = (
      <SceneBoundary
        fallback={
          <div className="fb-stage-fallback">
            <p>The 3D fields could not start on this device. The cards and the calendar show the same plans.</p>
          </div>
        }
      >
        <Suspense fallback={loading}>
          <FarmWorld strips={strips} day={shown} preset={preset} animate={!reducedMotion} palette={palette} onSelect={onSelectCard} />
        </Suspense>
      </SceneBoundary>
    );
  }

  const pct = (shown / (SEASON_DAYS - 1)) * 100;

  return (
    <div className="fb-stage-wrap">
      <div className="fb-stage">
        {canvas}

        <p className="fb-stage-tag">Illustration of your plan</p>
        {spring ? (
          <button type="button" className={`fb-stage-spring${spring.dry ? " is-dry" : ""}`} onClick={onSpring}>
            <span className="fb-stage-spring-text">
              Spring {spring.year} · {spring.text}
            </span>
          </button>
        ) : null}

        {preset === "overview" ? (
          <p className="fb-stage-key">
            <span className="lg lg-water" /> Blue band: soil water that spring, modeled
          </p>
        ) : null}
        {preset !== "overview" && selectedStrip ? (
          <div className="fb-stage-legend">
            <p className="fb-stage-legend-title">
              {selectedStrip.name}: {selectedState?.label ?? "not evaluated yet"}
            </p>
            {preset === "cutaway" ? (
              <ul>
                <li>
                  <span className="lg lg-roots" /> Roots while a cover or grain crop is alive
                </li>
                <li>
                  <span className="lg lg-water" /> Wetter soil below the blue line
                  {selectedStrip.weather.wetness !== null ? `: modeled wetness ${selectedStrip.weather.wetness.toFixed(2)} of 1` : ""}
                </li>
                <li>
                  <span className="lg lg-soil" /> Darker topsoil means a wetter spring. A regional model, not your field
                </li>
              </ul>
            ) : (
              <ul>
                <li>
                  <span className="lg lg-cover" /> Living plants at their planned stage, not measured growth
                </li>
                <li>
                  <span className="lg lg-residue" /> Straw is residue left from the last harvest
                </li>
              </ul>
            )}
          </div>
        ) : null}
        <p className="visually-hidden" aria-live="polite">
          {intro && !replay ? "" : `${seasonLabel(shown)}. ${description}.`}
        </p>
      </div>

      <div className="fb-season">
        {replay ? (
          <p className="fb-season-note">
            <strong className="tabular">{seasonLabel(shown)}</strong> · inside the 30 days before planting, with that spring's rain
          </p>
        ) : (
          <>
        <button
          type="button"
          className="fb-play"
          aria-pressed={playing}
          aria-label={playing ? "Pause the season" : "Play the season"}
          onClick={() => {
            setIntro(false);
            if (day >= SEASON_DAYS - 1) setDay(0);
            setPlaying((p) => !p);
          }}
        >
          {playing ? (
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
              <path d="M3 2h3v10H3zM8 2h3v10H8z" fill="currentColor" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
              <path d="M3.5 1.8v10.4l8.4-5.2z" fill="currentColor" />
            </svg>
          )}
        </button>
        <label htmlFor="season-day" className="fb-season-date tabular">
          {seasonLabel(day)}
          <span className="visually-hidden"> in the planned season</span>
        </label>
        <div className="fb-scrub" style={{ "--p": `${pct}%` } as CSSProperties}>
          <input
            id="season-day"
            type="range"
            min={0}
            max={SEASON_DAYS - 1}
            value={day}
            aria-valuetext={`${seasonLabel(day)}. ${description}`}
            onChange={(e) => {
              stop();
              setDay(Number(e.target.value));
            }}
          />
          <div className="fb-scrub-ticks" aria-hidden="true">
            {MONTH_TICKS.map((m) => (
              <span key={m.name} style={{ left: `${(m.day / (SEASON_DAYS - 1)) * 100}%` }}>
                {m.name}
              </span>
            ))}
          </div>
        </div>
          </>
        )}
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
      </div>
    </div>
  );
}
