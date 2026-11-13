import { useCallback, useEffect, useRef, useState } from "react";
import { DATA_URL, FIXTURE_URL, LOAD_TIMEOUT_MS, SAMPLE_LOCATION_ID } from "../config";
import { loadPreferred, type LoadResult } from "../data/loader";

export type BundleState = { status: "loading" } | LoadResult;

/**
 * Loads the data bundle once, with a retry. A request counter guarantees a slow,
 * older response can never replace a newer one (handbook p.14).
 */
export function useBundle(): { state: BundleState; retry: () => void } {
  const [state, setState] = useState<BundleState>({ status: "loading" });
  const requestId = useRef(0);

  const load = useCallback(() => {
    const id = ++requestId.current;
    setState({ status: "loading" });
    loadPreferred(DATA_URL, FIXTURE_URL, { timeoutMs: LOAD_TIMEOUT_MS, expectedLocationId: SAMPLE_LOCATION_ID }).then(
      (result) => {
        if (id === requestId.current) setState(result);
      },
    );
  }, []);

  useEffect(() => {
    load();
    return () => {
      requestId.current++;
    };
  }, [load]);

  return { state, retry: load };
}
