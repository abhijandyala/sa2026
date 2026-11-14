import { useEffect, useState, type RefObject } from "react";
import { PLACES, type Place } from "../../content/locations";
import type { LatLon } from "../../api/client";
import { Banner, Button, Drawer, Field } from "../../ui/components";
import type { GridCell } from "../../state/useData";
import { NcMap } from "./NcMap";

/*
  Choose a place (Phase 9). Union County is the saved sample and always loads. Other places
  need the live service, which finds the NASA POWER grid cell and says whether weather history
  exists there. Whether a point is in North Carolina is the backend's call, not this form's.
*/

export const CUSTOM_ID = "custom";

export function customPlace(p: LatLon): Place {
  return { id: CUSTOM_ID, name: `Point ${p.latitude.toFixed(2)}, ${p.longitude.toFixed(2)}`, latitude: p.latitude, longitude: p.longitude };
}

function parseCoord(text: string, lo: number, hi: number): number | null {
  const v = Number(text.trim());
  return text.trim() !== "" && Number.isFinite(v) && v >= lo && v <= hi ? v : null;
}

export function LocationDrawer({
  open,
  placeId,
  custom,
  hasLiveApi,
  samplePoint,
  resolved,
  onChoose,
  onClose,
  returnFocusRef,
}: {
  open: boolean;
  placeId: string;
  custom: LatLon | null;
  hasLiveApi: boolean;
  /** The saved sample's NASA POWER point, from the years response. */
  samplePoint: { lat: number; lon: number; source: string };
  /** The grid cell the service named for the place on screen, if it has. */
  resolved: { placeId: string; cell: GridCell } | null;
  onChoose: (placeId: string, custom: LatLon | null) => void;
  onClose: () => void;
  returnFocusRef: RefObject<HTMLElement>;
}) {
  const [choice, setChoice] = useState(placeId);
  const [lat, setLat] = useState(custom ? String(custom.latitude) : "");
  const [lon, setLon] = useState(custom ? String(custom.longitude) : "");
  const [errors, setErrors] = useState<{ lat?: string; lon?: string }>({});

  useEffect(() => {
    if (!open) return;
    setChoice(placeId);
    setErrors({});
  }, [open, placeId]);

  const typedLat = parseCoord(lat, -90, 90);
  const typedLon = parseCoord(lon, -180, 180);
  const typedPoint = typedLat !== null && typedLon !== null ? { latitude: typedLat, longitude: typedLon } : null;

  const submit = () => {
    if (choice !== CUSTOM_ID) return onChoose(choice, null);
    const la = parseCoord(lat, -90, 90);
    const lo = parseCoord(lon, -180, 180);
    const e = {
      lat: la === null ? "Enter a latitude between -90 and 90, for example 35.52." : undefined,
      lon: lo === null ? "Enter a longitude between -180 and 180, for example -78.37." : undefined,
    };
    setErrors(e);
    if (la === null || lo === null) {
      document.getElementById(la === null ? "loc-lat" : "loc-lon")?.focus();
      return;
    }
    onChoose(CUSTOM_ID, { latitude: la, longitude: lo });
  };

  return (
    <Drawer open={open} title="Choose a place" onClose={onClose} returnFocusRef={returnFocusRef}>
      <form
        className="farm-form"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <p className="form-intro">
          Each county here has its own saved NASA record and always loads. A point you type shows results only if it falls in
          one of those NASA grid cells; otherwise you see your dates only. A.C.R.E never borrows another place's weather.
        </p>
        {!hasLiveApi ? (
          <Banner kind="info">The live service is not connected in this build, so a typed point shows dates only.</Banner>
        ) : null}

        <NcMap
          choice={choice}
          typed={choice === CUSTOM_ID ? typedPoint : null}
          cell={resolved && resolved.placeId === choice ? resolved.cell : null}
          onPick={setChoice}
        />
        <p className="loc-cell" aria-live="polite">
          {choice === placeId && choice !== CUSTOM_ID
            ? `Saved record. NASA POWER point ${samplePoint.lat.toFixed(2)}, ${samplePoint.lon.toFixed(2)} (${samplePoint.source}).`
            : resolved && resolved.placeId === choice
              ? `NASA POWER grid cell ${resolved.cell.id ?? ""} centered ${resolved.cell.lat.toFixed(2)}, ${resolved.cell.lon.toFixed(2)}, ${resolved.cell.latStep}° by ${resolved.cell.lonStep}°, named by the service.`
              : choice === CUSTOM_ID
                ? "The service names the NASA POWER grid cell when you use this point."
                : "Saved record from NASA POWER for this county's grid cell."}
        </p>

        <fieldset className="form-group">
          <legend>Place</legend>
          <div className="loc-options">
            {PLACES.map((p) => (
              <label key={p.id} className="loc-option">
                <input type="radio" name="place" value={p.id} checked={choice === p.id} onChange={() => setChoice(p.id)} />
                <span>
                  <strong>{p.name}, NC</strong>
                  <span className="loc-note">
                    {p.sample ? "Sample field · saved NASA record" : `County center ${p.latitude.toFixed(2)}, ${p.longitude.toFixed(2)} · saved NASA record`}
                  </span>
                </span>
              </label>
            ))}
            <label className="loc-option">
              <input type="radio" name="place" value={CUSTOM_ID} checked={choice === CUSTOM_ID} onChange={() => setChoice(CUSTOM_ID)} />
              <span>
                <strong>A point I type</strong>
                <span className="loc-note">Latitude and longitude in decimal degrees</span>
              </span>
            </label>
          </div>
        </fieldset>

        {choice === CUSTOM_ID ? (
          <fieldset className="form-group">
            <legend>Your point</legend>
            <Field label="Latitude" htmlFor="loc-lat" error={errors.lat ?? null}>
              <input id="loc-lat" className="input" inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} />
            </Field>
            <Field label="Longitude" htmlFor="loc-lon" error={errors.lon ?? null}>
              <input id="loc-lon" className="input" inputMode="decimal" value={lon} onChange={(e) => setLon(e.target.value)} />
            </Field>
            <p className="form-note">
              The service finds the NASA grid cell for this point and reads the record it holds for that cell. Typed points are
              not saved in shared links.
            </p>
          </fieldset>
        ) : null}

        <div className="form-actions">
          <Button variant="primary" type="submit">
            Use this place
          </Button>
          <Button onClick={onClose}>Cancel</Button>
        </div>
      </form>
    </Drawer>
  );
}
