// Product-level constants. Change the name here and it changes everywhere.
export const APP_NAME = "A.C.R.E";
/** What the letters stand for. */
export const APP_FULL_NAME = "Agricultural Climate Replay Engine";
export const TASK_TITLE = "Compare winter crop plans";
export const TAGLINE = "Compare three winter plans for this farm against past springs recorded by NASA.";
export const CHALLENGE_LABEL = "NASA Space Apps 2026 · Field Shift";

// The saved NASA record: the backend's real responses, one folder per county (npm run data).
export const SAMPLE_BASE = "./data/nasa";
export const SAMPLE_LOCATION_ID = "union_county_sample";

// The live backend, used when the grower applies new dates or types a point. Set
// VITE_API_BASE at build time to the Railway service's public address, for example
// https://<service>.up.railway.app (no trailing path). Unset means saved records only.
export const API_BASE: string | null = (import.meta.env.VITE_API_BASE as string | undefined) || null;

// Bounded waits so the UI never shows an endless spinner (playbook p.30, p.45).
export const LOAD_TIMEOUT_MS = 8000;
// A live comparison replays 45 springs for five plans: about 5 s on a laptop, longer on a
// small shared host, and longer still if the host was asleep. Past this the saved record stays.
export const LIVE_TIMEOUT_MS = 45000;
