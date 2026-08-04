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

/**
 * A defect in the published source data, recorded rather than corrected.
 *
 * Shared by the bed and demand datasets — unlike the rest of the
 * AreaIndicators/AreaDemand pairs below, this one shape really is identical
 * on both sides
 * (both are emitted by tools/lib/provenance.py's write_csv_with_meta and
 * aggregated unchanged by the build_web_* scripts), so there is nothing to
 * drift apart. `id`/`summary`/`action` are always present; `scope`/`evidence`
 * are optional per entry, hence the index signature.
 *
 * Only render string fields directly — `scope` is an object and `evidence` an
 * array, and React cannot render an object (see the caveat note in
 * SourceNotes.tsx for the same trap).
 */
export interface KnownIssue {
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
  known_issues: KnownIssue[];
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

export type BedMetricKind = 'ratio' | 'actual' | 'need';
export type DemandMetricKind = 'demand_home_care' | 'demand_outpatient';
export type MetricKind = BedMetricKind | DemandMetricKind;

export interface MetricOption {
  kind: MetricKind;
  label: string;
}

// ---- Demand forecast (area_demand_R7.json / generated/area_demand.json) --
//
// Mirrors data/processed/area_demand_R7.json (see CLAUDE.md "web/ のデータ構成"
// and the M4 brief). Deliberately NOT reusing the AreaIndicators* types above:
// several fields have a different shape from the bed-indicator dataset (year
// keys are strings, `caveat` is an object with two keys instead of a single
// string, `source_sheet`/`original_title` are arrays because the source
// workbook has 2 sheets).

export type DemandCategoryKey = 'home_care' | 'outpatient';

export const DEMAND_CATEGORIES: DemandCategoryKey[] = ['home_care', 'outpatient'];

export interface AreaDemandArea {
  area_code: string;
  area_name: string;
  pref_code: string;
  pref_name: string;
  population_2024: number;
  population_2040: number;
  /** category -> { year (as a string key — see AreaDemandData.years) -> receipts_per_month } */
  demand: Record<DemandCategoryKey, Record<string, number>>;
}

export interface AreaDemandSource {
  name: string;
  publisher: string;
  url: string;
  page_url: string;
  fiscal_year: string;
  source_file: string;
  source_sha256: string;
  /** An array, not a single string: the source workbook has 2 sheets
   * (在宅（訪問診療）/外来). AreaIndicatorsSource has no source_sheet field
   * at all, so there is nothing to keep in sync here. */
  source_sheet: string[];
  acquired_date: string;
  license: string;
  original_title: string[];
  original_notes: string[];
  derived_via: Array<{ csv: string; meta: string }>;
}

export interface AreaDemandProcessing {
  script: string;
  inputs: Array<{ path: string; sha256: string }>;
  steps: string[];
  /** Object (not a string, unlike AreaIndicatorsProcessing.caveat): keeps the
   * caveats of the two source CSVs (demand_forecast/demand_population)
   * distinguishable. */
  caveat: { demand_forecast: string; demand_population: string };
}

export interface AreaDemandMetadata {
  title: string;
  source: AreaDemandSource;
  processing: AreaDemandProcessing;
  fields: Record<string, string>;
  /** Always present (possibly empty) — build_web_demand.py emits the key
   * unconditionally, so the demand 出典欄 needs no optional-chaining. */
  known_issues: KnownIssue[];
}

export interface AreaDemandData {
  metadata: AreaDemandMetadata;
  categories: DemandCategoryKey[];
  category_labels: Record<DemandCategoryKey, string>;
  /** Integers — unlike the keys of year_labels/AreaDemandArea.demand.<category>,
   * which are the string form of these same years (JSON object keys are always
   * strings; see CLAUDE.md/M4 brief). */
  years: number[];
  year_labels: Record<string, string>;
  baseline_year: number;
  areas: AreaDemandArea[];
}
