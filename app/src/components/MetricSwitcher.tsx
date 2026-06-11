import type { MetricsArtifact } from "../types";
import { metricLabel, switcherMetricIds } from "../metrics";

interface MetricSwitcherProps {
  artifact: MetricsArtifact;
  selectedMetricId: string;
  onSelect: (id: string) => void;
}

export function MetricSwitcher({
  artifact,
  selectedMetricId,
  onSelect,
}: MetricSwitcherProps) {
  return (
    <section className="panel switcher" aria-label="Metric switcher">
      <h2 className="panel-title">Metric</h2>
      <ul className="switcher-list">
        {switcherMetricIds(artifact).map((id) => {
          const available = artifact.metrics[id] != null;
          const active = id === selectedMetricId;
          return (
            <li key={id}>
              <button
                type="button"
                className={`switcher-item${active ? " is-active" : ""}`}
                disabled={!available}
                aria-pressed={active}
                onClick={() => onSelect(id)}
              >
                <span className="switcher-label">{metricLabel(id, artifact)}</span>
                {!available && <span className="soon-pill">soon</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
