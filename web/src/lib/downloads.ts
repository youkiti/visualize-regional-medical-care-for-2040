// 表示条件で絞り込んだCSVの「内容」を組み立てる純関数群（DOM非依存）。
// 実際にブラウザへダウンロードさせる副作用は triggerDownload.ts に分離してある
// （UIへの接続・ZIP一括配布は別チャンクで行う。ここでは純粋なデータ組み立て
// だけを実装する）。
//
// 値は画面と同じ関数（lib/metrics.ts の computeRatio 等）を通して算出し、
// ここで新しい計算規則は作らない。派生値（比・変化率）だけ小数第4位で丸める
// （原典由来の値＝病床数・レセプト件数/月・人口・面積は丸めずそのまま出す）。

import { computeRatio, demandCategoryOf, isDemandMetric } from './metrics';
import { toCsvText } from './csv';
import type { CsvValue } from './csv';
import type {
  AreaDemandArea,
  AreaDemandData,
  AreaDemandMetadata,
  AreaIndicator,
  AreaIndicatorsData,
  AreaIndicatorsMetadata,
  BedFunctionKey,
  BedMetricKind,
  DemandCategoryKey,
  DemandMetricKind,
  FacilityMetric,
  FacilityShard,
  FacilitySummaryMetadata,
  FacilityValueStatus,
  MetricKind,
} from '../types';

/** buildXxxCsv系が返す、ダウンロード対象そのもの（ファイル名 + 本文）。 */
export interface DownloadCsv {
  filename: string;
  text: string;
}

// 公表回。metadata側には機械可読な単独の「R7」キーが無く
// （source.fiscal_yearは「令和7年度（2025年度）」という人間可読の文字列で、
// パースは脆いので避ける）、ブリーフの「metadataから取れるならそちらを優先」
// を満たす専用フィールドが今のところ存在しないため固定値にしている。
const PUBLISHED_FY = 'R7';

const FOOTER_NOTE =
  "補足: 欠測は空欄（0とは異なる）。数値は桁区切りなし。派生値（比・変化率）は小数第4位で丸め。pandas は read_csv(path, comment='#') で読める";

const RATIO_UNAVAILABLE_NOTE = '必要数が0のため比は算出不可';

/** 派生値（比・変化率）を小数第4位で丸める。原典由来の値には使わない。 */
function round4(v: number): number {
  return Math.round(v * 1e4) / 1e4;
}

// ---- 由来ヘッダー（`#`行）の組み立て ---------------------------------------

/** buildPreambleが要求するsourceの最小形（AreaIndicators/AreaDemand/Facilityの各Sourceはこれを満たす）。 */
interface PreambleSource {
  name: string;
  publisher: string;
  fiscal_year: string;
  source_file: string;
  source_sha256: string;
  page_url: string;
  acquired_date: string;
  license: string;
}

interface PreambleOptions {
  source: PreambleSource;
  condition: string;
  caveat: string;
  /** 医療機関CSV用: 座標の出典（原典が2系統のため）。「掲載ページ」行の次に1行足す。 */
  extraSourceLine?: string;
  /** 追加の注記行（例:「注記（医療需要推計）: …」）。主注記の直後に足す。 */
  extraCaveatLines?: string[];
}

/** 全CSV共通の由来ヘッダー（`#`行の並び）を組み立てる。toCsvTextのpreambleへそのまま渡す。 */
function buildPreamble(opts: PreambleOptions): string[] {
  const { source, condition, caveat, extraSourceLine, extraCaveatLines = [] } = opts;
  const lines = [
    '2040年に向けた地域医療構想 可視化サイトからの出力',
    `データ名: ${source.name}`,
    `公表元: ${source.publisher} / 公表年度: ${source.fiscal_year}`,
    `原典ファイル: ${source.source_file}（SHA-256: ${source.source_sha256}）`,
    `掲載ページ: ${source.page_url}`,
    `取得日: ${source.acquired_date} / 利用規約: ${source.license}`,
  ];
  if (extraSourceLine) lines.push(extraSourceLine);
  lines.push(`出力条件: ${condition}`);
  lines.push(`注記: ${caveat}`);
  lines.push(...extraCaveatLines);
  lines.push(FOOTER_NOTE);
  return lines;
}

/** 区域識別列（全CSV共通の先頭5列: published_fy, area_code, area_name, pref_code, pref_name）。 */
function areaIdColumns(area: { area_code: string; area_name: string; pref_code: string; pref_name: string }): CsvValue[] {
  return [PUBLISHED_FY, area.area_code, area.area_name, area.pref_code, area.pref_name];
}

// ---- 2-1. buildAreaTableCsv: 全339区域 × 現在の指標（地図に出ている内容） --

const BED_METRIC_LABELS: Record<BedMetricKind, string> = {
  ratio: '過不足率',
  actual: '実績病床数',
  need: '必要数',
};

// 出力条件文字列の指標説明（例:「過不足率（2025年実績/2025年必要数）」）。
const BED_METRIC_DESCRIPTIONS: Record<BedMetricKind, string> = {
  ratio: '2025年実績/2025年必要数',
  actual: '2025年実績',
  need: '2025年必要数',
};

const DEMAND_METRIC_LABELS: Record<DemandMetricKind, string> = {
  demand_home_care: '在宅（訪問診療）',
  demand_outpatient: '外来',
};

export interface BuildAreaTableCsvArgs {
  indicators: AreaIndicatorsData;
  demand: AreaDemandData;
  metric: MetricKind;
  bedFunction: BedFunctionKey;
  year: number;
}

/**
 * 全339区域 × 現在選択中の指標（地図に出ている内容）を1CSVにする。
 * 病床指標（ratio/actual/need）のときは選択中の病床機能1つについて339行、
 * 需要指標（demand_home_care/demand_outpatient）のときは選択中の区分1つ・
 * 年度1つについて339行を出す（isDemandMetricで分岐）。
 */
export function buildAreaTableCsv(args: BuildAreaTableCsvArgs): DownloadCsv {
  const { indicators, demand, metric, bedFunction, year } = args;

  if (isDemandMetric(metric)) {
    return buildDemandAreaTableCsv(demand, metric, year);
  }
  return buildBedAreaTableCsv(indicators, metric, bedFunction);
}

function buildBedAreaTableCsv(indicators: AreaIndicatorsData, metric: BedMetricKind, bedFunction: BedFunctionKey): DownloadCsv {
  const bedFunctionLabel = indicators.function_labels[bedFunction];
  const header = [
    'published_fy',
    'area_code',
    'area_name',
    'pref_code',
    'pref_name',
    'bed_function',
    'actual_2025',
    'need_2025',
    'diff',
    'ratio',
    'note',
  ];
  const rows: CsvValue[][] = indicators.areas.map((area) => {
    const beds = area.beds[bedFunction];
    const ratio = computeRatio(beds.actual_2025, beds.need_2025);
    return [
      ...areaIdColumns(area),
      bedFunctionLabel,
      beds.actual_2025,
      beds.need_2025,
      beds.actual_2025 - beds.need_2025,
      ratio === null ? null : round4(ratio),
      ratio === null ? RATIO_UNAVAILABLE_NOTE : '',
    ];
  });

  const condition = `指標=${BED_METRIC_LABELS[metric]}（${BED_METRIC_DESCRIPTIONS[metric]}）, 病床機能=${bedFunctionLabel}, 対象=全${indicators.areas.length}構想区域`;
  const preamble = buildPreamble({
    source: indicators.metadata.source,
    condition,
    caveat: indicators.metadata.processing.caveat,
  });

  return {
    filename: `area_beds_${metric}_${bedFunction}_2025_R7.csv`,
    text: toCsvText(header, rows, { preamble }),
  };
}

function buildDemandAreaTableCsv(demand: AreaDemandData, metric: DemandMetricKind, year: number): DownloadCsv {
  const category = demandCategoryOf(metric);
  const categoryLabel = demand.category_labels[category];
  const header = [
    'published_fy',
    'area_code',
    'area_name',
    'pref_code',
    'pref_name',
    'demand_category',
    'year',
    'year_label',
    'receipts_per_month',
    'baseline_2024',
    'ratio_to_2024',
  ];
  const yearKey = String(year);
  const baselineKey = String(demand.baseline_year);
  const rows: CsvValue[][] = demand.areas.map((area) => {
    const value = area.demand[category][yearKey];
    const baseline = area.demand[category][baselineKey];
    return [...areaIdColumns(area), categoryLabel, year, demand.year_labels[yearKey], value, baseline, round4(value / baseline)];
  });

  const condition = `指標=${DEMAND_METRIC_LABELS[metric]}（レセプト件数/月・2024年度比）, 年度=${year}年度, 対象=全${demand.areas.length}構想区域`;
  const preamble = buildPreamble({
    source: demand.metadata.source,
    condition,
    caveat: demand.metadata.processing.caveat.demand_forecast,
  });

  return {
    filename: `area_demand_${category}_${year}_R7.csv`,
    text: toCsvText(header, rows, { preamble }),
  };
}

// ---- 2-2. buildAreaDetailCsv: 選択区域1つの指標（long形式） ----------------

const AREA_DETAIL_HEADER = [
  'published_fy',
  'area_code',
  'area_name',
  'pref_code',
  'pref_name',
  'dataset',
  'category',
  'series',
  'year',
  'value',
  'unit',
  'note',
];

// dataset=basic の各行は(function/demand categoryのような)複数値のグルーピング軸
// を持たないため、categoryは固定文字列にし、series側に具体的な項目名を持たせる
// （beds/demandのcategory×seriesという2軸構造と形をそろえるための設計判断）。
const BASIC_CATEGORY_LABEL = '基礎情報';

const BASELINE_POPULATION_NOTE =
  '基準人口の年は原典間で不一致（原典Excelの見出しは2024年度、公式説明書は2025年）。本サイトは原典Excelの値をそのまま出力している';

/** area.flow_rate_unavailable（原典の非数値センチネル、実データでは常に'XXX'）を注記文に埋め込む。 */
function flowRateNote(sourceValue: string | undefined): string {
  return `原典が'${sourceValue ?? 'XXX'}'（未算出）`;
}

export interface BuildAreaDetailCsvArgs {
  area: AreaIndicator;
  demandArea: AreaDemandArea | null;
  indicatorsMetadata: AreaIndicatorsMetadata;
  demandMetadata: AreaDemandMetadata;
  functions: BedFunctionKey[];
  functionLabels: Record<BedFunctionKey, string>;
  demandCategories: DemandCategoryKey[];
  demandCategoryLabels: Record<DemandCategoryKey, string>;
  demandYears: number[];
  demandYearLabels: Record<string, string>;
  baselineYear: number;
}

/**
 * 選択区域1つの指標をlong形式（1行=1事実）で出す。dataset=basic/beds/demandの
 * 3種の行を持つ。demandArea が null のときは、dataset=demand の行に加えて
 * dataset=basic のうち需要推計由来の2行（基準人口・2040年人口。いずれも
 * AreaDemandArea.population_* から取る値でAreaIndicatorには無い）も出さない。
 */
export function buildAreaDetailCsv(args: BuildAreaDetailCsvArgs): DownloadCsv {
  const {
    area,
    demandArea,
    indicatorsMetadata,
    demandMetadata,
    functions,
    functionLabels,
    demandCategories,
    demandCategoryLabels,
    demandYears,
    demandYearLabels,
    baselineYear,
  } = args;

  const idCols = areaIdColumns(area);
  const rows: CsvValue[][] = [];

  // dataset=basic
  rows.push([...idCols, 'basic', BASIC_CATEGORY_LABEL, '人口（2020年国勢調査）', 2020, area.population_2020, '人', '']);
  rows.push([...idCols, 'basic', BASIC_CATEGORY_LABEL, '面積', null, area.area_km2, 'km2', '']);
  // 推計流出/流入患者割合はyearを空欄にする: 原典（001723349.xlsx）も
  // area_basic.csv.meta.json のfields説明も対象年を一切書いていないため、
  // 勝手に年を補うと誤った基準年を主張することになる（CLAUDE.mdの
  // 「基準人口の年が公表物どうしで食い違っている罠」と同じ理由）。
  rows.push([
    ...idCols,
    'basic',
    BASIC_CATEGORY_LABEL,
    '推計流出患者割合',
    null,
    area.outflow_rate,
    '割合',
    area.outflow_rate === null ? flowRateNote(area.flow_rate_unavailable) : '',
  ]);
  rows.push([
    ...idCols,
    'basic',
    BASIC_CATEGORY_LABEL,
    '推計流入患者割合',
    null,
    area.inflow_rate,
    '割合',
    area.inflow_rate === null ? flowRateNote(area.flow_rate_unavailable) : '',
  ]);
  if (demandArea !== null) {
    rows.push([
      ...idCols,
      'basic',
      BASIC_CATEGORY_LABEL,
      '人口（医療需要推計の基準人口）',
      null,
      demandArea.population_2024,
      '人',
      BASELINE_POPULATION_NOTE,
    ]);
    rows.push([...idCols, 'basic', BASIC_CATEGORY_LABEL, '人口（2040年推計）', 2040, demandArea.population_2040, '人', '']);
  }

  // dataset=beds
  for (const fn of functions) {
    const label = functionLabels[fn];
    const beds = area.beds[fn];
    const ratio = computeRatio(beds.actual_2025, beds.need_2025);
    rows.push([...idCols, 'beds', label, '実績', 2025, beds.actual_2025, '床', '']);
    rows.push([...idCols, 'beds', label, '必要数', 2025, beds.need_2025, '床', '']);
    rows.push([...idCols, 'beds', label, '差（実績−必要数）', 2025, beds.actual_2025 - beds.need_2025, '床', '']);
    rows.push([
      ...idCols,
      'beds',
      label,
      '比（実績/必要数）',
      2025,
      ratio === null ? null : round4(ratio),
      '',
      ratio === null ? RATIO_UNAVAILABLE_NOTE : '',
    ]);
  }

  // dataset=demand
  if (demandArea !== null) {
    const baselineKey = String(baselineYear);
    for (const category of demandCategories) {
      const categoryLabel = demandCategoryLabels[category];
      const baseline = demandArea.demand[category][baselineKey];
      for (const year of demandYears) {
        const yearKey = String(year);
        const value = demandArea.demand[category][yearKey];
        const yearLabel = demandYearLabels[yearKey];
        rows.push([...idCols, 'demand', categoryLabel, 'レセプト件数/月', year, value, '件/月', yearLabel]);
        const ratioToBaseline = year === baselineYear ? 1 : round4(value / baseline);
        rows.push([...idCols, 'demand', categoryLabel, '2024年度比', year, ratioToBaseline, '', yearLabel]);
      }
    }
  }

  const condition = `対象=構想区域 ${area.area_code} ${area.area_name}（${area.pref_name}）`;
  // 需要側のcaveatはdemand_forecast/demand_populationの2キーだが、追加行は
  // ブリーフの指示どおり「1本」にするため、両方をこの1行にまとめて入れる
  // （このCSVはレセプト値・基準/2040年人口の両方を含むため、片方だけでは
  // 不十分と判断した）。
  const extraCaveatLines =
    demandArea !== null
      ? [`注記（医療需要推計）: ${demandMetadata.processing.caveat.demand_forecast} ${demandMetadata.processing.caveat.demand_population}`]
      : [];
  const preamble = buildPreamble({
    source: indicatorsMetadata.source,
    condition,
    caveat: indicatorsMetadata.processing.caveat,
    extraCaveatLines,
  });

  return {
    filename: `area_${area.area_code}_indicators_R7.csv`,
    text: toCsvText(AREA_DETAIL_HEADER, rows, { preamble }),
  };
}

// ---- 2-3. buildFacilityCsv: 選択区域の医療機関 × 21指標（long形式） --------

const FACILITY_HEADER = [
  'published_fy',
  'area_code',
  'area_name',
  'pref_code',
  'pref_name',
  'record_id',
  'facility_name',
  'municipality',
  'metric',
  'bed_function',
  'value',
  'value_status',
  'value_status_label',
  'functions',
  'match_status',
  'lon',
  'lat',
];

export interface BuildFacilityCsvArgs {
  shard: FacilityShard;
  metrics: FacilityMetric[];
  valueStatusLabels: Record<FacilityValueStatus, string>;
  facilitySummaryMetadata: FacilitySummaryMetadata;
}

/**
 * 選択区域の医療機関 × 21指標をlong形式（施設数×metrics.length行）で出す。
 * 座標を持たない施設（match_status!=='matched'）も行としては必ず出す
 * （位置の推測はしない、doc/REQUIREMENTS.md §4.3）。
 */
export function buildFacilityCsv(args: BuildFacilityCsvArgs): DownloadCsv {
  const { shard, metrics, valueStatusLabels, facilitySummaryMetadata } = args;
  const idCols = areaIdColumns(shard);

  const rows: CsvValue[][] = [];
  for (const facility of shard.facilities) {
    const functionsField = facility.functions ? facility.functions.join(';') : '';
    const lon = facility.coordinates ? facility.coordinates[0] : null;
    const lat = facility.coordinates ? facility.coordinates[1] : null;
    metrics.forEach((metric, i) => {
      const status = facility.value_status[i];
      const value = status === 'observed' ? facility.values[i] : null;
      rows.push([
        ...idCols,
        facility.record_id,
        facility.facility_name,
        facility.municipality,
        metric.metric,
        metric.bed_function,
        value,
        status,
        valueStatusLabels[status],
        functionsField,
        facility.match_status,
        lon,
        lat,
      ]);
    });
  }

  const condition = `対象=構想区域 ${shard.area_code} ${shard.area_name}（${shard.pref_name}）の医療機関 ${shard.facility_count}件 × ${metrics.length}指標`;
  const geoSource = facilitySummaryMetadata.geo_linkage_source;
  const extraSourceLine = `座標の出典: ${geoSource.name} / ${geoSource.page_url}`;
  const extraCaveatLines = [`注記（座標）: ${facilitySummaryMetadata.processing.caveat.facility_geo_linkage}`];
  const preamble = buildPreamble({
    source: facilitySummaryMetadata.source,
    condition,
    caveat: facilitySummaryMetadata.processing.caveat.facility_observations,
    extraSourceLine,
    extraCaveatLines,
  });

  return {
    filename: `area_${shard.area_code}_facilities_R7.csv`,
    text: toCsvText(FACILITY_HEADER, rows, { preamble }),
  };
}
