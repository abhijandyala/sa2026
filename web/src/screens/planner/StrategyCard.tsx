import type { OtherCheck, Plan } from "../../api/schema";
import { SOURCES, type Claim } from "../../content/strategies";
import { monthDay } from "../../data/format";
import type { CardVM, EraVM } from "../../view/build";
import { Button, SourceChip, Src, StatusPill } from "../../ui/components";
import { G } from "../../ui/Glossary";

/*
  One strategy card (Phase 2). Fixed slot order so the three cards line up (playbook p.40):
  name, sequence, headline count, earlier vs recent, calendar metrics, winter rain,
  this year's status, checks, the five headings, actions.
*/

const ERA_TEXT: Record<EraVM["result"], string> = {
  more_frequent_recent: "More often in recent years",
  less_frequent_recent: "Less often in recent years",
  similar: "About as often in both periods",
  insufficient_data: "Not enough complete years to compare periods",
};

const VERDICT: Record<OtherCheck["verdict"], { kind: "ok" | "check" | "unavailable" | "inapplicable"; label: string }> = {
  preferred: { kind: "ok", label: "Fits" },
  acceptable: { kind: "ok", label: "Acceptable" },
  caution: { kind: "check", label: "Caution" },
  avoid: { kind: "check", label: "Avoid" },
  manual_check: { kind: "unavailable", label: "Check in the field" },
  unknown: { kind: "unavailable", label: "Unknown" },
  inapplicable: { kind: "inapplicable", label: "Does not apply" },
};

function sequenceText(plan: Plan | null): string {
  if (!plan) return "";
  const w = plan.sequence.winter;
  const harvest = monthDay(plan.sequence.prev_harvest);
  const plant = monthDay(plan.sequence.next_plant);
  if (w.type === "cover") return `Corn (harvest ${harvest}) → rye ${monthDay(w.seed)}–${monthDay(w.terminate)} → soybeans ${plant}`;
  if (w.type === "winter_grain") return `Corn (harvest ${harvest}) → wheat ${monthDay(w.plant)}–${monthDay(w.harvest)} → soybeans ${plant}`;
  return `Corn (harvest ${harvest}) → no planted cover → soybeans ${plant}`;
}

function ClaimList({ claims }: { claims: Claim[] }) {
  return (
    <ul className="claims">
      {claims.map((c) => (
        <li key={c.text}>
          {c.text}{" "}
          {c.source ? (
            <SourceChip
              kind={SOURCES[c.source].kind === "nasa" ? "nasa" : SOURCES[c.source].kind === "ncstate" ? "ncstate" : "calculated"}
              href={SOURCES[c.source].url}
              title={SOURCES[c.source].title}
            />
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function StrategyCard({
  card,
  index,
  selected,
  earlier,
  onSelect,
  onEvidence,
  onAdjust,
  planSource = "sample",
}: {
  card: CardVM;
  index: number;
  selected: boolean;
  earlier?: { plan: Plan; count: number | null; denominator: number | null } | null;
  onSelect: () => void;
  onEvidence: () => void;
  onAdjust?: () => void;
  planSource?: "sample" | "farmer";
}) {
  const { content, soil, check, era, status } = card;
  const h = content.headings;
  return (
    <article
      className={`strategy-card${selected ? " is-selected" : ""}${status?.kind === "check" ? " tone-check" : ""}`}
      aria-labelledby={`card-${card.key}-name`}
    >
      <header className="sc-head">
        <span className="sc-index tabular" aria-hidden="true">
          {index}
        </span>
        <div>
          <h3 className="sc-name" id={`card-${card.key}-name`}>
            {content.name}
          </h3>
          <p className="sc-sub">{content.subtitle}</p>
        </div>
      </header>

      <div className="sc-headline">
        <div className="sc-metric-block">
          <span className={`sc-count${soil.mm === null ? " sc-count-muted" : ""}`}>
            {soil.mm === null ? "—" : soil.mm.toFixed(0)}
            {soil.mm === null ? null : <span className="sc-of"> mm</span>}
            <Src k={["nasa", "calculated"]} />
          </span>
          <span className="sc-meaning">
            median winter rain on ground with no <G id="living-cover">living cover</G>
            {soil.seasons ? <span className="sc-basis"> · {soil.seasons} winters</span> : null}
          </span>
        </div>
        <div className="sc-metric-block">
          {check.applies ? (
            <span className="sc-count">
              {check.count} <span className="sc-of">of {check.denominator}</span>
              <Src k={["nasa", "ncstate", "calculated"]} />
            </span>
          ) : (
            <span className="sc-count sc-count-muted sc-na">Does not apply</span>
          )}
          <span className="sc-meaning">
            {check.applies ? "springs would have needed a field-moisture check" : "no cover crop to end before planting"}
          </span>
        </div>
      </div>

      {era ? (
        <div className="sc-era" aria-label={`${era.measure}, earlier and recent periods`}>
          <span className="sc-era-measure">
            {era.measure}
            <Src k="calculated" />
          </span>
          <span className="tabular">
            {era.earlier.label}: <strong>{era.earlier.count}</strong> of {era.earlier.denominator}
          </span>
          <span className="tabular">
            {era.recent.label}: <strong>{era.recent.count}</strong> of {era.recent.denominator}
          </span>
          <span className="sc-era-result">{ERA_TEXT[era.result]}</span>
        </div>
      ) : (
        <div className="sc-era sc-era-empty">Earlier vs recent: not available</div>
      )}

      <p className="sc-sequence">
        {sequenceText(card.plan)}
        <Src k={planSource} />
      </p>

      <ul className="sc-metrics">
        {card.metrics.map((m) => (
          <li key={m}>{m}</li>
        ))}
      </ul>

      <div className="sc-earlier">
        {earlier && earlier.plan.sequence.winter.type === "cover" ? (
          <p>
            Ending rye {monthDay(earlier.plan.sequence.winter.terminate)} instead ({earlier.plan.calendar.termination_gap_days} days
            before planting):{" "}
            <strong className="tabular">
              {earlier.count ?? "—"} of {earlier.denominator ?? "—"}
            </strong>{" "}
            springs
          </p>
        ) : null}
      </div>

      <div className="sc-status">
        {status ? (
          <StatusPill kind={status.kind === "check" ? "check" : status.kind === "dry" ? "dry" : "unavailable"}>{status.text}</StatusPill>
        ) : (
          <span className="sc-status-none">No check in this spring</span>
        )}
      </div>

      <div className="sc-checks">
        {card.checks.length ? (
          <ul aria-label="Timing and rule checks">
            {card.checks.map((c) => (
              <li key={c.rule_id}>
                <StatusPill kind={VERDICT[c.verdict].kind}>{VERDICT[c.verdict].label}</StatusPill>
                {/* Backend reasons may start with a machine code ("catalog_missing: …"); show the words only. */}
                <span>{c.reason.replace(/^[a-z_]+:\s*/, "").replace(/^./, (ch) => ch.toUpperCase())}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      <details className="sc-details">
        <summary>Why, evidence, benefits, gaps and risks</summary>
        <dl>
          <dt>Why it's suggested</dt>
          <dd>
            <ClaimList claims={h.why} />
          </dd>
          <dt>Evidence</dt>
          <dd>
            <ClaimList claims={h.evidence} />
          </dd>
          <dt>Benefits</dt>
          <dd>
            <ClaimList claims={h.benefits} />
          </dd>
          <dt>Gaps</dt>
          <dd>
            <ClaimList claims={h.gaps} />
          </dd>
          <dt>Risks to review locally</dt>
          <dd>
            <ClaimList claims={h.risks} />
          </dd>
        </dl>
      </details>

      <div className="sc-actions">
        <Button variant={selected ? "primary" : "secondary"} aria-pressed={selected} onClick={onSelect}>
          {selected ? "Viewing this plan" : "View this plan"}
        </Button>
        {onAdjust ? <Button onClick={onAdjust}>Adjust rye timing</Button> : null}
        <Button onClick={onEvidence}>Show evidence</Button>
      </div>
    </article>
  );
}
