import { useEffect, useState, type ReactNode, type RefObject } from "react";
import type { OtherCheck, Plan } from "../../api/schema";
import { SOURCES, type Claim } from "../../content/strategies";
import { monthDay } from "../../data/format";
import type { CardVM, EraVM } from "../../view/build";
import { Button, Segmented, SourceChip, Src } from "../../ui/components";
import { WinterCell } from "./WinterCell";
import { WinterZoom } from "./WinterZoom";

/*
  One plan, looked at closely (redesigned Nov 13 to match the Compare page).
  Top card: both winters side by side, each as a rain glass, its number and the field
  seen from the side; the two winters are never added. The picture is the calendar.
  Below, three small cards: what to do before planting (counts first, one list at a
  time), what the plan is about (why, benefits, risks, what is not known), and how the
  earlier and recent springs compare.
*/

const ERA_TEXT: Record<EraVM["result"], string> = {
  more_frequent_recent: "More often in recent years.",
  less_frequent_recent: "Less often in recent years.",
  similar: "About as often in both periods.",
  insufficient_data: "Not enough complete years to compare the two periods.",
};

/** Four plain groups instead of seven verdict words: what to act on, what to look at, what is fine, what the tool could not check. */
const GROUPS: Array<{ id: string; title: string; tone: "act" | "look" | "fine"; verdicts: OtherCheck["verdict"][] }> = [
  { id: "act", title: "Talk over first", tone: "act", verdicts: ["avoid", "caution"] },
  { id: "look", title: "Check in the field", tone: "look", verdicts: ["manual_check"] },
  { id: "fine", title: "Already fine", tone: "fine", verdicts: ["preferred", "acceptable"] },
  { id: "unknown", title: "Could not be checked", tone: "look", verdicts: ["unknown"] },
];
type About = "why" | "benefits" | "risks" | "gaps";
const clean = (reason: string) => reason.replace(/^[a-z_]+:\s*/, "").replace(/^./, (ch) => ch.toUpperCase());
const FIT_TEXT = { matches: "Matches", partly: "Partly matches", tradeoff: "Trade-off" } as const;
const CROP: Record<string, string> = { field_corn: "Corn", soybean: "Soybeans" };

export function sequenceText(plan: Plan | null): string {
  const seq = plan?.sequence;
  if (!seq) return "";
  const w = seq.winter;
  const prev = CROP[seq.previous_crop_id] ?? seq.previous_crop_id;
  const next = (CROP[seq.next_crop_id] ?? seq.next_crop_id).toLowerCase();
  const harvest = monthDay(seq.prev_harvest);
  const plant = monthDay(seq.next_plant);
  if (w.type === "cover") return `${prev} harvest ${harvest}, rye ${monthDay(w.seed)} to ${monthDay(w.terminate)}, ${next} planted ${plant}`;
  if (w.type === "winter_grain") return `${prev} harvest ${harvest}, wheat ${monthDay(w.plant)} to ${monthDay(w.harvest)}, ${next} planted ${plant}`;
  return `${prev} harvest ${harvest}, no planted cover, ${next} planted ${plant}`;
}

function ClaimSource({ claim }: { claim: Claim }) {
  if (!claim.source) return null;
  const src = SOURCES[claim.source];
  return <SourceChip kind={src.kind === "nasa" ? "nasa" : src.kind === "ncstate" ? "ncstate" : "calculated"} href={src.url} title={src.title} />;
}

function Claims({ claims, tone = "note" }: { claims: Claim[]; tone?: "good" | "risk" | "gap" | "note" }) {
  return (
    <ul className={`pd-claims pd-tone-${tone}`}>
      {claims.map((c) => (
        <li key={c.text}>
          {c.text} <ClaimSource claim={c} />
        </li>
      ))}
    </ul>
  );
}

/** The winter's dates in a few words: what is seeded, when it ends, when the next crop goes in. */
function datesLine(plan: Plan | null): string {
  const seq = plan?.sequence;
  if (!seq) return "";
  const w = seq.winter;
  const next = `${(CROP[seq.next_crop_id] ?? seq.next_crop_id).toLowerCase()} planted ${monthDay(seq.next_plant)}`;
  if (w.type === "cover") return `Rye ${monthDay(w.seed)} to ${monthDay(w.terminate)} · ${next}`;
  if (w.type === "winter_grain") return `Wheat ${monthDay(w.plant)} to ${monthDay(w.harvest)} · ${next}`;
  return `Harvest ${monthDay(seq.prev_harvest)} · ${next}`;
}

export function PlanDetail({
  card,
  axisMax,
  earlier,
  planSource,
  selectedYear,
  onPickYear,
  onWhy,
  onAdjust,
  onEvidence,
  evidenceRef,
  toolbar,
}: {
  card: CardVM;
  /** The largest rain value across all plans, so a glass looks the same here as on the Compare page. */
  axisMax: number;
  earlier: { terminate: string; gap: number; count: number | null; denominator: number } | null;
  planSource: "sample" | "farmer";
  selectedYear: number | null;
  onPickYear: (year: number, leg: 1 | 2) => void;
  onWhy: (kind: "rain" | "check", leg: 1 | 2) => void;
  onAdjust?: () => void;
  onEvidence: () => void;
  /** Focus returns here when the evidence drawer closes. */
  evidenceRef?: RefObject<HTMLButtonElement>;
  /** Plan tabs and the priorities picker, shown at the top of the card. */
  toolbar?: ReactNode;
}) {
  const h = card.content.headings;
  // What the grower told us, then checks from both winters grouped by what to do with them.
  const lists = [
    ...(card.observations.length
      ? [
          {
            id: "you",
            title: "You told us",
            tone: "act" as const,
            items: card.observations.map((o) => ({ key: o.text, text: o.text, winter: "", source: o.source ?? null })),
          },
        ]
      : []),
    ...GROUPS.map((g) => {
      // The same sentence from both winters, or from two rules, is listed once with its winters.
      const merged = new Map<string, { key: string; text: string; winters: number[] }>();
      for (const l of card.legs) {
        for (const c of l.plan?.other_checks ?? []) {
          if (!g.verdicts.includes(c.verdict)) continue;
          const text = c.text ?? clean(c.reason);
          const item = merged.get(text) ?? { key: `${l.leg}${c.rule_id}`, text, winters: [] };
          if (!item.winters.includes(l.leg)) item.winters.push(l.leg);
          merged.set(text, item);
        }
      }
      return {
        id: g.id,
        title: g.title,
        tone: g.tone,
        items: [...merged.values()].map((it) => ({
          key: it.key,
          text: it.text,
          winter: it.winters.length === 2 ? "Both winters" : `Winter ${it.winters[0]}`,
          source: null as Claim["source"] | null,
        })),
      };
    }).filter((g) => g.items.length),
  ];
  const [openList, setOpenList] = useState<string | null>(lists[0]?.id ?? null);
  const [about, setAbout] = useState<About>("why");
  const [zoom, setZoom] = useState<{ leg: number; from: DOMRect } | null>(null);
  // A different plan has different lists: start again from its first one.
  useEffect(() => {
    setOpenList(lists[0]?.id ?? null);
    setZoom(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [card.key]);
  const shown = lists.find((l) => l.id === openList) ?? null;
  const zoomLeg = zoom ? card.legs[zoom.leg] : undefined;

  const aboutBody: Record<About, ReactNode> = {
    why: (
      <>
        <Claims claims={h.why} />
        <Claims claims={h.evidence} />
      </>
    ),
    benefits: <Claims claims={h.benefits} tone="good" />,
    risks: <Claims claims={h.risks} tone="risk" />,
    gaps: <Claims claims={h.gaps} tone="gap" />,
  };

  return (
    <>
      <section className="db-card fb-plan pd-hero" aria-labelledby="plan-title">
        {toolbar}
        <header className="db-card-head">
          <h2 id="plan-title">
            <span className="visually-hidden">{card.content.name}: </span>Winter rain with nothing growing
          </h2>
          <p className="cmp-key" aria-hidden="true">
            <span className="cmp-key-rain" /> rain with nothing growing
            <span className="cmp-key-live" /> crop or cover growing
            <span className="cmp-key-note">Illustration of planned dates</span>
          </p>
        </header>

        <div className="pd-winters">
          {card.legs.map((l, i) => (
            <div className="pd-winter" key={l.leg}>
              <p className="pd-winter-title">
                <span>Winter {l.leg}</span> {l.leg === 1 ? "after corn" : "after soybeans"}
              </p>
              <WinterCell
                planName={card.content.name}
                onZoom={(from) => setZoom({ leg: i, from })}
                leg={l}
                axisMax={axisMax}
                selectedYear={selectedYear}
                onPickYear={onPickYear}
                onWhy={onWhy}
                caption={
                  l.plan?.sequence ? (
                    <p className="pd-dates">
                      {datesLine(l.plan)} <Src k={planSource} />
                    </p>
                  ) : null
                }
              />
            </div>
          ))}
        </div>

        {card.priorityFits.length ? (
          <ul className="pd-fits" aria-label="How this plan fits your priorities">
            {card.priorityFits.map((f) => (
              <li key={f.priority}>
                <strong>
                  {FIT_TEXT[f.fit]}: {f.label.toLowerCase()}.
                </strong>{" "}
                {f.reason.text} <ClaimSource claim={f.reason} />
                {f.detail ? <span className="pd-fit-detail"> {f.detail}</span> : null}
              </li>
            ))}
          </ul>
        ) : null}

        <div className="pd-actions">
          {onAdjust ? (
            <Button variant="primary" onClick={onAdjust}>
              Adjust rye timing
            </Button>
          ) : null}
          <Button ref={evidenceRef} onClick={onEvidence}>
            Behind the numbers
          </Button>
          {earlier ? (
            <p className="pd-sequence">
              End the rye {monthDay(earlier.terminate)} instead ({earlier.gap} days before planting):{" "}
              <strong className="tabular">
                {earlier.count ?? "not available"} of {earlier.denominator}
              </strong>{" "}
              springs to check.
            </p>
          ) : null}
        </div>
        {zoom && zoomLeg ? <WinterZoom planName={card.content.name} leg={zoomLeg} axisMax={axisMax} from={zoom.from} onClose={() => setZoom(null)} /> : null}
      </section>

      <div className="pd-row">
        <section className="db-card pd-todo" aria-labelledby="pd-todo-title">
          <header className="db-card-head">
            <h2 id="pd-todo-title">Before you plant</h2>
          </header>
          {lists.length ? (
            <>
              <div className="pd-counts" role="group" aria-label="What to do, by kind">
                {lists.map((g) => (
                  <button
                    key={g.id}
                    type="button"
                    className={`pd-count is-${g.tone}${g.id === openList ? " is-on" : ""}`}
                    aria-pressed={g.id === openList}
                    onClick={() => setOpenList(g.id)}
                  >
                    <span className="pd-count-num tabular">{g.items.length}</span>
                    <span className="pd-count-label">{g.title}</span>
                  </button>
                ))}
              </div>
              {shown ? (
                <ul className={`pd-claims pd-list pd-tone-${shown.tone === "fine" ? "good" : shown.tone === "act" ? "risk" : "gap"}`} key={shown.id}>
                  {shown.items.map((it) => (
                    <li key={it.key}>
                      {it.text} {it.winter ? <span className="pd-where">{it.winter}</span> : null}
                      {it.source ? <ClaimSource claim={{ text: it.text, source: it.source }} /> : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <p className="pd-empty">Nothing to check for this plan yet.</p>
          )}
        </section>

        <section className="db-card pd-about" aria-labelledby="pd-about-title">
          <header className="db-card-head">
            <h2 id="pd-about-title">About this plan</h2>
            <Segmented
              label="About this plan"
              value={about}
              onChange={setAbout}
              options={[
                { value: "why", label: "Why" },
                { value: "benefits", label: "Benefits" },
                { value: "risks", label: "Risks" },
                { value: "gaps", label: "Not known" },
              ]}
            />
          </header>
          <div className="pd-about-body" key={about}>
            {aboutBody[about]}
          </div>
        </section>

        <section className="db-card pd-trend" aria-labelledby="pd-trend-title">
          <header className="db-card-head">
            <h2 id="pd-trend-title">Earlier and recent springs</h2>
          </header>
          {card.era ? (
            <div className="pd-era">
              <p className="pd-era-measure">
                {card.era.measure}
                <Src k="calculated" />
              </p>
              {[card.era.earlier, card.era.recent].map((e) => (
                <div className="pd-era-row" key={e.label}>
                  <span className="pd-era-label">{e.label}</span>
                  <span className="pd-era-dots" aria-hidden="true">
                    {Array.from({ length: e.denominator }, (_, i) => (
                      <span key={i} className={`ws-dot${i < e.count ? " is-on" : ""}`} />
                    ))}
                  </span>
                  <span className="tabular">
                    {e.count} of {e.denominator}
                  </span>
                </div>
              ))}
              <p className="pd-era-say">{ERA_TEXT[card.era.result]} Past records, not a forecast.</p>
            </div>
          ) : (
            <p className="pd-empty">Not available for this winter.</p>
          )}
        </section>
      </div>
    </>
  );
}
