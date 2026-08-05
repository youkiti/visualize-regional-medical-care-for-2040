import { describe, expect, it } from 'vitest';
import {
  buildAreaIndex,
  buildAreaMap,
  buildPrefectureMap,
  computeBBox,
  demandRatioKey as mjsDemandRatioKey,
  demandValueKey as mjsDemandValueKey,
  yoyActual2024Key as mjsYoyActual2024Key,
  yoyChangeRatioKey as mjsYoyChangeRatioKey,
  yoyPlanRatioKey as mjsYoyPlanRatioKey,
  yoyPlanValueKey as mjsYoyPlanValueKey,
} from '../../scripts/lib/merge.mjs';
import {
  demandRatioKey as tsDemandRatioKey,
  demandValueKey as tsDemandValueKey,
  yoyActual2024Key as tsYoyActual2024Key,
  yoyChangeRatioKey as tsYoyChangeRatioKey,
  yoyPlanRatioKey as tsYoyPlanRatioKey,
  yoyPlanValueKey as tsYoyPlanValueKey,
} from './metrics';

function makeArea(area_code: string, overrides: Partial<Record<string, unknown>> = {}) {
  return {
    area_code,
    area_name: `Area ${area_code}`,
    pref_code: area_code.slice(0, 2),
    pref_name: 'Pref',
    population_2020: 1000,
    area_km2: 12.3,
    outflow_rate: 0.1,
    inflow_rate: 0.2,
    beds: {
      total: { actual_2025: 100, need_2025: 80 },
      high_acute: { actual_2025: 10, need_2025: 0 },
      acute: { actual_2025: 40, need_2025: 30 },
      recovery: { actual_2025: 30, need_2025: 30 },
      chronic: { actual_2025: 20, need_2025: 20 },
    },
    ...overrides,
  };
}

// Minimal fixture for area_demand_R7.json's areas[]. Mirrors the shape
// described in the M4 brief (demand.<category>[<year as string>]).
function makeDemandArea(area_code: string, overrides: Partial<Record<string, unknown>> = {}) {
  return {
    area_code,
    area_name: `Area ${area_code}`,
    pref_code: area_code.slice(0, 2),
    pref_name: 'Pref',
    population_2024: 1000,
    population_2040: 900,
    demand: {
      home_care: { '2024': 100, '2030': 110, '2040': 120 },
      outpatient: { '2024': 200, '2030': 190, '2040': 180 },
    },
    ...overrides,
  };
}

function makeDemandData(areas: Array<Record<string, unknown>>) {
  return {
    categories: ['home_care', 'outpatient'],
    years: [2024, 2030, 2040],
    baseline_year: 2024,
    areas,
  };
}

// Minimal fixture for area_yoy_R6_R7.json's areas[] (M9). high_acute's
// plan_2025/actual_2024 default to 0 to exercise the 分母0→キー省略 path
// (real data: 70/339 areas have this for 高度急性期 — see YOY_RATIO_BIN_EDGES
// comment in metrics.ts).
function makeYoyArea(area_code: string, overrides: Partial<Record<string, unknown>> = {}) {
  return {
    area_code,
    area_name: `Area ${area_code}`,
    pref_code: area_code.slice(0, 2),
    pref_name: 'Pref',
    report_rate_2024: 1.0,
    report_rate_2025: 1.0,
    beds: {
      total: { plan_2025: 90, actual_2025: 100, actual_2024: 95 },
      high_acute: { plan_2025: 0, actual_2025: 10, actual_2024: 0 },
      acute: { plan_2025: 35, actual_2025: 40, actual_2024: 38 },
      recovery: { plan_2025: 28, actual_2025: 30, actual_2024: 29 },
      chronic: { plan_2025: 18, actual_2025: 20, actual_2024: 19 },
    },
    ...overrides,
  };
}

function makeYoyData(areas: Array<Record<string, unknown>>) {
  return {
    functions: ['total', 'high_acute', 'acute', 'recovery', 'chronic'],
    areas,
  };
}

function makePolygonFeature(area_code: string) {
  return {
    type: 'Feature',
    properties: {
      area_code,
      area_name: `Area ${area_code}`,
      pref_code: area_code.slice(0, 2),
      pref_name: 'Pref',
      boundary_source: 'test',
    },
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [100, 10],
          [101, 10],
          [101, 11],
          [100, 11],
          [100, 10],
        ],
      ],
    },
  };
}

function makeMultiPolygonFeature(area_code: string) {
  return {
    type: 'Feature',
    properties: {
      area_code,
      area_name: `Area ${area_code}`,
      pref_code: area_code.slice(0, 2),
      pref_name: 'Pref',
      boundary_source: 'test',
    },
    geometry: {
      type: 'MultiPolygon',
      coordinates: [
        [
          [
            [100, 10],
            [101, 10],
            [101, 11],
            [100, 11],
            [100, 10],
          ],
        ],
        [
          [
            [-5, -20],
            [-3, -20],
            [-3, -18],
            [-5, -18],
            [-5, -20],
          ],
        ],
      ],
    },
  };
}

describe('computeBBox', () => {
  it('computes the bbox of a Polygon', () => {
    const feature = makePolygonFeature('0001');
    expect(computeBBox(feature.geometry)).toEqual([100, 10, 101, 11]);
  });

  it('computes the bbox of a MultiPolygon across all parts', () => {
    const feature = makeMultiPolygonFeature('0002');
    expect(computeBBox(feature.geometry)).toEqual([-5, -20, 101, 11]);
  });

  it('throws for unsupported geometry types', () => {
    expect(() => computeBBox({ type: 'Point', coordinates: [0, 0] })).toThrow();
  });
});

describe('buildAreaMap', () => {
  it('produces flat scalar-only properties', () => {
    const boundaries = { features: [makePolygonFeature('0001')] };
    const indicators = { areas: [makeArea('0001')] };
    const demand = makeDemandData([makeDemandArea('0001')]);
    const yoy = makeYoyData([makeYoyArea('0001')]);

    const result = buildAreaMap(boundaries, indicators, demand, yoy);
    expect(result.features.length).toBe(1);

    const props = result.features[0].properties;
    for (const [key, value] of Object.entries(props)) {
      expect(
        typeof value === 'string' || typeof value === 'number',
        `property "${key}" should be a flat scalar, got ${typeof value}`
      ).toBe(true);
    }

    expect(props.area_code).toBe('0001');
    expect(props.a_total).toBe(100);
    expect(props.n_total).toBe(80);
    expect(props.r_total).toBeCloseTo(1.25);
  });

  it('omits the r_<fn> key entirely when need_2025 is 0', () => {
    const boundaries = { features: [makePolygonFeature('0001')] };
    const indicators = { areas: [makeArea('0001')] };
    const demand = makeDemandData([makeDemandArea('0001')]);
    const yoy = makeYoyData([makeYoyArea('0001')]);

    const result = buildAreaMap(boundaries, indicators, demand, yoy);
    const props = result.features[0].properties;

    expect(props.a_high_acute).toBe(10);
    expect(props.n_high_acute).toBe(0);
    expect('r_high_acute' in props).toBe(false);
  });

  it('computes correct bbox for Polygon and MultiPolygon features', () => {
    const boundaries = {
      features: [makePolygonFeature('0001'), makeMultiPolygonFeature('0002')],
    };
    const indicators = { areas: [makeArea('0001'), makeArea('0002')] };
    const demand = makeDemandData([makeDemandArea('0001'), makeDemandArea('0002')]);
    const yoy = makeYoyData([makeYoyArea('0001'), makeYoyArea('0002')]);

    const result = buildAreaMap(boundaries, indicators, demand, yoy);
    const [poly, multi] = result.features;

    expect([poly.properties.bb_w, poly.properties.bb_s, poly.properties.bb_e, poly.properties.bb_n]).toEqual([
      100, 10, 101, 11,
    ]);
    expect([multi.properties.bb_w, multi.properties.bb_s, multi.properties.bb_e, multi.properties.bb_n]).toEqual([
      -5, -20, 101, 11,
    ]);
  });

  it('throws when area_code sets differ between boundaries and indicators', () => {
    const boundaries = { features: [makePolygonFeature('0001'), makePolygonFeature('0002')] };
    const indicators = { areas: [makeArea('0001'), makeArea('0003')] };
    const demand = makeDemandData([makeDemandArea('0001'), makeDemandArea('0002')]);
    const yoy = makeYoyData([makeYoyArea('0001'), makeYoyArea('0002')]);

    expect(() => buildAreaMap(boundaries, indicators, demand, yoy)).toThrow();
  });

  it('adds flat demand value/ratio properties for every (category, year)', () => {
    const boundaries = { features: [makePolygonFeature('0001')] };
    const indicators = { areas: [makeArea('0001')] };
    const demand = makeDemandData([makeDemandArea('0001')]);
    const yoy = makeYoyData([makeYoyArea('0001')]);

    const result = buildAreaMap(boundaries, indicators, demand, yoy);
    const props = result.features[0].properties;

    expect(props.home_care_2024).toBe(100);
    expect(props.home_care_2030).toBe(110);
    expect(props.home_care_2040).toBe(120);
    expect(props.outpatient_2024).toBe(200);
    expect(props.outpatient_2030).toBe(190);
    expect(props.outpatient_2040).toBe(180);

    expect(props.home_care_r_2030).toBeCloseTo(1.1);
    expect(props.home_care_r_2040).toBeCloseTo(1.2);
    expect(props.outpatient_r_2030).toBeCloseTo(0.95);
    expect(props.outpatient_r_2040).toBeCloseTo(0.9);
  });

  it('sets the baseline-year (2024) demand ratio to exactly 1 for every category', () => {
    const boundaries = { features: [makePolygonFeature('0001')] };
    const indicators = { areas: [makeArea('0001')] };
    const demand = makeDemandData([makeDemandArea('0001')]);
    const yoy = makeYoyData([makeYoyArea('0001')]);

    const result = buildAreaMap(boundaries, indicators, demand, yoy);
    const props = result.features[0].properties;

    expect(props.home_care_r_2024).toBe(1);
    expect(props.outpatient_r_2024).toBe(1);
  });

  it('produces the same demand property keys as web/src/lib/metrics.ts', () => {
    const boundaries = { features: [makePolygonFeature('0001')] };
    const indicators = { areas: [makeArea('0001')] };
    const demand = makeDemandData([makeDemandArea('0001')]);
    const yoy = makeYoyData([makeYoyArea('0001')]);

    for (const category of demand.categories as Array<'home_care' | 'outpatient'>) {
      for (const year of demand.years) {
        expect(mjsDemandValueKey(category, year)).toBe(tsDemandValueKey(category, year));
        expect(mjsDemandRatioKey(category, year)).toBe(tsDemandRatioKey(category, year));
      }
    }

    // ...and those keys are exactly the ones buildAreaMap actually emits.
    const result = buildAreaMap(boundaries, indicators, demand, yoy);
    const props = result.features[0].properties;
    for (const category of demand.categories as Array<'home_care' | 'outpatient'>) {
      for (const year of demand.years) {
        expect(props[mjsDemandValueKey(category, year)]).toBeTypeOf('number');
        expect(props[mjsDemandRatioKey(category, year)]).toBeTypeOf('number');
      }
    }
  });

  it('throws when a demand area is missing for a boundary area_code', () => {
    const boundaries = { features: [makePolygonFeature('0001'), makePolygonFeature('0002')] };
    const indicators = { areas: [makeArea('0001'), makeArea('0002')] };
    // demand only has 0001, but boundaries/indicators have 0001+0002.
    const demand = makeDemandData([makeDemandArea('0001')]);
    const yoy = makeYoyData([makeYoyArea('0001'), makeYoyArea('0002')]);

    expect(() => buildAreaMap(boundaries, indicators, demand, yoy)).toThrow();
  });

  it('throws when a demand area is missing a category', () => {
    const boundaries = { features: [makePolygonFeature('0001')] };
    const indicators = { areas: [makeArea('0001')] };
    const brokenDemandArea = makeDemandArea('0001', {
      demand: { home_care: { '2024': 100, '2030': 110, '2040': 120 } }, // outpatient missing
    });
    const demand = makeDemandData([brokenDemandArea]);
    const yoy = makeYoyData([makeYoyArea('0001')]);

    expect(() => buildAreaMap(boundaries, indicators, demand, yoy)).toThrow();
  });

  it('throws when a demand value is non-numeric', () => {
    const boundaries = { features: [makePolygonFeature('0001')] };
    const indicators = { areas: [makeArea('0001')] };
    const brokenDemandArea = makeDemandArea('0001', {
      demand: {
        home_care: { '2024': 100, '2030': 'XXX', '2040': 120 },
        outpatient: { '2024': 200, '2030': 190, '2040': 180 },
      },
    });
    const demand = makeDemandData([brokenDemandArea]);
    const yoy = makeYoyData([makeYoyArea('0001')]);

    expect(() => buildAreaMap(boundaries, indicators, demand, yoy)).toThrow();
  });

  // ---- YoY (R6→R7 公表年度間比較, M9) ---------------------------------------

  it('adds flat YoY raw-value properties (always present) for every function', () => {
    const boundaries = { features: [makePolygonFeature('0001')] };
    const indicators = { areas: [makeArea('0001')] };
    const demand = makeDemandData([makeDemandArea('0001')]);
    const yoy = makeYoyData([makeYoyArea('0001')]);

    const result = buildAreaMap(boundaries, indicators, demand, yoy);
    const props = result.features[0].properties;

    expect(props.y_plan_total).toBe(90);
    expect(props.y_a24_total).toBe(95);
    expect(props.y_plan_acute).toBe(35);
    expect(props.y_a24_acute).toBe(38);
  });

  it('adds flat YoY ratio properties (実績2025÷見込量2025, 実績2025÷実績2024) when the denominator is non-zero', () => {
    const boundaries = { features: [makePolygonFeature('0001')] };
    const indicators = { areas: [makeArea('0001')] };
    const demand = makeDemandData([makeDemandArea('0001')]);
    const yoy = makeYoyData([makeYoyArea('0001')]);

    const result = buildAreaMap(boundaries, indicators, demand, yoy);
    const props = result.features[0].properties;

    expect(props.y_pa_total).toBeCloseTo(100 / 90);
    expect(props.y_yy_total).toBeCloseTo(100 / 95);
  });

  it('omits the y_pa_<fn>/y_yy_<fn> keys entirely when their denominator is 0 (not 0, not Infinity)', () => {
    const boundaries = { features: [makePolygonFeature('0001')] };
    const indicators = { areas: [makeArea('0001')] };
    const demand = makeDemandData([makeDemandArea('0001')]);
    // high_acute has plan_2025=0 and actual_2024=0 (mirrors real data:
    // 70/339 areas for 高度急性期 — see YOY_RATIO_BIN_EDGES comment).
    const yoy = makeYoyData([makeYoyArea('0001')]);

    const result = buildAreaMap(boundaries, indicators, demand, yoy);
    const props = result.features[0].properties;

    expect(props.y_plan_high_acute).toBe(0);
    expect(props.y_a24_high_acute).toBe(0);
    expect('y_pa_high_acute' in props).toBe(false);
    expect('y_yy_high_acute' in props).toBe(false);
  });

  it('produces the same YoY property keys as web/src/lib/metrics.ts', () => {
    const boundaries = { features: [makePolygonFeature('0001')] };
    const indicators = { areas: [makeArea('0001')] };
    const demand = makeDemandData([makeDemandArea('0001')]);
    const yoy = makeYoyData([makeYoyArea('0001')]);

    for (const fn of yoy.functions as Array<'total' | 'high_acute' | 'acute' | 'recovery' | 'chronic'>) {
      expect(mjsYoyPlanRatioKey(fn)).toBe(tsYoyPlanRatioKey(fn));
      expect(mjsYoyChangeRatioKey(fn)).toBe(tsYoyChangeRatioKey(fn));
      expect(mjsYoyPlanValueKey(fn)).toBe(tsYoyPlanValueKey(fn));
      expect(mjsYoyActual2024Key(fn)).toBe(tsYoyActual2024Key(fn));
    }

    // ...and those keys are exactly the ones buildAreaMap actually emits
    // (for a function whose denominators are non-zero, e.g. 'total').
    const result = buildAreaMap(boundaries, indicators, demand, yoy);
    const props = result.features[0].properties;
    expect(props[mjsYoyPlanValueKey('total')]).toBeTypeOf('number');
    expect(props[mjsYoyActual2024Key('total')]).toBeTypeOf('number');
    expect(props[mjsYoyPlanRatioKey('total')]).toBeTypeOf('number');
    expect(props[mjsYoyChangeRatioKey('total')]).toBeTypeOf('number');
  });

  it('throws when a yoy area is missing for a boundary area_code', () => {
    const boundaries = { features: [makePolygonFeature('0001'), makePolygonFeature('0002')] };
    const indicators = { areas: [makeArea('0001'), makeArea('0002')] };
    const demand = makeDemandData([makeDemandArea('0001'), makeDemandArea('0002')]);
    // yoy only has 0001, but boundaries/indicators/demand have 0001+0002.
    const yoy = makeYoyData([makeYoyArea('0001')]);

    expect(() => buildAreaMap(boundaries, indicators, demand, yoy)).toThrow();
  });
});

describe('buildAreaIndex', () => {
  it('produces one lightweight entry per boundary feature, in order', () => {
    const boundaries = { features: [makePolygonFeature('0001'), makeMultiPolygonFeature('0002')] };

    const result = buildAreaIndex(boundaries);
    expect(result.length).toBe(2);
    expect(result.map((e) => e.area_code)).toEqual(['0001', '0002']);
  });

  it('carries boundary_source through from the feature properties', () => {
    const feature = makePolygonFeature('0001');
    feature.properties.boundary_source = 'A38-20（国土数値情報）';
    const boundaries = { features: [feature] };

    const [entry] = buildAreaIndex(boundaries);
    expect(entry.boundary_source).toBe('A38-20（国土数値情報）');
  });

  it('computes the same bbox as buildAreaMap for Polygon and MultiPolygon features', () => {
    const boundaries = {
      features: [makePolygonFeature('0001'), makeMultiPolygonFeature('0002')],
    };
    const indicators = { areas: [makeArea('0001'), makeArea('0002')] };
    const demand = makeDemandData([makeDemandArea('0001'), makeDemandArea('0002')]);
    const yoy = makeYoyData([makeYoyArea('0001'), makeYoyArea('0002')]);

    const mapResult = buildAreaMap(boundaries, indicators, demand, yoy);
    const indexResult = buildAreaIndex(boundaries);

    for (let i = 0; i < indexResult.length; i++) {
      const mapProps = mapResult.features[i].properties;
      const indexEntry = indexResult[i];
      expect([indexEntry.bb_w, indexEntry.bb_s, indexEntry.bb_e, indexEntry.bb_n]).toEqual([
        mapProps.bb_w,
        mapProps.bb_s,
        mapProps.bb_e,
        mapProps.bb_n,
      ]);
    }
  });

  it('only exposes the documented fields (area_code/boundary_source/bbox)', () => {
    const boundaries = { features: [makePolygonFeature('0001')] };
    const [entry] = buildAreaIndex(boundaries);
    expect(Object.keys(entry).sort()).toEqual(['area_code', 'bb_e', 'bb_n', 'bb_s', 'bb_w', 'boundary_source']);
  });
});

// ---- buildPrefectureMap (概観レイヤ) ---------------------------------------
//
// 区域側と同じフラットなプロパティ名(a_/n_/r_<機能>・demandValueKey/
// demandRatioKey)を出すことを固定する。ここがずれると、地図の色が
// 片方の層でだけ静かに無色になる(CLAUDE.md「可視化実装で判明した罠」10と同型)。

function makePrefecture(pref_code: string, overrides: Partial<Record<string, unknown>> = {}) {
  return {
    pref_code,
    pref_name: `Pref ${pref_code}`,
    area_count: 3,
    population_2020: 100000,
    area_km2: 456.7,
    population_2024: 99000,
    population_2040: 88000,
    beds: {
      total: { actual_2025: 1000, need_2025: 800 },
      high_acute: { actual_2025: 100, need_2025: 0 },
      acute: { actual_2025: 400, need_2025: 300 },
      recovery: { actual_2025: 300, need_2025: 300 },
      chronic: { actual_2025: 200, need_2025: 200 },
    },
    demand: {
      home_care: { '2024': 1000, '2030': 1100, '2040': 1200 },
      outpatient: { '2024': 2000, '2030': 1900, '2040': 1800 },
    },
    ...overrides,
  };
}

function makePrefectureIndicators(prefectures: Array<Record<string, unknown>>) {
  return {
    categories: ['home_care', 'outpatient'],
    years: [2024, 2030, 2040],
    baseline_year: 2024,
    prefectures,
  };
}

function makePrefFeature(pref_code: string) {
  return {
    type: 'Feature',
    properties: {
      pref_code,
      pref_name: `Pref ${pref_code}`,
      boundary_source: 'test',
    },
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [130, 30],
          [131, 30],
          [131, 31],
          [130, 31],
          [130, 30],
        ],
      ],
    },
  };
}

describe('buildPrefectureMap', () => {
  it('emits the same flat bed property names as buildAreaMap', () => {
    const out = buildPrefectureMap(
      { features: [makePrefFeature('01')] },
      makePrefectureIndicators([makePrefecture('01')])
    );
    const props = out.features[0].properties;

    expect(props.pref_code).toBe('01');
    expect(props.pref_name).toBe('Pref 01');
    expect(props.boundary_source).toBe('test');
    expect(props.a_total).toBe(1000);
    expect(props.n_total).toBe(800);
    expect(props.r_total).toBeCloseTo(1000 / 800);
    // 区域固有のキーは持たない
    expect(props.area_code).toBeUndefined();
    expect(props.area_name).toBeUndefined();
  });

  it('omits r_<fn> when need_2025 is 0 (same rule as buildAreaMap)', () => {
    const out = buildPrefectureMap(
      { features: [makePrefFeature('01')] },
      makePrefectureIndicators([makePrefecture('01')])
    );
    const props = out.features[0].properties;
    expect(props.a_high_acute).toBe(100);
    expect(props.n_high_acute).toBe(0);
    expect('r_high_acute' in props).toBe(false);
  });

  it('emits demand value/ratio keys under the shared key functions', () => {
    const out = buildPrefectureMap(
      { features: [makePrefFeature('01')] },
      makePrefectureIndicators([makePrefecture('01')])
    );
    const props = out.features[0].properties;

    expect(props[mjsDemandValueKey('home_care', 2040)]).toBe(1200);
    expect(props[mjsDemandRatioKey('home_care', 2040)]).toBeCloseTo(1200 / 1000);
    expect(props[tsDemandValueKey('outpatient', 2030)]).toBe(1900);
    expect(props[tsDemandRatioKey('outpatient', 2030)]).toBeCloseTo(1900 / 2000);
    // 基準年は定義上ちょうど1.0
    expect(props[mjsDemandRatioKey('home_care', 2024)]).toBe(1);
  });

  it('attaches the feature bbox', () => {
    const out = buildPrefectureMap(
      { features: [makePrefFeature('01')] },
      makePrefectureIndicators([makePrefecture('01')])
    );
    const props = out.features[0].properties;
    expect([props.bb_w, props.bb_s, props.bb_e, props.bb_n]).toEqual([130, 30, 131, 31]);
  });

  it('preserves the boundary feature order', () => {
    const out = buildPrefectureMap(
      { features: [makePrefFeature('02'), makePrefFeature('01')] },
      makePrefectureIndicators([makePrefecture('01'), makePrefecture('02')])
    );
    expect(out.features.map((f) => f.properties.pref_code)).toEqual(['02', '01']);
  });

  it('throws when the pref_code sets differ', () => {
    expect(() =>
      buildPrefectureMap(
        { features: [makePrefFeature('01'), makePrefFeature('02')] },
        makePrefectureIndicators([makePrefecture('01')])
      )
    ).toThrow(/pref_code sets differ/);
  });

  it('throws when a demand year is missing rather than emitting NaN', () => {
    const broken = makePrefecture('01', {
      demand: {
        home_care: { '2024': 1000, '2030': 1100 }, // 2040 欠落
        outpatient: { '2024': 2000, '2030': 1900, '2040': 1800 },
      },
    });
    expect(() =>
      buildPrefectureMap({ features: [makePrefFeature('01')] }, makePrefectureIndicators([broken]))
    ).toThrow(/demand\.home_care\[2040\]/);
  });

  it('throws when beds for a function are missing rather than emitting undefined', () => {
    const broken = makePrefecture('01', {
      beds: {
        total: { actual_2025: 1000, need_2025: 800 },
        high_acute: { actual_2025: 100, need_2025: 0 },
        acute: { actual_2025: 400, need_2025: 300 },
        recovery: { actual_2025: 300, need_2025: 300 },
        // chronic 欠落
      },
    });
    expect(() =>
      buildPrefectureMap({ features: [makePrefFeature('01')] }, makePrefectureIndicators([broken]))
    ).toThrow(/beds\.chronic/);
  });
});
