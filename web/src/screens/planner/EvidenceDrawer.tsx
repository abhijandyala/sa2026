import type { RefObject } from "react";
import { SOURCES } from "../../content/strategies";
import { historicalDate, historicalWindow, mm, monthDay, plannedDate, wetness } from "../../data/format";
import type { FarmForm } from "../../state/form";
import type { Emphasis, Priority } from "../../state/model";
import type { ReplayState } from "../../state/useData";
import type { CardVM, ViewModel } from "../../view/build";
import { Button, Drawer, SourceChip } from "../../ui/components";

/*
  The evidence panel (cards 6.1 and 6.2). Answers a skeptical judge's first follow-up
  without leaving the planner (playbook p.43–44, handbook p.13):
  1. what this card says, then the facts behind it, then the backend's own reason;
  2. four sources, each labeled: NASA record, your field, NC State guidance, your plan;
  3. audit details to redo one number with a calculator, and the daily values as CSV.
  Opening it never changes the selection; closing returns focus to its button.
*/

const PRIORITY_LABEL: Record<Priority, string> = { soil: "Protect the soil", income: "Extra income", water: "Save water" };

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
}) {
  const y = view.selectedYear;
  const dry = view.thresholds.dry_spring;
  const heavy = view.thresholds.heavy_rain;
  const plan = card.plan;
  const w = plan?.sequence.winter;
  const sources = [...new Set(Object.values(card.content.headings).flat().map((c) => c.source).filter(Boolean))] as Array<keyof typeof SOURCES>;
  const daily = replay.status === "ready" && replay.data.year === y?.year ? replay.data : null;
  const backendReasons =
    daily && plan && daily.plan_id === plan.plan_id && !(card.key === "cover" && view.rye?.changed) ? daily.checks_triggered : [];
  const valid = daily ? daily.daily.filter((d) => d.precip_mm !== null).length : null;
  const complete = view.window?.years.filter((r) => r.status === "complete").length ?? 0;
  const excluded = view.window?.years.filter((r) => r.status !== "complete").map((r) => r.year) ?? [];
  const gap = plan?.calendar.termination_gap_days ?? plan?.calendar.harvest_to_plant_days ?? null;
  const ryeCheck = plan?.spring_checks.find((c) => c.check_id === "rye_soy_short_gap_moisture");

  return (
    <Drawer open={open} title={`Evidence: ${card.content.name}`} onClose={onClose} returnFocusRef={returnFocusRef}>
      <section className="ev-section ev-lead">
        <h3>What this card says</h3>
        <ul className="ev-facts">
          <li>
            Median winter rain on ground with no planned living cover:{" "}
            <strong>{card.soil.mm === null ? "not available" : mm(card.soil.mm)}</strong>
            {card.soil.seasons ? ` across ${card.soil.seasons} winters` : ""}. It counts rain on the calendar, not erosion; crop residue may
            still cover the ground.
          </li>
          <li>
            {card.check.applies ? (
              <>
                Field-moisture check: <strong>{card.check.count} of {card.check.denominator} springs</strong>.
              </>
            ) : (
              "The rye timing check does not apply to this plan."
            )}
          </li>
          {y ? (
            <li>
              This spring ({y.year}): <strong>{card.status ? card.status.text : "no check"}</strong>.
            </li>
          ) : null}
        </ul>
      </section>

      <section className="ev-section">
        <h3>The facts behind it</h3>
        <dl className="ev-dl">
          <dt>Spring</dt>
          <dd>{y ? `${y.year}, ${historicalWindow(y.window)}` : "None selected"}</dd>
          <dt>Rain in those 30 days</dt>
          <dd>
            {y ? mm(y.totalMm) : "—"} <SourceChip kind="nasa" />
          </dd>
          <dt>Rank (1 = driest)</dt>
          <dd>
            {y && y.rank !== null ? `${y.rank} of ${y.of}${y.isDry ? ", in the driest 20%" : ""}` : "Withheld"} <SourceChip kind="calculated" />
          </dd>
          <dt>Days from ending the winter crop to planting</dt>
          <dd>
            {gap === null ? "Does not apply" : `${gap} days`} <SourceChip kind="calculated" />
          </dd>
          <dt>Field moisture concern</dt>
          <dd>
            {tri(form.moistureConcern)} <SourceChip kind="farmer" />
          </dd>
        </dl>
        {backendReasons.length ? (
          <p className="ev-reason">
            <strong>Why the check appeared:</strong> {backendReasons.map((r) => r.reason).join("; ")}.
          </p>
        ) : card.status?.kind === "check" ? (
          <p className="ev-reason">
            <strong>Facts that met the rule:</strong>{" "}
            {[
              gap !== null && gap < 14 ? `a ${gap}-day gap (under 14)` : null,
              y?.isDry ? "a spring in the driest 20% (NASA)" : null,
              form.moistureConcern === "yes" ? "your reported moisture concern" : null,
            ]
              .filter(Boolean)
              .join(", ")}
            .
          </p>
        ) : null}
      </section>

      <section className="ev-section">
        <h3>
          1. NASA record <SourceChip kind="nasa" href={SOURCES["nasa-power"].url} />
        </h3>
        <p>
          NASA POWER daily data: precipitation (PRECTOTCORR, mm/day) and root-zone soil wetness (GWETROOT, 0–1) for the grid point at{" "}
          {view.grid.lat.toFixed(2)}°, {view.grid.lon.toFixed(2)}° near {view.locationLabel.replace(/\s*\(sample\)$/i, "")}.
        </p>
        <p className="ev-note">
          Limit: a regional estimate for a grid cell roughly 50 km across, not a farm gauge. Soil wetness {y ? `this spring: ${wetness(y.wetnessRoot)}` : ""}{" "}
          comes from a model, not a field reading.
        </p>
      </section>

      <section className="ev-section">
        <h3>
          2. Your field <SourceChip kind="farmer" />
        </h3>
        <p>
          Soil: {soilLabel(form)}
          {form.soilTexture ? `, ${form.soilTexture}` : ""}. Moisture concern: {tri(form.moistureConcern)}. Irrigation: {tri(form.irrigation)}
          {form.irrigation === "yes" ? " (context only; it does not change the check)" : ""}.
        </p>
        <p className="ev-note">Limit: a texture or a report says what to check; it does not measure this year's seedbed.</p>
      </section>

      <section className="ev-section">
        <h3>
          3. NC State guidance <SourceChip kind="ncstate" href={SOURCES["ncs-soy-4"].url} />
        </h3>
        <p>
          If low soil moisture is a concern, end the cover crop at least two weeks before soybean planting. The check fires when{" "}
          {(ryeCheck?.fires_when ?? "gap < 14 days AND (dry replay OR grower low-moisture concern)").replace("AND", "and").replace("OR", "or")}.
        </p>
        {card.checks.length ? (
          <ul className="ev-rules">
            {card.checks.map((c) => (
              <li key={c.rule_id}>
                <code>{c.rule_id}</code> {c.verdict.replace("_", " ")}: {c.reason.replace(/^[a-z_]+:\s*/, "")}
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
      </section>

      <section className="ev-section">
        <h3>
          4. Your plan <SourceChip kind={form.soilSource === "sample" ? "sample" : "farmer"} />
        </h3>
        {plan ? (
          <p>
            Corn harvest {monthDay(plan.sequence.prev_harvest)}
            {w?.type === "cover" ? `, rye ${monthDay(w.seed)} to ${monthDay(w.terminate)}` : ""}
            {w?.type === "winter_grain" ? `, wheat ${monthDay(w.plant)} to ${monthDay(w.harvest)}` : ""}, soybeans {monthDay(plan.sequence.next_plant)}.
            {card.key === "cover" && view.rye?.changed ? ` Rye end date moved on the slider from ${monthDay(view.rye.proposed.terminate)}.` : ""}
          </p>
        ) : (
          <p>Not available.</p>
        )}
        <p className="ev-note">
          Priorities: {priorities.length ? priorities.map((p) => PRIORITY_LABEL[p]).join(", ") : "none chosen"}. Emphasis:{" "}
          {emphasis === "cover" ? "more living cover" : "more time before planting"}. Priorities change what is shown first, never the numbers.
        </p>
      </section>

      <section className="ev-section ev-audit">
        <h3>Check one number yourself</h3>
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
            <summary>
              Daily values, {historicalWindow([daily.dates.spring_window.start, daily.dates.spring_window.end])}
            </summary>
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
                downloadCsv(`fieldback-${daily.plan_id}-${daily.year}-spring.csv`, [
                  ["date", "precip_mm", "gwetroot", "status"],
                  ...daily.daily.map((d) => [d.date, d.precip_mm === null ? "" : String(d.precip_mm), d.gwetroot == null ? "" : String(d.gwetroot), d.status ?? ""]),
                ])
              }
            >
              Download these days as CSV
            </Button>
          </details>
        ) : null}
      </section>
    </Drawer>
  );
}
