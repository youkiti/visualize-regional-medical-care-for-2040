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

// ---- Facility roster (area_facilities_R7.json / generated/facility_summary.json
// / public/facilities/<area_code>.json) --------------------------------------
//
// Mirrors data/processed/area_facilities_R7.json (tools/build_web_facilities.py)
// and its two derived artifacts (see CLAUDE.md "web/ のデータ構成" and the
// M5後半 Chunk A/C1 briefs). Deliberately NOT reusing AreaIndicators*/AreaDemand*
// above — this dataset's metadata shape diverges from both in its own way:
//   - it carries TWO source blocks, not one: `source` (facility_basic/
//     facility_observations/facility_functionsの由来、R7/001723127.xlsx) と
//     `geo_linkage_source`（P04名寄せの由来）。後者は source_file/source_sha256/
//     acquired_date/fiscal_year を持たない別のキー集合（代わりにinputsを持つ）
//   - `processing.caveat` は4キー（facility_basic/facility_observations/
//     facility_functions/facility_geo_linkage）のオブジェクト。AreaIndicators側は
//     単一文字列、AreaDemand側は2キーで、いずれとも形が違う
// (CLAUDE.md「可視化実装で判明した罠」11 — 表示用JSONを増やすとmetadataの形は
// 揃わない。Reactはオブジェクトをそのまま描画できないので、SourceNotesでは
// caveatの4本を個別に、source/geo_linkage_sourceを別々のJSXで描画する)

export type FacilityValueStatus = 'observed' | 'source_dash' | 'not_disclosed' | 'not_reported' | 'blank';

/** metrics配列の1要素。Facility.values/value_status とインデックスで対応する。 */
export interface FacilityMetric {
  key: string;
  metric: string;
  bed_function: string;
  label: string;
}

export type FacilityMatchStatus = 'matched' | 'candidate_only' | 'unmatched';

export interface Facility {
  record_id: string;
  facility_name: string;
  /** 未報告(value_status='not_reported')の医療機関は原典側で所在地欄も空欄のため空文字になる。 */
  municipality: string;
  /** 21要素。トップレベルmetricsと同じ順序・インデックス対応。value_status[i]==='observed' のときのみ数値、それ以外はnull。 */
  values: Array<number | null>;
  value_status: FacilityValueStatus[];
  /** 該当する機能が無い施設ではキー自体が省略される（0件を意味する空配列にはしない）。 */
  functions?: string[];
  /** 'matched'=座標あり / 'candidate_only'・'unmatched'=座標なし（位置の推測はしない、doc/REQUIREMENTS.md §4.3）。 */
  match_status: FacilityMatchStatus;
  /** [経度, 緯度]（度、JGD2011）。match_status==='matched' のときのみ存在する。 */
  coordinates?: [number, number];
}

/** web/public/facilities/<area_code>.json の形。区域選択時に個別取得する（バンドルしない）。 */
export interface FacilityShard {
  area_code: string;
  area_name: string;
  pref_code: string;
  pref_name: string;
  facility_count: number;
  geocoded_count: number;
  facilities: Facility[];
}

/** generated/facility_summary.json の areas[] 要素。facilities配列を含まない軽量な件数のみ。 */
export interface FacilitySummaryArea {
  area_code: string;
  facility_count: number;
  geocoded_count: number;
}

/** facility_basic/facility_observations/facility_functionsの3CSV共通の出典（R7/001723127.xlsx由来）。 */
export interface FacilitySource {
  name: string;
  publisher: string;
  url: string;
  page_url: string;
  fiscal_year: string;
  source_file: string;
  source_sha256: string;
  source_sheet: string;
  acquired_date: string;
  license: string;
  original_title: string;
  original_notes: string[];
  derived_via: Array<{ csv: string; meta: string }>;
}

/**
 * facility_geo_linkage.csv（P04名寄せ）由来の出典ブロック。FacilitySourceとは
 * キー集合が異なる別の形（source_file/source_sha256/fiscal_year/acquired_date
 * を持たない代わりにinputsを持つ）ため、型を使い回さない。
 */
export interface FacilityGeoLinkageSource {
  name: string;
  inputs: Array<{ file: string; role: string; source_sha256: string }>;
  license: string;
  page_url: string;
  derived_via: Array<{ csv: string; meta: string }>;
}

export interface FacilityProcessing {
  script: string;
  inputs: Array<{ path: string; sha256: string }>;
  steps: string[];
  /** 入力CSV4本ぶんのcaveatを持つオブジェクト（AreaIndicatorsProcessing.caveatの
   * 単一文字列ともAreaDemandProcessing.caveatの2キーとも形が違う）。 */
  caveat: {
    facility_basic: string;
    facility_observations: string;
    facility_functions: string;
    facility_geo_linkage: string;
  };
}

export interface FacilitySummaryMetadata {
  title: string;
  source: FacilitySource;
  geo_linkage_source: FacilityGeoLinkageSource;
  processing: FacilityProcessing;
  fields: Record<string, string>;
  known_issues: KnownIssue[];
}

export interface FacilitySummaryData {
  metadata: FacilitySummaryMetadata;
  /** 21指標の定義（表示順）。Facility.values/value_status とインデックスで対応する。 */
  metrics: FacilityMetric[];
  value_status_labels: Record<FacilityValueStatus, string>;
  /** facilities配列を含まない軽量な339区域ぶんの件数一覧。 */
  areas: FacilitySummaryArea[];
}

// ---- Bulk download manifest (generated/download_manifest.json) ------------
//
// Mirrors web/src/generated/download_manifest.json (written by
// web/scripts/sync-data.mjs, see its "8. download_manifest.json" comment for
// the exact construction). Deliberately NOT reusing any AreaIndicators*/
// AreaDemand*/FacilitySummary* type above — this JSON isn't a copy or a
// summary of a data/processed/*_R7.json source of truth like those are; it
// describes two independently-built build artifacts (the ZIP bundle under
// web/public/downloads/ and the standalone boundaries GeoJSON copy) plus the
// 13 CSVs packed into the ZIP, so its shape has nothing in common with the
// others (no `source`/`processing`/`known_issues` metadata block at all).

/** download_manifest.json の `bundle`: 加工済みCSV一括ダウンロードZIP本体の説明。 */
export interface DownloadManifestBundle {
  file: string;
  bytes: number;
  sha256: string;
  /** ZIP内の総エントリ数（CSV + 各.meta.json + README.md + MANIFEST.tsv）。 */
  entry_count: number;
  /** ZIP内のCSV本数（13）。entry_countとは別に持つ: UIの「CSV13本＋…」表記に使う。 */
  csv_count: number;
}

/** download_manifest.json の `boundaries`: 区域境界GeoJSON単体コピーの説明。ZIPには含まれない。 */
export interface DownloadManifestBoundaries {
  file: string;
  bytes: number;
  sha256: string;
}

/** download_manifest.json の `members[]`: ZIPに収録されたCSV1本ぶんの説明（.meta.jsonは含まない）。 */
export interface DownloadManifestMember {
  name: string;
  title: string;
  bytes: number;
  rows: number;
  sha256: string;
}

export interface DownloadManifest {
  bundle: DownloadManifestBundle;
  boundaries: DownloadManifestBoundaries;
  members: DownloadManifestMember[];
}

// ---- Prefecture overview layer (prefecture_indicators_R7.json /
// generated/prefecture_indicators.json / generated/pref_map.json) -----------
//
// Mirrors data/processed/prefecture_indicators_R7.json
// (tools/build_web_prefecture.py). Deliberately NOT reusing AreaIndicators*/
// AreaDemand* above — this dataset's metadata has yet another shape (CLAUDE.md
// 「可視化実装で判明した罠」11):
//   - TWO source blocks, `source_beds` (R7/001722915.xlsx由来) と
//     `source_demand` (R7/001728462.xlsx由来)。`source` という単一キーは無い
//   - `processing.caveat` は3キー（beds/demand_forecast/demand_population）。
//     AreaIndicators側は単一文字列、AreaDemand側は2キー、Facility側は4キーで、
//     どれとも違う
//   - 病床と需要が1つのオブジェクトに同居する（区域側は2ファイルに分かれている）
//
// 値の由来の差も型コメントとして残す: 病床は厚労省の都道府県別公表値そのもの、
// 需要と人口(population_2024/2040)は構想区域から本リポジトリが合計した派生値
// （known_issues の prefecture_demand_aggregated_by_this_repository）。

export interface PrefectureBeds {
  actual_2025: number;
  need_2025: number;
}

/** 1都道府県（または全国）ぶんの指標。national と prefectures[] で同じ形。 */
export interface PrefectureIndicator {
  /** ゼロ埋め2桁。全国は '00'（national のみ）。 */
  pref_code: string;
  pref_name: string;
  /** その都道府県に属する構想区域の数（全国は339）。 */
  area_count: number;
  population_2020: number;
  area_km2: number;
  /** 医療需要推計の基準人口。**構想区域の合計（派生値）**。 */
  population_2024: number;
  /** 2040年人口。**構想区域の合計（派生値）**。 */
  population_2040: number;
  /** 厚労省の都道府県別公表値そのもの（構想区域の合計と完全一致することを検証済み）。 */
  beds: Record<BedFunctionKey, PrefectureBeds>;
  /** category -> { year（文字列キー） -> レセプト件数/月 }。**構想区域の合計（派生値）**。 */
  demand: Record<DemandCategoryKey, Record<string, number>>;
}

/** 病床側（R7/001722915.xlsx由来）と需要側（R7/001728462.xlsx由来）で同じキー集合を持つ出典ブロック。 */
export interface PrefectureSource {
  name: string;
  publisher: string;
  url: string;
  page_url: string;
  fiscal_year: string;
  source_file: string;
  source_sha256: string;
  source_sheet: string;
  acquired_date: string;
  license: string;
  original_title: string;
  original_notes: string[];
  derived_via: Array<{ csv: string; meta: string }>;
}

export interface PrefectureProcessing {
  script: string;
  inputs: Array<{ path: string; sha256: string }>;
  steps: string[];
  /** 3キー。病床側2CSVは注記が同一なので beds 1本にまとめてある。 */
  caveat: { beds: string; demand_forecast: string; demand_population: string };
}

export interface PrefectureIndicatorsMetadata {
  title: string;
  /** `source` ではなく2ブロックに分かれている（上のコメント参照）。 */
  source_beds: PrefectureSource;
  source_demand: PrefectureSource;
  processing: PrefectureProcessing;
  fields: Record<string, string>;
  known_issues: KnownIssue[];
}

export interface PrefectureIndicatorsData {
  metadata: PrefectureIndicatorsMetadata;
  functions: BedFunctionKey[];
  function_labels: Record<BedFunctionKey, string>;
  categories: DemandCategoryKey[];
  category_labels: Record<DemandCategoryKey, string>;
  years: number[];
  year_labels: Record<string, string>;
  baseline_year: number;
  /** 全国（pref_code='00'）。境界を持たないため prefectures[] とは分けられている。 */
  national: PrefectureIndicator;
  /** 47都道府県（pref_codeの昇順）。全国は含まない。 */
  prefectures: PrefectureIndicator[];
}

/**
 * Flat properties of a single feature in generated/pref_map.json.
 * a_/n_/r_<機能> と需要のキーは area_map.json と同名（web/src/lib/metrics.ts の
 * readMetricValue/readDemandValue がどちらの層でもそのまま使える）。区域固有の
 * area_code/area_name は持たない。
 */
export interface PrefectureMapFeatureProperties {
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

/** 地図の表示単位。'area'=339構想区域（主表示）、'pref'=47都道府県（概観）。 */
export type MapLevel = 'pref' | 'area';
