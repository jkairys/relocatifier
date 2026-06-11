import { colorFor } from "../color";
import { formatValue, metricLabel, switcherMetricIds } from "../metrics";
import type { MetricsArtifact, PickedSuburb } from "../types";

interface StatSheetProps {
  artifact: MetricsArtifact;
  picked: PickedSuburb;
  selectedMetricId: string;
  pinned: boolean;
  onTogglePin: () => void;
  onClose: () => void;
}

const EM_DASH = "—";

export function StatSheet({
  artifact,
  picked,
  selectedMetricId,
  pinned,
  onTogglePin,
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
        <div className="stat-sheet-actions">
          <button
            type="button"
            className={`pin-btn${pinned ? " is-pinned" : ""}`}
            onClick={onTogglePin}
            aria-pressed={pinned}
            aria-label={
              pinned ? `Unpin ${name} from shortlist` : `Pin ${name} to shortlist`
            }
            title={pinned ? "Remove from shortlist" : "Add to shortlist"}
          >
            <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
              <path
                d="M12 3.6l2.5 5.06 5.6.81-4.05 3.95.96 5.57L12 16.36 7 18.99l.95-5.57L3.9 9.47l5.6-.81L12 3.6z"
                fill={pinned ? "currentColor" : "none"}
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinejoin="round"
              />
            </svg>
          </button>
          <button
            type="button"
            className="close-btn"
            onClick={onClose}
            aria-label="Close stat sheet"
          >
            ×
          </button>
        </div>
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
