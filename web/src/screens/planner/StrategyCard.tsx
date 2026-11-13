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

const CROP: Record<string, string> = { field_corn: "Corn", soybean: "Soybeans" };

function sequenceText(plan: Plan | null): string {
  const seq = plan?.sequence;
  if (!seq) return "";
  const w = seq.winter;
  const prev = CROP[seq.previous_crop_id] ?? seq.previous_crop_id;
  const next = (CROP[seq.next_crop_id] ?? seq.next_crop_id).toLowerCase();
  const harvest = monthDay(seq.prev_harvest);
  const plant = monthDay(seq.next_plant);
  if (w.type === "cover") return `${prev} (harvest ${harvest}) → rye ${monthDay(w.seed)}–${monthDay(w.terminate)} → ${next} ${plant}`;
  if (w.type === "winter_grain") return `${prev} (harvest ${harvest}) → wheat ${monthDay(w.plant)}–${monthDay(w.harvest)} → ${next} ${plant}`;
  return `${prev} (harvest ${harvest}) → no planted cover → ${next} ${plant}`;
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
  earlier?: { terminate: string; gap: number; count: number | null; denominator: number } | null;
  onSelect: () => void;
  onEvidence: () => void;
  onAdjust?: () => void;
  planSource?: "sample" | "farmer";
}) {
  const { content, era, status } = card;
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
        <table className="sc-legs">
          <caption className="visually-hidden">Each winter of the rotation, tested on its own against every past spring</caption>
          <thead>
            <tr>
              <th scope="col">Winter</th>
              <th scope="col">
                Rain, no <G id="living-cover">cover</G>
              </th>
              <th scope="col">Moisture check</th>
            </tr>
          </thead>
          <tbody>
            {card.legs.map((l) => (
              <tr key={l.leg} className={l.selected ? "is-current" : undefined} aria-current={l.selected ? "true" : undefined}>
                <th scope="row">
                  <span aria-hidden="true">{l.short}</span>
                  <span className="visually-hidden">{l.title}</span>
                  <span className="sc-leg-plant">{l.plant ? `plant ${monthDay(l.plant)}` : "dates not set"}</span>
                </th>
                {l.available ? (
                  <>
                    <td>
                      <span className="sc-count tabular">{l.soilMm === null ? "—" : l.soilMm.toFixed(0)}</span>
                      {l.soilMm === null ? null : <span className="sc-of"> mm</span>}
                      <Src k={["nasa", "calculated"]} />
                    </td>
                    <td>
                      {l.check.applies ? (
                        <>
                          <span className="sc-count tabular">{l.check.count}</span>
                          <span className="sc-of"> of {l.check.denominator}</span>
                          <Src k={["nasa", "ncstate", "calculated"]} />
                        </>
                      ) : (
                        <span className="sc-na">Does not apply</span>
                      )}
                    </td>
                  </>
                ) : (
                  <td colSpan={2} className="sc-leg-na">
                    Not evaluated yet
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="sc-legs-note">
          Median winter rain per winter; checks are springs out of all on record. Each winter is tested on its own; rows are never
          added.
        </p>
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
        <span className="sc-leg-label">{card.legs.find((l) => l.selected)?.title} winter: </span>
        {card.unavailableReason ? card.unavailableReason : sequenceText(card.plan)}
        <Src k={planSource} />
      </p>

      <ul className="sc-metrics">
        {card.metrics.map((m) => (
          <li key={m}>{m}</li>
        ))}
      </ul>

      <div className="sc-earlier">
        {earlier ? (
          <p>
            Ending rye {monthDay(earlier.terminate)} instead ({earlier.gap} days before planting):{" "}
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
