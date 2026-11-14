/*
  Places the grower can pick. Each county here has a NASA POWER record on the backend
  (data/snapshots/index.json on the backend branch; the ids are the backend's own) and a
  copy of its answers saved with the site, so every one opens with no live service.
  Union County is the sample the site starts on. A typed point needs the live service,
  which names its NASA grid cell. County points are approximate county centers, not farms.
  The frontend never decides whether a point is in North Carolina or which region it is in;
  the backend does.
*/

export interface Place {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  /** A NASA record for this place is saved with the site (public/data/nasa/<id>/). */
  saved?: true;
  /** The place the site opens on. */
  sample?: true;
}

/** Union County uses the backend's own sample point (tests/field/test_location.py). */
export const SAMPLE_PLACE: Place = { id: "union", name: "Union County", latitude: 34.98, longitude: -80.55, saved: true, sample: true };

export const PLACES: Place[] = [
  SAMPLE_PLACE,
  { id: "iredell", name: "Iredell County", latitude: 35.81, longitude: -80.87, saved: true },
  { id: "rowan", name: "Rowan County", latitude: 35.64, longitude: -80.53, saved: true },
  { id: "johnston", name: "Johnston County", latitude: 35.52, longitude: -78.37, saved: true },
  { id: "wayne", name: "Wayne County", latitude: 35.36, longitude: -77.99, saved: true },
  { id: "duplin", name: "Duplin County", latitude: 34.94, longitude: -77.93, saved: true },
  { id: "pitt", name: "Pitt County", latitude: 35.59, longitude: -77.37, saved: true },
  { id: "robeson", name: "Robeson County", latitude: 34.64, longitude: -79.1, saved: true },
];

export const placeById = (id: string): Place | undefined => PLACES.find((p) => p.id === id);
