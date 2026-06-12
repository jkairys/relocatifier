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
  /** [lng, lat] centroid for flyTo; optional defensively (older artifacts). */
  centre?: [number, number];
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

/** Imperative camera commands MapView exposes to the rest of the app. */
export interface MapApi {
  flyTo(centre: [number, number], zoom?: number): void;
}

/* ---------- Recent sales artifact (issue #3) ---------- */

/** One recently-sold listing. Any field may be null except `address`. */
export interface SaleRecord {
  address: string;
  /** Numeric sale price; null when suppressed ("price withheld"). */
  price: number | null;
  price_display: string | null;
  bedrooms: number | null;
  bathrooms: number | null;
  parking: number | null;
  land_size_sqm: number | null;
  property_type: string | null;
  /** ISO date (YYYY-MM-DD); null when unknown. */
  sale_date: string | null;
  /** WGS84 latitude of the property; null when it has no coordinates. */
  lat: number | null;
  /** WGS84 longitude of the property; null when it has no coordinates. */
  lon: number | null;
}

/** Sales for one suburb, keyed by SAL code in the artifact. */
export interface SalesSuburb {
  name: string;
  state: string;
  oth_slug: string;
  /** ISO timestamp of the last successful fetch for this suburb. */
  fetched_at: string;
  /** Sorted by sale_date desc, nulls last; everything <= 12 months old. */
  sales: SaleRecord[];
}

export interface SalesArtifact {
  schema_version: number;
  generated_at: string;
  suburbs: Record<string, SalesSuburb>;
}
