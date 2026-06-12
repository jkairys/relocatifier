import { formatAud } from "./metrics";
import type { SaleRecord } from "./types";

/** Window the stat sheet shows by default vs. behind the "show all" toggle. */
export const RECENT_MONTHS = 6;
export const ALL_MONTHS = 12;

/** Whole days between two dates (a - b), or null if `iso` is unparseable. */
function daysBetween(now: Date, iso: string): number | null {
  const then = new Date(iso);
  const ms = then.getTime();
  if (Number.isNaN(ms)) return null;
  return Math.floor((now.getTime() - ms) / 86_400_000);
}

/** "fetched N days ago" staleness phrasing; null when the timestamp is junk. */
export function staleness(fetchedAt: string, now: Date = new Date()): string | null {
  const days = daysBetween(now, fetchedAt);
  if (days == null) return null;
  if (days <= 0) return "data fetched today";
  if (days === 1) return "data fetched 1 day ago";
  return `data fetched ${days} days ago`;
}

/** True when a sale_date falls within `months` of `now` (client-side filter). */
export function withinMonths(
  saleDate: string | null,
  months: number,
  now: Date = new Date(),
): boolean {
  if (saleDate == null) return false;
  const cutoff = new Date(now);
  cutoff.setMonth(cutoff.getMonth() - months);
  const sale = new Date(saleDate);
  if (Number.isNaN(sale.getTime())) return false;
  return sale >= cutoff;
}

/** Sales within the window, sorted by sale_date desc (nulls excluded). */
export function salesWithin(
  sales: SaleRecord[],
  months: number,
  now: Date = new Date(),
): SaleRecord[] {
  return sales
    .filter((s) => withinMonths(s.sale_date, months, now))
    .sort((a, b) => (b.sale_date ?? "").localeCompare(a.sale_date ?? ""));
}

/** Compact display date, e.g. "14 Mar 26"; falls back to the raw string. */
export function formatSaleDate(saleDate: string | null): string {
  if (saleDate == null) return "—";
  const d = new Date(saleDate);
  if (Number.isNaN(d.getTime())) return saleDate;
  return d.toLocaleDateString("en-AU", {
    day: "numeric",
    month: "short",
    year: "2-digit",
  });
}

/**
 * Sale price for display. Numeric prices format like other prices in the app
 * (formatAud). A null price is an honest "price withheld" — never $0.
 */
export function formatSalePrice(sale: SaleRecord): string {
  if (sale.price != null) return formatAud(sale.price);
  if (sale.price_display != null) return sale.price_display;
  return "price withheld";
}
