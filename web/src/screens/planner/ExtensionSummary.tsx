import { useEffect, useRef, useState } from "react";
import type { OtherCheck } from "../../api/schema";
import { APP_NAME, CHALLENGE_LABEL } from "../../config";
import { CARDS, PRIORITY_INFO, SOURCES, type Claim, type Leg, type Priority, type SourceId } from "../../content/strategies";
import { historicalWindow, mm, monthDay, plannedDate, wetness } from "../../data/format";
import type { FarmForm } from "../../state/form";
import type { CardVM, ObservationVM, ViewModel } from "../../view/build";
import { Button } from "../../ui/components";

/*
  The Extension summary (Phase 8.1), printed on letter paper.
  Page 1 is the page to bring: dates, both winters' numbers for the three plans, what to
  discuss, rye timing and room for the adviser's notes. Page 2 holds each plan's five
  headings (why, evidence, benefits, gaps, risks) and the numbered sources.
  Built from the same view model as the planner, once per winter, so every number matches.

  On screen (Nov 13): the grower can type questions to bring (kept for this browser tab only,
  never put in the link), tick off items as they are discussed, and send the same numbers as
  plain text by copying them or opening an email draft. Printing shows what was typed and ticked.
*/

const QUESTIONS_KEY = "fieldback.summary.questions";
const readQuestions = () => {
  try {
    return window.sessionStorage.getItem(QUESTIONS_KEY) ?? "";
  } catch {
    return "";
  }
};

const TO_DISCUSS: OtherCheck["verdict"][] = ["avoid", "caution", "manual_check"];
/** The page holds this many lines; the rest are counted and left on the plan page. */
const DISCUSS_ON_PAGE = 8;
const VERDICT_WORD: Partial<Record<OtherCheck["verdict"], string>> = { avoid: "Avoid", caution: "Caution", manual_check: "Check" };
const FIT_WORD = { matches: "Matches", partly: "Partly", tradeoff: "Trade-off" } as const;
const LEG_SHORT: Record<Leg, string> = { 1: "corn → soy", 2: "soy → corn" };

const tri = (v: FarmForm["moistureConcern"]) => (v === "yes" ? "Yes" : v === "no" ? "No" : "Unknown");
const soilSource = (f: FarmForm) =>
  f.soilSource === "farmer" ? "reported by you" : f.soilSource === "usda" ? "USDA mapped estimate" : f.soilSource === "sample" ? "sample profile (fictional)" : "unknown";
const clean = (reason: string) => reason.replace(/^[a-z_]+:\s*/, "").replace(/^./, (ch) => ch.toUpperCase());

interface DiscussItem {
  key: string;
  verdict: OtherCheck["verdict"] | "observation";
  text: string;
  source: SourceId | null;
  where: string[];
}

/** Checks to talk over, merged when the same rule applies to several plans (display grouping only). */
function discussList(legViews: Record<Leg, ViewModel>): DiscussItem[] {
  const items = new Map<string, DiscussItem>();
  CARDS.forEach((content, i) => {
    ([1, 2] as Leg[]).forEach((l) => {
      const card = legViews[l].cards[i]!;
      for (const ch of card.checks) {
        if (!TO_DISCUSS.includes(ch.verdict)) continue;
        const key = `${l}:${ch.rule_id}`;
        const item = items.get(key) ?? { key, verdict: ch.verdict, text: clean(ch.reason), source: null, where: [] };
        item.where.push(content.name);
        items.set(key, item);
      }
    });
    const obs: ObservationVM[] = legViews[1].cards[i]!.observations;
    for (const o of obs) {
      const key = `obs:${o.text}`;
      const item = items.get(key) ?? { key, verdict: "observation", text: o.text, source: o.source, where: [] };
      item.where.push(content.name);
      items.set(key, item);
    }
  });
  const rank = (v: DiscussItem["verdict"]) => (v === "observation" ? -1 : TO_DISCUSS.indexOf(v));
  return [...items.values()].sort((a, b) => rank(a.verdict) - rank(b.verdict));
}

export function ExtensionSummary({
  view,
  legViews,
  form,
  priorities,
  planSource,
  placeLabel,
  onClose,
}: {
  view: ViewModel;
  legViews: Record<Leg, ViewModel>;
  form: FarmForm;
  priorities: Priority[];
  planSource: "sample" | "farmer";
  /** The place on screen (Phase 9); defaults to the backend's location label. */
  placeLabel?: string;
  onClose: () => void;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [copy, setCopy] = useState<"idle" | "copied" | "text" | "failed">("idle");
  const [questions, setQuestions] = useState(readQuestions);
  const [done, setDone] = useState<Set<string>>(() => new Set());
  const toggleDone = (key: string) =>
    setDone((cur) => {
      const next = new Set(cur);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  useEffect(() => {
    try {
      window.sessionStorage.setItem(QUESTIONS_KEY, questions);
    } catch {
      // Private windows may refuse storage; the questions still print from this page.
    }
  }, [questions]);

  useEffect(() => {
    headingRef.current?.focus();
    window.scrollTo(0, 0);
    const before = document.title;
    document.title = `Extension summary · ${APP_NAME}`;
    return () => {
      document.title = before;
    };
  }, []);

  // Numbered sources, NASA POWER first, then in the order the pages cite them.
  const order: SourceId[] = ["nasa-power"];
  const cite = (id: SourceId | null) => {
    if (!id) return null;
    if (!order.includes(id)) order.push(id);
    return <sup className="xs-ref">[{order.indexOf(id) + 1}]</sup>;
  };
  const claims = (list: Claim[]) =>
    list.map((c) => (
      <span key={c.text}>
        {c.text}
        {cite(c.source)}{" "}
      </span>
    ));

  const card = (l: Leg, i: number): CardVM => legViews[l].cards[i]!;
  const rye = view.rye;
  const boundary = rye && rye.boundaryIndex !== null ? rye.points[rye.boundaryIndex]! : null;
  const y = view.selectedYear;
  const discuss = discussList(legViews);
  const prepared = new Date().toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  const place = placeLabel ?? view.locationLabel.replace(/\s*\(sample\)$/i, "");

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopy("copied");
    } catch {
      setCopy("failed");
    }
  };

  // The same numbers as plain text, for an email or a text message to the adviser.
  const where = (d: DiscussItem) => `${d.key.startsWith("2:") ? "soy → corn: " : d.key.startsWith("1:") ? "corn → soy: " : ""}${d.where.join(", ")}`;
  const asText = () => {
    const lines: string[] = [
      `${APP_NAME} summary for ${place} (prepared ${prepared})`,
      "Past weather replayed for each plan. Not a forecast or a field measurement.",
      "",
    ];
    CARDS.forEach((content, i) => {
      lines.push(`${i + 1}. ${content.name}`);
      for (const l of card(1, i).legs) {
        lines.push(
          l.available
            ? `   ${l.title}: ${mm(l.soilMm)} winter rain with nothing growing${l.check.applies ? `; check soil moisture in ${l.check.count} of ${l.check.denominator} springs` : ""}`
            : `   ${l.title}: not evaluated yet`,
        );
      }
    });
    if (discuss.length) {
      lines.push("", "To discuss:");
      for (const d of discuss.slice(0, DISCUSS_ON_PAGE)) lines.push(`- ${d.verdict === "observation" ? "You reported" : VERDICT_WORD[d.verdict]}: ${d.text} (${where(d)})`);
    }
    if (questions.trim()) lines.push("", "My questions:", questions.trim());
    lines.push("", `Open it: ${window.location.href}`);
    return lines.join("\n");
  };
  const copyText = async () => {
    try {
      await navigator.clipboard.writeText(asText());
      setCopy("text");
    } catch {
      setCopy("failed");
    }
  };
  const email = () => {
    window.location.href = `mailto:?subject=${encodeURIComponent(`${APP_NAME} summary for ${place}`)}&body=${encodeURIComponent(asText())}`;
  };

  const foot = (page: number) => (
    <footer className="xs-foot">
      <p>
        <strong>Based on past weather near your farm. Not a forecast or a field measurement.</strong> Rainfall is a NASA POWER
        regional estimate; soil wetness is modeled. Talk this over with your Extension agent before changing your plan.
      </p>
      <p className="xs-trace">
        {CHALLENGE_LABEL} · {APP_NAME} · {place} · request {view.requestId} · snapshot {view.snapshotHash.slice(0, 12)} · page {page} of 2
      </p>
    </footer>
  );

  return (
    <div className="xs-wrap">
      <div className="xs-toolbar" role="toolbar" aria-label="Summary actions">
        <Button onClick={onClose}>← Back to the planner</Button>
        <span className="xs-toolbar-gap" />
        <span className="xs-copy-status" aria-live="polite">
          {copy === "copied" ? "Link copied" : copy === "text" ? "Summary copied as text" : copy === "failed" ? "Could not copy. The address bar has the link." : ""}
        </span>
        <Button onClick={copyLink}>Copy link</Button>
        <Button onClick={copyText}>Copy as text</Button>
        <Button onClick={email}>Email it</Button>
        <Button variant="primary" onClick={() => window.print()}>
          Print or save as PDF
        </Button>
      </div>

      {/* ------------------------------------------------------------------ page 1 */}
      <article className="xs-page" aria-labelledby="xs-title">
        <header className="xs-head">
          <div className="xs-brand">
            <span className="brand-mark" aria-hidden="true" />
            <span className="brand-name">{APP_NAME}</span>
          </div>
          <div className="xs-head-main">
            <h1 id="xs-title" ref={headingRef} tabIndex={-1}>
              Bring this to your Extension agent
            </h1>
            <p className="xs-meta">
              {place} · {planSource === "sample" ? "Sample field" : "Your dates"} · Prepared {prepared}
            </p>
          </div>
          {view.dataKind === "draft" ? <p className="xs-draft">Draft sample data: synthetic weather, not NASA records</p> : null}
        </header>

        <p className="xs-lede">
          Three plans, each winter replayed on its own against every spring NASA recorded here since 1981{cite("nasa-power")}.
        </p>

        <section aria-labelledby="xs-farm">
          <h2 id="xs-farm">Your farm and planned dates</h2>
          <table className="xs-table">
            <thead>
              <tr>
                <th scope="col">Winter 1 · corn → soybeans (2026–27)</th>
                <th scope="col">Winter 2 · soybeans → corn (2027–28)</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  Corn harvest {plannedDate(form.cornHarvest)} · soybeans planted {plannedDate(form.soyPlant)}
                </td>
                <td>
                  Soybean harvest {plannedDate(form.soyHarvest)} · corn planted {plannedDate(form.cornPlant)}
                </td>
              </tr>
              <tr>
                <td>
                  Rye {plannedDate(form.ryeSeed)} to {rye ? monthDay(rye.chosen.terminate) : plannedDate(form.ryeEnd)}
                </td>
                <td>
                  Rye {plannedDate(form.rye2Seed)} to {plannedDate(form.rye2End)}
                </td>
              </tr>
              <tr>
                <td>
                  Wheat {plannedDate(form.wheatPlant)} to {plannedDate(form.wheatHarvest)}, soybeans {plannedDate(form.soyDoubleCropPlant)}{" "}
                  <em>(not evaluated yet)</em>
                </td>
                <td>No winter grain in this winter</td>
              </tr>
            </tbody>
          </table>
          <p className="xs-context">
            <strong>Field moisture concern:</strong> {tri(form.moistureConcern)} · <strong>Irrigation:</strong> {tri(form.irrigation)} (context
            only) · <strong>Soil:</strong> {form.soilTexture ? `${form.soilTexture}, ` : ""}
            {soilSource(form)} · <strong>Priorities:</strong>{" "}
            {priorities.length ? priorities.map((p) => PRIORITY_INFO[p].label).join(", ") : "none chosen"}
          </p>
        </section>

        <section aria-labelledby="xs-plans">
          <h2 id="xs-plans">The three plans, both winters</h2>
          <div className="xs-plans">
            {CARDS.map((content, i) => {
              const c1 = card(1, i);
              const eras = ([1, 2] as Leg[]).map((l) => ({ l, era: card(l, i).era }));
              return (
                <div className="xs-plan" key={content.key}>
                  <h3>
                    {i + 1}. {content.name}
                  </h3>
                  <p className="xs-sub">{content.subtitle}</p>
                  <table className="xs-legs">
                    <thead>
                      <tr>
                        <th scope="col">Winter</th>
                        <th scope="col">Rain, no cover</th>
                        <th scope="col">Check</th>
                      </tr>
                    </thead>
                    <tbody>
                      {c1.legs.map((l) => (
                        <tr key={l.leg}>
                          <th scope="row">{l.short}</th>
                          {l.available ? (
                            <>
                              <td>{mm(l.soilMm)}</td>
                              <td>{l.check.applies ? `${l.check.count} of ${l.check.denominator}` : "n/a"}</td>
                            </>
                          ) : (
                            <td colSpan={2}>Not evaluated yet</td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <ul className="xs-list">
                    {eras.map(({ l, era }) =>
                      era ? (
                        <li key={l}>
                          {era.measure.replace(/^Springs with a field-moisture check$/, "Checks")} ({LEG_SHORT[l]}): {era.earlier.label}{" "}
                          {era.earlier.count}/{era.earlier.denominator}, {era.recent.label} {era.recent.count}/{era.recent.denominator}
                        </li>
                      ) : null,
                    )}
                    {c1.priorityFits.map((f) => (
                      <li key={f.priority}>
                        <strong>{FIT_WORD[f.fit]}:</strong> {f.label.toLowerCase()}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
          <p className="xs-note">
            Rain, no cover: median winter rain while no living cover is planned. Check: springs where NC State's field-moisture check
            applies{cite("ncs-soy-4")}, of all on record.
          </p>
        </section>

        {discuss.length ? (
          <section aria-labelledby="xs-discuss">
            <h2 id="xs-discuss">To discuss with your agent</h2>
            <ul className="xs-discuss">
              {discuss.slice(0, DISCUSS_ON_PAGE).map((d) => (
                <li key={d.key} className={done.has(d.key) ? "is-done" : undefined}>
                  <input
                    type="checkbox"
                    className="xs-tick-box"
                    checked={done.has(d.key)}
                    onChange={() => toggleDone(d.key)}
                    aria-label={`Discussed: ${d.text}`}
                  />
                  <strong>{d.verdict === "observation" ? "You reported" : VERDICT_WORD[d.verdict]}:</strong> {d.text}
                  {cite(d.source)} <span className="xs-where">({where(d)})</span>
                </li>
              ))}
            </ul>
            {discuss.length > DISCUSS_ON_PAGE ? (
              <p className="xs-note">
                {discuss.length - DISCUSS_ON_PAGE} more field checks are listed on each plan's page in {APP_NAME}.
              </p>
            ) : null}
          </section>
        ) : null}

        {rye ? (
          <section className="xs-rye" aria-labelledby="xs-rye">
            <h2 id="xs-rye">When to end the rye before soybeans</h2>
            <RyeStill points={rye.points} chosen={rye.index} boundary={rye.boundaryIndex} denominator={rye.denominator} />
            <div>
              <p>
                This plan ends rye <strong>{monthDay(rye.chosen.terminate)}</strong>, {rye.chosen.gap_days} days before soybeans: a
                field-moisture check in{" "}
                <strong>
                  {rye.chosen.checks_count ?? "—"} of {rye.denominator}
                </strong>{" "}
                springs.
                {boundary ? (
                  <>
                    {" "}
                    Ending by {monthDay(boundary.terminate)} ({boundary.gap_days} days before): {boundary.checks_count ?? "—"} of{" "}
                    {rye.denominator}, with {boundary.living_cover_days_planned} planned days of living rye instead of{" "}
                    {rye.chosen.living_cover_days_planned}.
                  </>
                ) : null}
              </p>
              {y && y.status === "complete" ? (
                <p className="xs-note">
                  Spring looked at on screen: {y.year}, {mm(y.totalMm)} in {historicalWindow(y.window)}
                  {y.rank !== null ? `, rank ${y.rank} of ${y.of} (1 = driest)` : ""}, modeled soil wetness {wetness(y.wetnessRoot)}.
                </p>
              ) : null}
            </div>
          </section>
        ) : null}

        <div className="xs-notes-row">
          <section className="xs-notes xs-ask" aria-labelledby="xs-ask">
            <h2 id="xs-ask">
              <label htmlFor="xs-questions">Your questions</label>
            </h2>
            <textarea
              id="xs-questions"
              className="xs-questions"
              value={questions}
              maxLength={600}
              rows={6}
              placeholder="Type what you want to ask. It prints here."
              onChange={(e) => setQuestions(e.target.value)}
            />
          </section>
          <section className="xs-notes" aria-labelledby="xs-notes">
            <h2 id="xs-notes">Notes from your adviser</h2>
            <div className="xs-lines" aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
              <span />
              <span />
            </div>
          </section>
        </div>

        {foot(1)}
      </article>

      {/* ------------------------------------------------------------------ page 2 */}
      <article className="xs-page xs-page-2" aria-labelledby="xs-details">
        <header className="xs-head">
          <div className="xs-brand">
            <span className="brand-mark" aria-hidden="true" />
            <span className="brand-name">{APP_NAME}</span>
          </div>
          <div className="xs-head-main">
            <h1 id="xs-details">The three plans in detail</h1>
            <p className="xs-meta">Why each plan, its evidence, benefits, gaps and risks to review locally. Numbers refer to the sources.</p>
          </div>
        </header>

        <div className="xs-plans">
          {CARDS.map((content, i) => {
            const h = content.headings;
            const fits = card(1, i).priorityFits;
            return (
              <div className="xs-plan" key={content.key}>
                <h3>
                  {i + 1}. {content.name}
                </h3>
                <dl className="xs-headings">
                  <dt>Why</dt>
                  <dd>{claims(h.why)}</dd>
                  <dt>Evidence</dt>
                  <dd>{claims(h.evidence)}</dd>
                  <dt>Benefits</dt>
                  <dd>{claims(h.benefits)}</dd>
                  <dt>Gaps</dt>
                  <dd>{claims(h.gaps)}</dd>
                  <dt>Risks</dt>
                  <dd>{claims(h.risks)}</dd>
                  {fits.length ? (
                    <>
                      <dt>Your priorities</dt>
                      <dd>
                        {fits.map((f) => (
                          <span key={f.priority}>
                            {FIT_WORD[f.fit]}, {f.label.toLowerCase()}: {f.reason.text}
                            {cite(f.reason.source)}{" "}
                          </span>
                        ))}
                      </dd>
                    </>
                  ) : null}
                </dl>
              </div>
            );
          })}
        </div>

        <section aria-labelledby="xs-sources">
          <h2 id="xs-sources">Sources</h2>
          <ol className="xs-sources">
            {order.map((id) => (
              <li key={id}>
                {SOURCES[id].publisher}, {SOURCES[id].title}. <span className="xs-url">{SOURCES[id].url}</span>
              </li>
            ))}
          </ol>
        </section>

        {foot(2)}
      </article>
    </div>
  );
}

/** The rye sweep as a still step chart: springs with a check for each end date. */
function RyeStill({
  points,
  chosen,
  boundary,
  denominator,
}: {
  points: Array<{ terminate: string; checks_count: number | null }>;
  chosen: number;
  boundary: number | null;
  denominator: number;
}) {
  const W = 240;
  const H = 46;
  const x = (i: number) => (points.length > 1 ? (i / (points.length - 1)) * W : 0);
  const yv = (c: number | null) => (c === null || !denominator ? H : H - (c / denominator) * H);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${yv(p.checks_count).toFixed(1)}`).join(" ");
  const first = points[0];
  const last = points[points.length - 1];
  return (
    <figure className="xs-still">
      <svg viewBox={`-4 -6 ${W + 8} ${H + 22}`} width={W + 8} height={H + 22} role="img" aria-label="Springs with a field-moisture check for each rye end date">
        <line x1={0} x2={W} y1={H} y2={H} className="xs-axis" />
        {boundary !== null ? <line x1={x(boundary)} x2={x(boundary)} y1={-4} y2={H} className="xs-boundary" /> : null}
        <path d={d} className="xs-curve" />
        <circle cx={x(chosen)} cy={yv(points[chosen]?.checks_count ?? null)} r={3.5} className="xs-dot" />
        {first ? (
          <text x={0} y={H + 13} className="xs-tick">
            {monthDay(first.terminate)}
          </text>
        ) : null}
        {last ? (
          <text x={W} y={H + 13} textAnchor="end" className="xs-tick">
            {monthDay(last.terminate)}
          </text>
        ) : null}
      </svg>
      <figcaption>Rye end date and springs with a check. Dashed: 14 days before soybeans. Dot: this plan.</figcaption>
    </figure>
  );
}
