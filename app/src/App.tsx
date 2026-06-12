import { useCallback, useEffect, useRef, useState } from "react";
import { ComparePanel } from "./components/ComparePanel";
import { EmptyState } from "./components/EmptyState";
import { Header } from "./components/Header";
import { LayerToggle } from "./components/LayerToggle";
import { Legend } from "./components/Legend";
import { MetricSwitcher } from "./components/MetricSwitcher";
import { ShortlistPanel } from "./components/ShortlistPanel";
import { StatSheet } from "./components/StatSheet";
import { defaultLayerVisibility } from "./layers";
import { MapView } from "./MapView";
import { firstAvailableMetric, METRIC_ORDER } from "./metrics";
import type { MapApi, PickedSuburb } from "./types";
import { useArtifacts } from "./useArtifacts";
import { useSales } from "./useSales";
import { useScraper } from "./useScraper";
import { useShortlist } from "./useShortlist";

export default function App() {
  const state = useArtifacts();
  const artifacts = state.status === "ready" ? state.artifacts : null;

  const [selectedMetricId, setSelectedMetricId] = useState(METRIC_ORDER[0]!.id);
  const [picked, setPicked] = useState<PickedSuburb | null>(null);
  const [layerVisibility, setLayerVisibility] = useState(defaultLayerVisibility);
  const [compareOpen, setCompareOpen] = useState(false);
  const shortlist = useShortlist();
  const { sales, reload: reloadSales } = useSales();
  const scraper = useScraper(reloadSales);
  const mapApiRef = useRef<MapApi | null>(null);

  // Once the artifact arrives, default to the first metric that has data.
  useEffect(() => {
    if (artifacts != null && artifacts.metrics.metrics[selectedMetricId] == null) {
      setSelectedMetricId(firstAvailableMetric(artifacts.metrics));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifacts]);

  // Close the compare view if the shortlist drops below two suburbs.
  useEffect(() => {
    if (compareOpen && shortlist.codes.length < 2) setCompareOpen(false);
  }, [compareOpen, shortlist.codes.length]);

  const toggleLayer = (layerId: string) =>
    setLayerVisibility((prev) => ({ ...prev, [layerId]: !prev[layerId] }));

  /** Shared selection path for search results and shortlist rows: fly + open sheet. */
  const selectSuburb = useCallback(
    (salCode: string) => {
      const record = artifacts?.metrics.suburbs[salCode];
      if (record == null) return;
      setPicked({ salCode, name: record.name, state: record.state });
      if (record.centre != null) mapApiRef.current?.flyTo(record.centre);
    },
    [artifacts],
  );

  return (
    <div className="app">
      <MapView
        artifacts={artifacts}
        selectedMetricId={selectedMetricId}
        selectedSalCode={picked?.salCode ?? null}
        pinnedSalCodes={shortlist.codes}
        layerVisibility={layerVisibility}
        mapApiRef={mapApiRef}
        onPick={setPicked}
      />
      <Header
        artifact={artifacts?.metrics ?? null}
        selectedMetricId={selectedMetricId}
        onSearchSelect={(entry) => selectSuburb(entry.salCode)}
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
            <ShortlistPanel
              artifact={artifacts.metrics}
              codes={shortlist.codes}
              selectedSalCode={picked?.salCode ?? null}
              compareOpen={compareOpen}
              onSelect={selectSuburb}
              onRemove={shortlist.remove}
              onToggleCompare={() => setCompareOpen((open) => !open)}
            />
          </div>
          <Legend
            artifact={artifacts.metrics}
            selectedMetricId={selectedMetricId}
          />
          {compareOpen && (
            <ComparePanel
              artifact={artifacts.metrics}
              codes={shortlist.codes}
              selectedMetricId={selectedMetricId}
              onSelect={selectSuburb}
              onClose={() => setCompareOpen(false)}
            />
          )}
          {picked != null && (
            <StatSheet
              artifact={artifacts.metrics}
              picked={picked}
              selectedMetricId={selectedMetricId}
              pinned={shortlist.has(picked.salCode)}
              sales={sales?.suburbs[picked.salCode] ?? null}
              scraper={scraper}
              onTogglePin={() => shortlist.toggle(picked.salCode)}
              onClose={() => setPicked(null)}
            />
          )}
        </>
      )}
      {state.status === "missing" && <EmptyState missing={state.missing} />}
    </div>
  );
}
