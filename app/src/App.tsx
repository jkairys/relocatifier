import { useEffect, useState } from "react";
import { EmptyState } from "./components/EmptyState";
import { Header } from "./components/Header";
import { LayerToggle } from "./components/LayerToggle";
import { Legend } from "./components/Legend";
import { MetricSwitcher } from "./components/MetricSwitcher";
import { StatSheet } from "./components/StatSheet";
import { defaultLayerVisibility } from "./layers";
import { MapView } from "./MapView";
import { firstAvailableMetric, METRIC_ORDER } from "./metrics";
import type { PickedSuburb } from "./types";
import { useArtifacts } from "./useArtifacts";

export default function App() {
  const state = useArtifacts();
  const artifacts = state.status === "ready" ? state.artifacts : null;

  const [selectedMetricId, setSelectedMetricId] = useState(METRIC_ORDER[0]!.id);
  const [picked, setPicked] = useState<PickedSuburb | null>(null);
  const [layerVisibility, setLayerVisibility] = useState(defaultLayerVisibility);

  // Once the artifact arrives, default to the first metric that has data.
  useEffect(() => {
    if (artifacts != null && artifacts.metrics.metrics[selectedMetricId] == null) {
      setSelectedMetricId(firstAvailableMetric(artifacts.metrics));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifacts]);

  const toggleLayer = (layerId: string) =>
    setLayerVisibility((prev) => ({ ...prev, [layerId]: !prev[layerId] }));

  return (
    <div className="app">
      <MapView
        artifacts={artifacts}
        selectedMetricId={selectedMetricId}
        selectedSalCode={picked?.salCode ?? null}
        layerVisibility={layerVisibility}
        onPick={setPicked}
      />
      <Header
        artifact={artifacts?.metrics ?? null}
        selectedMetricId={selectedMetricId}
      />
      {artifacts != null && (
        <>
          <div className="left-rail">
            <MetricSwitcher
              artifact={artifacts.metrics}
              selectedMetricId={selectedMetricId}
              onSelect={setSelectedMetricId}
            />
            <LayerToggle visibility={layerVisibility} onToggle={toggleLayer} />
          </div>
          <Legend
            artifact={artifacts.metrics}
            selectedMetricId={selectedMetricId}
          />
          {picked != null && (
            <StatSheet
              artifact={artifacts.metrics}
              picked={picked}
              selectedMetricId={selectedMetricId}
              onClose={() => setPicked(null)}
            />
          )}
        </>
      )}
      {state.status === "missing" && <EmptyState missing={state.missing} />}
    </div>
  );
}
