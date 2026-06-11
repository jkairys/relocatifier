import type { MetricDef } from "./types";

/** Fill for suburbs with a null value for the active metric. */
export const NO_DATA_COLOR = "#e3e6ea";

/**
 * Diverging ramp, green → yellow → red (RdYlGn reversed).
 * t = 0 is the GOOD end, t = 1 the BAD end.
 */
const STOPS: ReadonlyArray<readonly [number, readonly [number, number, number]]> = [
  [0.0, [26, 150, 65]], // green  #1a9641
  [0.25, [166, 217, 106]], // light green #a6d96a
  [0.5, [254, 224, 139]], // yellow #fee08b
  [0.75, [253, 174, 97]], // orange #fdae61
  [1.0, [215, 25, 28]], // red #d7191c
];

export function rampColor(t: number): string {
  const x = Math.min(1, Math.max(0, t));
  for (let i = 1; i < STOPS.length; i++) {
    const [t1, c1] = STOPS[i]!;
    if (x <= t1) {
      const [t0, c0] = STOPS[i - 1]!;
      const f = t1 === t0 ? 0 : (x - t0) / (t1 - t0);
      const r = Math.round(c0[0] + (c1[0] - c0[0]) * f);
      const g = Math.round(c0[1] + (c1[1] - c0[1]) * f);
      const b = Math.round(c0[2] + (c1[2] - c0[2]) * f);
      return `rgb(${r},${g},${b})`;
    }
  }
  const last = STOPS[STOPS.length - 1]![1];
  return `rgb(${last[0]},${last[1]},${last[2]})`;
}

/**
 * Position of a value within the Search Zone distribution:
 * p10 → 0, median → 0.5, p90 → 1 (piecewise linear, clamped).
 */
export function normalize(value: number, stats: MetricDef["stats"]): number {
  const { p10, median, p90 } = stats;
  if (value <= Math.min(p10, median)) return value <= p10 ? 0 : 0.5;
  if (value >= Math.max(p90, median)) return value >= p90 ? 1 : 0.5;
  if (value <= median) {
    return median === p10 ? 0.5 : 0.5 * ((value - p10) / (median - p10));
  }
  return p90 === median ? 0.5 : 0.5 + 0.5 * ((value - median) / (p90 - median));
}

/** 0 = good end per the metric's declared direction, 1 = bad end. */
export function badness(value: number, def: MetricDef): number {
  const n = normalize(value, def.stats);
  return def.direction === "lower_better" ? n : 1 - n;
}

export function colorFor(value: number | null, def: MetricDef | undefined): string {
  if (value == null || def == null) return NO_DATA_COLOR;
  return rampColor(badness(value, def));
}

/**
 * Ink or white, whichever reads better on the given ramp/no-data colour.
 * Accepts the `rgb(r,g,b)` strings rampColor emits and 6-digit hex.
 */
export function readableTextOn(color: string): string {
  let r = 0;
  let g = 0;
  let b = 0;
  const rgb = /^rgb\((\d+),(\d+),(\d+)\)$/.exec(color);
  if (rgb) {
    r = Number(rgb[1]);
    g = Number(rgb[2]);
    b = Number(rgb[3]);
  } else if (color.startsWith("#") && color.length === 7) {
    r = parseInt(color.slice(1, 3), 16);
    g = parseInt(color.slice(3, 5), 16);
    b = parseInt(color.slice(5, 7), 16);
  } else {
    return "#1a2233";
  }
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.55 ? "#1a2233" : "#ffffff";
}

/** CSS gradient for the legend bar, oriented low-value → high-value. */
export function legendGradient(def: MetricDef): string {
  const steps = 9;
  const colors: string[] = [];
  for (let i = 0; i < steps; i++) {
    const n = i / (steps - 1); // position along the value axis
    const t = def.direction === "lower_better" ? n : 1 - n;
    colors.push(rampColor(t));
  }
  return `linear-gradient(to right, ${colors.join(", ")})`;
}
