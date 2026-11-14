import { useEffect, useState, type ReactNode, type RefObject } from "react";
import { PRIORITY_INFO, SOURCES } from "../../content/strategies";
import { historicalDate, historicalWindow, mm, monthDay, plannedDate, wetness } from "../../data/format";
import type { FarmForm } from "../../state/form";
import type { Emphasis, Priority } from "../../state/model";
import type { ReplayState } from "../../state/useData";
import type { CardVM, ViewModel } from "../../view/build";
import { Accordion, type AccordionItem } from "../../ui/Accordion";
import { Button, Drawer, SourceChip } from "../../ui/components";
import { WinterPicture } from "./WinterPicture";

/*
  The "behind the numbers" panel (cards 6.1 and 6.2, redesigned Nov 13 to cut the words).
  It opens on the number that was clicked, shown as a picture with one sentence:
  - winter rain with nothing growing: the glass, the number and the field picture;
  - the soil-moisture check: the count, one dot per spring, and the plan's gap next to
    NC State's guidance.
  Everything a skeptical judge may ask for next (the picked spring, sources and limits,
  the guidance, the plan's dates, the audit values and the daily CSV) is folded into a
  closed list underneath (playbook p.43–44, handbook p.13).
  Opening it never changes the selection; closing returns focus to its button.
*/

const PRIORITY_LABEL: Record<Priority, string> = Object.fromEntries(
  Object.entries(PRIORITY_INFO).map(([k, v]) => [k, v.label]),
) as Record<Priority, string>;

function soilLabel(form: FarmForm): string {
  if (form.soilSource === "farmer") return "Reported by you";
  if (form.soilSource === "usda") return "USDA mapped estimate";
  if (form.soilSource === "sample") return "Sample profile (fictional)";
  return "Unknown";
}

function tri(v: FarmForm["moistureConcern"]): string {
  return v === "yes" ? "Yes" : v === "no" ? "No" : "Unknown";
}

function downloadCsv(name: string, rows: string[][]) {
  const csv = rows.map((r) => r.map((c) => (/[",\n]/.test(c) ? `"${c.replace(/"/g, '""')}"` : c)).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv + "\n"], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function EvidenceDrawer({
  open,
  view,
  card,
  form,
  replay,
  priorities,
  emphasis,
  onClose,
  returnFocusRef,
  focus = null,
  onExport,
}: {
  open: boolean;
  view: ViewModel;
  card: CardVM;
  form: FarmForm;
  replay: ReplayState;
  priorities: Priority[];
  emphasis: Emphasis;
  onClose: () => void;
  returnFocusRef: RefObject<HTMLElement>;
  /** Which part to open at, from a "see why" number on a card. */
  focus?: "rain" | "check" | null;
  /** Everything behind the page as one file, for anyone who wants to check it. */
  onExport?: () => void;
}) {
  const y = view.selectedYear;
  const dry = view.thresholds.dry_spring;
  const heavy = view.thresholds.heavy_rain;
  const plan = card.plan;
  const w = plan?.sequence?.winter;
  const sources = [...new Set(Object.values(card.content.headings).flat().map((c) => c.source).filter(Boolean))] as Array<keyof typeof SOURCES>;
  const daily = replay.status === "ready" && replay.data.year === y?.year ? replay.data : null;
  const backendReasons =
    daily && plan && daily.plan_id === plan.plan_id && !(card.key === "cover" && view.rye?.changed) ? daily.checks_triggered : [];
  const valid = daily ? daily.daily.filter((d) => d.precip_mm !== null).length : null;
  const complete = view.window?.years.filter((r) => r.status === "complete").length ?? 0;
  const excluded = view.window?.years.filter((r) => r.status !== "complete").map((r) => r.year) ?? [];
  const gap = plan?.calendar?.termination_gap_days ?? plan?.calendar?.harvest_to_plant_days ?? null;
  const ryeCheck = plan?.spring_checks.find((c) => c.check_id === "rye_soy_short_gap_moisture");

  const legVM = card.legs.find((l) => l.selected) ?? card.legs[0];
  // The guidance gap, read from the backend's own rule text ("gap < 14 days ...").
  const guideMatch = ryeCheck?.fires_when?.match(/gap\s*<\s*(\d+)\s*day/);
  const guideDays = guideMatch ? Number(guideMatch[1]) : null;
  // Display scaling only: the largest backend value on the page fills its glass.
  const axisMax = Math.max(0, ...view.cards.flatMap((c) => c.legs.map((l) => l.soilMm ?? 0)));
  const fill = card.soil.mm === null || axisMax <= 0 ? 0 : Math.max(0, Math.min(1, card.soil.mm / axisMax));
  const flagged = new Set(legVM?.checkYears ?? []);
  const [more, setMore] = useState<string | null>(null);
  useEffect(() => {
    if (open) setMore(null);
  }, [open, focus]);

  const winterLine = legVM ? `Winter ${legVM.leg} · ${legVM.leg === 1 ? "after corn" : "after soybeans"}` : "";

  const rainBlock = (
    <section className="ev-card" key="rain" aria-labelledby="ev-rain-title">
      <h3 id="ev-rain-title">Winter rain with nothing growing</h3>
      <p className="ev-big">
        <span className={`cmp-glass${card.soil.mm === null ? " is-missing" : ""}`} aria-hidden="true">
          <span style={{ height: `${fill * 100}%` }} />
        </span>
        {card.soil.mm === null ? (
          <span className="ev-big-text">Not available</span>
        ) : (
          <>
            <span className="ev-num tabular">{card.soil.mm.toFixed(0)}</span>
            <span className="ev-big-text">mm{card.soil.seasons ? ` · middle of ${card.soil.seasons} past winters` : ""}</span>
          </>
        )}
      </p>
      {plan?.sequence ? <WinterPicture plan={plan} /> : null}
      <p className="ev-say">
        Rain that fell between harvest and planting while nothing was growing. It counts rain, not erosion.{" "}
        <SourceChip kind="nasa" href={SOURCES["nasa-power"].url} />
      </p>
    </section>
  );

  const checkBlock = card.check.applies ? (
    <section className="ev-card" key="check" aria-labelledby="ev-check-title">
      <h3 id="ev-check-title">Check soil moisture before planting</h3>
      {card.check.count !== null && card.check.denominator !== null ? (
        <p className="ev-big">
          <span className="ev-num tabular">{card.check.count}</span>
          <span className="ev-big-text">of {card.check.denominator} past springs</span>
        </p>
      ) : null}
      {legVM?.springs.length ? (
        <div className="cmp-strip ev-dots" aria-hidden="true">
          {legVM.springs.map((sp) => (
            <span
              key={sp.year}
              className={`ws-dot has-tip${flagged.has(sp.year) ? " is-check" : ""}${sp.complete ? "" : " is-missing"}`}
              data-tip={`Spring ${sp.year}${flagged.has(sp.year) ? ": check soil moisture" : ""}`}
            />
          ))}
        </div>
      ) : null}
      {gap !== null && guideDays !== null ? (
        <div className="ev-gap" role="img" aria-label={`Your plan leaves ${gap} days between ending the rye and planting. NC State guidance is ${guideDays} days.`}>
          <p className="ev-gap-title">Days between ending the rye and planting</p>
          <div className="ev-gap-row">
            <span>Your plan</span>
            <span className="ev-gap-track">
              <span className="is-plan" style={{ width: `${(gap / Math.max(gap, guideDays)) * 100}%` }} />
            </span>
            <strong className="tabular">{gap} days</strong>
          </div>
          <div className="ev-gap-row">
            <span>NC State</span>
            <span className="ev-gap-track">
              <span className="is-guide" style={{ width: `${(guideDays / Math.max(gap, guideDays)) * 100}%` }} />
            </span>
            <strong className="tabular">{guideDays} days</strong>
          </div>
        </div>
      ) : null}
      <p className="ev-say">
        {gap !== null && guideDays !== null
          ? `Your plan ends the rye ${gap} days before planting. NC State says to leave at least ${guideDays} when dry soil is a concern, so the dry springs are marked: look at the field before you plant. `
          : "NC State says to end the cover crop at least two weeks before planting soybeans when dry soil is a concern, so the dry springs are marked: look at the field before you plant. "}
        <SourceChip kind="ncstate" href={ryeCheck?.source?.url ?? SOURCES["ncs-soy-4"].url} />
      </p>
    </section>
  ) : null;

  const lead: ReactNode[] = focus === "check" && checkBlock ? [checkBlock, rainBlock] : [rainBlock, checkBlock];

  const items: AccordionItem[] = [
    {
      id: "spring",
      title: "The spring you picked",
      meta: y ? y.year : undefined,
      body: (
        <div className="ev-section">
          <dl className="ev-dl">
            <dt>Dates</dt>
            <dd>{y ? historicalWindow(y.window) : "None selected"}</dd>
            <dt>Rain in those 30 days</dt>
            <dd>
              {y ? mm(y.totalMm) : "Not available"} <SourceChip kind="nasa" />
            </dd>
            <dt>Rank (1 = driest)</dt>
            <dd>
              {y && y.rank !== null ? `${y.rank} of ${y.of}${y.isDry ? ", in the driest 20%" : ""}` : "Withheld"} <SourceChip kind="calculated" />
            </dd>
            <dt>That spring on this plan</dt>
            <dd>{card.status ? card.status.text : "No check"}</dd>
          </dl>
          {backendReasons.length ? (
            <p className="ev-reason">
              <strong>Why the check appeared:</strong> {backendReasons.map((r) => r.reason).join("; ")}.
            </p>
          ) : card.status?.kind === "check" ? (
            <p className="ev-reason">
              <strong>Facts that met the rule:</strong>{" "}
              {[
                gap !== null && guideDays !== null && gap < guideDays ? `a ${gap}-day gap (under ${guideDays})` : null,
                y?.isDry ? "a spring in the driest 20% (NASA)" : null,
                form.moistureConcern === "yes" ? "your reported moisture concern" : null,
              ]
                .filter(Boolean)
                .join(", ")}
              .
            </p>
          ) : null}
        </div>
      ),
    },
    {
      id: "sources",
      title: "Where the numbers come from",
      body: (
        <div className="ev-section">
          <h4>
            NASA record <SourceChip kind="nasa" href={SOURCES["nasa-power"].url} />
          </h4>
          <p>
            NASA POWER daily rain (PRECTOTCORR) and root-zone soil wetness (GWETROOT) for the grid point at {view.grid.lat.toFixed(2)}°,{" "}
            {view.grid.lon.toFixed(2)}° near {view.locationLabel.replace(/\s*\(sample\)$/i, "")}.
          </p>
          <p className="ev-note">
            A regional estimate for a grid cell of about 55 by 57 km, not a farm gauge. Soil wetness{y ? ` (${wetness(y.wetnessRoot)} that spring)` : ""}{" "}
            comes from a model, not a field reading.
          </p>
          <h4>
            Your field <SourceChip kind="farmer" />
          </h4>
          <p>
            Soil: {soilLabel(form)}
            {form.soilTexture ? `, ${form.soilTexture}` : ""}. Moisture concern: {tri(form.moistureConcern)}. Irrigation: {tri(form.irrigation)}
            {form.irrigation === "yes" ? " (context only; it does not change the check)" : ""}.
          </p>
          <p className="ev-note">A texture or a report says what to check; it does not measure this year's seedbed.</p>
        </div>
      ),
    },
    {
      id: "guidance",
      title: "NC State guidance",
      body: (
        <div className="ev-section">
          <p>
            If low soil moisture is a concern, end the cover crop at least two weeks before soybean planting. The check appears when{" "}
            {(ryeCheck?.fires_when ?? "the gap is short and the spring is dry or the grower reports a low-moisture concern").replace("AND", "and").replace("OR", "or")}.
          </p>
          {card.checks.length ? (
            <ul className="ev-rules">
              {card.checks.map((c) => (
                <li key={c.rule_id}>
                  <code>{c.rule_id}</code> {c.verdict.replace("_", " ")}: {c.text ?? c.reason.replace(/^[a-z_]+:\s*/, "")}
                </li>
              ))}
            </ul>
          ) : null}
          <ul className="ev-sources">
            {sources.map((id) => (
              <li key={id}>
                <a href={SOURCES[id].url} target="_blank" rel="noreferrer">
                  {SOURCES[id].title}
                </a>{" "}
                · {SOURCES[id].publisher}
              </li>
            ))}
          </ul>
        </div>
      ),
    },
    {
      id: "plan",
      title: "This plan's dates",
      body: (
        <div className="ev-section">
          {plan?.sequence ? (
            <p>
              {plan.sequence.previous_crop_id === "soybean" ? "Soybean" : "Corn"} harvest {monthDay(plan.sequence.prev_harvest)}
              {w?.type === "cover" ? `, rye ${monthDay(w.seed)} to ${monthDay(w.terminate)}` : ""}
              {w?.type === "winter_grain" ? `, wheat ${monthDay(w.plant)} to ${monthDay(w.harvest)}` : ""},{" "}
              {plan.sequence.next_crop_id === "field_corn" ? "corn" : "soybeans"} {monthDay(plan.sequence.next_plant)}.
              {plan.dates_assumed ? " Sample dates, assumed until the handbook arrives." : ""}
              {card.key === "cover" && view.rye?.changed ? ` Rye end date moved on the slider from ${monthDay(view.rye.proposed.terminate)}.` : ""}{" "}
              <SourceChip kind={form.soilSource === "sample" ? "sample" : "farmer"} />
            </p>
          ) : (
            <p>{card.unavailableReason ?? "Not available."}</p>
          )}
          <p className="ev-note">
            Priorities: {priorities.length ? priorities.map((p) => PRIORITY_LABEL[p]).join(", ") : "none chosen"}. Emphasis:{" "}
            {emphasis === "cover" ? "more living cover" : "more time before planting"}. Priorities change what is shown first, never the numbers.
          </p>
        </div>
      ),
    },
    {
      id: "audit",
      title: "Check a number yourself",
      body: (
        <div className="ev-section">
          {onExport ? (
            <p className="ev-export">
              <Button className="btn btn-secondary btn-small" onClick={onExport}>
                Download every number as JSON
              </Button>
            </p>
          ) : null}
          <dl className="ev-dl">
            <dt>Window</dt>
            <dd>The 30 days ending the day before planting{y ? ` (${historicalDate(y.window[0])} to ${historicalDate(y.window[1])})` : ""}.</dd>
            <dt>Days with a value</dt>
            <dd>{valid === null ? "Loading or not available" : `${valid} of ${daily!.daily.length}`}</dd>
            <dt>Springs compared</dt>
            <dd>
              {complete} complete{excluded.length ? `; left out: ${excluded.join(", ")}` : "; none left out"}
            </dd>
            <dt>Median</dt>
            <dd>{view.chart.medianMm === null ? "Withheld" : mm(view.chart.medianMm)}</dd>
            <dt>Dry cutoff</dt>
            <dd>
              {dry.value === null ? "Not available" : mm(dry.value)}: {dry.method}
            </dd>
            <dt>Heavy-rain day</dt>
            <dd>{heavy.value === null ? `Definition pending (${heavy.method.toLowerCase()})` : `${heavy.value} ${heavy.unit}: ${heavy.method}`}</dd>
            <dt>Data</dt>
            <dd>
              {view.dataKind === "draft"
                ? "Draft sample: synthetic weather shaped like the service's output."
                : view.dataKind === "live"
                  ? "Live result for the dates you applied."
                  : "Saved NASA record."}{" "}
              Request {view.requestId} · snapshot {view.snapshotHash} · catalog {view.catalogVersion}
            </dd>
          </dl>

          {daily ? (
            <details className="ev-daily">
              <summary>Daily values, {historicalWindow([daily.dates.spring_window.start, daily.dates.spring_window.end])}</summary>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Date</th>
                      <th scope="col">Rain (mm)</th>
                      <th scope="col">Soil wetness</th>
                    </tr>
                  </thead>
                  <tbody>
                    {daily.daily.map((d) => (
                      <tr key={d.date}>
                        <th scope="row">{plannedDate(d.date)}</th>
                        <td className="num">{d.precip_mm === null ? "Missing" : d.precip_mm.toFixed(1)}</td>
                        <td className="num">{d.gwetroot == null ? "—" : d.gwetroot.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <th scope="row">Total</th>
                      <td className="num">{daily.spring.total_mm === null ? "—" : daily.spring.total_mm.toFixed(1)}</td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
              <Button
                className="btn btn-secondary btn-small"
                onClick={() =>
                  downloadCsv(`acre-${daily.plan_id}-${daily.year}-spring.csv`, [
                    ["date", "precip_mm", "gwetroot", "status"],
                    ...daily.daily.map((d) => [d.date, d.precip_mm === null ? "" : String(d.precip_mm), d.gwetroot == null ? "" : String(d.gwetroot), d.status ?? ""]),
                  ])
                }
              >
                Download these days as CSV
              </Button>
            </details>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <Drawer open={open} title={card.content.name} onClose={onClose} returnFocusRef={returnFocusRef}>
      {winterLine ? <p className="ev-winter">{winterLine}</p> : null}
      {lead}
      <div className="ev-more">
        <Accordion label={`More about these numbers: ${card.content.name}`} items={items} open={more} onOpen={(id) => setMore((cur) => (cur === id ? null : id))} />
      </div>
    </Drawer>
  );
}
