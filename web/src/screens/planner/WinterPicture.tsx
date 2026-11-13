import { useId, useMemo, useState, type PointerEvent, type ReactNode } from "react";
import type { Plan } from "../../api/schema";
import { fieldStateAt, MONTH_TICKS, SEASON_DAYS, seasonDay, seasonLabel } from "../../scene/growth";

/*
  One winter of one plan as a side view of the field (Compare page, Nov 13).
  The season runs left to right, September to June. What stands on the ground comes from
  the plan's dates (the same schematic stages the 3D fields use). Rain is drawn blue only
  over the stretches where nothing is growing, which is what the number above it counts.
  An illustration of planned dates: the streaks are not daily rainfall and nothing here
  is measured or computed.

  Pointing at the picture names the part under the pointer (what is on the ground and its
  planned dates). With `onOpen` the picture is a button that opens the large view.
*/

const W = 400;
const GROUND = 112;
const H = 132;
const PAD = 4;
const x = (day: number) => PAD + (day / (SEASON_DAYS - 1)) * (W - PAD * 2);
const n = (v: number) => v.toFixed(1);
/** Where a season day sits across the picture, in percent of its width. */
export const seasonPct = (day: number) => (x(day) / W) * 100;
/** The season day under a point across the picture (0 = left edge, 1 = right edge). */
export const dayAtFraction = (frac: number) =>
  Math.min(SEASON_DAYS - 1, Math.max(0, Math.round(((Math.min(1, Math.max(0, frac)) * W - PAD) / (W - PAD * 2)) * (SEASON_DAYS - 1))));
/** The picture may be taller than its drawing: the extra height is sky, so sky shapes start well above 0. */
const SKY = -280;
/** Plants are drawn 1.3 times taller than their schematic stage so they read from across a room. */
const PLANT_SCALE = `translate(0 ${GROUND}) scale(1 1.3) translate(0 ${-GROUND})`;

/** Rain streaks on a fixed lattice, so sliding the group down by one period loops without a jump. */
const RAIN_PERIOD = 22;
const rainPath = (gapX: number) => {
  let d = "";
  for (let c = -9; c * gapX < W + 24; c++) {
    const cx = c * gapX + 3;
    const phase = (((c * 37) % RAIN_PERIOD) + RAIN_PERIOD) % RAIN_PERIOD;
    for (let k = -14; k < 6; k++) {
      const y = phase + k * RAIN_PERIOD;
      d += `M${n(cx)} ${y}v7`;
    }
  }
  return d;
};
const RAIN = rainPath(9);
/** The wide strip is stretched sideways, so its streaks sit closer together in drawing units. */
const RAIN_WIDE = rainPath(4);

export type PartKind = "standing" | "bare" | "cover" | "grain" | "next";
/** One stretch of the season with the same thing on the ground. Days are season days; `to` is exclusive. */
export interface Part {
  kind: PartKind;
  from: number;
  to: number;
  title: string;
}
const CROP: Record<string, string> = { field_corn: "Corn", soybean: "Soybeans", cereal_rye: "Rye", winter_wheat: "Wheat" };
export const partDates = (p: Part) => `${seasonLabel(p.from)} to ${seasonLabel(p.to - 1)}`;

interface Drawing {
  parts: Part[];
  bare: Array<{ from: number; to: number }>;
  stubble: string;
  cornOld: string;
  cornNew: string;
  soyOld: string;
  soyNew: string;
  rye: string;
  ryeEnded: string;
  wheatGreen: string;
  wheatGold: string;
}

function draw(plan: Plan, wide = false): Drawing | null {
  if (!plan.sequence) return null;
  // The wide strip (Calendar page) is stretched sideways to any height: plants are drawn
  // closer together and their leaves narrower, so they keep their shape on screen.
  const step = wide ? { corn: 2, soy: 1, rye: 1, ended: 1, wheat: 1, stubble: 1 } : { corn: 4, soy: 3, rye: 3, ended: 2, wheat: 2, stubble: 2 };
  const f = wide ? 0.4 : 1;
  const dx = (v: number) => n(v * f);
  const seq = plan.sequence;
  const winterCrop = seq.winter.type === "none" ? undefined : CROP[seq.winter.crop_id];
  const titles: Record<PartKind, string> = {
    standing: `${CROP[seq.previous_crop_id] ?? "Crop"} before harvest`,
    bare: "Nothing growing",
    cover: `${winterCrop ?? "Cover crop"} growing`,
    grain: `${winterCrop ?? "Winter grain"} growing`,
    next: `${CROP[seq.next_crop_id] ?? "Next crop"} planted`,
  };
  let part: Part | null = null;
  const out: Drawing = { parts: [], bare: [], stubble: "", cornOld: "", cornNew: "", soyOld: "", soyNew: "", rye: "", ryeEnded: "", wheatGreen: "", wheatGold: "" };
  let run: { from: number; to: number } | null = null;
  const g = GROUND;
  for (let day = 0; day < SEASON_DAYS; day++) {
    const s = fieldStateAt(plan, day);
    if (!s) return null;
    const living = (s.cover.show && !s.cover.ended) || s.wheat.show;
    const standing = (s.corn.show && s.corn.mature) || (s.soy.show && s.soy.mature);
    const planted = s.label.includes("planted") || s.label.includes(" up");
    // Nothing growing: after the harvest, before the next planting, and no living cover or grain.
    const bare = !standing && !living && !planted;
    if (bare) {
      if (run) run.to = day + 1;
      else out.bare.push((run = { from: day, to: day + 1 }));
    } else run = null;
    const kind: PartKind = standing ? "standing" : s.wheat.show ? "grain" : living ? "cover" : planted ? "next" : "bare";
    if (part && part.kind === kind) part.to = day + 1;
    else out.parts.push((part = { kind, from: day, to: day + 1, title: titles[kind] }));

    const px = x(day);
    if (s.corn.show && s.corn.mature && day % step.corn === 0) {
      out.cornOld += `M${n(px)} ${g}v-52M${n(px)} ${g - 18}l${dx(-7)} -8M${n(px)} ${g - 31}l${dx(7)} -8`;
    } else if (s.soy.show && s.soy.mature && day % step.soy === 0) {
      out.soyOld += `M${n(px)} ${g}v-19M${n(px)} ${g - 7}l${dx(-4.5)} -7M${n(px)} ${g - 11}l${dx(4.5)} -7`;
    }
    if (s.cover.show && !s.cover.ended && day % step.rye === 0) {
      const h = 7 + 37 * s.cover.h;
      out.rye += `M${n(px)} ${g}l${dx(-2)} ${n(-h)}M${n(px)} ${g}l${dx(1.8)} ${n(-h * 0.8)}`;
    } else if (s.cover.show && s.cover.ended && day % step.ended === 0) {
      out.ryeEnded += `M${n(px)} ${g}l${dx(4.4)} -8`;
    }
    if (s.wheat.show && day % step.wheat === 0) {
      const h = 7 + 42 * s.wheat.h;
      const stem = `M${n(px)} ${g}v${n(-h)}`;
      if (s.wheat.ripe > 0.5) out.wheatGold += `${stem}M${n(px)} ${n(g - h)}v-5`;
      else out.wheatGreen += stem;
    }
    if (s.corn.show && !s.corn.mature && day % step.corn === 0) {
      const h = 50 * s.corn.h;
      out.cornNew += `M${n(px)} ${g}v${n(-h)}M${n(px)} ${n(g - h * 0.55)}l${dx(-3)} -2.5M${n(px)} ${n(g - h * 0.55)}l${dx(3)} -2.5`;
    } else if (s.soy.show && !s.soy.mature && day % step.soy === 0) {
      const h = 24 * s.soy.h;
      out.soyNew += `M${n(px)} ${g}v${n(-h)}M${n(px)} ${n(g - h)}l${dx(-2.4)} -1.6M${n(px)} ${n(g - h)}l${dx(2.4)} -1.6`;
    }
    if (bare && s.residue >= 1 && !s.cover.show && day % step.stubble === step.stubble - 1) {
      out.stubble += `M${n(px)} ${g}l${dx(1)} -5`;
    }
  }
  return out;
}

/** The parts of a plan's season, for the labels beside the large picture. */
export function partsOf(plan: Plan): Part[] {
  return draw(plan)?.parts ?? [];
}

export function WinterPicture({
  plan,
  large = false,
  wide = false,
  highlight = null,
  onHover,
  onOpen,
  openLabel,
  overlay,
}: {
  /** Drawn on top of the picture, in the same box (the Rye timing page puts its date handle here). */
  overlay?: ReactNode;
  plan: Plan;
  /** Large view: every month is labeled. */
  large?: boolean;
  /** Calendar strip: fills any box, stretched sideways; labels above and below are left to the page. */
  wide?: boolean;
  /** A part to mark from outside (the labels under the large picture). */
  highlight?: number | null;
  onHover?: (part: number | null) => void;
  /** When given, the picture is a button that opens the large view; it passes its place on screen. */
  onOpen?: (from: DOMRect) => void;
  openLabel?: string;
}) {
  const clip = useId();
  const d = useMemo(() => draw(plan, wide), [plan, wide]);
  const [hot, setHot] = useState<{ part: number; pct: number } | null>(null);
  if (!d) return null;
  const spoken = d.bare.length
    ? `Nothing growing ${d.bare.map((b) => `${seasonLabel(b.from)} to ${seasonLabel(b.to - 1)}`).join(" and ")}.`
    : "Something is growing through the whole winter.";
  const seq = plan.sequence!;
  const marks = [
    { label: "Harvest", day: seasonDay(seq.prev_harvest), side: "after" },
    { label: "Planting", day: seasonDay(seq.next_plant), side: "before" },
  ];

  const move = (e: PointerEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    const day = Math.min(SEASON_DAYS - 1, Math.max(0, Math.round(((frac * W - PAD) / (W - PAD * 2)) * (SEASON_DAYS - 1))));
    const i = d.parts.findIndex((p) => day >= p.from && day < p.to);
    if (i < 0) return;
    if (hot?.part !== i) onHover?.(i);
    setHot({ part: i, pct: frac * 100 });
  };
  const leave = () => {
    setHot(null);
    onHover?.(null);
  };
  const marked = hot?.part ?? highlight;
  const markedPart = marked === null ? null : (d.parts[marked] ?? null);
  const tip = hot ? d.parts[hot.part]! : null;

  const body = (
    <>
      <svg className="wp-svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio={wide ? "none" : "xMidYMax meet"} aria-hidden="true">
        <defs>
          <clipPath id={clip}>
            {d.bare.map((b) => (
              <rect key={b.from} x={x(b.from)} y={SKY} width={x(b.to) - x(b.from)} height={GROUND - SKY} />
            ))}
          </clipPath>
        </defs>
        {d.bare.map((b) => (
          <rect key={b.from} className="wp-zone" x={x(b.from)} y={SKY} width={x(b.to) - x(b.from)} height={GROUND - SKY} />
        ))}
        <g className="wp-slant">
          <path className="wp-rain-faint" d={wide ? RAIN_WIDE : RAIN} />
        </g>
        <g clipPath={`url(#${clip})`}>
          <g className="wp-slant">
            <path className="wp-rain" d={wide ? RAIN_WIDE : RAIN} />
          </g>
        </g>
        {marks.map((m) => (
          <path key={m.label} className="wp-mark" d={`M${n(x(m.day))} ${SKY}V${GROUND}`} />
        ))}
        <rect className="wp-soil" x={0} y={GROUND} width={W} height={H - GROUND} rx={3} />
        <rect className="wp-subsoil" x={0} y={GROUND + 9} width={W} height={H - GROUND - 9} rx={3} />
        {d.bare.map((b) => (
          <rect key={b.from} className="wp-wet" x={x(b.from)} y={GROUND} width={x(b.to) - x(b.from)} height={3.5} />
        ))}
        <g transform={PLANT_SCALE}>
          <path className="wp-stroke wp-stubble" d={d.stubble} />
          <path className="wp-stroke wp-corn-old" d={d.cornOld} />
          <path className="wp-stroke wp-soy-old" d={d.soyOld} />
          <path className="wp-stroke wp-rye-ended" d={d.ryeEnded} />
          <path className="wp-stroke wp-rye" d={d.rye} />
          <path className="wp-stroke wp-wheat-green" d={d.wheatGreen} />
          <path className="wp-stroke wp-wheat-gold" d={d.wheatGold} />
          <path className="wp-stroke wp-corn-new" d={d.cornNew} />
          <path className="wp-stroke wp-soy-new" d={d.soyNew} />
        </g>
        {markedPart ? (
          <g className="wp-hot">
            <rect x={x(markedPart.from)} y={SKY} width={x(markedPart.to) - x(markedPart.from)} height={H - SKY} />
            <path d={`M${n(x(markedPart.from))} ${H - 1.5}H${n(x(markedPart.to))}`} />
          </g>
        ) : null}
      </svg>
      {tip ? (
        <span className="wp-tip" style={{ left: `${hot!.pct}%`, transform: `translateX(-${hot!.pct}%)` }} aria-hidden="true">
          <span className="wp-tip-title">
            <span className={`wp-chip is-${tip.kind}`} />
            {tip.title}
          </span>
          <span className="wp-tip-dates">{partDates(tip)}</span>
        </span>
      ) : null}
      {onOpen ? (
        <span className="wp-expand" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 14 14">
            <path d="M8.5 2H12v3.5M12 2L8 6M5.5 12H2V8.5M2 12l4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      ) : null}
    </>
  );

  return (
    <figure className={`wp${large ? " is-large" : ""}${wide ? " is-wide" : ""}`}>
      <div className="wp-marks" aria-hidden="true">
        {marks.map((m) => (
          <span key={m.label} className={`is-${m.side}`} style={{ left: `${(x(m.day) / W) * 100}%` }}>
            {m.label}
          </span>
        ))}
      </div>
      {onOpen ? (
        <button
          type="button"
          className="wp-frame is-button"
          aria-label={openLabel ?? "Open the large picture"}
          onPointerMove={move}
          onPointerLeave={leave}
          onClick={(e) => onOpen(e.currentTarget.getBoundingClientRect())}
        >
          {body}
        </button>
      ) : (
        <div className="wp-frame" onPointerMove={overlay ? undefined : move} onPointerLeave={overlay ? undefined : leave}>
          {body}
          {overlay}
        </div>
      )}
      <div className="wp-months" aria-hidden="true">
        {MONTH_TICKS.filter((_, i) => large || i % 2 === 0).map((m) => (
          <span key={m.name} style={{ left: `${(x(m.day) / W) * 100}%` }}>
            {m.name}
          </span>
        ))}
      </div>
      <figcaption className="visually-hidden">{spoken}</figcaption>
    </figure>
  );
}
