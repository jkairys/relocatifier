import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type {
  ExpressionSpecification,
  MapGeoJSONFeature,
  MapLayerMouseEvent,
} from "maplibre-gl";
import { Protocol } from "pmtiles";
import { colorFor, NO_DATA_COLOR } from "./color";
import {
  LAYER_REGISTRY,
  SALES_DOTS_LAYER,
  SUBURB_ACTIVE_LAYER,
  SUBURB_FILL_LAYER,
  SUBURB_LINE_LAYER,
} from "./layers";
import { formatValue } from "./metrics";
import { formatSaleDate, formatSalePrice } from "./sales";
import { buildSaleDots, saleDotColor } from "./salesDots";
import type {
  Artifacts,
  MapApi,
  MetricsArtifact,
  PickedSuburb,
  SaleRecord,
  SalesArtifact,
} from "./types";

maplibregl.addProtocol("pmtiles", new Protocol().tile);

const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
const INITIAL_CENTER: [number, number] = [153.0, -27.5];
const INITIAL_ZOOM = 5.5;
/** The whole Search Zone: Cairns (-16.9) down to Batemans Bay (-35.7). */
const SEARCH_ZONE_BOUNDS: [[number, number], [number, number]] = [
  [144.8, -35.9], // SW
  [154.2, -16.7], // NE
];
const SOURCE_ID = "suburbs";
const SOURCE_LAYER = "suburbs";
const SALES_SOURCE_ID = "sales";
const ACCENT = "#3554d1";
/** Outline for pinned (shortlisted) suburbs — distinct from hover/selected. */
const PIN_COLOR = "#c026d3";
const FLY_ZOOM = 11.5;

interface MapViewProps {
  artifacts: Artifacts | null;
  selectedMetricId: string;
  selectedSalCode: string | null;
  pinnedSalCodes: readonly string[];
  layerVisibility: Record<string, boolean>;
  /** Recent-sales artifact, or null when absent (dots layer not added). */
  sales: SalesArtifact | null;
  mapApiRef: { current: MapApi | null };
  onPick: (suburb: PickedSuburb | null) => void;
}

interface FeatureRef {
  source: string;
  sourceLayer?: string;
  id: string;
}

function featureRef(salCode: string, isVector: boolean): FeatureRef {
  return isVector
    ? { source: SOURCE_ID, sourceLayer: SOURCE_LAYER, id: salCode }
    : { source: SOURCE_ID, id: salCode };
}

function pickedFrom(feature: MapGeoJSONFeature): PickedSuburb | null {
  const props = feature.properties as Record<string, unknown>;
  const salCode = props["sal_code"];
  if (typeof salCode !== "string" || salCode === "") return null;
  return {
    salCode,
    name: typeof props["name"] === "string" ? props["name"] : salCode,
    state: typeof props["state"] === "string" ? props["state"] : "",
  };
}

/** Escape user/vendor strings before injecting into popup HTML. */
function esc(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Read a feature property as a SaleRecord field, normalising types. */
function saleFromProps(props: Record<string, unknown>): SaleRecord {
  const numOrNull = (v: unknown): number | null =>
    typeof v === "number" && Number.isFinite(v) ? v : null;
  const strOrNull = (v: unknown): string | null =>
    typeof v === "string" && v !== "" ? v : null;
  return {
    address: typeof props["address"] === "string" ? props["address"] : "",
    price: numOrNull(props["price"]),
    price_display: strOrNull(props["price_display"]),
    bedrooms: numOrNull(props["bedrooms"]),
    bathrooms: numOrNull(props["bathrooms"]),
    parking: numOrNull(props["parking"]),
    land_size_sqm: numOrNull(props["land_size_sqm"]),
    property_type: strOrNull(props["property_type"]),
    sale_date: strOrNull(props["sale_date"]),
    lat: numOrNull(props["lat"]),
    lon: numOrNull(props["lon"]),
  };
}

/** Small markup for a sales dot popup; matches stat-sheet sales styling. */
function salePopupHtml(sale: SaleRecord): string {
  const specs: string[] = [];
  if (sale.bedrooms != null) specs.push(`${sale.bedrooms} bd`);
  if (sale.bathrooms != null) specs.push(`${sale.bathrooms} ba`);
  if (sale.land_size_sqm != null) specs.push(`${sale.land_size_sqm} m²`);
  const type = sale.property_type != null ? esc(sale.property_type) : "";
  return [
    `<div class="sale-popup">`,
    `<p class="sale-popup-address">${esc(sale.address)}</p>`,
    `<p class="sale-popup-price">${esc(formatSalePrice(sale))}</p>`,
    `<p class="sale-popup-meta">${esc(formatSaleDate(sale.sale_date))}</p>`,
    specs.length > 0
      ? `<p class="sale-popup-specs">${specs.map(esc).join(" · ")}</p>`
      : "",
    type !== "" ? `<p class="sale-popup-type">${type}</p>` : "",
    `</div>`,
  ].join("");
}

/** Paint every suburb's fill colour for one metric via feature-state. */
function applyMetricColors(
  map: maplibregl.Map,
  metrics: MetricsArtifact,
  metricId: string,
  isVector: boolean,
): void {
  const def = metrics.metrics[metricId];
  for (const [salCode, record] of Object.entries(metrics.suburbs)) {
    const value = record.values[metricId] ?? null;
    map.setFeatureState(featureRef(salCode, isVector), {
      fill: colorFor(value, def),
    });
  }
}

export function MapView({
  artifacts,
  selectedMetricId,
  selectedSalCode,
  pinnedSalCodes,
  layerVisibility,
  sales,
  mapApiRef,
  onPick,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const salesPopupRef = useRef<maplibregl.Popup | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const tipNameRef = useRef<HTMLSpanElement>(null);
  const tipValueRef = useRef<HTMLSpanElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [styleReady, setStyleReady] = useState(false);
  const [layersReady, setLayersReady] = useState(false);
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;
  // Live refs so map handlers (bound once) see the current metric/artifact.
  const metricsRef = useRef<MetricsArtifact | null>(artifacts?.metrics ?? null);
  metricsRef.current = artifacts?.metrics ?? null;
  const metricIdRef = useRef(selectedMetricId);
  metricIdRef.current = selectedMetricId;
  const hoveredRef = useRef<string | null>(null);
  const selectedRef = useRef<string | null>(null);
  const pinnedRef = useRef<ReadonlySet<string>>(new Set());
  // Live ref so the dots layer can read its current toggle state on first add.
  const layerVisibilityRef = useRef(layerVisibility);
  layerVisibilityRef.current = layerVisibility;
  const isVector = artifacts?.source.kind === "pmtiles";

  // Create the map once.
  useEffect(() => {
    const container = containerRef.current;
    if (container == null) return;
    // A permalink hash (#zoom/lat/lng) wins; otherwise fit the Search Zone.
    const hadHash = window.location.hash.length > 1;
    const map = new maplibregl.Map({
      container,
      style: STYLE_URL,
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
      hash: true,
      attributionControl: { compact: true },
    });
    if (!hadHash) {
      map.fitBounds(SEARCH_ZONE_BOUNDS, {
        animate: false,
        padding: { top: 72, bottom: 32, left: 48, right: 48 },
      });
    }
    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "bottom-right",
    );
    map.on("load", () => setStyleReady(true));
    map.on("error", (e) => console.warn("[map]", e.error?.message ?? e));
    mapRef.current = map;
    mapApiRef.current = {
      flyTo: (centre, zoom = FLY_ZOOM) =>
        map.flyTo({ center: centre, zoom, duration: 1600, essential: true }),
    };
    return () => {
      mapApiRef.current = null;
      mapRef.current = null;
      setStyleReady(false);
      setLayersReady(false);
      map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Add the suburb source + layers once artifacts and the style are ready.
  useEffect(() => {
    const map = mapRef.current;
    if (map == null || !styleReady || artifacts == null) return;
    if (map.getSource(SOURCE_ID) != null) return;

    const { source } = artifacts;
    if (source.kind === "pmtiles") {
      map.addSource(SOURCE_ID, {
        type: "vector",
        url: `pmtiles://${new URL(source.url, window.location.origin).href}`,
        promoteId: "sal_code",
      });
    } else {
      map.addSource(SOURCE_ID, {
        type: "geojson",
        data: source.url,
        promoteId: "sal_code",
      });
    }

    const vector = source.kind === "pmtiles";
    const sourceLayerProp = vector ? { "source-layer": SOURCE_LAYER } : {};
    // Keep basemap labels above the choropleth.
    const beforeId = map.getStyle().layers.find((l) => l.type === "symbol")?.id;

    const fillColor: ExpressionSpecification = [
      "coalesce",
      ["feature-state", "fill"],
      NO_DATA_COLOR,
    ];
    map.addLayer(
      {
        id: SUBURB_FILL_LAYER,
        type: "fill",
        source: SOURCE_ID,
        ...sourceLayerProp,
        paint: {
          "fill-color": fillColor,
          "fill-opacity": [
            "case",
            ["boolean", ["feature-state", "hover"], false],
            0.88,
            0.72,
          ],
        },
      },
      beforeId,
    );
    // Crisp hairline boundaries between polygons.
    map.addLayer(
      {
        id: SUBURB_LINE_LAYER,
        type: "line",
        source: SOURCE_ID,
        ...sourceLayerProp,
        paint: {
          "line-color": "#ffffff",
          "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.3, 10, 0.9],
          "line-opacity": 0.85,
        },
      },
      beforeId,
    );
    // Emphasis outline: selected/hover in accent, pinned in its own colour.
    map.addLayer(
      {
        id: SUBURB_ACTIVE_LAYER,
        type: "line",
        source: SOURCE_ID,
        ...sourceLayerProp,
        paint: {
          "line-color": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            ACCENT,
            ["boolean", ["feature-state", "hover"], false],
            ACCENT,
            PIN_COLOR,
          ],
          "line-width": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            2.25,
            ["boolean", ["feature-state", "hover"], false],
            1.5,
            ["boolean", ["feature-state", "pinned"], false],
            1.75,
            0,
          ],
        },
      },
      beforeId,
    );

    const setHover = (salCode: string | null) => {
      const prev = hoveredRef.current;
      if (prev === salCode) return;
      if (prev != null) {
        map.setFeatureState(featureRef(prev, vector), { hover: false });
      }
      if (salCode != null) {
        map.setFeatureState(featureRef(salCode, vector), { hover: true });
      }
      hoveredRef.current = salCode;
      map.getCanvas().style.cursor = salCode != null ? "pointer" : "";
    };

    // Cursor tooltip: name + active-metric value. State lives outside React;
    // updates are coalesced through rAF so mousemove stays cheap.
    const tip = { x: 0, y: 0, salCode: null as string | null, name: "" };
    const mapContainer = map.getContainer();
    let tipRaf: number | null = null;
    const renderTip = () => {
      tipRaf = null;
      const el = tooltipRef.current;
      if (el == null) return;
      if (tip.salCode == null) {
        el.style.opacity = "0";
        return;
      }
      const metrics = metricsRef.current;
      const metricId = metricIdRef.current;
      const record = metrics?.suburbs[tip.salCode];
      const def = metrics?.metrics[metricId];
      const value = record?.values[metricId] ?? null;
      const nameEl = tipNameRef.current;
      const valueEl = tipValueRef.current;
      if (nameEl) nameEl.textContent = record?.name ?? tip.name;
      if (valueEl) {
        valueEl.textContent =
          value != null ? formatValue(value, metricId, def?.format) : "no data";
        valueEl.classList.toggle("is-empty", value == null);
      }
      const pad = 14;
      const maxX = mapContainer.clientWidth - el.offsetWidth - 8;
      const maxY = mapContainer.clientHeight - el.offsetHeight - 8;
      el.style.transform = `translate(${Math.min(tip.x + pad, maxX)}px, ${Math.min(tip.y + pad, maxY)}px)`;
      el.style.opacity = "1";
    };
    const scheduleTip = () => {
      if (tipRaf == null) tipRaf = requestAnimationFrame(renderTip);
    };

    map.on("mousemove", SUBURB_FILL_LAYER, (e: MapLayerMouseEvent) => {
      const feature = e.features?.[0];
      const picked = feature ? pickedFrom(feature) : null;
      setHover(picked?.salCode ?? null);
      tip.x = e.point.x;
      tip.y = e.point.y;
      tip.salCode = picked?.salCode ?? null;
      tip.name = picked?.name ?? "";
      scheduleTip();
    });
    map.on("mouseleave", SUBURB_FILL_LAYER, () => {
      setHover(null);
      tip.salCode = null;
      scheduleTip();
    });
    map.on("click", (e) => {
      // A sales dot under the cursor handles its own click (popup) and must
      // not also fall through to suburb selection.
      const hitDot =
        map.getLayer(SALES_DOTS_LAYER) != null &&
        map.queryRenderedFeatures(e.point, { layers: [SALES_DOTS_LAYER] }).length > 0;
      if (hitDot) return;
      const features = map.getLayer(SUBURB_FILL_LAYER)
        ? map.queryRenderedFeatures(e.point, { layers: [SUBURB_FILL_LAYER] })
        : [];
      const first = features[0];
      onPickRef.current(first ? pickedFrom(first) : null);
    });

    // Sales dot: open a single popup; pointer cursor on hover.
    map.on("click", SALES_DOTS_LAYER, (e: MapLayerMouseEvent) => {
      const feature = e.features?.[0];
      if (feature == null) return;
      const sale = saleFromProps(feature.properties as Record<string, unknown>);
      const geom = feature.geometry;
      const coords: [number, number] =
        geom.type === "Point"
          ? [geom.coordinates[0]!, geom.coordinates[1]!]
          : [e.lngLat.lng, e.lngLat.lat];
      salesPopupRef.current?.remove();
      salesPopupRef.current = new maplibregl.Popup({
        closeButton: true,
        closeOnClick: true,
        maxWidth: "240px",
        className: "sale-popup-shell",
      })
        .setLngLat(coords)
        .setHTML(salePopupHtml(sale))
        .addTo(map);
    });
    map.on("mouseenter", SALES_DOTS_LAYER, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", SALES_DOTS_LAYER, () => {
      map.getCanvas().style.cursor = "";
    });

    setLayersReady(true);
  }, [styleReady, artifacts]);

  // Recolour when the metric (or artifact) changes.
  useEffect(() => {
    const map = mapRef.current;
    if (map == null || !layersReady || artifacts == null) return;
    applyMetricColors(map, artifacts.metrics, selectedMetricId, isVector);
  }, [layersReady, artifacts, selectedMetricId, isVector]);

  // Sync the selected-suburb outline.
  useEffect(() => {
    const map = mapRef.current;
    if (map == null || !layersReady) return;
    const prev = selectedRef.current;
    if (prev != null && prev !== selectedSalCode) {
      map.setFeatureState(featureRef(prev, isVector), { selected: false });
    }
    if (selectedSalCode != null) {
      map.setFeatureState(featureRef(selectedSalCode, isVector), {
        selected: true,
      });
    }
    selectedRef.current = selectedSalCode;
  }, [layersReady, selectedSalCode, isVector]);

  // Sync the pinned (shortlist) outlines.
  useEffect(() => {
    const map = mapRef.current;
    if (map == null || !layersReady) return;
    const next = new Set(pinnedSalCodes);
    for (const salCode of pinnedRef.current) {
      if (!next.has(salCode)) {
        map.setFeatureState(featureRef(salCode, isVector), { pinned: false });
      }
    }
    for (const salCode of next) {
      if (!pinnedRef.current.has(salCode)) {
        map.setFeatureState(featureRef(salCode, isVector), { pinned: true });
      }
    }
    pinnedRef.current = next;
  }, [layersReady, pinnedSalCodes, isVector]);

  // Recent-sales dots: build a GeoJSON source + circle layer from the artifact.
  // Absent-safe (no source when sales is null/empty) and refreshes on reload.
  useEffect(() => {
    const map = mapRef.current;
    if (map == null || !layersReady) return;

    const data = sales != null ? buildSaleDots(sales) : null;
    const existing = map.getSource(SALES_SOURCE_ID) as
      | maplibregl.GeoJSONSource
      | undefined;

    // Nothing to plot: tear down any prior dots layer/source + popup.
    if (data == null || data.features.length === 0) {
      salesPopupRef.current?.remove();
      salesPopupRef.current = null;
      if (map.getLayer(SALES_DOTS_LAYER) != null) map.removeLayer(SALES_DOTS_LAYER);
      if (existing != null) map.removeSource(SALES_SOURCE_ID);
      return;
    }

    if (existing != null) {
      existing.setData(data); // refresh after a run
    } else {
      map.addSource(SALES_SOURCE_ID, { type: "geojson", data });
    }

    if (map.getLayer(SALES_DOTS_LAYER) == null) {
      // Above the choropleth fill, below basemap labels.
      const beforeId = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
      map.addLayer(
        {
          id: SALES_DOTS_LAYER,
          type: "circle",
          source: SALES_SOURCE_ID,
          paint: {
            "circle-color": saleDotColor(),
            "circle-radius": [
              "interpolate",
              ["linear"],
              ["zoom"],
              8,
              3,
              12,
              5,
              15,
              7,
            ],
            "circle-stroke-width": 1,
            "circle-stroke-color": "#ffffff",
            "circle-opacity": 0.95,
          },
        },
        beforeId,
      );
      // Honour the current toggle state for the freshly-added layer.
      const visible = layerVisibilityRef.current["sales"] ?? true;
      map.setLayoutProperty(
        SALES_DOTS_LAYER,
        "visibility",
        visible ? "visible" : "none",
      );
    }
  }, [layersReady, sales]);

  // Apply layer-toggle visibility.
  useEffect(() => {
    const map = mapRef.current;
    if (map == null || !layersReady) return;
    for (const spec of LAYER_REGISTRY) {
      const visible = layerVisibility[spec.id] ?? spec.defaultVisible;
      for (const layerId of spec.mapLayerIds) {
        if (map.getLayer(layerId) != null) {
          map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
        }
      }
    }
  }, [layersReady, layerVisibility]);

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map-canvas" />
      <div ref={tooltipRef} className="map-tooltip" aria-hidden="true">
        <span ref={tipNameRef} className="map-tooltip-name" />
        <span ref={tipValueRef} className="map-tooltip-value" />
      </div>
    </div>
  );
}
