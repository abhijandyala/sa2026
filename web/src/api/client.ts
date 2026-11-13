import type { ZodType, ZodTypeDef } from "zod";
import { CompareResponse, ReplayResponse, SensitivityResponse, YearsResponse, type PlanInput } from "./schema";

/*
  Two ways to get data, one interface:
  - the saved sample (public/data/sample/*.json), always available and offline;
  - the live backend (Render), used for date edits when VITE_API_BASE is set.
  Playbook p.30 and p.45, handbook p.14: bounded waits, visible failures, and a
  slow or older response can never replace a newer one.
*/

export type Origin = "saved" | "live";

export type Failure = {
  ok: false;
  kind: "timeout" | "network" | "not-found" | "parse" | "schema" | "stale" | "offline";
  message: string;
  detail?: string;
};
export type Success<T> = { ok: true; data: T; origin: Origin };
export type Result<T> = Success<T> | Failure;

type FetchLike = (
  input: string,
  init?: { signal?: AbortSignal; method?: string; headers?: Record<string, string>; body?: string },
) => Promise<{ ok: boolean; status: number; text: () => Promise<string>; headers?: { get: (n: string) => string | null } }>;

export interface ClientOptions {
  sampleBase: string;
  apiBase?: string | null;
  timeoutMs: number;
  fetchImpl?: FetchLike;
}

function looksLikeHtml(contentType: string | null | undefined, body: string): boolean {
  if (contentType && contentType.toLowerCase().includes("text/html")) return true;
  return /^\s*</.test(body);
}

async function getJson<T>(
  url: string,
  schema: ZodType<T, ZodTypeDef, unknown>,
  opts: { timeoutMs: number; fetchImpl: FetchLike; init?: { method?: string; headers?: Record<string, string>; body?: string } },
): Promise<{ ok: true; data: T } | Failure> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs);
  let text: string;
  try {
    const res = await opts.fetchImpl(url, { ...opts.init, signal: controller.signal });
    if (res.status === 404) return { ok: false, kind: "not-found", message: "That data file was not found." };
    if (!res.ok) return { ok: false, kind: "network", message: `The service answered with an error (HTTP ${res.status}).` };
    text = await res.text();
    if (looksLikeHtml(res.headers?.get("content-type"), text)) {
      return { ok: false, kind: "not-found", message: "That data file was not found." };
    }
  } catch (err) {
    if (controller.signal.aborted) return { ok: false, kind: "timeout", message: "The service took too long to answer." };
    return { ok: false, kind: "network", message: "The service could not be reached.", detail: String(err) };
  } finally {
    clearTimeout(timer);
  }
  let json: unknown;
  try {
    json = JSON.parse(text);
  } catch (err) {
    return { ok: false, kind: "parse", message: "The data is not valid JSON.", detail: String(err) };
  }
  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    const first = parsed.error.issues[0];
    return {
      ok: false,
      kind: "schema",
      message: "The data does not match the agreed format.",
      detail: first ? `${first.path.join(".")}: ${first.message}` : undefined,
    };
  }
  return { ok: true, data: parsed.data };
}

export function createClient(opts: ClientOptions) {
  const fetchImpl: FetchLike = opts.fetchImpl ?? ((u, init) => fetch(u, init));
  const base = { timeoutMs: opts.timeoutMs, fetchImpl };
  const sample = (name: string) => `${opts.sampleBase.replace(/\/$/, "")}/${name}.json`;
  const api = (path: string) => (opts.apiBase ? `${opts.apiBase.replace(/\/$/, "")}${path}` : null);

  async function saved<T>(name: string, schema: ZodType<T, ZodTypeDef, unknown>): Promise<Result<T>> {
    const r = await getJson(sample(name), schema, base);
    return r.ok ? { ok: true, data: r.data, origin: "saved" } : r;
  }

  return {
    hasLiveApi: Boolean(opts.apiBase),

    /** The saved Union County sample: the judge path. Never needs the network beyond the site itself. */
    loadSample: async () => {
      const [years, compare, sensitivity] = await Promise.all([
        saved("years", YearsResponse),
        saved("compare", CompareResponse),
        saved("sensitivity", SensitivityResponse),
      ]);
      return { years, compare, sensitivity };
    },

    /**
     * Daily detail for one season. Saved sample by default; the live service when the
     * results on screen came from it (edited dates), so the detail matches the cards.
     */
    replay: async (year: number, planId: string, origin: Origin): Promise<Result<ReplayResponse>> => {
      const url = origin === "live" ? api(`/v1/seasons/${year}/replay?plan=${encodeURIComponent(planId)}`) : null;
      if (url) {
        const r = await getJson(url, ReplayResponse, base);
        return r.ok ? { ok: true, data: r.data, origin: "live" } : r;
      }
      return saved(`replay/${encodeURIComponent(planId)}/${year}`, ReplayResponse);
    },

    /** Recompute for edited dates. Needs the live API; a failure keeps the saved sample on screen. */
    compare: async (plans: PlanInput[], locationId: string): Promise<Result<CompareResponse>> => {
      const url = api("/v1/plans/compare");
      if (!url) return { ok: false, kind: "offline", message: "Editing dates needs the live service, which is not connected." };
      const r = await getJson(url, CompareResponse, {
        ...base,
        init: { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ location_id: locationId, plans }) },
      });
      return r.ok ? { ok: true, data: r.data, origin: "live" } : r;
    },
  };
}

export type Client = ReturnType<typeof createClient>;

/**
 * Keeps only the newest answer. Each call gets a ticket; an answer whose ticket is no
 * longer the latest is dropped (handbook p.14). The backend's meta.request_id is shown
 * in evidence; ordering is enforced here on the client side.
 */
export function latestOnly() {
  let ticket = 0;
  return {
    next: () => ++ticket,
    isLatest: (t: number) => t === ticket,
  };
}
