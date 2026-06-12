import { useState } from "react";
import { colorFor } from "../color";
import { formatValue, metricLabel, switcherMetricIds } from "../metrics";
import {
  ALL_MONTHS,
  formatSaleDate,
  formatSalePrice,
  RECENT_MONTHS,
  salesWithin,
  staleness,
} from "../sales";
import type {
  MetricsArtifact,
  PickedSuburb,
  SaleRecord,
  SalesSuburb,
} from "../types";
import type { ScraperState } from "../useScraper";

interface StatSheetProps {
  artifact: MetricsArtifact;
  picked: PickedSuburb;
  selectedMetricId: string;
  pinned: boolean;
  /** Sales for this suburb, or null when sales.json has nothing for it. */
  sales: SalesSuburb | null;
  /** Optional scraper control-plane state; controls render only when available. */
  scraper: ScraperState | null;
  onTogglePin: () => void;
  onClose: () => void;
}

const EM_DASH = "—";

function num(value: number | null): string {
  return value == null ? EM_DASH : String(value);
}

/** One row in the recent-sales table. */
function SaleRow({ sale }: { sale: SaleRecord }) {
  return (
    <tr className="sales-row">
      <td className="sales-date">{formatSaleDate(sale.sale_date)}</td>
      <td className="sales-price">{formatSalePrice(sale)}</td>
      <td className="sales-spec" title="bedrooms">
        {num(sale.bedrooms)}
      </td>
      <td className="sales-spec" title="bathrooms">
        {num(sale.bathrooms)}
      </td>
      <td className="sales-spec" title="land size (m²)">
        {sale.land_size_sqm == null ? EM_DASH : sale.land_size_sqm}
      </td>
      <td className="sales-type">{sale.property_type ?? EM_DASH}</td>
    </tr>
  );
}

/** "Recent sales" section, rendered only when this suburb has sales data. */
function RecentSales({ sales }: { sales: SalesSuburb }) {
  const [showAll, setShowAll] = useState(false);
  const months = showAll ? ALL_MONTHS : RECENT_MONTHS;
  const rows = salesWithin(sales.sales, months);
  const stale = staleness(sales.fetched_at);
  const hasTwelveMonth = salesWithin(sales.sales, ALL_MONTHS).length > 0;

  return (
    <section className="sales" aria-label="Recent sales">
      <div className="sales-head">
        <h3 className="panel-title sales-title">Recent sales</h3>
        {stale != null && <span className="sales-stale">{stale}</span>}
      </div>
      {rows.length === 0 ? (
        <p className="sales-empty">
          {showAll || !hasTwelveMonth
            ? "No sales recorded in the last 12 months."
            : `No sales in the last ${RECENT_MONTHS} months.`}
        </p>
      ) : (
        <table className="sales-table">
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Price</th>
              <th scope="col" title="bedrooms">
                Bd
              </th>
              <th scope="col" title="bathrooms">
                Ba
              </th>
              <th scope="col" title="land size (m²)">
                m²
              </th>
              <th scope="col">Type</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((sale, i) => (
              <SaleRow key={`${sale.address}-${sale.sale_date}-${i}`} sale={sale} />
            ))}
          </tbody>
        </table>
      )}
      {hasTwelveMonth && (
        <button
          type="button"
          className="sales-toggle"
          onClick={() => setShowAll((v) => !v)}
        >
          {showAll ? `Show last ${RECENT_MONTHS} months` : "Show all (12 mo)"}
        </button>
      )}
    </section>
  );
}

/** Watchlist controls, rendered only when the scraper service is available. */
function WatchlistControls({
  salCode,
  scraper,
}: {
  salCode: string;
  scraper: ScraperState;
}) {
  const onWatchlist = scraper.watchlist.has(salCode);
  const running = scraper.activeRun != null;
  const runningThis = scraper.activeRun?.salCode === salCode;

  return (
    <section className="watchlist-controls" aria-label="Watchlist controls">
      {onWatchlist ? (
        <button
          type="button"
          className="watchlist-btn"
          onClick={() => void scraper.refresh(salCode)}
          disabled={running}
        >
          {runningThis ? "Refreshing data…" : "On Watchlist — refresh data"}
        </button>
      ) : (
        <button
          type="button"
          className="watchlist-btn is-primary"
          onClick={() => void scraper.add(salCode)}
          disabled={running}
        >
          {runningThis ? "Adding…" : "Add to Watchlist"}
        </button>
      )}
      {runningThis && (
        <p className="watchlist-progress" role="status">
          <span className="watchlist-spinner" aria-hidden="true" />
          Fetching recent sales…
        </p>
      )}
      {scraper.notice != null && (
        <p className="watchlist-notice" role="alert">
          {scraper.notice}
          <button
            type="button"
            className="watchlist-notice-dismiss"
            onClick={scraper.dismissNotice}
            aria-label="Dismiss message"
          >
            ×
          </button>
        </p>
      )}
    </section>
  );
}

export function StatSheet({
  artifact,
  picked,
  selectedMetricId,
  pinned,
  sales,
  scraper,
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
      {sales != null && <RecentSales key={picked.salCode} sales={sales} />}
      {scraper != null && scraper.available && (
        <WatchlistControls salCode={picked.salCode} scraper={scraper} />
      )}
    </aside>
  );
}
