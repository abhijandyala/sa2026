import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createClient, latestOnly, type Failure, type Origin } from "../api/client";
import type { CompareResponse, SensitivityResponse, YearsResponse } from "../api/schema";
import { LOAD_TIMEOUT_MS, LIVE_TIMEOUT_MS, SAMPLE_BASE, API_BASE, SAMPLE_LOCATION_ID } from "../config";
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
  const order = useRef(latestOnly());

  const load = useCallback(() => {
    const t = order.current.next();
    setState({ status: "loading" });
    client.loadSample().then(({ years, compare, sensitivity }) => {
      if (!order.current.isLatest(t)) return;
      if (!years.ok) return setState({ status: "error", failure: years });
      if (!compare.ok) return setState({ status: "error", failure: compare });
      setState({
        status: "ready",
        data: { years: years.data, compare: compare.data, sensitivity: sensitivity.ok ? sensitivity.data : null, origin: "saved" },
      });
    });
  }, [client]);

  useEffect(() => {
    load();
  }, [load]);

  const apply = useCallback(
    async (form: FarmForm): Promise<ApplyOutcome> => {
      const t = order.current.next();
      setApplying(true);
      const r = await liveClient.compare(toPlanInputs(form), SAMPLE_LOCATION_ID);
      if (!order.current.isLatest(t)) return { ok: false, message: "A newer change replaced this one." };
      setApplying(false);
      if (!r.ok) {
        return {
          ok: false,
          message:
            r.kind === "offline"
              ? "Editing dates needs the live service, which is not connected. Showing the saved Union County sample."
              : `${r.message} Showing the saved Union County sample.`,
        };
      }
      setState((prev) =>
        prev.status === "ready" ? { status: "ready", data: { ...prev.data, compare: r.data, origin: "live" } } : prev,
      );
      return { ok: true };
    },
    [liveClient],
  );

  return { state, retry: load, apply, applying, hasLiveApi: client.hasLiveApi };
}
