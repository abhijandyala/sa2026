import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useLayoutEffect, useMemo, useRef, type ReactNode } from "react";
import * as THREE from "three";
import type { CardKey } from "../content/strategies";
import type { StripVM } from "../view/build";
import { fieldStateAt, type FieldState } from "./growth";

/*
  The 3D farm (Phase 4). Three fields side by side in card order. Everything shown is
  driven by plan dates, the selected past spring and modeled soil wetness; heights are
  schematic stages, not measured growth (playbook p.41). Loaded lazily so the planner
  never waits for it (card 4.1).
*/

export type CameraPreset = "overview" | "field" | "cutaway";

export interface ScenePalette {
  cover: string;
  coverEnded: string;
  wheat: string;
  wheatGreen: string;
  corn: string;
  cornGreen: string;
  soy: string;
  soyMature: string;
  residue: string;
  rain: string;
  action: string;
  check: string;
  water: string;
}

// Illustration colors for soil and grass (not UI tokens).
const SOIL_DRY = new THREE.Color("#C9A57A");
const SOIL_WET = new THREE.Color("#4B3426");
const SUBSOIL = "#8A6748";
const DEEP = "#6B4F37";
const GRASS = "#A7B892";

const FIELD_W = 7.4;
const FIELD_D = 9;
const GAP = 1.4;
const SOIL_H = 1.6;
const X = [-(FIELD_W + GAP), 0, FIELD_W + GAP];

function seeded(seed: number) {
  return () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  };
}

/** Grid positions with a little jitter, deterministic per field and crop. */
function grid(cols: number, rows: number, seed: number, jitter = 0.08) {
  const r = seeded(seed);
  const pts: Array<[number, number, number]> = [];
  for (let i = 0; i < cols; i++) {
    for (let j = 0; j < rows; j++) {
      const x = -FIELD_W / 2 + 0.35 + (i + 0.5) * ((FIELD_W - 0.7) / cols) + (r() - 0.5) * jitter;
      const z = -FIELD_D / 2 + 0.35 + (j + 0.5) * ((FIELD_D - 0.7) / rows) + (r() - 0.5) * jitter;
      pts.push([x, z, r()]);
    }
  }
  return pts;
}

function Crop({
  geometry,
  points,
  show,
  height,
  color,
  baseH,
  tilt = 0,
}: {
  geometry: THREE.BufferGeometry;
  points: Array<[number, number, number]>;
  show: boolean;
  height: number;
  color: string;
  baseH: number;
  tilt?: number;
}) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const tmp = useMemo(() => new THREE.Object3D(), []);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    points.forEach(([x, z, r], i) => {
      const h = Math.max(0.001, height * (0.85 + r * 0.3));
      tmp.position.set(x, (baseH * h) / 2, z);
      tmp.rotation.set(tilt * (r - 0.5), r * Math.PI * 2, tilt * (0.5 - r));
      tmp.scale.set(1, h, 1);
      tmp.updateMatrix();
      mesh.setMatrixAt(i, tmp.matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  }, [points, height, baseH, tilt, tmp]);
  return (
    <instancedMesh ref={ref} args={[geometry, undefined, points.length]} visible={show && height > 0.01}>
      <meshStandardMaterial color={color} flatShading roughness={0.9} />
    </instancedMesh>
  );
}

function Residue({ amount, color, seed }: { amount: number; color: string; seed: number }) {
  const ref = useRef<THREE.InstancedMesh>(null);
  const count = 260;
  const geo = useMemo(() => new THREE.BoxGeometry(0.42, 0.025, 0.07), []);
  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const r = seeded(seed);
    const tmp = new THREE.Object3D();
    for (let i = 0; i < count; i++) {
      tmp.position.set((r() - 0.5) * (FIELD_W - 0.4), 0.015, (r() - 0.5) * (FIELD_D - 0.4));
      tmp.rotation.set(0, r() * Math.PI, 0);
      tmp.updateMatrix();
      mesh.setMatrixAt(i, tmp.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
  }, [seed, geo]);
  useLayoutEffect(() => {
    if (ref.current) ref.current.count = Math.round(count * amount);
  }, [amount]);
  return (
    <instancedMesh ref={ref} args={[geo, undefined, count]}>
      <meshStandardMaterial color={color} flatShading />
    </instancedMesh>
  );
}

function Rain({ intensity, color, animate, seed }: { intensity: number; color: string; animate: boolean; seed: number }) {
  const count = Math.round(520 * intensity);
  const ref = useRef<THREE.Points>(null);
  const positions = useMemo(() => {
    const r = seeded(seed);
    const a = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      a[i * 3] = (r() - 0.5) * FIELD_W;
      a[i * 3 + 1] = r() * 9;
      a[i * 3 + 2] = (r() - 0.5) * FIELD_D;
    }
    return a;
  }, [count, seed]);
  useFrame((_, dt) => {
    if (!animate || !ref.current) return;
    const attr = ref.current.geometry.getAttribute("position") as THREE.BufferAttribute;
    const arr = attr.array as Float32Array;
    for (let i = 0; i < count; i++) {
      arr[i * 3 + 1]! -= dt * 9;
      if (arr[i * 3 + 1]! < 0) arr[i * 3 + 1] = 9;
    }
    attr.needsUpdate = true;
  });
  if (!count) return null;
  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial color={color} size={0.07} transparent opacity={0.8} depthWrite={false} />
    </points>
  );
}

function Flag({ color }: { color: string }) {
  return (
    <group position={[-FIELD_W / 2 + 0.5, 0, FIELD_D / 2 - 0.5]}>
      <mesh position={[0, 1.1, 0]}>
        <cylinderGeometry args={[0.04, 0.04, 2.2, 6]} />
        <meshStandardMaterial color="#3a3a32" />
      </mesh>
      <mesh position={[0.42, 1.9, 0]}>
        <boxGeometry args={[0.8, 0.5, 0.04]} />
        <meshStandardMaterial color={color} />
      </mesh>
    </group>
  );
}

const GHOST = ["#E2E6DD", "#D3D8CE", "#C4CABF"] as const;

function Field({
  strip,
  state,
  x,
  index,
  palette,
  animate,
  onSelect,
}: {
  strip: StripVM;
  state: FieldState | null;
  x: number;
  index: number;
  palette: ScenePalette;
  animate: boolean;
  onSelect: (k: CardKey) => void;
}) {
  const geos = useMemo(
    () => ({
      corn: new THREE.CylinderGeometry(0.05, 0.08, 1, 5),
      tuft: new THREE.ConeGeometry(0.16, 1, 5),
      wheat: new THREE.ConeGeometry(0.11, 1, 4),
      soy: new THREE.IcosahedronGeometry(0.2, 0),
    }),
    [],
  );
  const pts = useMemo(
    () => ({
      corn: grid(9, 15, 11 + index),
      tuft: grid(18, 18, 21 + index, 0.14),
      wheat: grid(16, 20, 31 + index, 0.1),
      soy: grid(9, 24, 41 + index, 0.05),
    }),
    [index],
  );

  const w = strip.weather;
  const wet = w.wetness;
  const soilColor = useMemo(() => {
    if (wet === null || !w.wetnessRange) return SOIL_DRY.clone().lerp(SOIL_WET, 0.5);
    const [lo, hi] = w.wetnessRange;
    const t = hi > lo ? (wet - lo) / (hi - lo) : 0.5;
    return SOIL_DRY.clone().lerp(SOIL_WET, 0.15 + 0.85 * t);
  }, [wet, w.wetnessRange]);
  // A plan the backend cannot evaluate yet is drawn as a pale, empty block, never as bare soil.
  const ghost = state === null;
  const waterTop = wet === null || ghost ? null : -SOIL_H + SOIL_H * Math.min(0.95, Math.max(0.05, wet));
  const rainIntensity =
    state?.inSpringWindow && w.complete && w.totalMm !== null && w.medianMm
      ? Math.min(2, Math.max(0.08, w.totalMm / w.medianMm))
      : 0;
  const wheatColor = useMemo(
    () => "#" + new THREE.Color(palette.wheatGreen).lerp(new THREE.Color(palette.wheat), state?.wheat.ripe ?? 0).getHexString(),
    [palette, state?.wheat.ripe],
  );

  return (
    <group position={[x, 0, 0]}>
      {/* Soil block: topsoil tinted by modeled wetness, then subsoil and deeper layers on the cut face. */}
      <mesh
        position={[0, -0.175, 0]}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(strip.key);
        }}
        onPointerOver={() => (document.body.style.cursor = "pointer")}
        onPointerOut={() => (document.body.style.cursor = "")}
      >
        <boxGeometry args={[FIELD_W, 0.35, FIELD_D]} />
        <meshStandardMaterial color={ghost ? GHOST[0] : soilColor} flatShading roughness={1} />
      </mesh>
      <mesh position={[0, -0.625, 0]}>
        <boxGeometry args={[FIELD_W, 0.55, FIELD_D]} />
        <meshStandardMaterial color={ghost ? GHOST[1] : SUBSOIL} roughness={1} />
      </mesh>
      <mesh position={[0, -1.25, 0]}>
        <boxGeometry args={[FIELD_W, 0.7, FIELD_D]} />
        <meshStandardMaterial color={ghost ? GHOST[2] : DEEP} roughness={1} />
      </mesh>
      {waterTop !== null ? (
        <group position={[0, 0, FIELD_D / 2 + 0.012]}>
          <mesh position={[0, (waterTop - SOIL_H) / 2, 0]}>
            <planeGeometry args={[FIELD_W, waterTop + SOIL_H]} />
            <meshBasicMaterial color={palette.water} transparent opacity={0.42} />
          </mesh>
          <mesh position={[0, waterTop, 0.002]}>
            <planeGeometry args={[FIELD_W, 0.05]} />
            <meshBasicMaterial color={palette.water} />
          </mesh>
        </group>
      ) : null}

      {strip.selected ? <SelectionFrame color={palette.action} /> : null}

      {state ? (
        <>
          <Residue amount={state.residue} color={palette.residue} seed={51 + index} />
          <Crop
            geometry={geos.corn}
            points={pts.corn}
            show={state.corn.show}
            height={state.corn.h}
            baseH={2.1}
            color={state.corn.mature ? palette.corn : palette.cornGreen}
          />
          <Crop
            geometry={geos.tuft}
            points={pts.tuft}
            show={state.cover.show}
            height={state.cover.h}
            baseH={0.75}
            color={state.cover.ended ? palette.coverEnded : palette.cover}
            tilt={state.cover.ended ? 1.6 : 0.15}
          />
          <Crop geometry={geos.wheat} points={pts.wheat} show={state.wheat.show} height={state.wheat.h} baseH={1.15} color={wheatColor} tilt={0.12} />
          <Crop
            geometry={geos.soy}
            points={pts.soy}
            show={state.soy.show}
            height={state.soy.h}
            baseH={0.9}
            color={state.soy.mature ? palette.soyMature : palette.soy}
          />
          {rainIntensity > 0 ? <Rain intensity={rainIntensity} color={palette.rain} animate={animate} seed={61 + index} /> : null}
        </>
      ) : null}
      {strip.status?.kind === "check" ? <Flag color={palette.check} /> : null}
    </group>
  );
}

function SelectionFrame({ color }: { color: string }) {
  const t = 0.12;
  const y = 0.02;
  return (
    <group>
      {[
        [0, y, FIELD_D / 2 + t / 2, FIELD_W + 2 * t, t],
        [0, y, -FIELD_D / 2 - t / 2, FIELD_W + 2 * t, t],
      ].map(([x, yy, z, w, d], i) => (
        <mesh key={`h${i}`} position={[x!, yy!, z!]}>
          <boxGeometry args={[w!, 0.06, d!]} />
          <meshBasicMaterial color={color} />
        </mesh>
      ))}
      {[-1, 1].map((s) => (
        <mesh key={`v${s}`} position={[(s * (FIELD_W + t)) / 2, y, 0]}>
          <boxGeometry args={[t, 0.06, FIELD_D]} />
          <meshBasicMaterial color={color} />
        </mesh>
      ))}
    </group>
  );
}

const FOV = 36;
const SCENE_HALF_W = (3 * FIELD_W + 2 * GAP) / 2 + 0.6;

/**
 * Camera distance that fits a box of half-width hw and half-height hh, seen from the
 * given elevation, in a canvas of this aspect ratio. Keeps the fields filling the band
 * whether it is short and wide (1280×720) or tall (expanded view).
 */
function fit(look: [number, number, number], hw: number, hh: number, elevDeg: number, aspect: number) {
  const v = Math.tan(((FOV / 2) * Math.PI) / 180);
  const dW = hw / (v * aspect);
  const dH = hh / v;
  const d = Math.max(dW, dH) * 1.08;
  const e = (elevDeg * Math.PI) / 180;
  return { pos: [look[0], look[1] + d * Math.sin(e), look[2] + d * Math.cos(e)] as [number, number, number], look };
}

function presetFor(preset: CameraPreset, x: number, aspect: number) {
  if (preset === "field") return fit([x, -0.3, 0.3], FIELD_W / 2 + 0.6, 2.8, 32, aspect);
  if (preset === "cutaway") return fit([x, -0.7, FIELD_D / 2], FIELD_W / 2 + 0.4, 1.5, 6, aspect);
  return fit([0, -0.6, 0.4], SCENE_HALF_W, 3.2, 28, aspect);
}

function CameraRig({ preset, focusX, animate }: { preset: CameraPreset; focusX: number; animate: boolean }) {
  const { camera, invalidate, size } = useThree();
  const aspect = size.width / Math.max(1, size.height);
  // With animation off the canvas renders on demand, so a new view must ask for a frame.
  useEffect(() => invalidate(), [preset, focusX, aspect, invalidate]);
  const target = presetFor(preset, focusX, aspect);
  const look = useRef(new THREE.Vector3(...target.look));
  const first = useRef(true);
  useFrame((_, dt) => {
    const k = animate && !first.current ? 1 - Math.pow(0.0015, dt) : 1;
    first.current = false;
    camera.position.lerp(new THREE.Vector3(...target.pos), k);
    look.current.lerp(new THREE.Vector3(...target.look), k);
    camera.lookAt(look.current);
  });
  return null;
}

export default function FarmWorld({
  strips,
  day,
  preset,
  animate,
  palette,
  onSelect,
  children,
}: {
  strips: StripVM[];
  day: number;
  preset: CameraPreset;
  animate: boolean;
  palette: ScenePalette;
  onSelect: (k: CardKey) => void;
  children?: ReactNode;
}) {
  const states = strips.map((s) => (s.plan ? fieldStateAt(s.plan, day) : null));
  const selectedIndex = Math.max(0, strips.findIndex((s) => s.selected));
  return (
    <Canvas
      className="world-canvas"
      dpr={[1, 1.75]}
      camera={{ position: [0, 9, 14], fov: FOV, near: 0.1, far: 200 }}
      gl={{ antialias: true, alpha: true, preserveDrawingBuffer: true }}
      frameloop={animate ? "always" : "demand"}
      onPointerMissed={() => (document.body.style.cursor = "")}
    >
      <hemisphereLight args={["#f3f6ff", "#5b4a36", 1.05]} />
      <directionalLight position={[8, 14, 10]} intensity={1.5} />
      <mesh position={[0, -SOIL_H - 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[3 * FIELD_W + 4 * GAP + 6, FIELD_D + 6]} />
        <meshStandardMaterial color={GRASS} roughness={1} />
      </mesh>
      {strips.map((s, i) => (
        <Field key={s.key} strip={s} state={states[i]!} x={X[i]!} index={i} palette={palette} animate={animate} onSelect={onSelect} />
      ))}
      <CameraRig preset={preset} focusX={X[selectedIndex]!} animate={animate} />
      {children}
    </Canvas>
  );
}
