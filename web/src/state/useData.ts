import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createClient, latestOnly, type Client, type Failure, type Origin, type PlaceRef, type ReplaySource } from "../api/client";
import type { CompareResponse, PlanInput, ReplayResponse, SensitivityResponse, YearsResponse } from "../api/schema";
import { LOAD_TIMEOUT_MS, LIVE_TIMEOUT_MS, SAMPLE_BASE, API_BASE } from "../config";
import { SAMPLE_PLACE, type Place } from "../content/locations";
import { toPlanInputs, type FarmForm } from "./form";

export interface Loaded {
  years: YearsResponse;
  compare: CompareResponse;
  sensitivity: SensitivityResponse | null;
  origin: Origin;
  /** The plans a live answer was computed for, so a season's daily detail can ask for the same plan. */
  inputs: PlanInput[] | null;
}

export type DataState =
  | { status: "loading" }
  | { status: "error"; failure: Failure }
  | { status: "ready"; data: Loaded };

export type ApplyOutcome = { ok: true } | { ok: false; message: string };

/** The NASA POWER grid cell the service named for a place (POST /v1/locations/resolve). */
export interface GridCell {
  id: string | null;
  lat: number;
  lon: number;
  latStep: number;
  lonStep: number;
}

/**
 * Where the results on screen come from. Every county in the place picker has a saved NASA
 * record stored with the site (`record` is the backend's id for it). A typed point needs the
 * live service to name its grid cell; it then uses the record of the county that shares the
 * cell. A place with no weather history shows dates only and never borrows another place's weather.
 */
export type PlaceState =
  | { kind: "saved"; place: Place; record: string; cell: GridCell | null }
  | { kind: "checking"; place: Place }
  | { kind: "live"; place: Place; record: string | null; guidanceNote: string | null; cell: GridCell | null }
  | { kind: "dates-only"; place: Place; reason: string; cell?: GridCell | null };

/** How live calls name this place: the backend's id when it has one, else the point (in the body, never a URL). */
export function placeRef(p: PlaceState): PlaceRef {
  const record = p.kind === "saved" || p.kind === "live" ? p.record : null;
  return { id: record ?? undefined, latitude: p.place.latitude, longitude: p.place.longitude };
}

/** Where the daily detail for one plan comes from, matching the results on screen. */
export function replaySource(data: Loaded, place: PlaceState, planId: string | null): ReplaySource | null {
  if (!planId || place.kind === "checking" || place.kind === "dates-only") return null;
  const plan = data.origin === "live" ? data.inputs?.find((p) => p.plan_id === planId) : undefined;
  if (plan) return { origin: "live", plan, place: placeRef(place) };
  return place.kind === "saved" ? { origin: "saved", placeId: place.record } : null;
}

const tidy = (reason: string | null | undefined) =>
  reason ? reason.replace(/^[a-z_]+:\s*/, "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : null;

/**
 * Loads the saved Union County record (always), switches to another county's saved record
 * on request, and recomputes through the live API when the grower applies new dates. If a
 * live call fails, the saved record stays on screen and the caller gets a plain message.
 */
export function useData() {
  const client = useMemo(
    () => createClient({ sampleBase: SAMPLE_BASE, apiBase: API_BASE, timeoutMs: LOAD_TIMEOUT_MS }),
    [],
  );
  const liveClient = useMemo(
    () => createClient({ sampleBase: SAMPLE_BASE, apiBase: API_BASE, timeoutMs: LIVE_TIMEOUT_MS }),
    [],
  );
  const [state, setState] = useState<DataState>({ status: "loading" });
  const [applying, setApplying] = useState(false);
  const [place, setPlace] = useState<PlaceState>({ kind: "saved", place: SAMPLE_PLACE, record: SAMPLE_PLACE.id, cell: null });
  const order = useRef(latestOnly());

  const load = useCallback(() => {
    const t = order.current.next();
    setState({ status: "loading" });
    client.loadSaved(SAMPLE_PLACE.id).then(({ years, compare, sensitivity }) => {
      if (!order.current.isLatest(t)) return;
      if (!years.ok) return setState({ status: "error", failure: years });
      if (!compare.ok) return setState({ status: "error", failure: compare });
      setPlace({ kind: "saved", place: SAMPLE_PLACE, record: SAMPLE_PLACE.id, cell: null });
      setState({ status: "ready", data: { years: years.data, compare: compare.data, sensitivity: sensitivity.ok ? sensitivity.data : null, origin: "saved", inputs: null } });
    });
  }, [client]);

  useEffect(() => {
    load();
  }, [load]);

  /** Live answer for these dates at this place: the comparison and the rye end-date sweep. */
  const recompute = useCallback(
    async (form: FarmForm, ref: PlaceRef) => {
      const inputs = toPlanInputs(form);
      const rye = inputs.find((p) => p.winter.type === "cover"); // winter 1's rye plan comes first
      const [compare, sweep] = await Promise.all([liveClient.compare(inputs, ref), rye ? liveClient.sensitivity(rye, ref) : null]);
      return { compare, sensitivity: sweep?.ok ? sweep.data : null, inputs };
    },
    [liveClient],
  );

  const apply = useCallback(
    async (form: FarmForm): Promise<ApplyOutcome> => {
      const t = order.current.next();
      setApplying(true);
      const r = await recompute(form, placeRef(place));
      if (!order.current.isLatest(t)) return { ok: false, message: "A newer change replaced this one." };
      setApplying(false);
      if (!r.compare.ok) {
        return {
          ok: false,
          message:
            r.compare.kind === "offline"
              ? "Editing dates needs the live service, which is not connected. Showing the saved record."
              : `${r.compare.message} The results on screen have not changed.`,
        };
      }
      const compare = r.compare.data;
      setState((prev) =>
        prev.status === "ready" ? { status: "ready", data: { ...prev.data, compare, sensitivity: r.sensitivity, origin: "live", inputs: r.inputs } } : prev,
      );
      return { ok: true };
    },
    [recompute, place],
  );

  /**
   * Switch to another place. A county in the picker opens its saved record. A typed point asks
   * the live service which grid cell it is in. `edited` says the grower's dates differ from the
   * sample's, so the saved record (sample dates) is followed by a live answer for those dates.
   */
  const chooseLocation = useCallback(
    async (next: Place, form: FarmForm, edited = false): Promise<void> => {
      const t = order.current.next();
      const latest = () => order.current.isLatest(t);

      /** Opens a county's saved record; false when the site has none for it. */
      const openSaved = async (record: string, cell: GridCell | null): Promise<boolean> => {
        const r = await client.loadSaved(record);
        if (!latest()) return true;
        if (!r.years.ok || !r.compare.ok) return false;
        const data: Loaded = { years: r.years.data, compare: r.compare.data, sensitivity: r.sensitivity.ok ? r.sensitivity.data : null, origin: "saved", inputs: null };
        const now: PlaceState = { kind: "saved", place: next, record, cell };
        setPlace(now);
        setState({ status: "ready", data });
        if (edited && liveClient.hasLiveApi) {
          const live = await recompute(form, placeRef(now));
          if (latest() && live.compare.ok) {
            const compare = live.compare.data;
            setState({ status: "ready", data: { ...data, compare, sensitivity: live.sensitivity, origin: "live", inputs: live.inputs } });
          }
        }
        return true;
      };

      if (next.saved) {
        if (await openSaved(next.id, null)) return;
        if (latest()) setPlace({ kind: "dates-only", place: next, reason: "The saved NASA record for this county could not be loaded." });
        return;
      }
      if (!liveClient.hasLiveApi) {
        setPlace({ kind: "dates-only", place: next, reason: "A typed point needs the live service, which is not connected in this build." });
        return;
      }
      setPlace({ kind: "checking", place: next });
      const resolved = await liveClient.resolveLocation(next);
      if (!latest()) return;
      if (!resolved.ok) return setPlace({ kind: "dates-only", place: next, reason: resolved.message });
      const loc = resolved.data.location;
      const g = loc.grid_cell;
      const cell: GridCell | null = g
        ? { id: loc.cell_id ?? null, lat: g.center_latitude, lon: g.center_longitude, latStep: g.lat_step_deg, lonStep: g.lon_step_deg }
        : null;
      if (loc.bounds && !loc.bounds.in_nc) {
        return setPlace({ kind: "dates-only", place: next, cell, reason: "This point is outside North Carolina, so it is not supported." });
      }
      if (!loc.weather?.supported) {
        return setPlace({
          kind: "dates-only",
          place: next,
          cell,
          reason: tidy(loc.weather?.reason ?? loc.reason) ?? "Weather history is not available for this grid cell yet.",
        });
      }
      // The county whose NASA record covers this point's grid cell, as the service names it.
      const record = loc.weather.location_id ?? null;
      if (record && (await openSaved(record, cell))) return;
      if (!latest()) return;

      // A cell the service has weather for but the site has no saved record of: ask it directly.
      const now: PlaceState = {
        kind: "live",
        place: next,
        record,
        cell,
        guidanceNote: loc.guidance?.supported ? null : (tidy(loc.guidance?.reason) ?? "NC State guidance region is unknown here."),
      };
      const live = await recompute(form, placeRef(now));
      if (!latest()) return;
      if (!live.compare.ok) return setPlace({ kind: "dates-only", place: next, cell, reason: live.compare.message });
      const compare = live.compare.data;
      // The year list and place label for that county; a point with no named county keeps none of another place's.
      const first = compare.plans.find((p) => p.sequence)?.plan_id;
      const years = record && first ? await liveClient.years(first, record) : null;
      if (!latest()) return;
      if (!years?.ok) return setPlace({ kind: "dates-only", place: next, cell, reason: years ? years.message : "The service did not name a county record for this point." });
      setState({ status: "ready", data: { years: years.data, compare, sensitivity: live.sensitivity, origin: "live", inputs: live.inputs } });
      setPlace(now);
    },
    [client, liveClient, recompute],
  );

  return { state, retry: load, apply, applying, hasLiveApi: client.hasLiveApi, client, place, chooseLocation };
}

export type ReplayState =
  | { status: "idle" }
  | { status: "loading"; year: number }
  | { status: "ready"; data: ReplayResponse }
  | { status: "error"; year: number; failure: Failure };

/**
 * Daily detail for the selected year (card 3.3). Loads on demand; while it loads the
 * previous year's detail is not shown, so a chart can never show the wrong year.
 */
export function useReplay(client: Client, year: number | null, planId: string | null, from: ReplaySource | null): ReplayState {
  const [state, setState] = useState<ReplayState>({ status: "idle" });
  const order = useRef(latestOnly());
  useEffect(() => {
    if (year === null || !planId || !from) {
      setState({ status: "idle" });
      return;
    }
    const t = order.current.next();
    setState({ status: "loading", year });
    client.replay(year, planId, from).then((r) => {
      if (!order.current.isLatest(t)) return;
      setState(r.ok ? { status: "ready", data: r.data } : { status: "error", year, failure: r });
    });
    // The source is rebuilt each render; its content, not its identity, decides a reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, year, planId, JSON.stringify(from)]);
  return state;
}
