// Product-level constants. Change the name here and it changes everywhere.
export const APP_NAME = "Fieldback";
export const TASK_TITLE = "Compare winter crop plans";
export const TAGLINE = "Compare three winter plans for this farm against past springs recorded by NASA.";
export const CHALLENGE_LABEL = "NASA Space Apps 2026 · Field Shift";

// Data file the planner loads. Rahul's pipeline writes the real bundle here;
// until then the synthetic fixture is used and the UI shows a banner.
export const DATA_URL = "./data/bundle.json";
export const FIXTURE_URL = "./data/fixture-synthetic.json";
export const SAMPLE_LOCATION_ID = "union-nc";

// Bounded fetch so the UI never shows an endless spinner (playbook p.30, p.45).
export const LOAD_TIMEOUT_MS = 8000;
