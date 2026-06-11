/** Types for the ETL artifact contract (docs/PRD.md §Artifact contract). */

export type Direction = "lower_better" | "higher_better";

export interface MetricStats {
  median: number;
  p10: number;
  p90: number;
}

export interface MetricDef {
  label: string;
  format: string;
  direction: Direction;
  stats: MetricStats;
}

export interface SuburbRecord {
  name: string;
  state: string;
  values: Record<string, number | null>;
}

export interface MetricsArtifact {
  schema_version: number;
  vintages: Record<string, string>;
  metrics: Record<string, MetricDef>;
  suburbs: Record<string, SuburbRecord>;
}

/** How suburb geometry is supplied to the map. */
export type SuburbSource =
  | { kind: "pmtiles"; url: string }
  /** Dev-only fallback so the UI can be exercised without tippecanoe output. */
  | { kind: "geojson"; url: string };

export interface Artifacts {
  metrics: MetricsArtifact;
  source: SuburbSource;
}

export type ArtifactState =
  | { status: "loading" }
  | { status: "missing"; missing: string[] }
  | { status: "ready"; artifacts: Artifacts };

/** A suburb picked on the map (properties straight off the vector feature). */
export interface PickedSuburb {
  salCode: string;
  name: string;
  state: string;
}
