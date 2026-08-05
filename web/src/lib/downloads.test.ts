import { describe, expect, it } from 'vitest';
import { buildAreaDetailCsv, buildAreaFlowCsv, buildAreaTableCsv, buildFacilityCsv } from './downloads';
import type {
  AreaDemandArea,
  AreaDemandData,
  AreaFlowEntry,
  AreaFlowMetadata,
  AreaIndicator,
  AreaIndicatorsData,
  AreaYoyArea,
  AreaYoyData,
  AreaYoyMetadata,
  BedFunctionKey,
  Facility,
  FacilityMetric,
  FacilityShard,
  FacilitySummaryMetadata,
  FacilityValueStatus,
  FlowDirectionKey,
  FlowPhaseGroup,
  FlowPhaseKey,
} from '../types';

// 小さなインラインフィクスチャのみを使う。src/generated/* はnpm run sync-data
// が生成するもので、npm run test（vitest）にはpre*フックが無くまっさらな
// チェックアウトでは存在しないため、ここではimportしない
// （CLAUDE.md「可視化実装で判明した罠」#8）。

const FULL_FUNCTION_LABELS: Record<BedFunctionKey, string> = {
  total: '合計',
  high_acute: '高度急性期',
  acute: '急性期',
  recovery: '回復期',
  chronic: '慢性期',
};

function makeIndicatorsArea(overrides: Partial<AreaIndicator> = {}): AreaIndicator {
  return {
    area_code: '0101',
    area_name: '南渡島',
    pref_code: '01',
    pref_name: '北海道',
    population_2020: 359223,
    area_km2: 2670.6,
    outflow_rate: 0.035,
    inflow_rate: 0.085,
    beds: {
      total: { actual_2025: 4995, need_2025: 4857 },
      high_acute: { actual_2025: 661, need_2025: 585 },
      acute: { actual_2025: 2471, need_2025: 1759 },
      recovery: { actual_2025: 801, need_2025: 1618 },
      chronic: { actual_2025: 1062, need_2025: 895 },
    },
    ...overrides,
  };
}

const INDICATORS_METADATA: AreaIndicatorsData['metadata'] = {
  title: 'test-indicators',
  source: {
    name: '②構想区域の病床数等（別添４）',
    publisher: '厚生労働省',
    url: 'https://example.test/001723349.xlsx',
    page_url: 'https://example.test/page',
    fiscal_year: '令和7年度（2025年度）',
    source_file: 'R7/001723349.xlsx',
    source_sha256: 'aaaa',
    acquired_date: '2026-08-04',
    license: 'テスト利用規約',
    original_notes: [],
    derived_via: [],
  },
  processing: {
    script: 'tools/build_web_data.py',
    inputs: [],
    steps: [],
    caveat: '病床の注記テキスト',
  },
  fields: {},
  known_issues: [],
};

function makeIndicatorsData(areas: AreaIndicator[]): AreaIndicatorsData {
  return {
    metadata: INDICATORS_METADATA,
    functions: ['total', 'high_acute', 'acute', 'recovery', 'chronic'],
    function_labels: FULL_FUNCTION_LABELS,
    areas,
  };
}

function makeDemandArea(overrides: Partial<AreaDemandArea> = {}): AreaDemandArea {
  return {
    area_code: '0101',
    area_name: '南渡島',
    pref_code: '01',
    pref_name: '北海道',
    population_2024: 340005,
    population_2040: 259252,
    demand: {
      home_care: { '2024': 4382.75, '2030': 4942.96, '2040': 5464.615 },
      outpatient: { '2024': 261882.17, '2030': 244362.64, '2040': 211020.46 },
    },
    ...overrides,
  };
}

const DEMAND_METADATA: AreaDemandData['metadata'] = {
  title: 'test-demand',
  source: {
    name: '構想区域別の医療需要推計',
    publisher: '厚生労働省',
    url: 'https://example.test/001728462.xlsx',
    page_url: 'https://example.test/demand-page',
    fiscal_year: '令和7年度（2025年度）',
    source_file: 'R7/001728462.xlsx',
    source_sha256: 'bbbb',
    source_sheet: ['将来の在宅（訪問診療）需要推計', '将来の外来需要推計'],
    acquired_date: '2026-08-04',
    license: 'テスト利用規約',
    original_title: ['将来の在宅（訪問診療）需要推計', '将来の外来需要推計'],
    original_notes: [],
    derived_via: [],
  },
  processing: {
    script: 'tools/build_web_demand.py',
    inputs: [],
    steps: [],
    caveat: {
      demand_forecast: 'レセプト件数/月の注記',
      demand_population: '基準人口の注記',
    },
  },
  fields: {},
  known_issues: [],
};

function makeDemandData(areas: AreaDemandArea[]): AreaDemandData {
  return {
    metadata: DEMAND_METADATA,
    categories: ['home_care', 'outpatient'],
    category_labels: { home_care: '在宅（訪問診療）', outpatient: '外来' },
    years: [2024, 2030, 2040],
    year_labels: { '2024': '2024年度', '2030': '2030年度（現状投影）', '2040': '2040年度（現状投影）' },
    baseline_year: 2024,
    areas,
  };
}

function makeYoyArea(overrides: Partial<AreaYoyArea> = {}): AreaYoyArea {
  return {
    area_code: '0101',
    area_name: '南渡島',
    pref_code: '01',
    pref_name: '北海道',
    report_rate_2024: 0.95,
    report_rate_2025: 1.0,
    beds: {
      total: { plan_2025: 5216, actual_2025: 4995, actual_2024: 5243 },
      high_acute: { plan_2025: 0, actual_2025: 661, actual_2024: 0 },
      acute: { plan_2025: 2322, actual_2025: 2471, actual_2024: 2363 },
      recovery: { plan_2025: 778, actual_2025: 801, actual_2024: 785 },
      chronic: { plan_2025: 1160, actual_2025: 1062, actual_2024: 1155 },
    },
    ...overrides,
  };
}

const YOY_METADATA: AreaYoyMetadata = {
  title: 'test-yoy',
  source: [
    {
      published_fy: 'R7',
      name: '②構想区域の病床数等（別添４）',
      publisher: '厚生労働省',
      url: 'https://example.test/001723349.xlsx',
      page_url: 'https://example.test/yoy-page',
      fiscal_year: '令和7年度（2025年度）',
      source_file: 'R7/001723349.xlsx',
      source_sha256: 'r7hash',
      source_sheet: '構想区域別必要量との比較',
      acquired_date: '2026-08-04',
      license: 'テスト利用規約',
      original_title: 'R7原題',
      original_notes: [],
    },
    {
      published_fy: 'R6',
      name: '別添４③（構想区域の病床数等の状況）',
      publisher: '厚生労働省',
      url: 'https://example.test/001723128.zip',
      source_note: '令和6年度版一括DL zip に同梱',
      page_url: 'https://example.test/yoy-page',
      fiscal_year: '令和6年度',
      source_file: 'R6/別添４③（構想区域の病床数等の状況）.xlsx',
      source_sha256: 'r6hash',
      source_sheet: '構想区域別必要量との比較',
      acquired_date: '2026-08-05',
      license: 'テスト利用規約',
      original_title: 'R6原題',
      original_notes: [],
    },
  ],
  processing: {
    script: 'tools/build_web_yoy.py',
    inputs: [],
    steps: [],
    caveat: '年度間比較の注記テキスト（見込量2025はR6公表時点の見込み）',
  },
  fields: {},
  known_issues: [
    {
      id: 'area_yoy_2024_actual_from_r6',
      summary: '2024年実績はR6公表分を採用した',
      action: 'beds.*.actual_2024はpublished_fy==R6の値である',
    },
  ],
};

function makeYoyData(areas: AreaYoyArea[]): AreaYoyData {
  return {
    metadata: YOY_METADATA,
    functions: ['total', 'high_acute', 'acute', 'recovery', 'chronic'],
    function_labels: FULL_FUNCTION_LABELS,
    areas,
  };
}

const FACILITY_METRICS: FacilityMetric[] = [
  { key: 'beds_total', metric: '病床数', bed_function: '休棟中等含む計', label: '病床数（休棟中等含む計）' },
  { key: 'doctors_fulltime', metric: '医師数（常勤）', bed_function: '', label: '医師数（常勤）' },
  { key: 'ambulance', metric: '救急車の受入件数', bed_function: '', label: '救急車の受入件数' },
];

const VALUE_STATUS_LABELS: Record<FacilityValueStatus, string> = {
  observed: '実測値',
  source_dash: '原典が「-」',
  not_disclosed: '非公表（NDBの利用に関するガイドラインにより一部非公表）',
  not_reported: '未報告（病床機能報告を未報告の医療機関）',
  blank: '空欄（原典セルが空欄）',
};

function makeFacility(overrides: Partial<Facility> = {}): Facility {
  return {
    record_id: 'R7-0101-14',
    facility_name: '市立函館病院',
    municipality: '函館市',
    values: [582, 20, null],
    value_status: ['observed', 'observed', 'not_disclosed'],
    functions: ['地域支援', '三次救急'],
    match_status: 'matched',
    coordinates: [140.7301711, 41.80541985],
    ...overrides,
  };
}

function makeShard(overrides: Partial<FacilityShard> = {}): FacilityShard {
  return {
    area_code: '0101',
    area_name: '南渡島',
    pref_code: '01',
    pref_name: '北海道',
    facility_count: 1,
    geocoded_count: 1,
    facilities: [makeFacility()],
    ...overrides,
  };
}

const FACILITY_SUMMARY_METADATA: FacilitySummaryMetadata = {
  title: 'test-facilities',
  source: {
    name: '③構想区域の医療機関の病床数、診療実績等（別添５）',
    publisher: '厚生労働省',
    url: 'https://example.test/001723127.xlsx',
    page_url: 'https://example.test/facility-page',
    fiscal_year: '令和7年度（2025年度）',
    source_file: 'R7/001723127.xlsx',
    source_sha256: 'cccc',
    source_sheet: '339シート',
    acquired_date: '2026-08-04',
    license: 'テスト利用規約',
    original_title: '構想区域別の医療機関の病床機能報告上の病床数、診療実績、医師数等',
    original_notes: [],
    derived_via: [],
  },
  geo_linkage_source: {
    name: 'facility_basic.csv × P04-20のレコードリンケージ',
    inputs: [],
    license: 'テスト利用規約2',
    page_url: 'https://example.test/geo-page',
    derived_via: [],
  },
  processing: {
    script: 'tools/build_web_facilities.py',
    inputs: [],
    steps: [],
    caveat: {
      facility_basic: 'facility_basicの注記',
      facility_observations: 'facility_observationsの注記',
      facility_functions: 'facility_functionsの注記',
      facility_geo_linkage: 'facility_geo_linkageの注記',
    },
  },
  fields: {},
  known_issues: [],
};

// ---- buildAreaTableCsv ------------------------------------------------------

describe('buildAreaTableCsv (bed metrics)', () => {
  it('produces one row per area for the selected bed function, with a self-describing filename/header', () => {
    const areaA = makeIndicatorsArea();
    const areaB = makeIndicatorsArea({
      area_code: '0102',
      area_name: '南檜山',
      beds: { ...areaA.beds, high_acute: { actual_2025: 0, need_2025: 0 } },
    });
    const indicators = makeIndicatorsData([areaA, areaB]);
    const demand = makeDemandData([makeDemandArea()]);
    const yoy = makeYoyData([makeYoyArea()]);

    const { filename, text } = buildAreaTableCsv({
      indicators,
      demand,
      yoy,
      metric: 'ratio',
      bedFunction: 'high_acute',
      year: 2024,
    });

    expect(filename).toBe('area_beds_ratio_high_acute_2025_R7.csv');

    const lines = text.split('\r\n');
    const headerLine = lines.find((l) => l.startsWith('published_fy,'))!;
    expect(headerLine).toBe(
      'published_fy,area_code,area_name,pref_code,pref_name,bed_function,actual_2025,need_2025,diff,ratio,note'
    );

    const rowA = lines.find((l) => l.startsWith('R7,0101,'))!;
    expect(rowA).toBe('R7,0101,南渡島,01,北海道,高度急性期,661,585,76,1.1299,');

    // need_2025=0 -> ratio null (欠測=空欄) + note
    const rowB = lines.find((l) => l.startsWith('R7,0102,'))!;
    expect(rowB).toBe('R7,0102,南檜山,01,北海道,高度急性期,0,0,0,,必要数が0のため比は算出不可');
  });

  it('varies filename/condition text by metric (actual/need), and embeds the source SHA-256/page URL', () => {
    const indicators = makeIndicatorsData([makeIndicatorsArea()]);
    const demand = makeDemandData([makeDemandArea()]);
    const yoy = makeYoyData([makeYoyArea()]);

    const { filename, text } = buildAreaTableCsv({
      indicators,
      demand,
      yoy,
      metric: 'actual',
      bedFunction: 'total',
      year: 2024,
    });

    expect(filename).toBe('area_beds_actual_total_2025_R7.csv');
    expect(text).toContain('出力条件: 指標=実績病床数（2025年実績）, 病床機能=合計, 対象=全1構想区域');
    expect(text).toContain('原典ファイル: R7/001723349.xlsx（SHA-256: aaaa）');
    expect(text).toContain('掲載ページ: https://example.test/page');
    expect(text).toContain('注記: 病床の注記テキスト');
  });
});

describe('buildAreaTableCsv (demand metrics)', () => {
  it('produces one row per area for the selected category/year, rounding ratio_to_2024 to 4 decimals', () => {
    const indicators = makeIndicatorsData([makeIndicatorsArea()]);
    const demand = makeDemandData([makeDemandArea()]);
    const yoy = makeYoyData([makeYoyArea()]);

    const { filename, text } = buildAreaTableCsv({
      indicators,
      demand,
      yoy,
      metric: 'demand_home_care',
      bedFunction: 'total',
      year: 2040,
    });

    expect(filename).toBe('area_demand_home_care_2040_R7.csv');

    const lines = text.split('\r\n');
    const headerLine = lines.find((l) => l.startsWith('published_fy,'))!;
    expect(headerLine).toBe(
      'published_fy,area_code,area_name,pref_code,pref_name,demand_category,year,year_label,receipts_per_month,baseline_2024,ratio_to_2024'
    );

    const row = lines.find((l) => l.startsWith('R7,0101,'))!;
    // 5464.615 / 4382.75 = 1.24686... -> rounds to 1.2468 (小数第4位)
    expect(row).toBe('R7,0101,南渡島,01,北海道,在宅（訪問診療）,2040,2040年度（現状投影）,5464.615,4382.75,1.2468');

    expect(text).toContain('出力条件: 指標=在宅（訪問診療）（レセプト件数/月・2024年度比）, 年度=2040年度, 対象=全1構想区域');
    expect(text).toContain('原典ファイル: R7/001728462.xlsx（SHA-256: bbbb）');
    expect(text).toContain('注記: レセプト件数/月の注記');
  });

  it('uses the outpatient category label/key and the requested year in the filename', () => {
    const indicators = makeIndicatorsData([makeIndicatorsArea()]);
    const demand = makeDemandData([makeDemandArea()]);
    const yoy = makeYoyData([makeYoyArea()]);

    const { filename, text } = buildAreaTableCsv({
      indicators,
      demand,
      yoy,
      metric: 'demand_outpatient',
      bedFunction: 'total',
      year: 2040,
    });

    expect(filename).toBe('area_demand_outpatient_2040_R7.csv');
    const row = text.split('\r\n').find((l) => l.startsWith('R7,0101,'))!;
    expect(row).toBe('R7,0101,南渡島,01,北海道,外来,2040,2040年度（現状投影）,211020.46,261882.17,0.8058');
  });
});

describe('buildAreaTableCsv (yoy metrics)', () => {
  it('produces one row per area for yoy_plan_vs_actual (実績2025/見込量2025), with a self-describing filename/header', () => {
    const indicators = makeIndicatorsData([makeIndicatorsArea()]);
    const demand = makeDemandData([makeDemandArea()]);
    const areaA = makeYoyArea();
    const areaB = makeYoyArea({
      area_code: '0102',
      area_name: '南檜山',
      beds: { ...areaA.beds, high_acute: { plan_2025: 0, actual_2025: 0, actual_2024: 0 } },
    });
    const yoy = makeYoyData([areaA, areaB]);

    const { filename, text } = buildAreaTableCsv({
      indicators,
      demand,
      yoy,
      metric: 'yoy_plan_vs_actual',
      bedFunction: 'high_acute',
      year: 2024,
    });

    expect(filename).toBe('area_yoy_yoy_plan_vs_actual_high_acute_R6_R7.csv');

    const lines = text.split('\r\n');
    const headerLine = lines.find((l) => l.startsWith('area_code,'))!;
    expect(headerLine).toBe(
      'area_code,area_name,pref_code,pref_name,bed_function,plan_2025_r6,actual_2025_r7,actual_2024_r6,report_rate_2024_r6,report_rate_2025_r7,ratio,note'
    );

    // published_fyという列自体を持たない（'R6+R7'という無い値を発明しない代わりに
    // 列名(_r6/_r7)へ由来を持たせている。修正1a）。
    // high_acute: plan_2025=0 -> ratio null (欠測=空欄) + note, actual_2025 unaffected.
    const rowA = lines.find((l) => l.startsWith('0101,'))!;
    expect(rowA).toBe('0101,南渡島,01,北海道,高度急性期,0,661,0,0.95,1,,見込量2025が0のため比は算出不可');

    const rowB = lines.find((l) => l.startsWith('0102,'))!;
    expect(rowB).toBe('0102,南檜山,01,北海道,高度急性期,0,0,0,0.95,1,,見込量2025が0のため比は算出不可');
  });

  it('produces yoy_actual_change (実績2025/実績2024) rows, and embeds both R7/R6 source blocks + the 2024実績 known issue', () => {
    const indicators = makeIndicatorsData([makeIndicatorsArea()]);
    const demand = makeDemandData([makeDemandArea()]);
    const yoy = makeYoyData([makeYoyArea()]);

    const { filename, text } = buildAreaTableCsv({
      indicators,
      demand,
      yoy,
      metric: 'yoy_actual_change',
      bedFunction: 'total',
      year: 2024,
    });

    expect(filename).toBe('area_yoy_yoy_actual_change_total_R6_R7.csv');

    const row = text.split('\r\n').find((l) => l.startsWith('0101,'))!;
    // 4995 / 5243 = 0.95269... -> rounds to 0.9527 (小数第4位)
    expect(row).toBe('0101,南渡島,01,北海道,合計,5216,4995,5243,0.95,1,0.9527,');

    expect(text).toContain(
      '出力条件: 指標=実績の1年変化（2024→2025）（2025年実績（R7公表）/2024年実績（R6公表））, 病床機能=合計, 対象=全1構想区域'
    );
    expect(text).toContain('原典ファイル: R7/001723349.xlsx（SHA-256: r7hash）');
    expect(text).toContain(
      'R6公表分の原典ファイル: R6/別添４③（構想区域の病床数等の状況）.xlsx（SHA-256: r6hash） / 取得日: 2026-08-05'
    );
    expect(text).toContain('注記: 年度間比較の注記テキスト（見込量2025はR6公表時点の見込み）');
    expect(text).toContain('注記（2024年実績の採用について）: 2024年実績はR6公表分を採用した／beds.*.actual_2024はpublished_fy==R6の値である');
  });
});

// ---- buildAreaDetailCsv -----------------------------------------------------

describe('buildAreaDetailCsv', () => {
  const baseArgs = {
    indicatorsMetadata: INDICATORS_METADATA,
    demandMetadata: DEMAND_METADATA,
    yoyMetadata: YOY_METADATA,
    // 年度間比較を明示的にテストしないケースでは yoyArea: null にしておき、
    // dataset=yoy の行・注記が一切出ないこと（demandArea:nullの扱いと同じ)を
    // 既存のアサーションが検証し続けられるようにする。
    yoyArea: null as AreaYoyArea | null,
    functionLabels: FULL_FUNCTION_LABELS,
    demandCategoryLabels: { home_care: '在宅（訪問診療）', outpatient: '外来' },
    baselineYear: 2024,
  };

  it('emits basic/beds/demand rows for a fully-populated area, with rounded derived values', () => {
    const area = makeIndicatorsArea();
    const demandArea = makeDemandArea();

    const { filename, text } = buildAreaDetailCsv({
      ...baseArgs,
      area,
      demandArea,
      functions: ['high_acute'],
      demandCategories: ['home_care', 'outpatient'],
      demandYears: [2024, 2040],
      demandYearLabels: { '2024': '2024年度', '2040': '2040年度（現状投影）' },
    });

    expect(filename).toBe('area_0101_indicators_R7.csv');

    const lines = text.split('\r\n');
    const headerLine = lines.find((l) => l.startsWith('published_fy,'))!;
    expect(headerLine).toBe(
      'published_fy,area_code,area_name,pref_code,pref_name,dataset,category,series,year,value,unit,note'
    );

    // dataset=basic
    expect(lines).toContain('R7,0101,南渡島,01,北海道,basic,基礎情報,人口（2020年国勢調査）,2020,359223,人,');
    expect(lines).toContain('R7,0101,南渡島,01,北海道,basic,基礎情報,面積,,2670.6,km2,');
    // 推計流出/流入患者割合はyear列を空欄にする（原典が対象年を明示していないため）
    expect(lines).toContain('R7,0101,南渡島,01,北海道,basic,基礎情報,推計流出患者割合,,0.035,割合,');
    expect(lines).toContain('R7,0101,南渡島,01,北海道,basic,基礎情報,推計流入患者割合,,0.085,割合,');
    expect(
      lines.find((l) => l.includes('人口（医療需要推計の基準人口）'))
    ).toBe(
      'R7,0101,南渡島,01,北海道,basic,基礎情報,人口（医療需要推計の基準人口）,,340005,人,基準人口の年は原典間で不一致（原典Excelの見出しは2024年度、公式説明書は2025年）。本サイトは原典Excelの値をそのまま出力している'
    );
    expect(lines).toContain('R7,0101,南渡島,01,北海道,basic,基礎情報,人口（2040年推計）,2040,259252,人,');

    // dataset=beds (functions=['high_acute'] のみ)
    expect(lines).toContain('R7,0101,南渡島,01,北海道,beds,高度急性期,実績,2025,661,床,');
    expect(lines).toContain('R7,0101,南渡島,01,北海道,beds,高度急性期,必要数,2025,585,床,');
    expect(lines).toContain('R7,0101,南渡島,01,北海道,beds,高度急性期,差（実績−必要数）,2025,76,床,');
    expect(lines).toContain('R7,0101,南渡島,01,北海道,beds,高度急性期,比（実績/必要数）,2025,1.1299,,');

    // dataset=demand（2区分 x 2年度）
    expect(lines).toContain('R7,0101,南渡島,01,北海道,demand,在宅（訪問診療）,レセプト件数/月,2024,4382.75,件/月,2024年度');
    expect(lines).toContain('R7,0101,南渡島,01,北海道,demand,在宅（訪問診療）,2024年度比,2024,1,,2024年度');
    expect(lines).toContain(
      'R7,0101,南渡島,01,北海道,demand,在宅（訪問診療）,レセプト件数/月,2040,5464.615,件/月,2040年度（現状投影）'
    );
    expect(lines).toContain(
      'R7,0101,南渡島,01,北海道,demand,在宅（訪問診療）,2024年度比,2040,1.2468,,2040年度（現状投影）'
    );
    expect(lines).toContain(
      'R7,0101,南渡島,01,北海道,demand,外来,レセプト件数/月,2040,211020.46,件/月,2040年度（現状投影）'
    );
    expect(lines).toContain('R7,0101,南渡島,01,北海道,demand,外来,2024年度比,2040,0.8058,,2040年度（現状投影）');

    expect(text).toContain('出力条件: 対象=構想区域 0101 南渡島（北海道）');
    expect(text).toContain('注記: 病床の注記テキスト');
    expect(text).toContain('注記（医療需要推計）: レセプト件数/月の注記 基準人口の注記');
  });

  it('omits dataset=demand rows and the two demand-derived basic rows when demandArea is null', () => {
    const area = makeIndicatorsArea();

    const { text } = buildAreaDetailCsv({
      ...baseArgs,
      area,
      demandArea: null,
      functions: ['high_acute'],
      demandCategories: ['home_care', 'outpatient'],
      demandYears: [2024, 2040],
      demandYearLabels: { '2024': '2024年度', '2040': '2040年度（現状投影）' },
    });

    expect(text).not.toContain(',demand,');
    expect(text).not.toContain('人口（医療需要推計の基準人口）');
    expect(text).not.toContain('人口（2040年推計）');
    expect(text).not.toContain('注記（医療需要推計）');
    // yoyArea is also null in baseArgs -> dataset=yoy rows/note must be absent too.
    expect(text).not.toContain(',yoy,');
    expect(text).not.toContain('注記（年度間比較）');
    // basic/beds rows are still present
    expect(text).toContain('人口（2020年国勢調査）');
    expect(text).toContain('高度急性期,実績');
  });

  it('leaves outflow/inflow value blank and notes the source sentinel when the rates are null (三重県のパターン)', () => {
    const area = makeIndicatorsArea({
      area_code: '2405',
      area_name: '桑名',
      outflow_rate: null,
      inflow_rate: null,
      flow_rate_unavailable: 'XXX',
    });

    const { text } = buildAreaDetailCsv({
      ...baseArgs,
      area,
      demandArea: null,
      functions: ['high_acute'],
      demandCategories: [],
      demandYears: [],
      demandYearLabels: {},
    });

    const lines = text.split('\r\n');
    expect(lines).toContain(
      "R7,2405,桑名,01,北海道,basic,基礎情報,推計流出患者割合,,,割合,原典が'XXX'（未算出）"
    );
    expect(lines).toContain(
      "R7,2405,桑名,01,北海道,basic,基礎情報,推計流入患者割合,,,割合,原典が'XXX'（未算出）"
    );
  });

  it('marks the bed ratio unavailable (blank + note) when need_2025 is 0', () => {
    const area = makeIndicatorsArea({
      beds: {
        ...makeIndicatorsArea().beds,
        chronic: { actual_2025: 0, need_2025: 0 },
      },
    });

    const { text } = buildAreaDetailCsv({
      ...baseArgs,
      area,
      demandArea: null,
      functions: ['chronic'],
      demandCategories: [],
      demandYears: [],
      demandYearLabels: {},
    });

    const lines = text.split('\r\n');
    expect(lines).toContain(
      'R7,0101,南渡島,01,北海道,beds,慢性期,比（実績/必要数）,2025,,,必要数が0のため比は算出不可'
    );
  });

  // ---- dataset=yoy (年度間比較 R6→R7, M9) ----------------------------------

  it('emits dataset=yoy rows with per-row published_fy (R6 for plan_2025/actual_2024/report_rate_2024, R7 for actual_2025/report_rate_2025, blank for derived ratios — not a made-up "R6+R7")', () => {
    const area = makeIndicatorsArea();
    const yoyArea = makeYoyArea();

    const { text } = buildAreaDetailCsv({
      ...baseArgs,
      area,
      demandArea: null,
      yoyArea,
      functions: ['total', 'high_acute'],
      demandCategories: [],
      demandYears: [],
      demandYearLabels: {},
    });

    const lines = text.split('\r\n');

    // 報告率（区域単位、機能に依存しない）
    expect(lines).toContain('R6,0101,南渡島,01,北海道,yoy,病床機能報告の報告率,報告率2024（R6公表）,2024,0.95,割合,');
    expect(lines).toContain('R7,0101,南渡島,01,北海道,yoy,病床機能報告の報告率,報告率2025（R7公表）,2025,1,割合,');

    // 機能別の生値（合計）
    expect(lines).toContain('R6,0101,南渡島,01,北海道,yoy,合計,見込量2025（R6公表）,2025,5216,床,');
    expect(lines).toContain('R7,0101,南渡島,01,北海道,yoy,合計,実績2025（R7公表）,2025,4995,床,');
    expect(lines).toContain('R6,0101,南渡島,01,北海道,yoy,合計,実績2024（R6公表）,2024,5243,床,');

    // 派生値（比・変化率）はpublished_fyを空欄にする（単一の公表回に帰属しない。
    // 'R6+R7'という無い値は発明しない）。理由はnote列に書く。丸めは5464.615と
    // 同じ小数第4位: 4995/5216 = 0.95765... -> 0.9576、4995/5243 = 0.95269... -> 0.9527
    expect(lines).toContain(
      ',0101,南渡島,01,北海道,yoy,合計,比（実績2025/見込量2025）,,0.9576,,実績2025(R7公表)÷見込量2025(R6公表)のため単一の公表年度に帰属しない'
    );
    expect(lines).toContain(
      ',0101,南渡島,01,北海道,yoy,合計,変化率（実績2025/実績2024）,,0.9527,,実績2025(R7公表)÷実績2024(R6公表)のため単一の公表年度に帰属しない'
    );

    expect(text).toContain('注記（年度間比較）: 年度間比較の注記テキスト（見込量2025はR6公表時点の見込み）');
    expect(text).toContain(
      '注記（2024年実績の採用について）: 2024年実績はR6公表分を採用した／beds.*.actual_2024はpublished_fy==R6の値である'
    );
  });

  it('marks the yoy ratios unavailable (blank + note) when their denominator is 0 (高度急性期のように見込量/実績2024が0の区域がある)', () => {
    const area = makeIndicatorsArea();
    const yoyArea = makeYoyArea();

    const { text } = buildAreaDetailCsv({
      ...baseArgs,
      area,
      demandArea: null,
      yoyArea,
      functions: ['high_acute'],
      demandCategories: [],
      demandYears: [],
      demandYearLabels: {},
    });

    const lines = text.split('\r\n');
    expect(lines).toContain(
      ',0101,南渡島,01,北海道,yoy,高度急性期,比（実績2025/見込量2025）,,,,実績2025(R7公表)÷見込量2025(R6公表)のため単一の公表年度に帰属しない／見込量2025が0のため比は算出不可'
    );
    expect(lines).toContain(
      ',0101,南渡島,01,北海道,yoy,高度急性期,変化率（実績2025/実績2024）,,,,実績2025(R7公表)÷実績2024(R6公表)のため単一の公表年度に帰属しない／実績2024が0のため比は算出不可'
    );
  });
});

// ---- buildFacilityCsv -------------------------------------------------------

describe('buildFacilityCsv', () => {
  it('emits one row per facility per metric, with facility identity columns repeated', () => {
    const shard = makeShard();

    const { filename, text } = buildFacilityCsv({
      shard,
      metrics: FACILITY_METRICS,
      valueStatusLabels: VALUE_STATUS_LABELS,
      facilitySummaryMetadata: FACILITY_SUMMARY_METADATA,
    });

    expect(filename).toBe('area_0101_facilities_R7.csv');

    const lines = text.split('\r\n');
    const headerLine = lines.find((l) => l.startsWith('published_fy,'))!;
    expect(headerLine).toBe(
      'published_fy,area_code,area_name,pref_code,pref_name,record_id,facility_name,municipality,metric,bed_function,value,value_status,value_status_label,functions,match_status,lon,lat'
    );

    const dataRows = lines.filter((l) => l.startsWith('R7,0101,'));
    expect(dataRows).toHaveLength(3); // 1施設 x 3指標

    expect(dataRows[0]).toBe(
      'R7,0101,南渡島,01,北海道,R7-0101-14,市立函館病院,函館市,病床数,休棟中等含む計,582,observed,実測値,地域支援;三次救急,matched,140.7301711,41.80541985'
    );
  });

  it('leaves value blank (not 0/null-as-zero) for a non-observed metric, but keeps the row', () => {
    const shard = makeShard();

    const { text } = buildFacilityCsv({
      shard,
      metrics: FACILITY_METRICS,
      valueStatusLabels: VALUE_STATUS_LABELS,
      facilitySummaryMetadata: FACILITY_SUMMARY_METADATA,
    });

    const ambulanceRow = text.split('\r\n').find((l) => l.includes(',救急車の受入件数,'))!;
    expect(ambulanceRow).toBe(
      'R7,0101,南渡島,01,北海道,R7-0101-14,市立函館病院,函館市,救急車の受入件数,,,not_disclosed,非公表（NDBの利用に関するガイドラインにより一部非公表）,地域支援;三次救急,matched,140.7301711,41.80541985'
    );
  });

  it('leaves lon/lat blank for a facility without coordinates, and functions blank when absent (位置の推測はしない)', () => {
    const facility = makeFacility({ record_id: 'R7-0101-99', match_status: 'unmatched' });
    delete (facility as Partial<Facility>).coordinates;
    delete (facility as Partial<Facility>).functions;
    const shard = makeShard({ facilities: [facility], facility_count: 1, geocoded_count: 0 });

    const { text } = buildFacilityCsv({
      shard,
      metrics: FACILITY_METRICS,
      valueStatusLabels: VALUE_STATUS_LABELS,
      facilitySummaryMetadata: FACILITY_SUMMARY_METADATA,
    });

    const row = text.split('\r\n').find((l) => l.startsWith('R7,0101,') && l.includes('R7-0101-99') && l.includes('病床数,休棟中等含む計'))!;
    expect(row).toBe(
      'R7,0101,南渡島,01,北海道,R7-0101-99,市立函館病院,函館市,病床数,休棟中等含む計,582,observed,実測値,,unmatched,,'
    );
  });

  it('includes both source blocks (facility_observations + geo_linkage) in the preamble', () => {
    const shard = makeShard();

    const { text } = buildFacilityCsv({
      shard,
      metrics: FACILITY_METRICS,
      valueStatusLabels: VALUE_STATUS_LABELS,
      facilitySummaryMetadata: FACILITY_SUMMARY_METADATA,
    });

    expect(text).toContain('原典ファイル: R7/001723127.xlsx（SHA-256: cccc）');
    expect(text).toContain('掲載ページ: https://example.test/facility-page');
    expect(text).toContain('座標の出典: facility_basic.csv × P04-20のレコードリンケージ / https://example.test/geo-page');
    expect(text).toContain('注記: facility_observationsの注記');
    expect(text).toContain('注記（座標）: facility_geo_linkageの注記');
    expect(text).toContain('出力条件: 対象=構想区域 0101 南渡島（北海道）の医療機関 1件 × 3指標');
  });
});

// ---- buildAreaFlowCsv -------------------------------------------------------

const FLOW_DIRECTION_LABELS: Record<FlowDirectionKey, string> = { inflow: '流入率', outflow: '流出率' };
const FLOW_PHASE_LABELS: Record<FlowPhaseKey, string> = {
  acute: '高度急性期+急性期',
  comprehensive: '包括期',
  chronic: '慢性期',
};

const FLOW_METADATA: AreaFlowMetadata = {
  title: 'test-flow',
  source: {
    name: '④構想区域の流出率及び流入率（別添５）',
    publisher: '厚生労働省',
    url: 'https://example.test/001723366.xlsx',
    page_url: 'https://example.test/flow-page',
    fiscal_year: '令和7年度（2025年度）',
    source_file: 'R7/001723366.xlsx',
    source_sha256: 'dddd',
    source_sheet: ['流入率', '流出率'],
    acquired_date: '2026-08-04',
    license: 'テスト利用規約',
    original_title: '流入率・流出率',
    original_notes: [],
    derived_via: [],
  },
  processing: {
    script: 'tools/build_web_flow.py',
    inputs: [],
    steps: [],
    caveat: {
      patient_flow: '流入率・流出率の注記',
      patient_flow_total: '全体値の注記',
    },
  },
  fields: {},
  known_issues: [],
};

const EMPTY_FLOW_GROUP: FlowPhaseGroup = { self_rate: null, self_rank: null, partners: [], value_error_count: 0 };

function makeFlowEntry(direction: FlowDirectionKey, phase: FlowPhaseKey, group: FlowPhaseGroup): AreaFlowEntry {
  const emptyPhases = { acute: EMPTY_FLOW_GROUP, comprehensive: EMPTY_FLOW_GROUP, chronic: EMPTY_FLOW_GROUP };
  const emptyDirection = { overall_rate: 0, phases: emptyPhases };
  return {
    area_code: '0101',
    flows: {
      inflow: direction === 'inflow' ? { overall_rate: 0.05, phases: { ...emptyPhases, [phase]: group } } : emptyDirection,
      outflow:
        direction === 'outflow' ? { overall_rate: 0.033216957073430975, phases: { ...emptyPhases, [phase]: group } } : emptyDirection,
    },
  };
}

describe('buildAreaFlowCsv', () => {
  const area = makeIndicatorsArea(); // area_code '0101', area_name '南渡島', pref_code '01', pref_name '北海道'
  const area0103 = makeIndicatorsArea({ area_code: '0103', area_name: '渡島西部' });
  const area0104 = makeIndicatorsArea({ area_code: '0104', area_name: '桧山' });
  const areas = [area, area0103, area0104];

  it('reconstructs the source row order, inserting the self row at self_rank when self_rank >= 2', () => {
    const group: FlowPhaseGroup = {
      self_rate: 0.123456789,
      self_rank: 2,
      partners: [
        ['0104', 0.3],
        ['0103', 0.05],
      ],
      value_error_count: 0,
    };
    const flowEntry = makeFlowEntry('outflow', 'chronic', group);

    const { filename, text } = buildAreaFlowCsv({
      area,
      flowEntry,
      direction: 'outflow',
      phase: 'chronic',
      directionLabels: FLOW_DIRECTION_LABELS,
      phaseLabels: FLOW_PHASE_LABELS,
      flowMetadata: FLOW_METADATA,
      areas,
    });

    expect(filename).toBe('area_flow_0101_outflow_chronic_R7.csv');

    const lines = text.split('\r\n');
    const headerLine = lines.find((l) => l.startsWith('area_code,'))!;
    expect(headerLine).toBe(
      'area_code,area_name,direction,phase,rank,partner_area_code,partner_pref_name,partner_area_name,rate'
    );

    // rank1: 最初のpartner(0104)、rank2: 自区域(self_rank=2の位置)、rank3: 2番目のpartner(0103)
    const dataLines = lines.filter((l) => l.startsWith('0101,南渡島,outflow,chronic,'));
    expect(dataLines).toHaveLength(3);
    expect(dataLines[0]).toBe('0101,南渡島,outflow,chronic,1,0104,北海道,桧山,0.3');
    // 自区域行は生値(丸めない)のまま出る
    expect(dataLines[1]).toBe('0101,南渡島,outflow,chronic,2,0101,北海道,南渡島,0.123456789');
    expect(dataLines[2]).toBe('0101,南渡島,outflow,chronic,3,0103,北海道,渡島西部,0.05');
  });

  it('numbers partners 1..N with no self row when self_rank is null (自区域行なしのグループ)', () => {
    const group: FlowPhaseGroup = {
      self_rate: null,
      self_rank: null,
      partners: [
        ['0102', 0.4],
        ['0103', 0.1],
      ],
      value_error_count: 1,
    };
    // 0102は未定義areaでも(名前解決できなくても)行は出す
    const flowEntry = makeFlowEntry('inflow', 'chronic', group);

    const { text } = buildAreaFlowCsv({
      area,
      flowEntry,
      direction: 'inflow',
      phase: 'chronic',
      directionLabels: FLOW_DIRECTION_LABELS,
      phaseLabels: FLOW_PHASE_LABELS,
      flowMetadata: FLOW_METADATA,
      areas,
    });

    const lines = text.split('\r\n');
    const dataLines = lines.filter((l) => l.startsWith('0101,南渡島,inflow,chronic,'));
    expect(dataLines).toHaveLength(2);
    expect(dataLines[0]).toBe('0101,南渡島,inflow,chronic,1,0102,,,0.4');
    expect(dataLines[1]).toBe('0101,南渡島,inflow,chronic,2,0103,北海道,渡島西部,0.1');
  });

  it('embeds the source SHA-256/page URL and both truncation notes in the preamble', () => {
    const group: FlowPhaseGroup = { self_rate: 0.9, self_rank: 1, partners: [], value_error_count: 0 };
    const flowEntry = makeFlowEntry('outflow', 'acute', group);

    const { text } = buildAreaFlowCsv({
      area,
      flowEntry,
      direction: 'outflow',
      phase: 'acute',
      directionLabels: FLOW_DIRECTION_LABELS,
      phaseLabels: FLOW_PHASE_LABELS,
      flowMetadata: FLOW_METADATA,
      areas,
    });

    expect(text).toContain('原典ファイル: R7/001723366.xlsx（SHA-256: dddd）');
    expect(text).toContain('掲載ページ: https://example.test/flow-page');
    expect(text).toContain('出力条件: 対象=構想区域 0101 南渡島（北海道）, 方向=流出率（outflow）, 区分=高度急性期+急性期（acute）');
    expect(text).toContain(
      '注記: 原典は一定数以上の患者がいる区域のみ表示するため、rateの合計は1になりません（表示されていない分は算出できません）'
    );
    expect(text).toContain('注記（全体値について）: 全体の流入率・流出率は3区分の合計ではありません');
  });
});
