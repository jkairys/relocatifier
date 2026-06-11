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
import type { Artifacts, MetricsArtifact, PickedSuburb } from "./types";

maplibregl.addProtocol("pmtiles", new Protocol().tile);

const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
const INITIAL_CENTER: [number, number] = [153.0, -27.5];
const INITIAL_ZOOM = 5.5;
const SOURCE_ID = "suburbs";
const SOURCE_LAYER = "suburbs";
const ACCENT = "#3554d1";

interface MapViewProps {
  artifacts: Artifacts | null;
  selectedMetricId: string;
  selectedSalCode: string | null;
  layerVisibility: Record<string, boolean>;
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
  layerVisibility,
  onPick,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [styleReady, setStyleReady] = useState(false);
  const [layersReady, setLayersReady] = useState(false);
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;
  const hoveredRef = useRef<string | null>(null);
  const selectedRef = useRef<string | null>(null);
  const isVector = artifacts?.source.kind === "pmtiles";

  // Create the map once.
  useEffect(() => {
    const container = containerRef.current;
    if (container == null) return;
    const map = new maplibregl.Map({
      container,
      style: STYLE_URL,
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
      attributionControl: { compact: true },
    });
    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "bottom-right",
    );
    map.on("load", () => setStyleReady(true));
    map.on("error", (e) => console.warn("[map]", e.error?.message ?? e));
    mapRef.current = map;
    return () => {
      mapRef.current = null;
      setStyleReady(false);
      setLayersReady(false);
      map.remove();
    };
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
    // Emphasis outline for the hovered / selected suburb.
    map.addLayer(
      {
        id: SUBURB_ACTIVE_LAYER,
        type: "line",
        source: SOURCE_ID,
        ...sourceLayerProp,
        paint: {
          "line-color": ACCENT,
          "line-width": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            2.25,
            ["boolean", ["feature-state", "hover"], false],
            1.5,
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

    map.on("mousemove", SUBURB_FILL_LAYER, (e: MapLayerMouseEvent) => {
      const feature = e.features?.[0];
      const picked = feature ? pickedFrom(feature) : null;
      setHover(picked?.salCode ?? null);
    });
    map.on("mouseleave", SUBURB_FILL_LAYER, () => setHover(null));
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

  return <div ref={containerRef} className="map-canvas" />;
}
