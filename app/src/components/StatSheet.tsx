import { colorFor } from "../color";
import { formatValue, metricLabel, switcherMetricIds } from "../metrics";
import type { MetricsArtifact, PickedSuburb } from "../types";

interface StatSheetProps {
  artifact: MetricsArtifact;
  picked: PickedSuburb;
  selectedMetricId: string;
  onClose: () => void;
}

const EM_DASH = "—";

export function StatSheet({
  artifact,
  picked,
  selectedMetricId,
  onClose,
}: StatSheetProps) {
  const record = artifact.suburbs[picked.salCode];
  const name = record?.name ?? picked.name;
  const state = record?.state ?? picked.state;

  return (
    <aside className="panel stat-sheet" aria-label={`Stat sheet for ${name}`}>
      <div className="stat-sheet-head">
        <div>
          <h2 className="stat-sheet-name">{name}</h2>
          <p className="stat-sheet-sub">
            {state}
            <span className="stat-sheet-sal">SAL {picked.salCode}</span>
          </p>
        </div>
        <button
          type="button"
          className="close-btn"
          onClick={onClose}
          aria-label="Close stat sheet"
        >
          ×
        </button>
      </div>
      <dl className="stat-list">
        {switcherMetricIds(artifact).map((id) => {
          const def = artifact.metrics[id];
          const value = record?.values[id] ?? null;
          const hasValue = value != null && def != null;
          return (
            <div
              key={id}
              className={`stat-row${id === selectedMetricId ? " is-active" : ""}`}
            >
              <dt>{metricLabel(id, artifact)}</dt>
              <dd>
                {hasValue ? (
                  <>
                    <span
                      className="stat-swatch"
                      style={{ background: colorFor(value, def) }}
                      aria-hidden="true"
                    />
                    {formatValue(value, id, def.format)}
                  </>
                ) : (
                  <span className="stat-empty">{EM_DASH}</span>
                )}
              </dd>
            </div>
          );
        })}
      </dl>
    </aside>
  );
}
