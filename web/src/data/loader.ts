import { Bundle } from "./schema";
import type { Bundle as BundleT } from "./schema";

/*
  Loads Rahul's data bundle. Playbook p.30 and p.45, handbook p.14:
  - bounded fetch, no endless spinner;
  - a schema or location mismatch surfaces as a visible error instead of a quiet fallback;
  - only a missing real bundle (404) falls back to the synthetic fixture, and the
    result says so, so the UI can show the "Synthetic test data" banner.
*/

export type LoadError = {
  status: "error";
  kind: "timeout" | "network" | "not-found" | "parse" | "schema" | "mismatch";
  message: string;
  detail?: string;
};

export type LoadOk = {
  status: "ok";
  bundle: BundleT;
  origin: "data" | "fixture";
};

export type LoadResult = LoadOk | LoadError;

type FetchLike = (input: string, init?: { signal?: AbortSignal }) => Promise<{
  ok: boolean;
  status: number;
  text: () => Promise<string>;
  headers?: { get: (name: string) => string | null };
}>;

/**
 * Dev servers and many static hosts answer a missing file with the app's index.html
 * and status 200 (single-page-app fallback). Treat an HTML answer as "not found".
 */
function looksLikeHtml(contentType: string | null | undefined, body: string): boolean {
  if (contentType && contentType.toLowerCase().includes("text/html")) return true;
  return /^\s*</.test(body);
}

export async function loadBundle(
  url: string,
  opts: { timeoutMs: number; expectedLocationId?: string; fetchImpl?: FetchLike },
): Promise<LoadResult> {
  const fetchImpl: FetchLike = opts.fetchImpl ?? ((u, init) => fetch(u, init));
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs);

  let text: string;
  try {
    const res = await fetchImpl(url, { signal: controller.signal });
    if (res.status === 404) {
      return { status: "error", kind: "not-found", message: "No saved data file was found." };
    }
    if (!res.ok) {
      return { status: "error", kind: "network", message: `The data file could not be loaded (HTTP ${res.status}).` };
    }
    text = await res.text();
    if (looksLikeHtml(res.headers?.get("content-type"), text)) {
      return { status: "error", kind: "not-found", message: "No saved data file was found." };
    }
  } catch (err) {
    if (controller.signal.aborted) {
      return { status: "error", kind: "timeout", message: "Loading the saved NASA record took too long." };
    }
    return { status: "error", kind: "network", message: "The data file could not be loaded.", detail: String(err) };
  } finally {
    clearTimeout(timer);
  }

  let json: unknown;
  try {
    json = JSON.parse(text);
  } catch (err) {
    return { status: "error", kind: "parse", message: "The data file is not valid JSON.", detail: String(err) };
  }

  const parsed = Bundle.safeParse(json);
  if (!parsed.success) {
    const first = parsed.error.issues[0];
    return {
      status: "error",
      kind: "schema",
      message: "The data file does not match the agreed format.",
      detail: first ? `${first.path.join(".")}: ${first.message}` : undefined,
    };
  }

  const bundle = parsed.data;
  if (opts.expectedLocationId && bundle.manifest.point.id !== opts.expectedLocationId) {
    return {
      status: "error",
      kind: "mismatch",
      message: `This saved record is for ${bundle.manifest.point.label}, not the selected location.`,
    };
  }

  return { status: "ok", bundle, origin: bundle.manifest.synthetic ? "fixture" : "data" };
}

/** Real bundle first; only if it does not exist yet, the synthetic fixture. */
export async function loadPreferred(
  dataUrl: string,
  fixtureUrl: string,
  opts: { timeoutMs: number; expectedLocationId?: string; fetchImpl?: FetchLike },
): Promise<LoadResult> {
  const real = await loadBundle(dataUrl, opts);
  if (real.status === "error" && real.kind === "not-found") {
    return loadBundle(fixtureUrl, opts);
  }
  return real;
}
