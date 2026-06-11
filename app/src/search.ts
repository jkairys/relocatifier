import type { MetricsArtifact } from "./types";

/**
 * Type-ahead over suburb names. Names are NOT unique — not even within a
 * state — so every result carries its state, and entries whose name+state
 * pair collides with another suburb are flagged so the UI can show the
 * SAL code as a tiebreaker.
 */
export interface SearchEntry {
  salCode: string;
  name: string;
  state: string;
  centre: [number, number] | null;
  /** Another suburb shares this exact name+state pair. */
  ambiguous: boolean;
  nameLower: string;
}

export function buildSearchIndex(artifact: MetricsArtifact): SearchEntry[] {
  const counts = new Map<string, number>();
  for (const rec of Object.values(artifact.suburbs)) {
    const key = `${rec.name}|${rec.state}`;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const entries: SearchEntry[] = Object.entries(artifact.suburbs).map(
    ([salCode, rec]) => ({
      salCode,
      name: rec.name,
      state: rec.state,
      centre: rec.centre ?? null,
      ambiguous: (counts.get(`${rec.name}|${rec.state}`) ?? 0) > 1,
      nameLower: rec.name.toLowerCase(),
    }),
  );
  // Stable, human-friendly order: name, then state, then SAL code.
  entries.sort(
    (a, b) =>
      a.nameLower.localeCompare(b.nameLower) ||
      a.state.localeCompare(b.state) ||
      a.salCode.localeCompare(b.salCode),
  );
  return entries;
}

/** Prefix matches rank before substring matches; capped at `limit`. */
export function searchSuburbs(
  index: readonly SearchEntry[],
  query: string,
  limit = 8,
): SearchEntry[] {
  const q = query.trim().toLowerCase();
  if (q === "") return [];
  const prefix: SearchEntry[] = [];
  const substring: SearchEntry[] = [];
  for (const entry of index) {
    const at = entry.nameLower.indexOf(q);
    if (at === 0) {
      prefix.push(entry);
      if (prefix.length >= limit) break;
    } else if (at > 0 && substring.length < limit) {
      substring.push(entry);
    }
  }
  return [...prefix, ...substring].slice(0, limit);
}
