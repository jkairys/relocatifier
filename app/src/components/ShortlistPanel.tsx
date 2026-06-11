import { useState } from "react";
import type { MetricsArtifact } from "../types";

interface ShortlistPanelProps {
  artifact: MetricsArtifact;
  codes: string[];
  selectedSalCode: string | null;
  compareOpen: boolean;
  onSelect: (salCode: string) => void;
  onRemove: (salCode: string) => void;
  onToggleCompare: () => void;
}

export function ShortlistPanel({
  artifact,
  codes,
  selectedSalCode,
  compareOpen,
  onSelect,
  onRemove,
  onToggleCompare,
}: ShortlistPanelProps) {
  const [collapsed, setCollapsed] = useState(false);
  // Only render codes the artifact knows about (stale pins stay stored but hidden).
  const known = codes.filter((c) => artifact.suburbs[c] != null);

  return (
    <section className="panel shortlist" aria-label="Shortlist">
      <button
        type="button"
        className="shortlist-head"
        onClick={() => setCollapsed((c) => !c)}
        aria-expanded={!collapsed}
      >
        <h2 className="panel-title shortlist-title">
          Shortlist
          {known.length > 0 && (
            <span className="shortlist-count">{known.length}</span>
          )}
        </h2>
        <svg
          className={`shortlist-chevron${collapsed ? " is-collapsed" : ""}`}
          viewBox="0 0 12 12"
          width="12"
          height="12"
          aria-hidden="true"
        >
          <path
            d="m2.5 4.5 3.5 3.5 3.5-3.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {!collapsed && (
        <>
          {known.length === 0 ? (
            <p className="shortlist-hint">
              Star a suburb on its stat sheet to pin it here.
            </p>
          ) : (
            <ul className="shortlist-list">
              {known.map((salCode) => {
                const rec = artifact.suburbs[salCode];
                if (rec == null) return null;
                const active = salCode === selectedSalCode;
                return (
                  <li key={salCode} className="shortlist-row">
                    <button
                      type="button"
                      className={`shortlist-item${active ? " is-active" : ""}`}
                      onClick={() => onSelect(salCode)}
                      title={`Fly to ${rec.name}`}
                    >
                      <span className="shortlist-name">{rec.name}</span>
                      <span className="shortlist-state">{rec.state}</span>
                    </button>
                    <button
                      type="button"
                      className="shortlist-remove"
                      onClick={() => onRemove(salCode)}
                      aria-label={`Remove ${rec.name} from shortlist`}
                      title="Remove"
                    >
                      ×
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {known.length >= 2 && (
            <button
              type="button"
              className={`shortlist-compare${compareOpen ? " is-active" : ""}`}
              onClick={onToggleCompare}
              aria-pressed={compareOpen}
            >
              {compareOpen ? "Hide comparison" : `Compare ${known.length} suburbs`}
            </button>
          )}
        </>
      )}
    </section>
  );
}
