// Shared TypeScript types mirroring the two generated data artifacts
// (see web/scripts/sync-data.mjs). Kept hand-written rather than derived
// from the JSON import so call sites get precise, documented shapes.

export type BedFunctionKey = 'total' | 'high_acute' | 'acute' | 'recovery' | 'chronic';

export const BED_FUNCTIONS: BedFunctionKey[] = ['total', 'high_acute', 'acute', 'recovery', 'chronic'];

export interface AreaBeds {
  actual_2025: number;
  need_2025: number;
}

export interface AreaIndicator {
  area_code: string;
  area_name: string;
  pref_code: string;
  pref_name: string;
  population_2020: number;
  area_km2: number;
  outflow_rate: number | null;
  inflow_rate: number | null;
  /** Present only when outflow_rate/inflow_rate are null (原典が'XXX'=未算出). */
  flow_rate_unavailable?: string;
  beds: Record<BedFunctionKey, AreaBeds>;
}

export interface AreaIndicatorsSource {
  name: string;
  publisher: string;
  url: string;
  page_url: string;
  fiscal_year: string;
  source_file: string;
  source_sha256: string;
  acquired_date: string;
  license: string;
  original_notes: string[];
  derived_via: Array<{ csv: string; meta: string }>;
}

export interface AreaIndicatorsProcessing {
  script: string;
  inputs: Array<{ path: string; sha256: string }>;
  steps: string[];
  caveat: string;
}

export interface AreaIndicatorsKnownIssue {
  id: string;
  summary: string;
  action: string;
  [key: string]: unknown;
}

export interface AreaIndicatorsMetadata {
  title: string;
  source: AreaIndicatorsSource;
  processing: AreaIndicatorsProcessing;
  fields: Record<string, string>;
  known_issues: AreaIndicatorsKnownIssue[];
}

export interface AreaIndicatorsData {
  metadata: AreaIndicatorsMetadata;
  functions: BedFunctionKey[];
  function_labels: Record<BedFunctionKey, string>;
  areas: AreaIndicator[];
}

/** Flat properties of a single feature in generated/area_map.json. */
export interface AreaMapFeatureProperties {
  area_code: string;
  area_name: string;
  pref_code: string;
  pref_name: string;
  boundary_source: string;
  a_total: number;
  n_total: number;
  r_total?: number;
  a_high_acute: number;
  n_high_acute: number;
  r_high_acute?: number;
  a_acute: number;
  n_acute: number;
  r_acute?: number;
  a_recovery: number;
  n_recovery: number;
  r_recovery?: number;
  a_chronic: number;
  n_chronic: number;
  r_chronic?: number;
  bb_w: number;
  bb_s: number;
  bb_e: number;
  bb_n: number;
}

/**
 * Flat entry of a single area in generated/area_index.json — a lightweight
 * (bundled, not fetched) lookup used to resolve a bbox/boundary_source for
 * an area_code without depending on the map's current load/viewport state
 * (see App.tsx's selection flow).
 */
export interface AreaIndexEntry {
  area_code: string;
  boundary_source: string;
  bb_w: number;
  bb_s: number;
  bb_e: number;
  bb_n: number;
}

export type MetricKind = 'ratio' | 'actual' | 'need';

export interface MetricOption {
  kind: MetricKind;
  label: string;
}
