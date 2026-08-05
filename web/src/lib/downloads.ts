// 表示条件で絞り込んだCSVの「内容」を組み立てる純関数群（DOM非依存）。
// 実際にブラウザへダウンロードさせる副作用は triggerDownload.ts に分離してある
// （UIへの接続・ZIP一括配布は別チャンクで行う。ここでは純粋なデータ組み立て
// だけを実装する）。
//
// 値は画面と同じ関数（lib/metrics.ts の computeRatio 等）を通して算出し、
// ここで新しい計算規則は作らない。派生値（比・変化率）だけ小数第4位で丸める
// （原典由来の値＝病床数・レセプト件数/月・人口・面積は丸めずそのまま出す）。

import { computeRatio, demandCategoryOf, isDemandMetric, isYoyMetric } from './metrics';
import { toCsvText } from './csv';
import type { CsvValue } from './csv';
import type {
  AreaDemandArea,
  AreaDemandData,
  AreaDemandMetadata,
  AreaFlowEntry,
  AreaFlowMetadata,
  AreaIndicator,
  AreaIndicatorsData,
  AreaIndicatorsMetadata,
  AreaYoyArea,
  AreaYoyData,
  AreaYoyMetadata,
  BedFunctionKey,
  BedMetricKind,
  DemandCategoryKey,
  DemandMetricKind,
  FacilityMetric,
  FacilityShard,
  FacilitySummaryMetadata,
  FacilityValueStatus,
  FlowDirectionKey,
  FlowPhaseKey,
  MetricKind,
  PrefectureIndicator,
  PrefectureIndicatorsData,
  PrefectureIndicatorsMetadata,
  PrefectureYoyData,
  PrefectureYoyEntry,
  PrefectureYoyMetadata,
  YoyMetricKind,
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
  /** 医療機関CSV用: 座標の出典（原典が2系統のため）。「掲載ページ」行の次に足す。
   * M13以降、医療機関CSVは座標源自体が2系統（P04名寄せ+医療情報ネット）になったため
   * 配列も受け付ける（1行/系統ずつ）。単一文字列も引き続き使える（他CSVの1系統のみの用途）。 */
  extraSourceLine?: string | string[];
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
  if (extraSourceLine) {
    lines.push(...(Array.isArray(extraSourceLine) ? extraSourceLine : [extraSourceLine]));
  }
  lines.push(`出力条件: ${condition}`);
  lines.push(`注記: ${caveat}`);
  lines.push(...extraCaveatLines);
  lines.push(FOOTER_NOTE);
  return lines;
}

/**
 * 区域識別列（全CSV共通の先頭5列: published_fy, area_code, area_name, pref_code, pref_name）を
 * 任意のpublished_fy値で組み立てる。基礎情報・病床・医療需要推計の各データセットはすべて
 * R7単独公表分なので下のareaIdColumns()（固定でPUBLISHED_FY）を使うが、年度間比較
 * （dataset=yoy、buildAreaDetailCsv）は行ごとにR6/R7が混在するため、行ごとに正しい
 * published_fyを渡す必要がある。fyには空文字も渡せる（R6/R7両方の値から算出した
 * 派生の比の行のように、単一の公表回に帰属しない場合。'R6+R7'のような無い値は
 * 発明しない — CLAUDE.md 罠20）。
 */
function areaIdColumnsWithFy(
  area: { area_code: string; area_name: string; pref_code: string; pref_name: string },
  fy: string
): CsvValue[] {
  return [fy, area.area_code, area.area_name, area.pref_code, area.pref_name];
}

/** 区域識別列（全CSV共通の先頭5列: published_fy, area_code, area_name, pref_code, pref_name）。 */
function areaIdColumns(area: { area_code: string; area_name: string; pref_code: string; pref_name: string }): CsvValue[] {
  return areaIdColumnsWithFy(area, PUBLISHED_FY);
}

/**
 * 区域識別列（published_fyを含まない4列: area_code, area_name, pref_code, pref_name）。
 * buildYoyAreaTableCsv専用: この横持ちCSVは値そのものが列ごとにR6/R7混在
 * （plan_2025_r6/actual_2025_r7/…）で単一のpublished_fy列に収まらないため、
 * 列名の接尾辞（_r6/_r7）で由来を示し、published_fy列自体を持たない（修正1a）。
 */
function areaIdColumnsNoFy(area: {
  area_code: string;
  area_name: string;
  pref_code: string;
  pref_name: string;
}): CsvValue[] {
  return [area.area_code, area.area_name, area.pref_code, area.pref_name];
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

const YOY_METRIC_LABELS: Record<YoyMetricKind, string> = {
  yoy_plan_vs_actual: '見込量比（2025年）',
  yoy_actual_change: '実績の1年変化（2024→2025）',
};

// 出力条件文字列の指標説明（例:「2025年実績（R7公表）/2025年見込量（R6公表）」）。
const YOY_METRIC_DESCRIPTIONS: Record<YoyMetricKind, string> = {
  yoy_plan_vs_actual: '2025年実績（R7公表）/2025年見込量（R6公表）',
  yoy_actual_change: '2025年実績（R7公表）/2024年実績（R6公表）',
};

const YOY_RATIO_UNAVAILABLE_NOTE: Record<YoyMetricKind, string> = {
  yoy_plan_vs_actual: '見込量2025が0のため比は算出不可',
  yoy_actual_change: '実績2024が0のため比は算出不可',
};

/**
 * buildAreaDetailCsv の dataset=yoy 派生比行（比・変化率）で published_fy を
 * 空欄にする理由をnote列に書くための文言。この2行はR6公表分（見込量2025/実績2024）
 * とR7公表分（実績2025）の両方から算出した値で、単一の公表回に帰属しないため
 * published_fyを空欄にしている（'R6+R7'のような無い値は発明しない。CLAUDE.md
 * 罠20「公表物が言っていない年を出力に足さない」と同じ規律）。
 */
const YOY_RATIO_FY_NOTE: Record<YoyMetricKind, string> = {
  yoy_plan_vs_actual: '実績2025(R7公表)÷見込量2025(R6公表)のため単一の公表年度に帰属しない',
  yoy_actual_change: '実績2025(R7公表)÷実績2024(R6公表)のため単一の公表年度に帰属しない',
};

export interface BuildAreaTableCsvArgs {
  indicators: AreaIndicatorsData;
  demand: AreaDemandData;
  yoy: AreaYoyData;
  metric: MetricKind;
  bedFunction: BedFunctionKey;
  year: number;
}

/**
 * 全339区域 × 現在選択中の指標（地図に出ている内容）を1CSVにする。
 * 病床指標（ratio/actual/need）のときは選択中の病床機能1つについて339行、
 * 需要指標（demand_home_care/demand_outpatient）のときは選択中の区分1つ・
 * 年度1つについて339行、年度間比較指標（yoy_plan_vs_actual/yoy_actual_change）
 * のときは選択中の病床機能1つについて339行を出す（isDemandMetric/isYoyMetricで分岐）。
 */
export function buildAreaTableCsv(args: BuildAreaTableCsvArgs): DownloadCsv {
  const { indicators, demand, yoy, metric, bedFunction, year } = args;

  if (isYoyMetric(metric)) {
    return buildYoyAreaTableCsv(yoy, metric, bedFunction);
  }
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

/** metadata.source（R7/R6の2要素配列）から指定published_fyの出典ブロックを取り出す。 */
function findYoySource(yoyMetadata: AreaYoyMetadata, publishedFy: 'R7' | 'R6') {
  return yoyMetadata.source.find((s) => s.published_fy === publishedFy);
}

/** area_yoy_R6_R7.json の known_issues から「2024年実績はR6公表分を採用した」の1件を取り出す。 */
function findYoyActualFromR6Issue(yoyMetadata: AreaYoyMetadata) {
  return yoyMetadata.known_issues.find((issue) => issue.id === 'area_yoy_2024_actual_from_r6') ?? null;
}

// published_fyは持たない（値は1つの公表回に帰属しない: plan_2025はR6、actual_2025
// はR7、actual_2024/report_rate_2024はR6、report_rate_2025はR7、ratioはR6/R7両方から
// 算出。'R6+R7'のような発明した値でpublished_fy列を埋めない代わりに、列名自体に
// 由来を持たせる。data/processed/area_yoy_diff.csv が既に採っている
// plan_2025_r6/actual_2025_r7/actual_2024_r6 の命名に、report_rate_2024_r6/
// report_rate_2025_r7を揃えて追加した形）。
function buildYoyAreaTableCsv(yoy: AreaYoyData, metric: YoyMetricKind, bedFunction: BedFunctionKey): DownloadCsv {
  const bedFunctionLabel = yoy.function_labels[bedFunction];
  const header = [
    'area_code',
    'area_name',
    'pref_code',
    'pref_name',
    'bed_function',
    'plan_2025_r6',
    'actual_2025_r7',
    'actual_2024_r6',
    'report_rate_2024_r6',
    'report_rate_2025_r7',
    'ratio',
    'note',
  ];
  const rows: CsvValue[][] = yoy.areas.map((area) => {
    const beds = area.beds[bedFunction];
    const denominator = metric === 'yoy_plan_vs_actual' ? beds.plan_2025 : beds.actual_2024;
    const ratio = computeRatio(beds.actual_2025, denominator);
    return [
      ...areaIdColumnsNoFy(area),
      bedFunctionLabel,
      beds.plan_2025,
      beds.actual_2025,
      beds.actual_2024,
      area.report_rate_2024,
      area.report_rate_2025,
      ratio === null ? null : round4(ratio),
      ratio === null ? YOY_RATIO_UNAVAILABLE_NOTE[metric] : '',
    ];
  });

  const condition = `指標=${YOY_METRIC_LABELS[metric]}（${YOY_METRIC_DESCRIPTIONS[metric]}）, 病床機能=${bedFunctionLabel}, 対象=全${yoy.areas.length}構想区域`;
  const r6Source = findYoySource(yoy.metadata, 'R6');
  const extraSourceLine = r6Source
    ? `R6公表分の原典ファイル: ${r6Source.source_file}（SHA-256: ${r6Source.source_sha256}） / 取得日: ${r6Source.acquired_date}`
    : undefined;
  const yoyIssue = findYoyActualFromR6Issue(yoy.metadata);
  const preamble = buildPreamble({
    source: findYoySource(yoy.metadata, 'R7') ?? yoy.metadata.source[0],
    condition,
    caveat: yoy.metadata.processing.caveat,
    extraSourceLine,
    extraCaveatLines: yoyIssue ? [`注記（2024年実績の採用について）: ${yoyIssue.summary}／${yoyIssue.action}`] : [],
  });

  return {
    filename: `area_yoy_${metric}_${bedFunction}_R6_R7.csv`,
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
  /** area_yoy.json から引いた当該区域の年度間比較データ。339区域全件に存在するはずだが
   * （sync-data.mjsが突合検証済み）、型上は見つからない場合に備える。 */
  yoyArea: AreaYoyArea | null;
  indicatorsMetadata: AreaIndicatorsMetadata;
  demandMetadata: AreaDemandMetadata;
  yoyMetadata: AreaYoyMetadata;
  functions: BedFunctionKey[];
  functionLabels: Record<BedFunctionKey, string>;
  demandCategories: DemandCategoryKey[];
  demandCategoryLabels: Record<DemandCategoryKey, string>;
  demandYears: number[];
  demandYearLabels: Record<string, string>;
  baselineYear: number;
}

/**
 * 選択区域1つの指標をlong形式（1行=1事実）で出す。dataset=basic/beds/demand/yoyの
 * 4種の行を持つ。demandArea が null のときは、dataset=demand の行に加えて
 * dataset=basic のうち需要推計由来の2行（基準人口・2040年人口。いずれも
 * AreaDemandArea.population_* から取る値でAreaIndicatorには無い）も出さない。
 * yoyArea が null のときは dataset=yoy の行を出さない。
 */
export function buildAreaDetailCsv(args: BuildAreaDetailCsvArgs): DownloadCsv {
  const {
    area,
    demandArea,
    yoyArea,
    indicatorsMetadata,
    demandMetadata,
    yoyMetadata,
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

  // dataset=yoy（年度間比較 R6→R7）。行ごとにpublished_fyが変わる
  // （見込量2025・実績2024・報告率2024はR6公表、実績2025・報告率2025はR7公表）ので、
  // idColsではなくareaIdColumnsWithFy(area, <その行のfy>)を都度使う。比・変化率の
  // 2行はR6/R7両方から算出した値で単一の公表回に帰属しないため、'R6+R7'のような
  // 無い値を発明する代わりにpublished_fyを空欄にし、理由をnote列(YOY_RATIO_FY_NOTE)
  // に書く（修正1b）。
  if (yoyArea !== null) {
    const yoyReportRateLabel = '病床機能報告の報告率';
    rows.push([
      ...areaIdColumnsWithFy(area, 'R6'),
      'yoy',
      yoyReportRateLabel,
      '報告率2024（R6公表）',
      2024,
      yoyArea.report_rate_2024,
      '割合',
      '',
    ]);
    rows.push([
      ...areaIdColumnsWithFy(area, 'R7'),
      'yoy',
      yoyReportRateLabel,
      '報告率2025（R7公表）',
      2025,
      yoyArea.report_rate_2025,
      '割合',
      '',
    ]);

    for (const fn of functions) {
      const label = functionLabels[fn];
      const beds = yoyArea.beds[fn];
      rows.push([...areaIdColumnsWithFy(area, 'R6'), 'yoy', label, '見込量2025（R6公表）', 2025, beds.plan_2025, '床', '']);
      rows.push([...areaIdColumnsWithFy(area, 'R7'), 'yoy', label, '実績2025（R7公表）', 2025, beds.actual_2025, '床', '']);
      rows.push([...areaIdColumnsWithFy(area, 'R6'), 'yoy', label, '実績2024（R6公表）', 2024, beds.actual_2024, '床', '']);

      const planRatio = computeRatio(beds.actual_2025, beds.plan_2025);
      rows.push([
        ...areaIdColumnsWithFy(area, ''),
        'yoy',
        label,
        '比（実績2025/見込量2025）',
        null,
        planRatio === null ? null : round4(planRatio),
        '',
        planRatio === null
          ? `${YOY_RATIO_FY_NOTE.yoy_plan_vs_actual}／${YOY_RATIO_UNAVAILABLE_NOTE.yoy_plan_vs_actual}`
          : YOY_RATIO_FY_NOTE.yoy_plan_vs_actual,
      ]);

      const changeRatio = computeRatio(beds.actual_2025, beds.actual_2024);
      rows.push([
        ...areaIdColumnsWithFy(area, ''),
        'yoy',
        label,
        '変化率（実績2025/実績2024）',
        null,
        changeRatio === null ? null : round4(changeRatio),
        '',
        changeRatio === null
          ? `${YOY_RATIO_FY_NOTE.yoy_actual_change}／${YOY_RATIO_UNAVAILABLE_NOTE.yoy_actual_change}`
          : YOY_RATIO_FY_NOTE.yoy_actual_change,
      ]);
    }
  }

  const condition = `対象=構想区域 ${area.area_code} ${area.area_name}（${area.pref_name}）`;
  // 需要側のcaveatはdemand_forecast/demand_populationの2キーだが、追加行は
  // ブリーフの指示どおり「1本」にするため、両方をこの1行にまとめて入れる
  // （このCSVはレセプト値・基準/2040年人口の両方を含むため、片方だけでは
  // 不十分と判断した）。年度間比較(yoy)も同様に、caveatと「2024年実績はR6公表分を
  // 採用した」known_issueをそれぞれ1行にまとめて入れる（ハードコードせず
  // area_yoy_R6_R7.jsonから取る。CLAUDE.md「原典側の欠陥の記録先」参照）。
  const extraCaveatLines = [
    ...(demandArea !== null
      ? [`注記（医療需要推計）: ${demandMetadata.processing.caveat.demand_forecast} ${demandMetadata.processing.caveat.demand_population}`]
      : []),
    ...(yoyArea !== null
      ? [
          `注記（年度間比較）: ${yoyMetadata.processing.caveat}`,
          ...(() => {
            const yoyIssue = findYoyActualFromR6Issue(yoyMetadata);
            return yoyIssue ? [`注記（2024年実績の採用について）: ${yoyIssue.summary}／${yoyIssue.action}`] : [];
          })(),
        ]
      : []),
  ];
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
  'coordinate_source',
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
 * 座標を持たない施設（coordinatesキーが無い施設。座標の有無はmatch_statusでは
 * 判定しない — CLAUDE.md「可視化実装で判明した罠」36）も行としては必ず出す
 * （位置の推測はしない、doc/REQUIREMENTS.md §4.3）。coordinate_source列は座標を
 * 持つ行のみ'ksj_p04'/'iryojoho'が入り、持たない行は空欄（M13）。
 */
export function buildFacilityCsv(args: BuildFacilityCsvArgs): DownloadCsv {
  const { shard, metrics, valueStatusLabels, facilitySummaryMetadata } = args;
  const idCols = areaIdColumns(shard);

  const rows: CsvValue[][] = [];
  for (const facility of shard.facilities) {
    const functionsField = facility.functions ? facility.functions.join(';') : '';
    const lon = facility.coordinates ? facility.coordinates[0] : null;
    const lat = facility.coordinates ? facility.coordinates[1] : null;
    const coordinateSource = facility.coordinate_source ?? '';
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
        coordinateSource,
        lon,
        lat,
      ]);
    });
  }

  const condition = `対象=構想区域 ${shard.area_code} ${shard.area_name}（${shard.pref_name}）の医療機関 ${shard.facility_count}件 × ${metrics.length}指標`;
  const geoSource = facilitySummaryMetadata.geo_linkage_source;
  const geoAuditSource = facilitySummaryMetadata.geo_audit_source;
  // 座標源は2系統（M13）。P04名寄せ（既定）に加え、それで座標が得られなかった
  // 施設を補完した医療情報ネット由来ぶんの出典行を追加する。
  const extraSourceLine = [
    `座標の出典（国土数値情報P04との名寄せ）: ${geoSource.name} / ${geoSource.page_url}`,
    `座標の出典（医療情報ネット、P04名寄せで座標が得られなかった施設のみ）: ${geoAuditSource.name} / ` +
      `${geoAuditSource.page_url}（参照時点: ${geoAuditSource.reference_snapshot_date}）`,
  ];
  const extraCaveatLines = [
    `注記（座標・P04名寄せ）: ${facilitySummaryMetadata.processing.caveat.facility_geo_linkage}`,
    `注記（座標源の採用方針）: ${facilitySummaryMetadata.processing.caveat.coordinate_adoption}`,
  ];
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

// ---- 2-4. buildAreaFlowCsv: 選択区域1つ・方向1つ・区分1つの流入出内訳 -------

const FLOW_HEADER = [
  'area_code',
  'area_name',
  'direction',
  'phase',
  'rank',
  'partner_area_code',
  'partner_pref_name',
  'partner_area_name',
  'rate',
];

const FLOW_TRUNCATION_CAVEAT =
  '原典は一定数以上の患者がいる区域のみ表示するため、rateの合計は1になりません（表示されていない分は算出できません）';
const FLOW_OVERALL_CAVEAT_LINE = '注記（全体値について）: 全体の流入率・流出率は3区分の合計ではありません';

export interface BuildAreaFlowCsvArgs {
  area: AreaIndicator;
  flowEntry: AreaFlowEntry;
  direction: FlowDirectionKey;
  phase: FlowPhaseKey;
  directionLabels: Record<FlowDirectionKey, string>;
  phaseLabels: Record<FlowPhaseKey, string>;
  flowMetadata: AreaFlowMetadata;
  /** 相手区域の名前・都道府県名を引くための一覧（area_indicators.json由来）。 */
  areas: AreaIndicator[];
}

/**
 * 選択区域1つ・方向1つ・区分1つの流入出内訳を、原典の並び（率の降順）を復元した
 * 形で出す。self_rank!==null のときは、長さ partners.length+1 の配列を作り、
 * self_rank-1 の位置へ自区域の行を挿し込み、残りの位置へ partners（自区域を
 * 除いた原典順）を順に詰める。self_rank===null のときは partners をそのまま
 * 1..N とする（AreaFlowEntry.partners は既に自区域を除く率降順で保持されている
 * ため、詰め直すだけで原典の行位置が正確に再現できる — types.tsのFlowPartner
 * のコメント参照）。
 */
export function buildAreaFlowCsv(args: BuildAreaFlowCsvArgs): DownloadCsv {
  const { area, flowEntry, direction, phase, directionLabels, phaseLabels, flowMetadata, areas } = args;
  const areaByCode = new Map(areas.map((a) => [a.area_code, a]));
  const group = flowEntry.flows[direction].phases[phase];
  const { self_rate, self_rank, partners } = group;

  const hasSelfRow = self_rank !== null && self_rate !== null;
  const total = partners.length + (hasSelfRow ? 1 : 0);
  const slots: Array<{ code: string; rate: number } | null> = new Array(total).fill(null);
  if (hasSelfRow) {
    slots[self_rank - 1] = { code: area.area_code, rate: self_rate };
  }
  let partnerIdx = 0;
  for (let i = 0; i < total; i++) {
    if (slots[i] !== null) continue;
    const partner = partners[partnerIdx++];
    slots[i] = { code: partner[0], rate: partner[1] };
  }

  const rows: CsvValue[][] = slots.map((slot, i) => {
    if (!slot) {
      throw new Error(`buildAreaFlowCsv: slot ${i} unfilled (self_rank/partners inconsistent with group data)`);
    }
    const partnerArea = areaByCode.get(slot.code);
    return [
      area.area_code,
      area.area_name,
      direction,
      phase,
      i + 1,
      slot.code,
      partnerArea?.pref_name ?? '',
      partnerArea?.area_name ?? '',
      slot.rate,
    ];
  });

  const condition = `対象=構想区域 ${area.area_code} ${area.area_name}（${area.pref_name}）, 方向=${directionLabels[direction]}（${direction}）, 区分=${phaseLabels[phase]}（${phase}）`;
  const preamble = buildPreamble({
    source: flowMetadata.source,
    condition,
    caveat: FLOW_TRUNCATION_CAVEAT,
    extraCaveatLines: [FLOW_OVERALL_CAVEAT_LINE],
  });

  return {
    filename: `area_flow_${area.area_code}_${direction}_${phase}_R7.csv`,
    text: toCsvText(FLOW_HEADER, rows, { preamble }),
  };
}

// ---- 2-5/2-6. 都道府県層（概観レイヤ）のCSV ---------------------------------
//
// 上の 2-1（buildAreaTableCsv）・2-2（buildAreaDetailCsv）の都道府県版。区域側の
// 関数を level で分岐させるのではなく別関数にしてあるのは、データセットの形が
// そもそも違うため（prefecture_indicators_R7.json は病床と需要が1つのオブジェクトに
// 同居し、metadataは `source` ではなく source_beds / source_demand の2ブロック。
// CLAUDE.md「可視化実装で判明した罠」11）。
//
// published_fy は PUBLISHED_FY（'R7'）固定でよい。都道府県層のデータセットは
// 病床・需要ともR7単独公表分で、区域側の年度間比較（buildYoyAreaTableCsv）のように
// 行ごとにR6/R7が混ざることがない。

/**
 * 全国（pref_code='00'）を行に含めない理由。出力条件行に必ず入れる。
 * 47都道府県と同じ列に並べると、利用者が actual_2025 等を合計したときに
 * 二重計上になる（画面のパネルは「（参考）」と畳んで区別しているが、CSVには
 * 畳む仕組みが無い）。
 */
const NATIONAL_EXCLUDED_NOTE = '全国（pref_code=00）は含まない。47都道府県と合計すると二重計上になるため';

/**
 * 都道府県の需要・基準人口が派生値であることを、行の真横（note列）でも言うための文言。
 * preambleのknown_issue引用（prefectureDerivedCaveatLines）と重複するが、
 * CLAUDE.md 罠25「派生であることは値の真横にも注記を置く」に従う。CSVでの"真横"は列。
 */
const PREF_DERIVED_NOTE = '構想区域の値を本サイトが合計した派生値（厚生労働省の都道府県別公表値ではない）';

/**
 * 都道府県層の年度間比較で、2024年実績の由来について添える注記。
 * 区域側は「R7公表分が使えないのでR6公表分を採用した」という判断
 * （known_issue: area_yoy_2024_actual_from_r6）を書くが、都道府県層では両者が
 * 全キー一致する（tools/build_web_prefecture_yoy.py 検証9）ので判断自体が無い。
 * 同じ列名 actual_2024_r6 を見た利用者が区域側と同じ判断があったと誤解しないよう、
 * 一致している事実の方を書く。
 */
const PREF_YOY_2024_IDENTICAL_NOTE =
  '注記（2024年実績について）: 都道府県ではR6公表分とR7公表分の2024年実績が全て一致するため、どちらの公表回から採っても同じ値です（構想区域ではR7公表分に既知の欠陥があり、R6公表分を採用しています）';

/** 都道府県識別列（全CSV共通の先頭4列: published_fy, pref_code, pref_name, area_count）。 */
function prefIdColumns(pref: PrefectureIndicator): CsvValue[] {
  return [PUBLISHED_FY, pref.pref_code, pref.pref_name, pref.area_count];
}

/**
 * prefecture_indicators_R7.json の known_issues から「医療需要推計と基準人口は
 * 本リポジトリが構想区域から合計した派生値」の1件を取り出し、preamble の注記行
 * 1本に畳む。文言はハードコードせず metadata から引く
 * （CLAUDE.md「原典側の欠陥の記録先」。区域側の findYoyActualFromR6Issue と同じ作り）。
 */
function prefectureDerivedCaveatLines(metadata: PrefectureIndicatorsMetadata): string[] {
  const issue = metadata.known_issues.find((i) => i.id === 'prefecture_demand_aggregated_by_this_repository');
  return issue ? [`注記（医療需要・基準人口が派生値であること）: ${issue.summary}／${issue.action}`] : [];
}

// ---- 2-5. buildPrefectureTableCsv: 全47都道府県 × 現在の指標 ---------------

export interface BuildPrefectureTableCsvArgs {
  prefectures: PrefectureIndicatorsData;
  prefectureYoy: PrefectureYoyData;
  metric: MetricKind;
  bedFunction: BedFunctionKey;
  year: number;
}

/**
 * 全47都道府県 × 現在選択中の指標（都道府県表示中の地図に出ている内容）を1CSVにする。
 * 全国（pref_code='00'）は含まない（NATIONAL_EXCLUDED_NOTE 参照）。
 * 病床・需要・年度間比較の3系統に分岐する（区域側の buildAreaTableCsv と同じ構成）。
 */
export function buildPrefectureTableCsv(args: BuildPrefectureTableCsvArgs): DownloadCsv {
  const { prefectures, prefectureYoy, metric, bedFunction, year } = args;

  if (isYoyMetric(metric)) {
    return buildYoyPrefectureTableCsv(prefectureYoy, metric, bedFunction);
  }
  if (isDemandMetric(metric)) {
    return buildDemandPrefectureTableCsv(prefectures, metric, year);
  }
  return buildBedPrefectureTableCsv(prefectures, metric, bedFunction);
}

function buildBedPrefectureTableCsv(
  data: PrefectureIndicatorsData,
  metric: BedMetricKind,
  bedFunction: BedFunctionKey
): DownloadCsv {
  const bedFunctionLabel = data.function_labels[bedFunction];
  const header = [
    'published_fy',
    'pref_code',
    'pref_name',
    'area_count',
    'bed_function',
    'actual_2025',
    'need_2025',
    'diff',
    'ratio',
    'note',
  ];
  const rows: CsvValue[][] = data.prefectures.map((pref) => {
    const beds = pref.beds[bedFunction];
    const ratio = computeRatio(beds.actual_2025, beds.need_2025);
    return [
      ...prefIdColumns(pref),
      bedFunctionLabel,
      beds.actual_2025,
      beds.need_2025,
      beds.actual_2025 - beds.need_2025,
      ratio === null ? null : round4(ratio),
      ratio === null ? RATIO_UNAVAILABLE_NOTE : '',
    ];
  });

  const condition = `指標=${BED_METRIC_LABELS[metric]}（${BED_METRIC_DESCRIPTIONS[metric]}）, 病床機能=${bedFunctionLabel}, 対象=全${data.prefectures.length}都道府県（${NATIONAL_EXCLUDED_NOTE}）`;
  // 病床は厚生労働省の都道府県別公表値そのものなので source_beds だけでよい
  // （需要側の出典・派生値の注記は足さない。このCSVは需要の列を持たない）。
  const preamble = buildPreamble({
    source: data.metadata.source_beds,
    condition,
    caveat: data.metadata.processing.caveat.beds,
  });

  return {
    filename: `prefecture_beds_${metric}_${bedFunction}_2025_R7.csv`,
    text: toCsvText(header, rows, { preamble }),
  };
}

function buildDemandPrefectureTableCsv(
  data: PrefectureIndicatorsData,
  metric: DemandMetricKind,
  year: number
): DownloadCsv {
  const category = demandCategoryOf(metric);
  const categoryLabel = data.category_labels[category];
  const header = [
    'published_fy',
    'pref_code',
    'pref_name',
    'area_count',
    'demand_category',
    'year',
    'year_label',
    'receipts_per_month',
    'baseline_2024',
    'ratio_to_2024',
    'note',
  ];
  const yearKey = String(year);
  const baselineKey = String(data.baseline_year);
  const rows: CsvValue[][] = data.prefectures.map((pref) => {
    const value = pref.demand[category][yearKey];
    const baseline = pref.demand[category][baselineKey];
    return [
      ...prefIdColumns(pref),
      categoryLabel,
      year,
      data.year_labels[yearKey],
      value,
      baseline,
      round4(value / baseline),
      PREF_DERIVED_NOTE,
    ];
  });

  const condition = `指標=${DEMAND_METRIC_LABELS[metric]}（レセプト件数/月・2024年度比）, 年度=${year}年度, 対象=全${data.prefectures.length}都道府県（${NATIONAL_EXCLUDED_NOTE}）`;
  const preamble = buildPreamble({
    source: data.metadata.source_demand,
    condition,
    caveat: data.metadata.processing.caveat.demand_forecast,
    extraCaveatLines: prefectureDerivedCaveatLines(data.metadata),
  });

  return {
    filename: `prefecture_demand_${category}_${year}_R7.csv`,
    text: toCsvText(header, rows, { preamble }),
  };
}

/**
 * 都道府県層の年度間比較（R6→R7）。列構成は区域版 buildYoyAreaTableCsv と同じ規律で、
 * published_fy列を持たず列名の接尾辞（_r6/_r7）で由来を示す（値が列ごとにR6/R7混在する
 * ため。CLAUDE.md 罠33）。
 *
 * 区域版との違いは注記2点:
 *   - 実績2024はR6公表分だが、都道府県ではR7公表分と全キー一致する（ビルド時の検証9）
 *   - 分母0が無いので「算出不可」の行は出ない
 */
function buildYoyPrefectureTableCsv(
  data: PrefectureYoyData,
  metric: YoyMetricKind,
  bedFunction: BedFunctionKey
): DownloadCsv {
  const bedFunctionLabel = data.function_labels[bedFunction];
  const header = [
    'pref_code',
    'pref_name',
    'bed_function',
    'plan_2025_r6',
    'actual_2025_r7',
    'actual_2024_r6',
    'report_rate_2024_r6',
    'report_rate_2025_r7',
    'ratio',
    'note',
  ];
  const rows: CsvValue[][] = data.prefectures.map((pref) => {
    const beds = pref.beds[bedFunction];
    const denominator = metric === 'yoy_plan_vs_actual' ? beds.plan_2025 : beds.actual_2024;
    const ratio = computeRatio(beds.actual_2025, denominator);
    return [
      pref.pref_code,
      pref.pref_name,
      bedFunctionLabel,
      beds.plan_2025,
      beds.actual_2025,
      beds.actual_2024,
      pref.report_rate_2024,
      pref.report_rate_2025,
      ratio === null ? null : round4(ratio),
      ratio === null ? YOY_RATIO_UNAVAILABLE_NOTE[metric] : '',
    ];
  });

  const condition = `指標=${YOY_METRIC_LABELS[metric]}（${YOY_METRIC_DESCRIPTIONS[metric]}）, 病床機能=${bedFunctionLabel}, 対象=全${data.prefectures.length}都道府県（${NATIONAL_EXCLUDED_NOTE}）`;
  const r6Source = data.metadata.source.find((s) => s.published_fy === 'R6');
  const extraSourceLine = r6Source
    ? `R6公表分の原典ファイル: ${r6Source.source_file}（SHA-256: ${r6Source.source_sha256}） / 取得日: ${r6Source.acquired_date}`
    : undefined;
  const preamble = buildPreamble({
    source: data.metadata.source.find((s) => s.published_fy === 'R7') ?? data.metadata.source[0],
    condition,
    caveat: data.metadata.processing.caveat,
    extraSourceLine,
    extraCaveatLines: [PREF_YOY_2024_IDENTICAL_NOTE],
  });

  return {
    filename: `prefecture_yoy_${metric}_${bedFunction}_R6_R7.csv`,
    text: toCsvText(header, rows, { preamble }),
  };
}

// ---- 2-6. buildPrefectureDetailCsv: 選択都道府県1つの指標（long形式） -------

const PREFECTURE_DETAIL_HEADER = [
  'published_fy',
  'pref_code',
  'pref_name',
  'area_count',
  'dataset',
  'category',
  'series',
  'year',
  'value',
  'unit',
  'note',
];

export interface BuildPrefectureDetailCsvArgs {
  prefecture: PrefectureIndicator;
  metadata: PrefectureIndicatorsMetadata;
  /** prefecture_yoy.json から引いた当該県の年度間比較。無ければ dataset=yoy の行を出さない。 */
  yoyEntry: PrefectureYoyEntry | null;
  yoyMetadata: PrefectureYoyMetadata;
  functions: BedFunctionKey[];
  functionLabels: Record<BedFunctionKey, string>;
  demandCategories: DemandCategoryKey[];
  demandCategoryLabels: Record<DemandCategoryKey, string>;
  demandYears: number[];
  demandYearLabels: Record<string, string>;
  baselineYear: number;
}

/**
 * 選択中の都道府県1つの指標をlong形式（1行=1事実）で出す。dataset=basic/beds/demand の
 * 3種の行を持つ（区域側 buildAreaDetailCsv の yoy 相当は都道府県層に無い）。
 * 全国（pref_code='00'）の行は含まない — 対象は選択中の1都道府県のみ。
 *
 * 値の由来が行によって違う（病床・2020年人口・面積は厚生労働省の都道府県別公表値、
 * 需要と基準人口/2040年人口は構想区域からの合計）ため、派生の行だけ note 列に
 * PREF_DERIVED_NOTE を入れて区別する。
 */
export function buildPrefectureDetailCsv(args: BuildPrefectureDetailCsvArgs): DownloadCsv {
  const {
    prefecture,
    metadata,
    yoyEntry,
    yoyMetadata,
    functions,
    functionLabels,
    demandCategories,
    demandCategoryLabels,
    demandYears,
    demandYearLabels,
    baselineYear,
  } = args;

  const idCols = prefIdColumns(prefecture);
  const rows: CsvValue[][] = [];

  // dataset=basic。population_2020・area_km2 は prefecture_basic.csv 由来の
  // 公表値そのものなので note は空、population_2024/2040 は構想区域の合計なので
  // PREF_DERIVED_NOTE を付ける（metadata.fields の説明と一致させてある）。
  rows.push([...idCols, 'basic', BASIC_CATEGORY_LABEL, '人口（2020年国勢調査）', 2020, prefecture.population_2020, '人', '']);
  rows.push([...idCols, 'basic', BASIC_CATEGORY_LABEL, '面積', null, prefecture.area_km2, 'km2', '']);
  rows.push([
    ...idCols,
    'basic',
    BASIC_CATEGORY_LABEL,
    '人口（医療需要推計の基準人口）',
    null,
    prefecture.population_2024,
    '人',
    `${PREF_DERIVED_NOTE}／${BASELINE_POPULATION_NOTE}`,
  ]);
  rows.push([
    ...idCols,
    'basic',
    BASIC_CATEGORY_LABEL,
    '人口（2040年推計）',
    2040,
    prefecture.population_2040,
    '人',
    PREF_DERIVED_NOTE,
  ]);

  // dataset=beds（厚生労働省の都道府県別公表値そのもの。区域からの合計ではない）
  for (const fn of functions) {
    const label = functionLabels[fn];
    const beds = prefecture.beds[fn];
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

  // dataset=demand（構想区域からの合計＝派生値。区域側と違い note に年度ラベルと
  // 派生である旨の両方を入れる）
  const baselineKey = String(baselineYear);
  for (const category of demandCategories) {
    const categoryLabel = demandCategoryLabels[category];
    const baseline = prefecture.demand[category][baselineKey];
    for (const year of demandYears) {
      const yearKey = String(year);
      const value = prefecture.demand[category][yearKey];
      const yearNote = `${demandYearLabels[yearKey]}／${PREF_DERIVED_NOTE}`;
      rows.push([...idCols, 'demand', categoryLabel, 'レセプト件数/月', year, value, '件/月', yearNote]);
      const ratioToBaseline = year === baselineYear ? 1 : round4(value / baseline);
      rows.push([...idCols, 'demand', categoryLabel, '2024年度比', year, ratioToBaseline, '', yearNote]);
    }
  }

  // dataset=yoy（年度間比較 R6→R7）。区域側 buildAreaDetailCsv と違い published_fy 列は
  // 行ごとに変えられない（このCSVの識別列は都道府県層の R7 単独データセット由来で固定）
  // ため、系列名（「見込量2025（R6公表）」等）と note で公表回を示す。
  if (yoyEntry !== null) {
    const yoyReportRateLabel = '病床機能報告の報告率';
    rows.push([
      ...idCols,
      'yoy',
      yoyReportRateLabel,
      '報告率2024（R6公表）',
      2024,
      yoyEntry.report_rate_2024,
      '割合',
      '',
    ]);
    rows.push([
      ...idCols,
      'yoy',
      yoyReportRateLabel,
      '報告率2025（R7公表）',
      2025,
      yoyEntry.report_rate_2025,
      '割合',
      '',
    ]);

    for (const fn of functions) {
      const label = functionLabels[fn];
      const beds = yoyEntry.beds[fn];
      rows.push([...idCols, 'yoy', label, '見込量2025（R6公表）', 2025, beds.plan_2025, '床', '']);
      rows.push([...idCols, 'yoy', label, '実績2025（R7公表）', 2025, beds.actual_2025, '床', '']);
      rows.push([
        ...idCols,
        'yoy',
        label,
        '実績2024（R6公表）',
        2024,
        beds.actual_2024,
        '床',
        'R7公表分と同じ値（都道府県では両公表回が全て一致する）',
      ]);

      const planRatio = computeRatio(beds.actual_2025, beds.plan_2025);
      rows.push([
        ...idCols,
        'yoy',
        label,
        '比（実績2025/見込量2025）',
        null,
        planRatio === null ? null : round4(planRatio),
        '',
        planRatio === null ? YOY_RATIO_UNAVAILABLE_NOTE.yoy_plan_vs_actual : '',
      ]);

      const changeRatio = computeRatio(beds.actual_2025, beds.actual_2024);
      rows.push([
        ...idCols,
        'yoy',
        label,
        '変化率（実績2025/実績2024）',
        null,
        changeRatio === null ? null : round4(changeRatio),
        '',
        changeRatio === null ? YOY_RATIO_UNAVAILABLE_NOTE.yoy_actual_change : '',
      ]);
    }
  }

  const condition = `対象=都道府県 ${prefecture.pref_code} ${prefecture.pref_name}（構想区域 ${prefecture.area_count} 区域）`;
  // このCSVは病床と需要の両方を含むため、主出典を病床側(source_beds)にして
  // 需要側(source_demand)を追加の出典行として並べる（区域側は病床と需要で
  // ファイルが分かれているため、この形になるのは都道府県層だけ）。
  const demandSource = metadata.source_demand;
  const preamble = buildPreamble({
    source: metadata.source_beds,
    condition,
    caveat: metadata.processing.caveat.beds,
    extraSourceLine: `医療需要推計の原典ファイル: ${demandSource.source_file}（SHA-256: ${demandSource.source_sha256}） / 掲載ページ: ${demandSource.page_url}`,
    extraCaveatLines: [
      `注記（医療需要推計）: ${metadata.processing.caveat.demand_forecast} ${metadata.processing.caveat.demand_population}`,
      ...prefectureDerivedCaveatLines(metadata),
      ...(yoyEntry !== null
        ? [`注記（年度間比較）: ${yoyMetadata.processing.caveat}`, PREF_YOY_2024_IDENTICAL_NOTE]
        : []),
    ],
  });

  return {
    filename: `prefecture_${prefecture.pref_code}_indicators_R7.csv`,
    text: toCsvText(PREFECTURE_DETAIL_HEADER, rows, { preamble }),
  };
}
