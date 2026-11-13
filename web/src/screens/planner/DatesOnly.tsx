import type { PlaceState } from "../../state/useData";
import { Button } from "../../ui/components";

/*
  Shown instead of the results when the chosen place has no weather record (Phase 9).
  The planned dates still compare; nothing from another place's weather is shown.
*/
export function DatesOnly({
  place,
  onBack,
  onChoose,
}: {
  place: Extract<PlaceState, { kind: "dates-only" | "checking" }>;
  onBack: () => void;
  onChoose: () => void;
}) {
  const name = `${place.place.name}, NC`;
  return (
    <section className="dates-only" aria-labelledby="dates-only-title" aria-busy={place.kind === "checking"}>
      <p className="marker">{name}</p>
      <h2 id="dates-only-title">
        {place.kind === "checking" ? `Checking NASA weather history for ${place.place.name}…` : `No saved record for ${place.place.name} yet. Showing dates only.`}
      </h2>
      {place.kind === "dates-only" ? <p className="dates-only-reason">{place.reason}</p> : null}
      <p>
        Your planned dates are compared on the calendar below. Rain, dry springs and field-moisture checks need weather history for
        this place, so they are not shown.
      </p>
      <div className="dates-only-actions">
        <Button variant="primary" onClick={onBack}>
          Back to the Union County sample
        </Button>
        <Button onClick={onChoose}>Choose another place</Button>
      </div>
    </section>
  );
}
