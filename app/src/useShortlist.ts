import { useCallback, useEffect, useState } from "react";

/** localStorage key for pinned suburbs (an ordered array of SAL codes). */
const STORAGE_KEY = "relocatifier.shortlist.v1";

function load(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw == null) return [];
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.filter((x): x is string => typeof x === "string");
    }
  } catch {
    /* corrupt or unavailable storage — start empty */
  }
  return [];
}

export interface Shortlist {
  /** Pinned SAL codes, in the order they were pinned. */
  codes: string[];
  has(salCode: string): boolean;
  toggle(salCode: string): void;
  remove(salCode: string): void;
}

/** Pinned suburbs, persisted to localStorage as SAL codes. */
export function useShortlist(): Shortlist {
  const [codes, setCodes] = useState<string[]>(load);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(codes));
    } catch {
      /* storage full or unavailable — shortlist still works in-memory */
    }
  }, [codes]);

  const has = useCallback(
    (salCode: string) => codes.includes(salCode),
    [codes],
  );
  const toggle = useCallback((salCode: string) => {
    setCodes((prev) =>
      prev.includes(salCode)
        ? prev.filter((c) => c !== salCode)
        : [...prev, salCode],
    );
  }, []);
  const remove = useCallback((salCode: string) => {
    setCodes((prev) => prev.filter((c) => c !== salCode));
  }, []);

  return { codes, has, toggle, remove };
}
