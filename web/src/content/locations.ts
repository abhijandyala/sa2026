/*
  Places the grower can pick (Phase 9). Union County is the saved sample: its weather is
  stored with the site and always loads. Every other place needs the live service, which
  resolves the point to a NASA POWER grid cell and says whether weather history exists.
  County points are approximate county centers, not farms. The frontend never decides
  whether a point is in North Carolina or which region it is in; the backend does.
*/

export interface Place {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  /** The saved sample, stored with the site. */
  sample?: true;
}

/** Union County uses the backend's own sample point (tests/field/test_location.py). */
export const SAMPLE_PLACE: Place = { id: "union", name: "Union County", latitude: 34.98, longitude: -80.55, sample: true };

export const PLACES: Place[] = [
  SAMPLE_PLACE,
  { id: "iredell", name: "Iredell County", latitude: 35.81, longitude: -80.87 },
  { id: "rowan", name: "Rowan County", latitude: 35.64, longitude: -80.53 },
  { id: "johnston", name: "Johnston County", latitude: 35.52, longitude: -78.37 },
  { id: "wayne", name: "Wayne County", latitude: 35.36, longitude: -77.99 },
  { id: "duplin", name: "Duplin County", latitude: 34.94, longitude: -77.93 },
  { id: "pitt", name: "Pitt County", latitude: 35.59, longitude: -77.37 },
  { id: "robeson", name: "Robeson County", latitude: 34.64, longitude: -79.1 },
];

export const placeById = (id: string): Place | undefined => PLACES.find((p) => p.id === id);
