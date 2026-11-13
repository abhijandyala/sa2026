import type { RefObject } from "react";
import { SOURCES } from "../../content/strategies";
import { historicalWindow, mm, wetness } from "../../data/format";
import type { FarmForm } from "../../state/form";
import type { CardVM, ViewModel } from "../../view/build";
import { Drawer, SourceChip } from "../../ui/components";

/*
  First version of the evidence panel (full version is Phase 6). It answers "why does
  this card say that?" from four places: the NASA record, the grower's own report,
  the NC State rule, and the plan dates. Opening it never changes the selection.
*/
export function EvidenceDrawer({
  open,
  view,
  card,
  form,
  onClose,
  returnFocusRef,
}: {
  open: boolean;
  view: ViewModel;
  card: CardVM;
  form: FarmForm;
  onClose: () => void;
  returnFocusRef: RefObject<HTMLElement>;
}) {
  const y = view.selectedYear;
  const dry = view.thresholds.dry_spring;
  const heavy = view.thresholds.heavy_rain;
  const sources = [...new Set(Object.values(card.content.headings).flat().map((c) => c.source).filter(Boolean))] as Array<keyof typeof SOURCES>;
  const soil =
    form.soilSource === "farmer" ? "Reported by the grower" : form.soilSource === "usda" ? "USDA mapped estimate" : form.soilSource === "sample" ? "Sample profile (fictional)" : "Unknown";

  return (
    <Drawer open={open} title={`Evidence: ${card.content.name}`} onClose={onClose} returnFocusRef={returnFocusRef}>
      <section className="ev-section">
        <h3>What this card shows</h3>
        <p>
          Median winter rain on ground with no planned living cover: {card.soil.mm === null ? "not available" : mm(card.soil.mm)}
          {card.soil.seasons ? ` across ${card.soil.seasons} winters` : ""}. This counts rain and calendar overlap; crop residue may
          still cover the ground.
        </p>
        <p>
          {card.check.applies
            ? `Field-moisture check (NC State, rule cr_tt_03): ${card.check.count} of ${card.check.denominator} springs. It fires when the gap is under 14 days and the spring was dry or you reported a moisture concern.`
            : "The rye timing check does not apply to this plan."}
          {card.status ? ` This spring: ${card.status.text.toLowerCase()}.` : ""}
        </p>
      </section>

      <section className="ev-section">
        <h3>
          NASA record <SourceChip kind="nasa" href={SOURCES["nasa-power"].url} />
        </h3>
        {y ? (
          <p>
            Spring {y.year}: {mm(y.totalMm)} in {historicalWindow(y.window)}, rank {y.rank} of {y.of} (1 = driest). Modeled soil
            wetness {wetness(y.wetnessRoot)}.
          </p>
        ) : (
          <p>No year selected.</p>
        )}
        <p className="ev-note">{view.gridNote}. Regional estimate, not a farm gauge.</p>
        <p className="ev-note">
          Dry window: {dry.method}. Cutoff {dry.value === null ? "not available" : mm(dry.value)}.
        </p>
        <p className="ev-note">
          Heavy-rain day: {heavy.value === null ? `definition pending (${heavy.method.toLowerCase()})` : `${heavy.value} ${heavy.unit}, ${heavy.method}`}.
        </p>
      </section>

      <section className="ev-section">
        <h3>
          Your field <SourceChip kind="farmer" />
        </h3>
        <p>
          Moisture concern: {form.moistureConcern === "unknown" ? "Unknown" : form.moistureConcern === "yes" ? "Yes" : "No"}. Irrigation:{" "}
          {form.irrigation === "unknown" ? "Unknown" : form.irrigation === "yes" ? "Yes (context only)" : "No"}. Soil: {soil}
          {form.soilTexture ? `, ${form.soilTexture}` : ""}.
        </p>
      </section>

      <section className="ev-section">
        <h3>
          Crop guidance <SourceChip kind="ncstate" />
        </h3>
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
        <h3>About this data</h3>
        <p className="ev-note">
          {view.dataKind === "draft"
            ? "Draft sample: synthetic weather shaped like the backend's output. Numbers are illustrative."
            : view.dataKind === "live"
              ? "Live result from the Field Shift service for the dates you applied."
              : "Saved NASA record for the Union County sample."}{" "}
          Request {view.requestId}.
        </p>
      </section>
    </Drawer>
  );
}
