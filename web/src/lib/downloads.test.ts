import { describe, expect, it } from 'vitest';
import { buildAreaDetailCsv, buildAreaTableCsv, buildFacilityCsv } from './downloads';
import type {
  AreaDemandArea,
  AreaDemandData,
  AreaIndicator,
  AreaIndicatorsData,
  BedFunctionKey,
  Facility,
  FacilityMetric,
  FacilityShard,
  FacilitySummaryMetadata,
  FacilityValueStatus,
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

    const { filename, text } = buildAreaTableCsv({ indicators, demand, metric: 'ratio', bedFunction: 'high_acute', year: 2024 });

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

    const { filename, text } = buildAreaTableCsv({ indicators, demand, metric: 'actual', bedFunction: 'total', year: 2024 });

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

    const { filename, text } = buildAreaTableCsv({
      indicators,
      demand,
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

    const { filename, text } = buildAreaTableCsv({
      indicators,
      demand,
      metric: 'demand_outpatient',
      bedFunction: 'total',
      year: 2040,
    });

    expect(filename).toBe('area_demand_outpatient_2040_R7.csv');
    const row = text.split('\r\n').find((l) => l.startsWith('R7,0101,'))!;
    expect(row).toBe('R7,0101,南渡島,01,北海道,外来,2040,2040年度（現状投影）,211020.46,261882.17,0.8058');
  });
});

// ---- buildAreaDetailCsv -----------------------------------------------------

describe('buildAreaDetailCsv', () => {
  const baseArgs = {
    indicatorsMetadata: INDICATORS_METADATA,
    demandMetadata: DEMAND_METADATA,
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
