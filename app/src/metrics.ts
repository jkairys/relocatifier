import type { MetricsArtifact } from "./types";

/**
 * The seven Discovery v1 metrics, in PRD order. The switcher and stat sheet
 * always render all seven; ones absent from metrics.json show as "soon".
 * Labels here are fallbacks — the artifact's own label wins when present.
 */
export interface MetricSpec {
  id: string;
  label: string;
  /** Fallback formatter when the artifact's `format` key is unknown. */
  format: (v: number) => string;
}

const int = (v: number) => Math.round(v).toLocaleString("en-AU");
const dec1 = (v: number) =>
  v.toLocaleString("en-AU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function formatAud(v: number): string {
  if (Math.abs(v) >= 1_000_000) {
    const m = v / 1_000_000;
    return `$${m.toLocaleString("en-AU", { maximumFractionDigits: 2 })}M`;
  }
  if (Math.abs(v) >= 10_000) return `$${Math.round(v / 1000)}k`;
  return `$${int(v)}`;
}

export const METRIC_ORDER: readonly MetricSpec[] = [
  { id: "median_age", label: "Median age", format: (v) => `${int(v)} yrs` },
  { id: "pct_children", label: "Children 0–14", format: (v) => `${dec1(v)}%` },
  { id: "median_rent_house", label: "Median weekly rent", format: (v) => `$${int(v)}/wk` },
  { id: "median_house_price", label: "Median house price", format: formatAud },
  { id: "gross_yield", label: "Gross yield", format: (v) => `${dec1(v)}%` },
  { id: "icsea", label: "ICSEA", format: int },
  { id: "crime_rate", label: "Crime rate", format: (v) => `${dec1(v)} /1k` },
];

/** Formatters keyed by the artifact's `format` field. */
const FORMATTERS: Record<string, (v: number) => string> = {
  years: (v) => `${int(v)} yrs`,
  percent: (v) => `${dec1(v)}%`,
  aud: formatAud,
  currency: formatAud,
  aud_per_week: (v) => `$${int(v)}/wk`,
  rent_weekly: (v) => `$${int(v)}/wk`,
  index: int,
  per_1000: (v) => `${dec1(v)} /1k`,
};

export function formatValue(value: number, metricId: string, artifactFormat?: string): string {
  if (artifactFormat) {
    const f = FORMATTERS[artifactFormat];
    if (f) return f(value);
  }
  const spec = METRIC_ORDER.find((m) => m.id === metricId);
  if (spec) return spec.format(value);
  return value.toLocaleString("en-AU", { maximumFractionDigits: 2 });
}

export function metricLabel(id: string, artifact: MetricsArtifact | null): string {
  const fromArtifact = artifact?.metrics[id]?.label;
  if (fromArtifact) return fromArtifact;
  return METRIC_ORDER.find((m) => m.id === id)?.label ?? id;
}

/**
 * Switcher rows: the seven canonical metrics in order, plus (defensively)
 * any extra metric the ETL emits that we don't know about yet.
 */
export function switcherMetricIds(artifact: MetricsArtifact | null): string[] {
  const known = METRIC_ORDER.map((m) => m.id);
  const extras = artifact
    ? Object.keys(artifact.metrics).filter((id) => !known.includes(id))
    : [];
  return [...known, ...extras];
}

export function firstAvailableMetric(artifact: MetricsArtifact): string {
  for (const m of METRIC_ORDER) if (artifact.metrics[m.id]) return m.id;
  return Object.keys(artifact.metrics)[0] ?? METRIC_ORDER[0]!.id;
}
