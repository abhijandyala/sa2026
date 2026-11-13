import { useEffect, useRef, useState, type RefObject } from "react";
import { validateForm, type FarmForm, type FormErrors } from "../../state/form";
import { Banner, Button, DateField, Drawer, Field, TriStateField } from "../../ui/components";

/*
  The farm form (card 1.3). Order: what is already planned, the winter dates, then the
  field context (playbook p.39). Edits stay a draft until Apply dates; errors sit beside
  their field and focus moves to the first one. Unknown is a real answer.
*/

const LABELS: Record<keyof FarmForm, string> = {
  cornHarvest: "Corn harvest date",
  soyPlant: "Planned soybean planting date",
  ryeSeed: "Rye seeding date",
  ryeEnd: "When would you end the rye cover?",
  ryeEndEarlier: "An earlier rye end date to compare",
  wheatPlant: "Wheat planting date",
  wheatHarvest: "Wheat harvest date",
  soyDoubleCropPlant: "Soybean planting date after wheat",
  soyHarvest: "Soybean harvest date",
  rye2Seed: "Rye seeding date",
  rye2End: "When would you end the rye before corn?",
  cornPlant: "Planned corn planting date",
  moistureConcern: "Field moisture concern",
  irrigation: "Irrigation available",
  soilSource: "Where the soil information comes from",
  soilTexture: "Soil texture",
};

export function FarmFormDrawer({
  open,
  draft,
  pending,
  applying,
  hasLiveApi,
  message,
  onEdit,
  onApply,
  onDiscard,
  onClose,
  returnFocusRef,
}: {
  open: boolean;
  draft: FarmForm;
  pending: boolean;
  applying: boolean;
  hasLiveApi: boolean;
  message: string | null;
  onEdit: (patch: Partial<FarmForm>) => void;
  onApply: () => void;
  onDiscard: () => void;
  onClose: () => void;
  returnFocusRef: RefObject<HTMLElement>;
}) {
  const [errors, setErrors] = useState<FormErrors>({});
  const [focusField, setFocusField] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (!open) setErrors({});
  }, [open]);

  // Move focus to the first error once React has drawn it (playbook p.39).
  useEffect(() => {
    if (!focusField) return;
    formRef.current?.querySelector<HTMLElement>(`#f-${focusField}`)?.focus();
    setFocusField(null);
  }, [focusField]);

  const date = (key: keyof FarmForm, hint?: string) => (
    <DateField
      id={`f-${key}`}
      label={LABELS[key]}
      value={(draft[key] as string) || null}
      hint={hint}
      error={errors[key] ?? null}
      onChange={(v) => {
        onEdit({ [key]: v ?? "" });
        if (errors[key]) setErrors((e) => ({ ...e, [key]: undefined }));
      }}
    />
  );

  const submit = () => {
    const e = validateForm(draft);
    setErrors(e);
    const first = Object.keys(e)[0];
    if (first) {
      setFocusField(first);
      return;
    }
    onApply();
  };

  const errorCount = Object.values(errors).filter(Boolean).length;

  return (
    <Drawer open={open} title="Edit farm dates" onClose={onClose} returnFocusRef={returnFocusRef}>
      <form
        ref={formRef}
        className="farm-form"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <p className="form-intro">
          A rotation has two winters. Each is replayed against every past spring for the same calendar dates and shown on its own.
        </p>

        {errorCount > 1 ? (
          <Banner kind="error">
            {errorCount} dates need attention. Each one is marked below.
          </Banner>
        ) : null}

        <p className="form-section">Winter 1: corn → soybeans (2026–27)</p>
        <fieldset className="form-group">
          <legend>What is already planned</legend>
          {date("cornHarvest")}
          {date("soyPlant", "Full-season soybeans after the winter plan.")}
        </fieldset>

        <fieldset className="form-group">
          <legend>Winter cover: cereal rye</legend>
          {date("ryeSeed")}
          {date("ryeEnd", "End rye cover = terminate it. NC State suggests at least 14 days before soybeans if soil moisture is a concern.")}
          {date("ryeEndEarlier")}
        </fieldset>

        <fieldset className="form-group">
          <legend>Grain crop: winter wheat</legend>
          <p className="form-note">Not evaluated yet: wheat windows are still being sourced. Your dates are kept for when they are.</p>
          {date("wheatPlant")}
          {date("wheatHarvest")}
          {date("soyDoubleCropPlant")}
        </fieldset>

        <p className="form-section">Winter 2: soybeans → corn (2027–28)</p>
        <fieldset className="form-group">
          <legend>What is already planned</legend>
          {date("soyHarvest")}
          {date("cornPlant")}
        </fieldset>
        <fieldset className="form-group">
          <legend>Winter cover: cereal rye</legend>
          {date("rye2Seed")}
          {date("rye2End", "NC State catalog rule cr_tt_01 prefers ending rye 7–14 days before corn.")}
        </fieldset>

        <fieldset className="form-group">
          <legend>Your field</legend>
          <TriStateField
            id="f-moisture"
            label={LABELS.moistureConcern}
            hint="Reported by you. Yes shows the NC State timing guidance on short gaps in every year."
            value={draft.moistureConcern}
            onChange={(v) => onEdit({ moistureConcern: v })}
          />
          <TriStateField
            id="f-irrigation"
            label={LABELS.irrigation}
            hint="Recorded as context only. It does not change the moisture check."
            value={draft.irrigation}
            onChange={(v) => onEdit({ irrigation: v })}
          />
          <Field label={LABELS.soilSource} htmlFor="f-soilSource" hint="Kept separate from weather data in the evidence.">
            <select
              id="f-soilSource"
              className="input"
              value={draft.soilSource}
              onChange={(e) => onEdit({ soilSource: e.target.value as FarmForm["soilSource"] })}
            >
              <option value="sample">Sample profile (fictional)</option>
              <option value="farmer">Reported by me</option>
              <option value="usda">USDA mapped estimate</option>
              <option value="unknown">Unknown</option>
            </select>
          </Field>
          <Field label={LABELS.soilTexture} htmlFor="f-soilTexture" hint="Optional, for example sandy loam.">
            <input
              id="f-soilTexture"
              className="input"
              type="text"
              value={draft.soilTexture}
              onChange={(e) => onEdit({ soilTexture: e.target.value })}
            />
          </Field>
        </fieldset>

        {message ? <Banner kind="info">{message}</Banner> : null}
        {!hasLiveApi && !message ? (
          <p className="form-note">
            The live service is not connected in this build, so new dates can be checked here but results stay on the saved
            Union County sample.
          </p>
        ) : null}

        <div className="form-actions">
          <Button variant="primary" type="submit" disabled={applying}>
            {applying ? "Checking past springs…" : "Apply dates"}
          </Button>
          <Button onClick={onDiscard} disabled={applying}>
            {pending ? "Discard changes" : "Close"}
          </Button>
          {pending ? <span className="pending-note">Edited, not applied yet</span> : null}
        </div>
      </form>
    </Drawer>
  );
}
