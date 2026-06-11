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
  SUBURB_ACTIVE_LAYER,
  SUBURB_FILL_LAYER,
  SUBURB_LINE_LAYER,
} from "./layers";
import { formatValue } from "./metrics";
import type { Artifacts, MapApi, MetricsArtifact, PickedSuburb } from "./types";

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
  mapApiRef,
  onPick,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
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
      const features = map.getLayer(SUBURB_FILL_LAYER)
        ? map.queryRenderedFeatures(e.point, { layers: [SUBURB_FILL_LAYER] })
        : [];
      const first = features[0];
      onPickRef.current(first ? pickedFrom(first) : null);
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
