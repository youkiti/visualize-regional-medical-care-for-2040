// Pure functions used by MapView / Legend / AreaPanel: ratio computation,
// fixed-bin classification for the ratio metric, runtime quantile bins for
// the actual/need metrics, and display formatting. No React, no MapLibre —
// keeps this file trivially unit-testable (see metrics.test.ts).

import type { BedFunctionKey, BedMetricKind, DemandCategoryKey, DemandMetricKind, MetricKind } from '../types';

/**
 * 2025実績 ÷ 2025必要数。need=0 のときは「0でも∞でもない算出不可」を表すため
 * null を返す（actual が 0 でも >0 でも同様）。
 */
export function computeRatio(actual: number, need: number): number | null {
  if (need === 0) return null;
  return actual / need;
}

// Fixed, multiplicatively-symmetric bin edges around 1.0. Each edge is the
// reciprocal of its counterpart (1/1.30, 1/1.15, 1/1.05) so the palette
// keeps the same meaning across bed functions. Lower bound inclusive, upper
// bound exclusive (see table in the M3 brief / doc/REQUIREMENTS.md §3.2).
export const RATIO_BIN_EDGES = [0.77, 0.87, 0.95, 1.05, 1.15, 1.3] as const;

export const RATIO_BIN_COLORS = [
  '#184f95',
  '#2a78d6',
  '#86b6ef',
  '#e1e0d9',
  '#ee9391',
  '#e34948',
  '#a32c2b',
] as const;

export const RATIO_BIN_LABELS = [
  '0.77倍未満（必要数を大きく下回る）',
  '0.77 〜 0.87',
  '0.87 〜 0.95',
  '0.95 〜 1.05（ほぼ同等）',
  '1.05 〜 1.15',
  '1.15 〜 1.30',
  '1.30倍以上（必要数を大きく上回る）',
] as const;

export const RATIO_UNAVAILABLE_COLOR = '#f9f9f7';
export const RATIO_UNAVAILABLE_OUTLINE_COLOR = '#898781';
export const RATIO_UNAVAILABLE_LABEL = '算出不可（必要数0）';

/**
 * Classify a value into one of `edges.length + 1` fixed bins (0-indexed),
 * given a strictly ascending list of bin edges. Lower bound inclusive, upper
 * bound exclusive; the last bin is closed (value >= edges[edges.length - 1]
 * all fall into index edges.length).
 */
export function classifyBin(value: number, edges: readonly number[]): number {
  for (let i = 0; i < edges.length; i++) {
    if (value < edges[i]) return i;
  }
  return edges.length;
}

/**
 * Classify a ratio value into one of the 7 fixed bins (0-indexed).
 * Lower bound inclusive, upper bound exclusive; the last bin is closed
 * (r >= 1.30 all fall into index 6).
 */
export function classifyRatioBin(r: number): number {
  return classifyBin(r, RATIO_BIN_EDGES);
}

// ---- Demand forecast (在宅・外来) change-ratio classification ------------
//
// Fixed (not quantile) bin edges around 1.0 = baseline_year (2024), so the
// color scale keeps the same meaning no matter which forecast year is
// selected. Verified to cover the observed range for both categories and all
// forecast years (home_care: 0.76-2.02, outpatient: 0.51-1.23) — see M4
// brief. Reuses RATIO_BIN_COLORS (below/above 1.0 = blue/red, same direction
// as the bed actual/need ratio) rather than a new palette.
export const DEMAND_RATIO_BIN_EDGES = [0.67, 0.83, 0.95, 1.05, 1.2, 1.5] as const;

export const DEMAND_RATIO_BIN_LABELS = [
  '-33%未満（大きく減少）',
  '-33% 〜 -17%',
  '-17% 〜 -5%',
  '-5% 〜 +5%（ほぼ横ばい）',
  '+5% 〜 +20%',
  '+20% 〜 +50%',
  '+50%以上（大きく増加）',
] as const;

/**
 * Classify a demand change ratio (value(year) / value(baseline_year)) into
 * one of the 7 fixed DEMAND_RATIO_BIN_EDGES bins (0-indexed). Same
 * inclusive-lower/exclusive-upper convention as classifyRatioBin.
 */
export function classifyDemandRatioBin(r: number): number {
  return classifyBin(r, DEMAND_RATIO_BIN_EDGES);
}

// Continuous (actual / need) metric ramp — light to dark blue.
export const SEQUENTIAL_RAMP_COLORS = [
  '#cde2fb',
  '#9ec5f4',
  '#6da7ec',
  '#3987e5',
  '#256abf',
  '#184f95',
  '#0d366b',
] as const;

export const QUANTILE_BIN_COUNT = 7;

/**
 * Compute QUANTILE_BIN_COUNT+1 edges (min ... max) from a set of values using
 * linear-interpolation quantiles. Degenerates gracefully: empty input
 * returns all-zero edges; a single distinct value returns all-equal edges.
 */
export function computeQuantileEdges(values: number[], binCount: number = QUANTILE_BIN_COUNT): number[] {
  if (values.length === 0) return new Array(binCount + 1).fill(0);

  const sorted = [...values].sort((a, b) => a - b);
  const n = sorted.length;

  const quantileAt = (p: number): number => {
    if (n === 1) return sorted[0];
    const idx = p * (n - 1);
    const lo = Math.floor(idx);
    const hi = Math.ceil(idx);
    if (lo === hi) return sorted[lo];
    const frac = idx - lo;
    return sorted[lo] + (sorted[hi] - sorted[lo]) * frac;
  };

  const edges: number[] = [];
  for (let i = 0; i <= binCount; i++) {
    edges.push(quantileAt(i / binCount));
  }
  return edges;
}

// ---- Formatting ---------------------------------------------------------

export function formatInteger(n: number): string {
  return Math.round(n).toLocaleString('ja-JP');
}

// Table-cell variant: the reason (need=0) is spelled out inline since the
// cell appears next to actual/need numbers rather than a legend.
export const RATIO_UNAVAILABLE_CELL_LABEL = '—（必要数0）';

export function formatRatio(r: number | null): string {
  if (r === null) return RATIO_UNAVAILABLE_CELL_LABEL;
  return `${r.toFixed(2)}倍`;
}

export function formatPercent(r: number | null, digits: number = 1): string {
  if (r === null) return '未算出（原典 XXX）';
  return `${(r * 100).toFixed(digits)}%`;
}

export function formatDiff(actual: number, need: number): string {
  const diff = actual - need;
  const sign = diff > 0 ? '+' : '';
  return `${sign}${formatInteger(diff)}`;
}

export function formatKm2(km2: number): string {
  return `${km2.toLocaleString('ja-JP', { maximumFractionDigits: 1, minimumFractionDigits: 1 })} km²`;
}

/**
 * Format a demand change ratio (value(year) / value(baseline_year)) as a
 * signed percentage, e.g. 1.304 -> "+30.4%", 0.828 -> "-17.2%". Same
 * no-sign-for-zero convention as formatDiff.
 *
 * The sign is decided from the *rounded* figure, not the raw one: a change too
 * small to survive rounding must read "0.0%", never "-0.0%" (which shows a
 * minus sign next to a zero and reads as a decrease the digits don't support).
 * Real data hits this — 峡南・在宅2050年度 (-0.037%) と
 * 宮崎東諸県・外来2035年度 (-0.008%)。
 */
export function formatChangeRatio(ratio: number): string {
  // toFixed stays the single rounding authority; only the sign is re-derived.
  const rounded = ((ratio - 1) * 100).toFixed(1);
  if (Number(rounded) === 0) return '0.0%';
  return `${Number(rounded) > 0 ? '+' : ''}${rounded}%`;
}

/** レセプト件数/月 の表示用整形（在宅・外来の医療需要推計）。 */
export function formatReceipts(value: number): string {
  return `${formatInteger(value)} 件/月`;
}

// ---- Sequential (actual/need) classification -----------------------------

/**
 * Collapse a non-decreasing edge list down to its distinct (strictly
 * ascending) values. Quantile edges can repeat when many areas share the
 * same value (e.g. many areas with actual_2025=0 for a rare bed function
 * like 高度急性期), which would otherwise produce zero-width bins.
 *
 * Always returns at least 2 values (i.e. at least 1 bin), even for
 * completely degenerate input (every value identical, or empty input) —
 * callers never have to special-case "no bins".
 */
export function distinctEdges(edges: number[]): number[] {
  const out: number[] = [];
  for (const e of edges) {
    if (out.length === 0 || e !== out[out.length - 1]) {
      out.push(e);
    }
  }
  if (out.length === 0) return [0, 0];
  if (out.length === 1) return [out[0], out[0]];
  return out;
}

/**
 * Pick `binCount` colors from `colors`, spaced as evenly as possible and
 * always including both endpoints (index 0 and colors.length-1). Used to
 * shrink the 7-color SEQUENTIAL_RAMP_COLORS palette down to however many
 * distinct bins `distinctEdges` produced (e.g. 6 bins -> indices
 * [0, 1, 2, 4, 5, 6]).
 */
export function selectRampColors<T>(colors: readonly T[], binCount: number): T[] {
  if (binCount <= 0) return [];
  if (binCount === 1) return [colors[0]];
  const lastIdx = colors.length - 1;
  const out: T[] = [];
  for (let i = 0; i < binCount; i++) {
    out.push(colors[Math.round((i * lastIdx) / (binCount - 1))]);
  }
  return out;
}

export interface SequentialClasses {
  /** Distinct ascending boundaries; length === colors.length + 1. */
  edges: number[];
  /** One color per bin, drawn from SEQUENTIAL_RAMP_COLORS. */
  colors: string[];
}

/**
 * Derive the actual bins to render (map `step` expression and Legend rows)
 * from the raw quantile edges: dedupe first, then size the color selection
 * to match. MapView and Legend both call this so the map fill and the
 * legend rows are always in sync.
 */
export function computeSequentialClasses(
  rawEdges: number[],
  palette: readonly string[] = SEQUENTIAL_RAMP_COLORS
): SequentialClasses {
  const edges = distinctEdges(rawEdges);
  const colors = selectRampColors(palette, edges.length - 1);
  return { edges, colors };
}

// ---- MetricKind classification ---------------------------------------------
//
// MetricKind (types.ts) is BedMetricKind | DemandMetricKind. UI code
// (Controls/App/MapView/Legend) needs to branch on which family a MetricKind
// belongs to and, for demand metrics, recover the DemandCategoryKey the
// area_demand_R7.json / area_map.json flat keys below are keyed by.

const DEMAND_METRIC_CATEGORY: Record<DemandMetricKind, DemandCategoryKey> = {
  demand_home_care: 'home_care',
  demand_outpatient: 'outpatient',
};

/** True for the 2 demand-forecast metric kinds ('demand_home_care'/'demand_outpatient'). */
export function isDemandMetric(metric: MetricKind): metric is DemandMetricKind {
  return metric === 'demand_home_care' || metric === 'demand_outpatient';
}

/** The DemandCategoryKey (area_demand_R7.json key) a DemandMetricKind reads from. */
export function demandCategoryOf(metric: DemandMetricKind): DemandCategoryKey {
  return DEMAND_METRIC_CATEGORY[metric];
}

// ---- MapLibre helpers -----------------------------------------------------

/**
 * Read the value for the currently-selected bed metric off a flat
 * properties record. Bed-only (BedMetricKind, not MetricKind): callers with a
 * possibly-demand MetricKind must branch via isDemandMetric() first and read
 * demand values via readDemandValue/readDemandRatio instead — the a_/n_/r_
 * flat keys this reads have nothing in common with the demand ones.
 */
export function readMetricValue(
  props: Record<string, unknown>,
  metric: BedMetricKind,
  fn: BedFunctionKey
): number | null {
  if (metric === 'ratio') {
    const r = props[`r_${fn}`];
    return typeof r === 'number' ? r : null;
  }
  const key = metric === 'actual' ? `a_${fn}` : `n_${fn}`;
  const v = props[key];
  return typeof v === 'number' ? v : null;
}

/** Bed-only (BedMetricKind, not MetricKind) — see readMetricValue. */
export function formatMetricValue(metric: BedMetricKind, value: number | null): string {
  if (metric === 'ratio') return formatRatio(value);
  if (value === null) return '—';
  return `${formatInteger(value)} 床`;
}

// ---- Demand forecast (area_map.json) flat property keys -------------------
//
// Mirrors web/scripts/lib/merge.mjs's demandValueKey/demandRatioKey exactly
// (merge.test.ts checks the two agree) so a key-naming change in one file
// can't silently drift from the other (see M4 brief).

/** Flat property key for a single (category, year) demand value, e.g. "home_care_2040". */
export function demandValueKey(category: DemandCategoryKey, year: number): string {
  return `${category}_${year}`;
}

/** Flat property key for a single (category, year) demand change ratio, e.g. "home_care_r_2040". */
export function demandRatioKey(category: DemandCategoryKey, year: number): string {
  return `${category}_r_${year}`;
}

/** Read the demand value for (category, year) off a flat properties record. */
export function readDemandValue(
  props: Record<string, unknown>,
  category: DemandCategoryKey,
  year: number
): number | null {
  const v = props[demandValueKey(category, year)];
  return typeof v === 'number' ? v : null;
}

/** Read the demand change ratio (value(year) / value(baseline_year)) for (category, year) off a flat properties record. */
export function readDemandRatio(
  props: Record<string, unknown>,
  category: DemandCategoryKey,
  year: number
): number | null {
  const v = props[demandRatioKey(category, year)];
  return typeof v === 'number' ? v : null;
}
