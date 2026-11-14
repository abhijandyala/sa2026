import { useEffect, useState } from "react";
import { createClient } from "../api/client";
import type { CompareResponse, SensitivityResponse, YearsResponse } from "../api/schema";
import { LOAD_TIMEOUT_MS, SAMPLE_BASE } from "../config";

/** The saved NASA record, loaded once for the marketing pages so their demos and numbers are the app's own. */
export interface SiteData {
  years: YearsResponse;
  compare: CompareResponse;
  sensitivity: SensitivityResponse | null;
  origin: "saved";
}

let cached: Promise<SiteData | null> | null = null;
function load(): Promise<SiteData | null> {
  cached ??= createClient({ sampleBase: SAMPLE_BASE, timeoutMs: LOAD_TIMEOUT_MS })
    .loadSample()
    .then(({ years, compare, sensitivity }) =>
      years.ok && compare.ok ? { years: years.data, compare: compare.data, sensitivity: sensitivity.ok ? sensitivity.data : null, origin: "saved" as const } : null,
    )
    .catch(() => null);
  return cached;
}

/** `undefined` while loading, `null` when the saved record could not be read. */
export function useSiteData(): SiteData | null | undefined {
  const [data, setData] = useState<SiteData | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    load().then((d) => live && setData(d));
    return () => {
      live = false;
    };
  }, []);
  return data;
}
