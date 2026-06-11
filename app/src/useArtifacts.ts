import { useEffect, useState } from "react";
import type { ArtifactState, MetricsArtifact, SuburbSource } from "./types";

export const METRICS_URL = "/data/metrics.json";
export const PMTILES_URL = "/data/suburbs.pmtiles";
/** Dev-only mock geometry so the UI can be built before the ETL exists. */
const MOCK_GEOJSON_URL = "/data/suburbs.mock.geojson";

/**
 * True when a fetch produced a real artifact, not the dev server's SPA
 * fallback (Vite can answer unknown paths with index.html).
 */
function isRealResponse(res: Response): boolean {
  if (!res.ok) return false;
  const type = res.headers.get("content-type") ?? "";
  return !type.includes("text/html");
}

async function probe(url: string): Promise<boolean> {
  try {
    const res = await fetch(url, { headers: { Range: "bytes=0-15" } });
    return isRealResponse(res);
  } catch {
    return false;
  }
}

async function fetchMetrics(): Promise<MetricsArtifact | null> {
  try {
    const res = await fetch(METRICS_URL, { cache: "no-cache" });
    if (!isRealResponse(res)) return null;
    const json: unknown = await res.json();
    if (
      typeof json === "object" &&
      json !== null &&
      "metrics" in json &&
      "suburbs" in json
    ) {
      return json as MetricsArtifact;
    }
    return null;
  } catch {
    return null;
  }
}

async function resolveSuburbSource(): Promise<SuburbSource | null> {
  if (await probe(PMTILES_URL)) {
    return { kind: "pmtiles", url: PMTILES_URL };
  }
  if (import.meta.env.DEV && (await probe(MOCK_GEOJSON_URL))) {
    return { kind: "geojson", url: MOCK_GEOJSON_URL };
  }
  return null;
}

/** Loads metrics.json and locates suburb geometry; reports what's missing. */
export function useArtifacts(): ArtifactState {
  const [state, setState] = useState<ArtifactState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [metrics, source] = await Promise.all([
        fetchMetrics(),
        resolveSuburbSource(),
      ]);
      if (cancelled) return;
      const missing: string[] = [];
      if (source == null) missing.push(PMTILES_URL);
      if (metrics == null) missing.push(METRICS_URL);
      if (metrics != null && source != null) {
        setState({ status: "ready", artifacts: { metrics, source } });
      } else {
        setState({ status: "missing", missing });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
