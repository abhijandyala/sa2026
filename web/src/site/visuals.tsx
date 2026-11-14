import { useEffect, useState, type CSSProperties } from "react";
import { monthDay } from "../data/format";
import { Roll } from "../ui/Roll";
import { WinterPicture } from "../screens/planner/WinterPicture";
import { useInView, whole, type Numbers } from "./Site";

/*
  Small animated pictures for the marketing pages, each drawn from the saved record:
  the same glass, dots and field pictures the planner uses, set on the reference page's
  line-art panel. They replace the stock photos and UI screenshots of the page this
  layout follows.
*/

/** Thin contour lines, cyan to violet, behind a floating card. */
export function LinePanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="st-lines">
      <svg className="st-lines-art" viewBox="0 0 600 420" preserveAspectRatio="none" aria-hidden="true">
        {Array.from({ length: 26 }, (_, i) => (
          <path
            key={i}
            d={`M${-20 + i * 9} 420 V${250 - i * 3} Q${-20 + i * 9} ${120 - i * 2} ${160 + i * 10} ${110 - i * 3} H620`}
            fill="none"
            stroke={i % 2 ? "#2ADCEB" : "#B58CF0"}
            strokeOpacity={0.16 + (i / 26) * 0.4}
            strokeWidth="1"
          />
        ))}
      </svg>
      <div className="st-lines-card">{children}</div>
    </div>
  );
}

/** Rain on bare ground: the glass and the field, switching between no cover and rye. */
export function BareRainCard({ n }: { n: Numbers }) {
  const [ref, seen] = useInView<HTMLDivElement>(false);
  const [rye, setRye] = useState(false);
  useEffect(() => {
    if (!seen) return;
    const id = window.setInterval(() => setRye((v) => !v), 3200);
    return () => window.clearInterval(id);
  }, [seen]);
  const card = n.view.cards.find((c) => c.key === (rye ? "cover" : "current"));
  const leg = card?.legs[0];
  const max = Math.max(1, n.bareNow ?? 0, n.bareCover ?? 0);
  return (
    <div className="st-card" ref={ref}>
      <p className="st-card-kicker">{card?.content.name} · winter after corn</p>
      <p className="st-card-big">
        <span className="cmp-glass" aria-hidden="true">
          <span style={{ height: `${Math.min(1, (leg?.soilMm ?? 0) / max) * 100}%` }} />
        </span>
        <Roll value={whole(leg?.soilMm)} />
        <span className="st-card-unit">mm of rain with nothing growing</span>
      </p>
      {leg?.plan?.sequence ? <WinterPicture plan={leg.plan} /> : null}
    </div>
  );
}

/** Dry springs: one dot per spring, the flagged ones lighting up in turn. */
export function SpringDotsCard({ n }: { n: Numbers }) {
  const [ref, seen] = useInView<HTMLDivElement>(false);
  const leg = n.view.cards.find((c) => c.key === "cover")?.legs[0];
  const flagged = new Set(leg?.checkYears ?? []);
  const order = [...flagged].sort((a, b) => a - b);
  return (
    <div className={`st-card${seen ? " is-playing" : ""}`} ref={ref}>
      <p className="st-card-kicker">
        Springs since {n.firstYear ?? ""}, one dot each
      </p>
      <p className="st-card-big">
        <Roll value={seen ? whole(n.checks) : "0"} />
        <span className="st-card-unit">of {n.of ?? n.springs} to check soil moisture first</span>
      </p>
      <div className="st-dotgrid" aria-hidden="true">
        {(leg?.springs ?? []).map((s) => (
          <span
            key={s.year}
            className={flagged.has(s.year) ? "is-check" : undefined}
            style={{ "--d": `${order.indexOf(s.year) * 140}ms` } as CSSProperties}
          />
        ))}
      </div>
      <p className="st-card-foot">Amber: a dry spring with the rye ended less than two weeks before planting.</p>
    </div>
  );
}

/** The two-week rule: the plan's gap against the guidance. */
export function GapCard({ n }: { n: Numbers }) {
  const [ref, seen] = useInView<HTMLDivElement>(false);
  const rye = n.view.rye;
  const boundary = rye && rye.boundaryIndex !== null ? rye.points[rye.boundaryIndex] : null;
  const guide = boundary?.gap_days ?? null;
  const gap = n.gap;
  const max = Math.max(1, gap ?? 0, guide ?? 0);
  return (
    <div className={`st-card${seen ? " is-playing" : ""}`} ref={ref}>
      <p className="st-card-kicker">Days between ending the rye and planting</p>
      <div className="st-gap">
        <div>
          <span>Your plan</span>
          <span className="st-gap-track">
            <i className="is-plan" style={{ width: `${((gap ?? 0) / max) * 100}%` }} />
          </span>
          <strong className="tabular">{gap ?? "–"} days</strong>
        </div>
        <div>
          <span>NC State</span>
          <span className="st-gap-track">
            <i className="is-guide" style={{ width: `${((guide ?? 0) / max) * 100}%` }} />
          </span>
          <strong className="tabular">{guide ?? "–"} days</strong>
        </div>
      </div>
      {boundary && rye ? (
        <p className="st-card-foot">
          End the rye by {monthDay(boundary.terminate)} and the check clears in all {rye.denominator} springs.
        </p>
      ) : null}
    </div>
  );
}

/** Three plates in the air: what the planner stacks into one picture. */
export function LayerStack() {
  return (
    <div className="st-stack" aria-hidden="true">
      <div className="st-plate is-3">
        <span>Your dates</span>
      </div>
      <div className="st-plate is-2">
        <span>NC State guidance</span>
      </div>
      <div className="st-plate is-1">
        <span>NASA past weather</span>
      </div>
      <div className="st-plate is-glass" />
    </div>
  );
}

/**
  The two sources as ring badges, with a tube of rings running off the card behind them
  (the dark trust card's art). The tube drifts by one ring spacing and loops, so it reads as flowing.
*/
export function SourceBadges() {
  const R = 66;
  const STEP = 8;
  const badges = [
    { x: 96, top: "NASA", bottom: "POWER" },
    { x: 236, top: "NC State", bottom: "Extension" },
  ];
  const rings = Array.from({ length: 52 }, (_, i) => 236 + i * STEP);
  return (
    <svg className="st-badges" viewBox="0 0 540 400" preserveAspectRatio="xMinYMid slice" aria-hidden="true">
      <defs>
        <linearGradient id="st-tube-ink" gradientUnits="userSpaceOnUse" x1="236" y1="0" x2="560" y2="0">
          <stop offset="0" stopColor="#2adceb" />
          <stop offset="1" stopColor="#b58cf0" />
        </linearGradient>
      </defs>
      <g className="st-tube" stroke="url(#st-tube-ink)">
        {rings.map((x) => (
          <circle key={x} cx={x} cy="200" r={R} />
        ))}
      </g>
      {badges.map((b) => (
        <g key={b.top} className="st-badge">
          <circle cx={b.x} cy="200" r={R} />
          <circle className="is-inner" cx={b.x} cy="200" r={R - 8} />
          <text x={b.x} y="192">
            {b.top}
          </text>
          <line x1={b.x - 30} x2={b.x + 30} y1="200.5" y2="200.5" />
          <text x={b.x} y="220">
            {b.bottom}
          </text>
        </g>
      ))}
    </svg>
  );
}

/** A slow wheel of the inputs the planner takes. */
export function InputWheel() {
  const items = ["Corn harvest", "Rye seeding", "Rye end date", "Soybean planting", "Soybean harvest", "Corn planting", "Soil texture", "Moisture concern", "Irrigation", "Priorities", "Place", "Wheat dates"];
  return (
    <div className="st-wheel" aria-hidden="true">
      <span className="st-wheel-hub">
        <span className="fb-mark" />
      </span>
      <span className="st-wheel-track" />
      <div className="st-wheel-mask">
        <div className="st-wheel-ring">
          {items.map((label, i) => (
            <span key={label} style={{ "--a": `${(i / items.length) * 360}deg` } as CSSProperties}>
              <b>
                <i />
                {label}
              </b>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

/** The request and the answer, as the service really exchanges them. */
export function ApiPanel({ n }: { n: Numbers }) {
  const [ref, seen] = useInView<HTMLDivElement>(false);
  const plan = n.view.cards.find((c) => c.key === "cover")?.legs[0]?.plan;
  const w = plan?.sequence?.winter;
  const lines = [
    "POST /v1/plans/compare",
    "{",
    `  "plan_id": "${plan?.plan_id ?? "corn_soy__rye"}",`,
    `  "winter": { "kind": "cover",`,
    `    "seed": "${w && w.type === "cover" ? w.seed : "10-01"}", "terminate": "${w && w.type === "cover" ? w.terminate : "04-30"}" },`,
    `  "next_plant": "${plan?.sequence?.next_plant ?? "05-12"}"`,
    "}",
    "",
    "200 OK",
    `  "rain_mm_outside_cover": ${n.bareCover ?? "…"},`,
    `  "count": ${n.checks ?? "…"}, "denominator": ${n.of ?? "…"}`,
  ];
  return (
    <div className={`st-code${seen ? " is-playing" : ""}`} ref={ref} aria-hidden="true">
      <p className="st-code-head">
        Field Shift API <span>200 OK</span>
      </p>
      <pre>
        {lines.map((l, i) => (
          <span key={i} style={{ "--d": `${i * 160}ms` } as CSSProperties} className={i >= 8 ? "is-out" : undefined}>
            {l || " "}
            {"\n"}
          </span>
        ))}
      </pre>
    </div>
  );
}

/** The printed summary, its boxes being ticked. */
export function SummarySheet() {
  const [ref, seen] = useInView<HTMLDivElement>(false);
  const rows = ["Field moisture concern", "Rye seeding date", "Soil temperature at planting", "Nitrogen after rye"];
  return (
    <div className={`st-sheet${seen ? " is-playing" : ""}`} ref={ref} aria-hidden="true">
      <div className="st-sheet-page">
        <p className="st-sheet-title">Bring this to your Extension agent</p>
        <div className="st-sheet-cols">
          <span />
          <span />
          <span />
        </div>
        <p className="st-sheet-sub">To discuss</p>
        {rows.map((r, i) => (
          <p key={r} className="st-sheet-row" style={{ "--d": `${600 + i * 700}ms` } as CSSProperties}>
            <i />
            {r}
          </p>
        ))}
        <p className="st-sheet-sub">Your questions</p>
        <span className="st-sheet-line" />
        <span className="st-sheet-line" />
      </div>
    </div>
  );
}

/** A question typed into a box, then the answer the Rye timing page gives. */
export function AskRye({ n }: { n: Numbers }) {
  const [ref, seen] = useInView<HTMLDivElement>(false);
  const question = "What if I end the rye a week earlier?";
  const [typed, setTyped] = useState(0);
  useEffect(() => {
    if (!seen) {
      setTyped(0);
      return;
    }
    if (typed >= question.length) return;
    const id = window.setTimeout(() => setTyped((c) => c + 1), 46);
    return () => window.clearTimeout(id);
  }, [seen, typed, question.length]);
  const rye = n.view.rye;
  const done = typed >= question.length;
  const rows = rye
    ? [
        { p: rye.proposed, tag: "Your plan" },
        ...(rye.earlierIndex !== null ? [{ p: rye.points[rye.earlierIndex]!, tag: "A week earlier" }] : []),
        ...(rye.boundaryIndex !== null ? [{ p: rye.points[rye.boundaryIndex]!, tag: "Last date that clears" }] : []),
      ]
    : [];
  return (
    <div className={`st-ask${done ? " is-answered" : ""}`} ref={ref}>
      <p className="st-ask-q">
        <span className="st-ask-who" aria-hidden="true" />
        <span aria-label={question}>
          <span aria-hidden="true">{question.slice(0, typed)}</span>
          {!done ? <i className="st-caret" aria-hidden="true" /> : null}
        </span>
      </p>
      <div className="st-ask-a">
        <p className="st-ask-lead">
          <span className="fb-mark" aria-hidden="true" /> Replayed against {rye?.denominator ?? n.springs} past springs
        </p>
        <ul>
          {rows.map(({ p, tag }, i) => (
            <li key={p.terminate} style={{ "--d": `${200 + i * 220}ms` } as CSSProperties}>
              <span>End rye {monthDay(p.terminate)}</span>
              <span>{p.gap_days} days before planting</span>
              <span className={(p.checks_count ?? 0) > 0 ? "is-warn" : "is-clear"}>
                {p.checks_count ?? "–"} of {rye?.denominator} springs to check
              </span>
              <span className="st-ask-tag">{tag}</span>
            </li>
          ))}
        </ul>
        <p className="st-ask-foot">NC State: end the cover at least two weeks before planting soybeans if low soil moisture is a concern.</p>
      </div>
    </div>
  );
}
