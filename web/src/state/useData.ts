import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createClient, latestOnly, type Client, type Failure, type Origin } from "../api/client";
import type { CompareResponse, ReplayResponse, SensitivityResponse, YearsResponse } from "../api/schema";
import { LOAD_TIMEOUT_MS, LIVE_TIMEOUT_MS, SAMPLE_BASE, API_BASE } from "../config";
import { SAMPLE_PLACE, type Place } from "../content/locations";
import { toPlanInputs, type FarmForm } from "./form";

export interface Loaded {
  years: YearsResponse;
  compare: CompareResponse;
  sensitivity: SensitivityResponse | null;
  origin: Origin;
}

export type DataState =
  | { status: "loading" }
  | { status: "error"; failure: Failure }
  | { status: "ready"; data: Loaded };

export type ApplyOutcome = { ok: true } | { ok: false; message: string };

/**
 * Where the results on screen come from (Phase 9). Only the Union County sample is saved
 * with the site. Another place shows results only when the live service has weather history
 * for its grid cell; otherwise the planner shows dates only and never borrows another
 * place's weather.
 */
/** The NASA POWER grid cell the service named for a place (POST /v1/locations/resolve). */
export interface GridCell {
  id: string | null;
  lat: number;
  lon: number;
  latStep: number;
  lonStep: number;
}

export type PlaceState =
  | { kind: "sample"; place: Place }
  | { kind: "checking"; place: Place }
  | { kind: "live"; place: Place; guidanceNote: string | null; cell: GridCell | null }
  | { kind: "dates-only"; place: Place; reason: string; cell?: GridCell | null };

const tidy = (reason: string | null | undefined) =>
  reason ? reason.replace(/^[a-z_]+:\s*/, "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : null;

/**
 * Loads the saved sample (always), then recomputes through the live API when the grower
 * applies new dates. If the live call fails, the saved sample stays on screen and the
 * caller gets a plain message to show (card 1.4).
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
  const [place, setPlace] = useState<PlaceState>({ kind: "sample", place: SAMPLE_PLACE });
  const order = useRef(latestOnly());
  const saved = useRef<Loaded | null>(null);

  const load = useCallback(() => {
    const t = order.current.next();
    setState({ status: "loading" });
    client.loadSample().then(({ years, compare, sensitivity }) => {
      if (!order.current.isLatest(t)) return;
      if (!years.ok) return setState({ status: "error", failure: years });
      if (!compare.ok) return setState({ status: "error", failure: compare });
      const data: Loaded = { years: years.data, compare: compare.data, sensitivity: sensitivity.ok ? sensitivity.data : null, origin: "saved" };
      saved.current = data;
      setPlace({ kind: "sample", place: SAMPLE_PLACE });
      setState({ status: "ready", data });
    });
  }, [client]);

  useEffect(() => {
    load();
  }, [load]);

  const apply = useCallback(
    async (form: FarmForm): Promise<ApplyOutcome> => {
      const t = order.current.next();
      setApplying(true);
      const where = place.kind === "live" ? place.place : SAMPLE_PLACE;
      const r = await liveClient.compare(toPlanInputs(form), where);
      if (!order.current.isLatest(t)) return { ok: false, message: "A newer change replaced this one." };
      setApplying(false);
      if (!r.ok) {
        return {
          ok: false,
          message:
            r.kind === "offline"
              ? "Editing dates needs the live service, which is not connected. Showing the saved Union County sample."
              : `${r.message} The results on screen have not changed.`,
        };
      }
      setState((prev) =>
        prev.status === "ready" ? { status: "ready", data: { ...prev.data, compare: r.data, origin: "live" } } : prev,
      );
      return { ok: true };
    },
    [liveClient, place],
  );

  /** Switch to another place. Union County restores the saved sample; others need the live service. */
  const chooseLocation = useCallback(
    async (next: Place, form: FarmForm): Promise<void> => {
      const t = order.current.next();
      if (next.sample) {
        setPlace({ kind: "sample", place: next });
        if (saved.current) setState({ status: "ready", data: saved.current });
        return;
      }
      if (!liveClient.hasLiveApi) {
        setPlace({
          kind: "dates-only",
          place: next,
          reason: "Other places need the live service, which is not connected in this build.",
        });
        return;
      }
      setPlace({ kind: "checking", place: next });
      const resolved = await liveClient.resolveLocation(next);
      if (!order.current.isLatest(t)) return;
      if (!resolved.ok) return setPlace({ kind: "dates-only", place: next, reason: resolved.message });
      const loc = resolved.data.location;
      const g = loc.grid_cell;
      const cell: GridCell | null = g
        ? { id: loc.cell_id ?? null, lat: g.center_latitude, lon: g.center_longitude, latStep: g.lat_step_deg, lonStep: g.lon_step_deg }
        : null;
      if (loc.bounds && !loc.bounds.in_nc) {
        return setPlace({ kind: "dates-only", place: next, cell, reason: "This point is outside North Carolina, so it is not supported." });
      }
      if (!loc.weather.supported) {
        return setPlace({
          kind: "dates-only",
          place: next,
          cell,
          reason: tidy(loc.weather.reason) ?? "Weather history is not available for this grid cell yet.",
        });
      }
      const r = await liveClient.compare(toPlanInputs(form), next);
      if (!order.current.isLatest(t)) return;
      if (!r.ok) return setPlace({ kind: "dates-only", place: next, cell, reason: r.message });
      setState((prev) =>
        prev.status === "ready"
          ? { status: "ready", data: { ...prev.data, compare: r.data, sensitivity: null, origin: "live" } }
          : prev,
      );
      setPlace({
        kind: "live",
        place: next,
        cell,
        guidanceNote: loc.guidance.supported ? null : (tidy(loc.guidance.reason) ?? "NC State guidance region is unknown here."),
      });
    },
    [liveClient],
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
export function useReplay(client: Client, year: number | null, planId: string | null, origin: Origin): ReplayState {
  const [state, setState] = useState<ReplayState>({ status: "idle" });
  const order = useRef(latestOnly());
  useEffect(() => {
    if (year === null || !planId) {
      setState({ status: "idle" });
      return;
    }
    const t = order.current.next();
    setState({ status: "loading", year });
    client.replay(year, planId, origin).then((r) => {
      if (!order.current.isLatest(t)) return;
      setState(r.ok ? { status: "ready", data: r.data } : { status: "error", year, failure: r });
    });
  }, [client, year, planId, origin]);
  return state;
}
