import { StrictMode, Suspense, lazy, useEffect, useMemo } from "react";
import { createRoot } from "react-dom/client";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components.css";
import "./styles/layout.css";
import "./styles/fieldback.css";
import { seasonDay } from "./scene/growth";
import type { ScenePalette } from "./scene/FarmWorld";
import { WinterPicture } from "./screens/planner/WinterPicture";
import { useSiteData } from "./site/useSiteData";
import { buildView } from "./view/build";

/*
  Development only (npm run dev, then /shots.html?what=…). Renders one of the app's own
  visuals alone on a transparent page, at a fixed size, so it can be captured for slides
  without the rest of the screen. Not part of the build: only index.html is.

    ?what=plot&i=0|1|2     one 3D field (no cover, rye, wheat) at mid-winter
    ?what=winter&i=0|1|2   that plan's side-view winter picture
    ?what=dots             the 45 springs, with the ones flagged for a moisture check
*/
const FarmWorld = lazy(() => import("./scene/FarmWorld"));

const PALETTE: ScenePalette = {
  cover: "#4FB56F",
  coverEnded: "#B9A36B",
  wheat: "#D2AE4E",
  wheatGreen: "#6E9E52",
  corn: "#C4A15C",
  cornGreen: "#5C9A44",
  soy: "#5E8C3A",
  soyMature: "#A88B4A",
  residue: "#E3D3A8",
  rain: "#0B6E86",
  action: "#004656",
  accent: "#2ADCEB",
  check: "#E08A1E",
  water: "#2AA8C4",
};

/** Widens the lens after the scene has aimed its camera, so the whole field is in frame with room to spare. */
function Widen({ fov }: { fov: number }) {
  const { camera, invalidate } = useThree();
  useEffect(() => {
    const lens = camera as THREE.PerspectiveCamera;
    lens.fov = fov;
    lens.updateProjectionMatrix();
    invalidate();
  }, [camera, fov, invalidate]);
  return null;
}

function Shot() {
  const q = new URLSearchParams(window.location.search);
  const what = q.get("what") ?? "plot";
  const i = Number(q.get("i") ?? 0);
  const day = seasonDay(q.get("day") ?? "01-15");
  const data = useSiteData();
  const view = useMemo(() => (data ? buildView(data, { card: "cover", year: null, leg: 1 }) : null), [data]);
  if (!view || !data) return null;

  if (what === "plot") {
    // One field, never marked as selected, so nothing but the field itself is drawn.
    const strip = { ...view.strips[i]!, selected: false, status: null as never };
    return (
      <div style={{ width: 1200, height: 900 }}>
        <Suspense fallback={null}>
          <FarmWorld strips={[strip]} day={day} preset="field" animate palette={PALETTE} onSelect={() => {}}>
            <Widen fov={Number(q.get("fov") ?? 40)} />
          </FarmWorld>
        </Suspense>
      </div>
    );
  }

  if (what === "winter") {
    const plan = view.strips[i]!.plan;
    return <div style={{ width: 1400, padding: 24 }}>{plan ? <WinterPicture plan={plan} large /> : null}</div>;
  }

  // The 45 springs as dots; the backend's own list says which ones the rye plan flags.
  const rye = data.compare.plans.find((p) => p.plan_id === "corn_soy__rye");
  const flagged = new Set(rye?.spring_checks[0]?.qualifying_years ?? []);
  const years = Object.values(data.compare.spring_windows ?? {})[0]?.years.map((y) => y.year) ?? [];
  return (
    <svg width={1500} height={300} viewBox="0 0 1500 300" role="img" aria-label={`${flagged.size} of ${years.length} springs flagged`}>
      {years.map((y, k) => (
        <circle key={y} cx={50 + (k % 15) * 100} cy={50 + Math.floor(k / 15) * 100} r={34} fill={flagged.has(y) ? "#E08A1E" : "#D5D9DC"} />
      ))}
    </svg>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Shot />
  </StrictMode>,
);
