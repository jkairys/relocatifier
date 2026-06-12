import type { ExpressionSpecification } from "maplibre-gl";
import type { Feature, FeatureCollection, Point } from "geojson";
import { rampColor } from "./color";
import { RECENT_MONTHS, withinMonths } from "./sales";
import type { SaleRecord, SalesArtifact } from "./types";

/**
 * Recent-sales dots: one point per sale in the last {@link RECENT_MONTHS}
 * months that carries coordinates, across every suburb in the artifact.
 *
 * Colour encodes price relative to all currently-plotted priced sales, in
 * five quantile classes with HARD boundaries (project convention: green =
 * cheaper → red = dearer). Price-withheld sales plot grey. This mirrors the
 * choropleth's discrete green→red ramp; we reuse {@link rampColor} so the two
 * layers stay visually consistent.
 */

/** Grey for price-withheld (and any non-classifiable) dots. */
export const SALES_WITHHELD_COLOR = "#9aa3b2";

/** Number of quantile colour classes. */
const CLASS_COUNT = 5;

/** Discrete class colours, cheap (green) → dear (red), from the shared ramp. */
export const SALES_CLASS_COLORS: readonly string[] = Array.from(
  { length: CLASS_COUNT },
  (_, i) => rampColor(i / (CLASS_COUNT - 1)),
);

/** Feature properties carried on each dot for paint + popup. */
interface SaleDotProps {
  salCode: string;
  address: string;
  price: number | null;
  price_display: string | null;
  bedrooms: number | null;
  bathrooms: number | null;
  parking: number | null;
  land_size_sqm: number | null;
  property_type: string | null;
  sale_date: string | null;
  /** 0..CLASS_COUNT-1 price-quantile class; -1 when price is withheld. */
  priceClass: number;
}

type SaleDotFeature = Feature<Point, SaleDotProps>;
export type SaleDotCollection = FeatureCollection<Point, SaleDotProps>;

/** A plottable recent sale: in-window and carrying finite coordinates. */
function isPlottable(sale: SaleRecord, now: Date): boolean {
  return (
    withinMonths(sale.sale_date, RECENT_MONTHS, now) &&
    typeof sale.lat === "number" &&
    Number.isFinite(sale.lat) &&
    typeof sale.lon === "number" &&
    Number.isFinite(sale.lon)
  );
}

/**
 * Quantile breakpoints splitting `prices` into {@link CLASS_COUNT} classes.
 * Returns the (CLASS_COUNT - 1) interior boundaries, ascending. Empty when
 * there are too few distinct prices to form boundaries.
 */
function quantileBreaks(prices: number[]): number[] {
  const sorted = [...prices].sort((a, b) => a - b);
  if (sorted.length < 2) return [];
  const breaks: number[] = [];
  for (let i = 1; i < CLASS_COUNT; i++) {
    const rank = (sorted.length - 1) * (i / CLASS_COUNT);
    const lo = Math.floor(rank);
    const hi = Math.ceil(rank);
    const frac = rank - lo;
    breaks.push(sorted[lo]! + (sorted[hi]! - sorted[lo]!) * frac);
  }
  // Collapse duplicate boundaries (heavily-tied prices) so step() stays valid.
  return breaks.filter((b, i) => i === 0 || b > breaks[i - 1]!);
}

/** Class index 0..CLASS_COUNT-1 for one price given ascending breakpoints. */
function classFor(price: number, breaks: number[]): number {
  let cls = 0;
  for (const b of breaks) {
    if (price >= b) cls++;
    else break;
  }
  return cls;
}

/**
 * Build the dot FeatureCollection for the current artifact. Price classes are
 * computed here (not via a MapLibre data expression) so quantiles reflect the
 * exact set of plotted sales, with hard class boundaries.
 */
export function buildSaleDots(
  artifact: SalesArtifact,
  now: Date = new Date(),
): SaleDotCollection {
  const features: SaleDotFeature[] = [];
  const prices: number[] = [];

  for (const suburb of Object.values(artifact.suburbs)) {
    for (const sale of suburb.sales) {
      if (!isPlottable(sale, now)) continue;
      if (sale.price != null && Number.isFinite(sale.price)) prices.push(sale.price);
    }
  }
  const breaks = quantileBreaks(prices);

  for (const [salCode, suburb] of Object.entries(artifact.suburbs)) {
    for (const sale of suburb.sales) {
      if (!isPlottable(sale, now)) continue;
      const priceClass =
        sale.price != null && Number.isFinite(sale.price)
          ? classFor(sale.price, breaks)
          : -1;
      features.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: [sale.lon!, sale.lat!] },
        properties: {
          salCode,
          address: sale.address,
          price: sale.price,
          price_display: sale.price_display,
          bedrooms: sale.bedrooms,
          bathrooms: sale.bathrooms,
          parking: sale.parking,
          land_size_sqm: sale.land_size_sqm,
          property_type: sale.property_type,
          sale_date: sale.sale_date,
          priceClass,
        },
      });
    }
  }

  return { type: "FeatureCollection", features };
}

/**
 * Paint colour by the pre-computed `priceClass`: a hard "match" over the class
 * index (never a continuous gradient). Withheld (-1) → grey.
 */
export function saleDotColor(): ExpressionSpecification {
  const cases: (string | number)[] = [];
  SALES_CLASS_COLORS.forEach((color, i) => {
    cases.push(i, color);
  });
  return [
    "match",
    ["get", "priceClass"],
    ...cases,
    SALES_WITHHELD_COLOR, // default: withheld / unclassified
  ] as unknown as ExpressionSpecification;
}
