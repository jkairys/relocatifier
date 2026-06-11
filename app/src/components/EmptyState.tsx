interface EmptyStateProps {
  missing: string[];
}

export function EmptyState({ missing }: EmptyStateProps) {
  return (
    <div className="empty-state-backdrop">
      <div className="empty-state">
        <div className="empty-state-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="28" height="28" fill="none">
            <path
              d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Zm0 0v14m6-12v14"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </svg>
        </div>
        <h2>No data artifacts found</h2>
        <p>
          Build them with <code>task etl:fetch</code> then{" "}
          <code>task etl:build</code>, and reload.
        </p>
        {missing.length > 0 && (
          <ul className="empty-state-missing">
            {missing.map((path) => (
              <li key={path}>
                <code>{path}</code>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
