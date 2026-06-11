import { colorFor, readableTextOn } from "../color";
import { formatValue, metricLabel, switcherMetricIds } from "../metrics";
import type { MetricsArtifact } from "../types";

interface ComparePanelProps {
  artifact: MetricsArtifact;
  codes: string[];
  selectedMetricId: string;
  onSelect: (salCode: string) => void;
  onClose: () => void;
}

const EM_DASH = "—";

/**
 * Compact side-by-side table: pinned suburbs as columns, the seven metrics
 * as rows, every cell tinted with the same relative-to-stats ramp the map uses.
 */
export function ComparePanel({
  artifact,
  codes,
  selectedMetricId,
  onSelect,
  onClose,
}: ComparePanelProps) {
  const known = codes.filter((c) => artifact.suburbs[c] != null);
  if (known.length < 2) return null;

  return (
    <section className="panel compare" aria-label="Compare shortlisted suburbs">
      <div className="compare-head">
        <h2 className="panel-title compare-title">Compare</h2>
        <button
          type="button"
          className="close-btn"
          onClick={onClose}
          aria-label="Close comparison"
        >
          ×
        </button>
      </div>
      <div className="compare-scroll">
        <table className="compare-table">
          <thead>
            <tr>
              <th className="compare-metric-col" aria-label="Metric" />
              {known.map((salCode) => {
                const rec = artifact.suburbs[salCode];
                if (rec == null) return null;
                return (
                  <th key={salCode}>
                    <button
                      type="button"
                      className="compare-suburb"
                      onClick={() => onSelect(salCode)}
                      title={`Fly to ${rec.name}`}
                    >
                      <span className="compare-suburb-name">{rec.name}</span>
                      <span className="compare-suburb-state">{rec.state}</span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {switcherMetricIds(artifact).map((metricId) => {
              const def = artifact.metrics[metricId];
              return (
                <tr
                  key={metricId}
                  className={metricId === selectedMetricId ? "is-active" : ""}
                >
                  <th scope="row" className="compare-metric-col">
                    {metricLabel(metricId, artifact)}
                  </th>
                  {known.map((salCode) => {
                    const value =
                      artifact.suburbs[salCode]?.values[metricId] ?? null;
                    const hasValue = value != null && def != null;
                    const bg = colorFor(value, def);
                    return (
                      <td
                        key={salCode}
                        className="compare-cell"
                        style={
                          hasValue
                            ? { background: bg, color: readableTextOn(bg) }
                            : undefined
                        }
                      >
                        {hasValue
                          ? formatValue(value, metricId, def.format)
                          : EM_DASH}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
