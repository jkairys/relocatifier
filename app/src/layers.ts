/**
 * Toggleable map layers. Future layers (e.g. parcels, v1.1) are added here:
 * one registry entry mapping a toggle to the MapLibre layer ids it controls.
 */
export interface LayerSpec {
  id: string;
  label: string;
  /** MapLibre layer ids whose visibility this toggle drives. */
  mapLayerIds: readonly string[];
  defaultVisible: boolean;
  /**
   * Data-dependent layers (e.g. "sales") are only meaningful when their
   * artifact is present; the toggle for these is hidden until data exists.
   */
  requiresData?: boolean;
}

export const SUBURB_FILL_LAYER = "suburbs-fill";
export const SUBURB_LINE_LAYER = "suburbs-line";
export const SUBURB_ACTIVE_LAYER = "suburbs-active";
export const SALES_DOTS_LAYER = "sales-dots";

/** Toggle id for the recent-sales dots layer. */
export const SALES_LAYER_ID = "sales";

export const LAYER_REGISTRY: readonly LayerSpec[] = [
  {
    id: "suburbs",
    label: "Suburbs",
    mapLayerIds: [SUBURB_FILL_LAYER, SUBURB_LINE_LAYER, SUBURB_ACTIVE_LAYER],
    defaultVisible: true,
  },
  {
    id: SALES_LAYER_ID,
    label: "Recent sales",
    mapLayerIds: [SALES_DOTS_LAYER],
    defaultVisible: true,
    requiresData: true,
  },
  // { id: "parcels", label: "Parcels", mapLayerIds: [...], defaultVisible: false },
];

export function defaultLayerVisibility(): Record<string, boolean> {
  return Object.fromEntries(LAYER_REGISTRY.map((l) => [l.id, l.defaultVisible]));
}
