import type { MetricsArtifact } from "../types";
import { metricLabel } from "../metrics";

interface HeaderProps {
  artifact: MetricsArtifact | null;
  selectedMetricId: string;
}

function formatVintages(vintages: Record<string, string>): string {
  return Object.entries(vintages)
    .map(([source, vintage]) => `${source.replace(/_/g, " ")} ${vintage}`)
    .join(" · ");
}

export function Header({ artifact, selectedMetricId }: HeaderProps) {
  const vintages = artifact ? formatVintages(artifact.vintages) : null;
  return (
    <header className="header">
      <div className="wordmark">
        <span className="wordmark-dot" aria-hidden="true" />
        relocatifier
      </div>
      {artifact != null && (
        <div className="header-meta">
          <span className="header-metric">
            {metricLabel(selectedMetricId, artifact)}
          </span>
          {vintages != null && vintages !== "" && (
            <span className="header-vintage" title="Data vintage">
              {vintages}
            </span>
          )}
        </div>
      )}
    </header>
  );
}
