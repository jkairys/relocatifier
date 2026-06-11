import { legendGradient, NO_DATA_COLOR } from "../color";
import { formatValue, metricLabel } from "../metrics";
import type { MetricsArtifact } from "../types";

interface LegendProps {
  artifact: MetricsArtifact;
  selectedMetricId: string;
}

export function Legend({ artifact, selectedMetricId }: LegendProps) {
  const def = artifact.metrics[selectedMetricId];
  if (def == null) return null;
  const fmt = (v: number) => formatValue(v, selectedMetricId, def.format);
  return (
    <section className="panel legend" aria-label="Legend">
      <h2 className="panel-title">{metricLabel(selectedMetricId, artifact)}</h2>
      <div className="legend-ramp" style={{ background: legendGradient(def) }} />
      <div className="legend-ticks">
        <span>{fmt(def.stats.p10)}</span>
        <span>{fmt(def.stats.median)}</span>
        <span>{fmt(def.stats.p90)}</span>
      </div>
      <div className="legend-tick-labels">
        <span>p10</span>
        <span>median</span>
        <span>p90</span>
      </div>
      <div className="legend-nodata">
        <span className="legend-swatch" style={{ background: NO_DATA_COLOR }} />
        no data
      </div>
    </section>
  );
}
