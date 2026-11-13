// Product-level constants. Change the name here and it changes everywhere.
export const APP_NAME = "Fieldback";
export const TASK_TITLE = "Compare winter crop plans";
export const TAGLINE = "Compare three winter plans for this farm against past springs recorded by NASA.";
export const CHALLENGE_LABEL = "NASA Space Apps 2026 · Field Shift";

// The saved Union County sample, shaped like the backend API (backend docs/api/examples).
// Real generated output from the backend replaces these files with the same names.
export const SAMPLE_BASE = "./data/nasa";
export const SAMPLE_LOCATION_ID = "union_county_sample";

// The live backend, used only when the grower applies new dates. Set VITE_API_BASE at
// build time (for example the Render URL). Unset means saved sample only.
export const API_BASE: string | null = (import.meta.env.VITE_API_BASE as string | undefined) || null;

// Bounded waits so the UI never shows an endless spinner (playbook p.30, p.45).
export const LOAD_TIMEOUT_MS = 8000;
// A sleeping free-tier host can take a while to wake; past this the saved sample stays.
export const LIVE_TIMEOUT_MS = 20000;
