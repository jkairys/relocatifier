/**
 * Thin client for the listings-scraper control-plane service (issue #3).
 *
 * Every call is non-fatal: network errors and unexpected statuses resolve to a
 * typed result rather than throwing, so the app degrades gracefully when the
 * service is down. The service is optional — relocatifier.com has neither the
 * service nor sales.json.
 */

const BASE_URL = import.meta.env.VITE_SCRAPER_URL ?? "http://localhost:8210";

export type RunStatus = "running" | "completed" | "failed";

export interface RunInfo {
  run_id: string;
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  detail: unknown;
}

/** Discriminated result for the mutating calls so callers can branch honestly. */
export type ScraperResult<T> =
  | { ok: true; value: T }
  /** A reachable service refused with a body — surfaced verbatim. */
  | { ok: false; status: number; detail: string }
  /** The service was unreachable (offline / CORS / network). */
  | { ok: false; status: 0; detail: string };

/**
 * Pull an honest `detail` string out of a FastAPI error body. FastAPI puts the
 * message under `detail` (string, or a validation array). Falls back to the
 * raw text. Never throws.
 */
async function readDetail(res: Response): Promise<string> {
  try {
    const text = await res.text();
    if (!text) return `${res.status} ${res.statusText}`.trim();
    try {
      const json: unknown = JSON.parse(text);
      if (json != null && typeof json === "object" && "detail" in json) {
        const detail = (json as { detail: unknown }).detail;
        if (typeof detail === "string") return detail;
        return JSON.stringify(detail);
      }
    } catch {
      /* not JSON — fall through to raw text */
    }
    return text;
  } catch {
    return `${res.status} ${res.statusText}`.trim();
  }
}

let healthPromise: Promise<boolean> | null = null;

/**
 * Probe GET /health exactly once per session; the result is cached. Resolves
 * false on any failure. Watchlist controls render only when this is true.
 */
export function checkHealth(): Promise<boolean> {
  if (healthPromise == null) {
    healthPromise = (async () => {
      try {
        const res = await fetch(`${BASE_URL}/health`, { cache: "no-cache" });
        if (!res.ok) return false;
        const json: unknown = await res.json();
        return (
          json != null &&
          typeof json === "object" &&
          (json as { status?: unknown }).status === "ok"
        );
      } catch {
        return false;
      }
    })();
  }
  return healthPromise;
}

/** POST /watchlist/{sal_code}. 422 detail is surfaced verbatim by the caller. */
export async function addToWatchlist(
  salCode: string,
): Promise<ScraperResult<unknown>> {
  try {
    const res = await fetch(
      `${BASE_URL}/watchlist/${encodeURIComponent(salCode)}`,
      { method: "POST" },
    );
    if (res.ok) {
      const value: unknown = await res.json().catch(() => null);
      return { ok: true, value };
    }
    return { ok: false, status: res.status, detail: await readDetail(res) };
  } catch {
    return { ok: false, status: 0, detail: "Scraper service unreachable." };
  }
}

/** DELETE /watchlist/{sal_code} → 204. */
export async function removeFromWatchlist(
  salCode: string,
): Promise<ScraperResult<null>> {
  try {
    const res = await fetch(
      `${BASE_URL}/watchlist/${encodeURIComponent(salCode)}`,
      { method: "DELETE" },
    );
    if (res.ok) return { ok: true, value: null };
    return { ok: false, status: res.status, detail: await readDetail(res) };
  } catch {
    return { ok: false, status: 0, detail: "Scraper service unreachable." };
  }
}

/** GET /watchlist → membership rows. Resolves [] on any failure. */
export async function fetchWatchlist(): Promise<unknown[]> {
  try {
    const res = await fetch(`${BASE_URL}/watchlist`, { cache: "no-cache" });
    if (!res.ok) return [];
    const json: unknown = await res.json();
    return Array.isArray(json) ? json : [];
  } catch {
    return [];
  }
}

/**
 * POST /runs for the given suburb. 202 → { run_id }. 409 (single-flight: a run
 * is already in progress) is returned as a non-ok result the caller handles
 * gracefully.
 */
export async function startRun(
  salCode: string,
): Promise<ScraperResult<{ run_id: string }>> {
  try {
    const res = await fetch(`${BASE_URL}/runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sal_codes: [salCode] }),
    });
    if (res.ok) {
      const json: unknown = await res.json().catch(() => null);
      const runId =
        json != null && typeof json === "object" && "run_id" in json
          ? (json as { run_id: unknown }).run_id
          : null;
      if (typeof runId === "string") return { ok: true, value: { run_id: runId } };
      return { ok: false, status: res.status, detail: "Run started but no run_id returned." };
    }
    return { ok: false, status: res.status, detail: await readDetail(res) };
  } catch {
    return { ok: false, status: 0, detail: "Scraper service unreachable." };
  }
}

/** GET /runs/{run_id}. Resolves null on any failure (caller keeps polling). */
export async function fetchRun(runId: string): Promise<RunInfo | null> {
  try {
    const res = await fetch(`${BASE_URL}/runs/${encodeURIComponent(runId)}`, {
      cache: "no-cache",
    });
    if (!res.ok) return null;
    const json: unknown = await res.json();
    if (
      json != null &&
      typeof json === "object" &&
      "status" in json &&
      "run_id" in json
    ) {
      return json as RunInfo;
    }
    return null;
  } catch {
    return null;
  }
}
