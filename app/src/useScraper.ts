import { useCallback, useEffect, useRef, useState } from "react";
import {
  addToWatchlist,
  checkHealth,
  fetchRun,
  fetchWatchlist,
  startRun,
} from "./scraperClient";

/** How often to poll GET /runs/{id} while a run is in flight. */
const POLL_INTERVAL_MS = 2500;

interface WatchlistRow {
  sal_code?: unknown;
}

/** A run currently being tracked for one suburb. */
export interface ActiveRun {
  salCode: string;
  runId: string;
}

export interface ScraperState {
  /** GET /health succeeded (checked once, cached). Gates the controls. */
  available: boolean;
  /** SAL codes currently on the watchlist (best-effort; [] when unknown). */
  watchlist: Set<string>;
  /** The in-flight run, if any. Controls are disabled while non-null. */
  activeRun: ActiveRun | null;
  /** Transient inline message (e.g. a 422 refusal detail, surfaced verbatim). */
  notice: string | null;
  /** Add a suburb to the watchlist, then auto-trigger its first run. */
  add: (salCode: string) => Promise<void>;
  /** Trigger a refresh run for a suburb already on the watchlist. */
  refresh: (salCode: string) => Promise<void>;
  /** Clear the current inline notice. */
  dismissNotice: () => void;
}

/**
 * Owns the optional scraper control-plane lifecycle: health gating, watchlist
 * membership, and run start + poll. On run completion it calls `onSalesChanged`
 * so the caller can re-fetch sales.json. Every interaction is non-fatal.
 */
export function useScraper(onSalesChanged: () => void): ScraperState {
  const [available, setAvailable] = useState(false);
  const [watchlist, setWatchlist] = useState<Set<string>>(new Set());
  const [activeRun, setActiveRun] = useState<ActiveRun | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Keep the latest sales-changed callback without re-subscribing the poller.
  const onSalesChangedRef = useRef(onSalesChanged);
  onSalesChangedRef.current = onSalesChanged;

  const reloadWatchlist = useCallback(async () => {
    const rows = await fetchWatchlist();
    const codes = new Set<string>();
    for (const row of rows) {
      const code = (row as WatchlistRow).sal_code;
      if (typeof code === "string") codes.add(code);
    }
    setWatchlist(codes);
  }, []);

  // Probe health once; only then load the watchlist.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const ok = await checkHealth();
      if (cancelled) return;
      setAvailable(ok);
      if (ok) await reloadWatchlist();
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadWatchlist]);

  // Poll the active run until it leaves "running", then refresh sales + watchlist.
  useEffect(() => {
    if (activeRun == null) return;
    let cancelled = false;
    const timer = setInterval(() => {
      void (async () => {
        const info = await fetchRun(activeRun.runId);
        if (cancelled || info == null) return;
        if (info.status !== "running") {
          setActiveRun(null);
          if (info.status === "failed") {
            setNotice("Refresh run failed. Data may be unchanged.");
          }
          onSalesChangedRef.current();
          void reloadWatchlist();
        }
      })();
    }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [activeRun, reloadWatchlist]);

  const refresh = useCallback(async (salCode: string) => {
    setNotice(null);
    const result = await startRun(salCode);
    if (result.ok) {
      setActiveRun({ salCode, runId: result.value.run_id });
    } else if (result.status === 409) {
      // Single-flight: a run is already underway elsewhere. Handle gracefully.
      setNotice("A refresh is already in progress. Please wait for it to finish.");
    } else {
      setNotice(result.detail);
    }
  }, []);

  const add = useCallback(
    async (salCode: string) => {
      setNotice(null);
      const result = await addToWatchlist(salCode);
      if (!result.ok) {
        // 422 = honest refusal (slug unresolvable/ambiguous); surface verbatim.
        setNotice(result.detail);
        return;
      }
      setWatchlist((prev) => new Set(prev).add(salCode));
      // On success, auto-trigger the suburb's first run.
      await refresh(salCode);
    },
    [refresh],
  );

  const dismissNotice = useCallback(() => setNotice(null), []);

  return {
    available,
    watchlist,
    activeRun,
    notice,
    add,
    refresh,
    dismissNotice,
  };
}
