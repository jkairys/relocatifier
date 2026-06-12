import { useCallback, useEffect, useState } from "react";
import type { SalesArtifact } from "./types";

export const SALES_URL = "/data/sales.json";

/**
 * True when a fetch produced a real artifact, not the dev server's SPA
 * fallback (Vite can answer unknown paths with index.html). Mirrors the
 * guard in useArtifacts.ts.
 */
function isRealResponse(res: Response): boolean {
  if (!res.ok) return false;
  const type = res.headers.get("content-type") ?? "";
  return !type.includes("text/html");
}

/**
 * Fetch the recent-sales artifact. A 404 (no Watchlist yet) or any fetch
 * failure is NORMAL and resolves to null silently — the app then behaves
 * exactly as it does today, with no console noise.
 */
async function fetchSales(): Promise<SalesArtifact | null> {
  try {
    const res = await fetch(SALES_URL, { cache: "no-cache" });
    if (!isRealResponse(res)) return null;
    const json: unknown = await res.json();
    if (
      typeof json === "object" &&
      json !== null &&
      "suburbs" in json &&
      typeof (json as { suburbs: unknown }).suburbs === "object"
    ) {
      return json as SalesArtifact;
    }
    return null;
  } catch {
    return null;
  }
}

export interface SalesState {
  /** The loaded artifact, or null when absent (the common, graceful case). */
  sales: SalesArtifact | null;
  /** Re-fetch sales.json (e.g. after a scraper run completes). */
  reload: () => Promise<void>;
}

/** Loads sales.json once on mount and exposes an idempotent reload. */
export function useSales(): SalesState {
  const [sales, setSales] = useState<SalesArtifact | null>(null);

  const reload = useCallback(async () => {
    const next = await fetchSales();
    setSales(next);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const next = await fetchSales();
      if (!cancelled) setSales(next);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { sales, reload };
}
