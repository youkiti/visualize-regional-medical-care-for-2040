import { describe, expect, it } from 'vitest';
import {
  demandRatioKey as mjsDemandRatioKey,
  demandValueKey as mjsDemandValueKey,
  yoyActual2024Key as mjsYoyActual2024Key,
  yoyChangeRatioKey as mjsYoyChangeRatioKey,
  yoyPlanRatioKey as mjsYoyPlanRatioKey,
  yoyPlanValueKey as mjsYoyPlanValueKey,
} from '../../scripts/lib/merge.mjs';
import {
  classifyBin,
  classifyDemandRatioBin,
  classifyRatioBin,
  classifyYoyRatioBin,
  computeQuantileEdges,
  computeRatio,
  computeSequentialClasses,
  demandCategoryOf,
  demandRatioKey,
  demandValueKey,
  DEMAND_RATIO_BIN_EDGES,
  DEMAND_RATIO_BIN_LABELS,
  distinctEdges,
  formatChangeRatio,
  formatDiff,
  formatInteger,
  formatPercent,
  formatRatio,
  formatReceipts,
  formatYoyChangeRatio,
  formatYoyRatio,
  isDemandMetric,
  isYoyMetric,
  RATIO_BIN_COLORS,
  RATIO_BIN_EDGES,
  RATIO_BIN_LABELS,
  readDemandRatio,
  readDemandValue,
  readYoyRatio,
  readYoyValue,
  SEQUENTIAL_RAMP_COLORS,
  selectRampColors,
  YOY_RATIO_BIN_EDGES,
  YOY_RATIO_BIN_LABELS,
  YOY_UNAVAILABLE_CELL_LABEL,
  yoyActual2024Key,
  yoyChangeRatioKey,
  yoyPlanRatioKey,
  yoyPlanValueKey,
} from './metrics';

describe('computeRatio', () => {
  it('computes actual/need for the normal case', () => {
    expect(computeRatio(100, 50)).toBe(2);
    expect(computeRatio(50, 100)).toBe(0.5);
  });

  it('returns null (算出不可) when need=0 and actual=0', () => {
    expect(computeRatio(0, 0)).toBeNull();
  });

  it('returns null (算出不可, not 0 or Infinity) when need=0 and actual>0', () => {
    const r = computeRatio(120, 0);
    expect(r).toBeNull();
    expect(r).not.toBe(0);
    expect(r).not.toBe(Infinity);
  });
});

describe('classifyRatioBin', () => {
  it('has 7 bins with matching colors/labels', () => {
    expect(RATIO_BIN_COLORS.length).toBe(7);
    expect(RATIO_BIN_LABELS.length).toBe(7);
    expect(RATIO_BIN_EDGES.length).toBe(6);
  });

  it('classifies values well inside each bin', () => {
    expect(classifyRatioBin(0.5)).toBe(0);
    expect(classifyRatioBin(0.8)).toBe(1);
    expect(classifyRatioBin(0.9)).toBe(2);
    expect(classifyRatioBin(1.0)).toBe(3);
    expect(classifyRatioBin(1.1)).toBe(4);
    expect(classifyRatioBin(1.2)).toBe(5);
    expect(classifyRatioBin(2.83)).toBe(6);
  });

  it('boundary values are inclusive on the lower edge, exclusive on the upper edge', () => {
    // Each boundary belongs to the bin that starts at that value, not the
    // bin that ends there.
    expect(classifyRatioBin(0.77)).toBe(1);
    expect(classifyRatioBin(0.87)).toBe(2);
    expect(classifyRatioBin(0.95)).toBe(3);
    expect(classifyRatioBin(1.05)).toBe(4);
    expect(classifyRatioBin(1.15)).toBe(5);
    expect(classifyRatioBin(1.3)).toBe(6);
  });

  it('values just below a boundary stay in the lower bin', () => {
    expect(classifyRatioBin(0.7699999)).toBe(0);
    expect(classifyRatioBin(1.2999999)).toBe(5);
  });
});

describe('classifyBin (generalized)', () => {
  it('classifyRatioBin is a thin wrapper around classifyBin(r, RATIO_BIN_EDGES)', () => {
    for (const r of [0.5, 0.77, 0.8, 0.87, 0.95, 1.0, 1.05, 1.15, 1.3, 2.83]) {
      expect(classifyBin(r, RATIO_BIN_EDGES)).toBe(classifyRatioBin(r));
    }
  });

  it('classifies with an arbitrary edge list, inclusive lower / exclusive upper', () => {
    const edges = [10, 20, 30];
    expect(classifyBin(5, edges)).toBe(0);
    expect(classifyBin(10, edges)).toBe(1);
    expect(classifyBin(19.999, edges)).toBe(1);
    expect(classifyBin(20, edges)).toBe(2);
    expect(classifyBin(30, edges)).toBe(3);
    expect(classifyBin(1000, edges)).toBe(3);
  });
});

describe('classifyDemandRatioBin', () => {
  it('has 7 bins with matching labels, reusing the 7-color RATIO_BIN_COLORS palette', () => {
    expect(RATIO_BIN_COLORS.length).toBe(7);
    expect(DEMAND_RATIO_BIN_LABELS.length).toBe(7);
    expect(DEMAND_RATIO_BIN_EDGES.length).toBe(6);
  });

  it('classifies values well inside each bin', () => {
    expect(classifyDemandRatioBin(0.5)).toBe(0);
    expect(classifyDemandRatioBin(0.75)).toBe(1);
    expect(classifyDemandRatioBin(0.9)).toBe(2);
    expect(classifyDemandRatioBin(1.0)).toBe(3);
    expect(classifyDemandRatioBin(1.1)).toBe(4);
    expect(classifyDemandRatioBin(1.35)).toBe(5);
    expect(classifyDemandRatioBin(2.02)).toBe(6);
  });

  it('boundary values are inclusive on the lower edge, exclusive on the upper edge', () => {
    expect(classifyDemandRatioBin(0.67)).toBe(1);
    expect(classifyDemandRatioBin(0.83)).toBe(2);
    expect(classifyDemandRatioBin(0.95)).toBe(3);
    expect(classifyDemandRatioBin(1.05)).toBe(4);
    expect(classifyDemandRatioBin(1.2)).toBe(5);
    expect(classifyDemandRatioBin(1.5)).toBe(6);
  });

  it('values just below a boundary stay in the lower bin', () => {
    expect(classifyDemandRatioBin(0.6699999)).toBe(0);
    expect(classifyDemandRatioBin(1.4999999)).toBe(5);
  });

  it('covers the observed data range for both categories (home_care 0.76-2.02, outpatient 0.51-1.23)', () => {
    expect(classifyDemandRatioBin(0.51)).toBe(0);
    expect(classifyDemandRatioBin(0.76)).toBe(1);
    expect(classifyDemandRatioBin(1.23)).toBe(5);
    expect(classifyDemandRatioBin(2.02)).toBe(6);
  });
});

describe('classifyYoyRatioBin', () => {
  it('has 7 bins with matching labels, reusing the 7-color RATIO_BIN_COLORS palette', () => {
    expect(RATIO_BIN_COLORS.length).toBe(7);
    expect(YOY_RATIO_BIN_LABELS.length).toBe(7);
    expect(YOY_RATIO_BIN_EDGES.length).toBe(6);
  });

  it('the edges are strictly ascending', () => {
    for (let i = 1; i < YOY_RATIO_BIN_EDGES.length; i++) {
      expect(YOY_RATIO_BIN_EDGES[i]).toBeGreaterThan(YOY_RATIO_BIN_EDGES[i - 1]);
    }
  });

  it('classifies values well inside each bin', () => {
    expect(classifyYoyRatioBin(0.5)).toBe(0);
    expect(classifyYoyRatioBin(0.9)).toBe(1);
    expect(classifyYoyRatioBin(0.95)).toBe(2);
    expect(classifyYoyRatioBin(1.0)).toBe(3);
    expect(classifyYoyRatioBin(1.05)).toBe(4);
    expect(classifyYoyRatioBin(1.1)).toBe(5);
    expect(classifyYoyRatioBin(2.0)).toBe(6);
  });

  it('boundary values are inclusive on the lower edge, exclusive on the upper edge', () => {
    expect(classifyYoyRatioBin(0.85)).toBe(1);
    expect(classifyYoyRatioBin(0.93)).toBe(2);
    expect(classifyYoyRatioBin(0.98)).toBe(3);
    expect(classifyYoyRatioBin(1.02)).toBe(4);
    expect(classifyYoyRatioBin(1.075)).toBe(5);
    expect(classifyYoyRatioBin(1.18)).toBe(6);
  });

  it('values just below a boundary stay in the lower bin', () => {
    expect(classifyYoyRatioBin(0.8499999)).toBe(0);
    expect(classifyYoyRatioBin(1.1799999)).toBe(5);
  });
});

describe('isDemandMetric / demandCategoryOf', () => {
  it('is true only for the 2 demand metric kinds', () => {
    expect(isDemandMetric('demand_home_care')).toBe(true);
    expect(isDemandMetric('demand_outpatient')).toBe(true);
    expect(isDemandMetric('ratio')).toBe(false);
    expect(isDemandMetric('actual')).toBe(false);
    expect(isDemandMetric('need')).toBe(false);
  });

  it('maps each DemandMetricKind to its DemandCategoryKey', () => {
    expect(demandCategoryOf('demand_home_care')).toBe('home_care');
    expect(demandCategoryOf('demand_outpatient')).toBe('outpatient');
  });
});

describe('isYoyMetric', () => {
  it('is true only for the 2 YoY (R6→R7) metric kinds', () => {
    expect(isYoyMetric('yoy_plan_vs_actual')).toBe(true);
    expect(isYoyMetric('yoy_actual_change')).toBe(true);
    expect(isYoyMetric('ratio')).toBe(false);
    expect(isYoyMetric('actual')).toBe(false);
    expect(isYoyMetric('need')).toBe(false);
    expect(isYoyMetric('demand_home_care')).toBe(false);
    expect(isYoyMetric('demand_outpatient')).toBe(false);
  });
});

describe('demand property key helpers', () => {
  it('demandValueKey/demandRatioKey match the merge.mjs implementation used by sync-data', () => {
    for (const category of ['home_care', 'outpatient'] as const) {
      for (const year of [2024, 2030, 2035, 2040, 2045, 2050]) {
        expect(demandValueKey(category, year)).toBe(mjsDemandValueKey(category, year));
        expect(demandRatioKey(category, year)).toBe(mjsDemandRatioKey(category, year));
      }
    }
  });

  it('demandValueKey/demandRatioKey follow the documented naming rule', () => {
    expect(demandValueKey('home_care', 2040)).toBe('home_care_2040');
    expect(demandRatioKey('home_care', 2040)).toBe('home_care_r_2040');
    expect(demandValueKey('outpatient', 2024)).toBe('outpatient_2024');
    expect(demandRatioKey('outpatient', 2024)).toBe('outpatient_r_2024');
  });
});

describe('YoY (R6→R7) property key helpers', () => {
  const FUNCTIONS = ['total', 'high_acute', 'acute', 'recovery', 'chronic'] as const;

  it('yoyPlanRatioKey/yoyChangeRatioKey/yoyPlanValueKey/yoyActual2024Key match the merge.mjs implementation used by sync-data', () => {
    for (const fn of FUNCTIONS) {
      expect(yoyPlanRatioKey(fn)).toBe(mjsYoyPlanRatioKey(fn));
      expect(yoyChangeRatioKey(fn)).toBe(mjsYoyChangeRatioKey(fn));
      expect(yoyPlanValueKey(fn)).toBe(mjsYoyPlanValueKey(fn));
      expect(yoyActual2024Key(fn)).toBe(mjsYoyActual2024Key(fn));
    }
  });

  it('follow the documented naming rule', () => {
    expect(yoyPlanRatioKey('total')).toBe('y_pa_total');
    expect(yoyChangeRatioKey('total')).toBe('y_yy_total');
    expect(yoyPlanValueKey('total')).toBe('y_plan_total');
    expect(yoyActual2024Key('total')).toBe('y_a24_total');
    expect(yoyPlanRatioKey('high_acute')).toBe('y_pa_high_acute');
    expect(yoyChangeRatioKey('high_acute')).toBe('y_yy_high_acute');
  });
});

describe('readYoyRatio / readYoyValue', () => {
  const props = { y_pa_total: 1.03, y_a24_total: 5243, y_yy_high_acute: 0.7 };

  it('reads a present numeric ratio for the given metric', () => {
    expect(readYoyRatio(props, 'yoy_plan_vs_actual', 'total')).toBeCloseTo(1.03);
    expect(readYoyRatio(props, 'yoy_actual_change', 'high_acute')).toBeCloseTo(0.7);
  });

  it('returns null (算出不可) for a missing ratio key', () => {
    expect(readYoyRatio(props, 'yoy_actual_change', 'total')).toBeNull();
    expect(readYoyRatio(props, 'yoy_plan_vs_actual', 'high_acute')).toBeNull();
  });

  it('readYoyValue reads a raw value by its already-built key', () => {
    expect(readYoyValue(props, 'y_a24_total')).toBe(5243);
    expect(readYoyValue(props, 'y_plan_total')).toBeNull();
  });
});

describe('readDemandValue / readDemandRatio', () => {
  const props = { home_care_2040: 5464.6, home_care_r_2040: 1.247, outpatient_2024: 261882 };

  it('reads a present numeric value', () => {
    expect(readDemandValue(props, 'home_care', 2040)).toBeCloseTo(5464.6);
    expect(readDemandRatio(props, 'home_care', 2040)).toBeCloseTo(1.247);
  });

  it('returns null for a missing key', () => {
    expect(readDemandValue(props, 'outpatient', 2040)).toBeNull();
    expect(readDemandRatio(props, 'outpatient', 2040)).toBeNull();
  });

  it('returns null for a non-numeric value', () => {
    expect(readDemandValue({ home_care_2040: 'XXX' }, 'home_care', 2040)).toBeNull();
  });
});

describe('computeQuantileEdges', () => {
  it('produces binCount+1 non-decreasing edges spanning [min, max]', () => {
    const values = Array.from({ length: 339 }, (_, i) => i + 1);
    const edges = computeQuantileEdges(values);
    expect(edges.length).toBe(8);
    expect(edges[0]).toBe(1);
    expect(edges[edges.length - 1]).toBe(339);
    for (let i = 1; i < edges.length; i++) {
      expect(edges[i]).toBeGreaterThanOrEqual(edges[i - 1]);
    }
  });

  it('does not crash when many values are duplicated', () => {
    const values = [
      ...Array.from({ length: 300 }, () => 10),
      ...Array.from({ length: 39 }, (_, i) => 100 + i),
    ];
    const edges = computeQuantileEdges(values);
    expect(edges.length).toBe(8);
    expect(edges.every((e) => Number.isFinite(e))).toBe(true);
  });

  it('does not crash when all values are identical', () => {
    const values = Array.from({ length: 339 }, () => 42);
    const edges = computeQuantileEdges(values);
    expect(edges.every((e) => e === 42)).toBe(true);
  });

  it('handles empty input without crashing', () => {
    const edges = computeQuantileEdges([]);
    expect(edges.length).toBe(8);
    expect(edges.every((e) => Number.isFinite(e))).toBe(true);
  });
});

describe('distinctEdges', () => {
  it('returns the edges unchanged when already strictly ascending', () => {
    const edges = [0, 10, 20, 30, 40, 50, 60, 70];
    expect(distinctEdges(edges)).toEqual([0, 10, 20, 30, 40, 50, 60, 70]);
  });

  it('collapses duplicate leading edges (real-data degeneracy: 高度急性期 x 実績病床数)', () => {
    // 339区域中69区域が0床のときの computeQuantileEdges() 相当の入力。
    const edges = [0, 0, 11.57, 40.86, 187.14, 409.86, 1073.71, 7764];
    expect(distinctEdges(edges)).toEqual([0, 11.57, 40.86, 187.14, 409.86, 1073.71, 7764]);
  });

  it('collapses duplicates anywhere in the sequence, not just at the ends', () => {
    const edges = [0, 0, 0, 5, 10, 10, 10, 20];
    expect(distinctEdges(edges)).toEqual([0, 5, 10, 20]);
  });

  it('collapses an all-equal edge list down to a single bin (2 identical edges)', () => {
    const edges = new Array(8).fill(42);
    expect(distinctEdges(edges)).toEqual([42, 42]);
  });

  it('does not crash on empty input', () => {
    expect(distinctEdges([])).toEqual([0, 0]);
  });
});

describe('selectRampColors', () => {
  it('returns the full palette unchanged when binCount equals the palette length', () => {
    expect(selectRampColors(SEQUENTIAL_RAMP_COLORS, 7)).toEqual([...SEQUENTIAL_RAMP_COLORS]);
  });

  it('picks indices [0,1,2,4,5,6] for 6 bins out of a 7-color palette', () => {
    const picked = selectRampColors(SEQUENTIAL_RAMP_COLORS, 6);
    const expected = [0, 1, 2, 4, 5, 6].map((i) => SEQUENTIAL_RAMP_COLORS[i]);
    expect(picked).toEqual(expected);
  });

  it('always includes both palette endpoints (binCount >= 2)', () => {
    // A single bin has only one color slot, so it can't hold both distinct
    // endpoints — that case is covered separately below.
    for (let binCount = 2; binCount <= 7; binCount++) {
      const picked = selectRampColors(SEQUENTIAL_RAMP_COLORS, binCount);
      expect(picked[0]).toBe(SEQUENTIAL_RAMP_COLORS[0]);
      expect(picked[picked.length - 1]).toBe(SEQUENTIAL_RAMP_COLORS[SEQUENTIAL_RAMP_COLORS.length - 1]);
    }
  });

  it('returns a single color for a single bin', () => {
    expect(selectRampColors(SEQUENTIAL_RAMP_COLORS, 1)).toEqual([SEQUENTIAL_RAMP_COLORS[0]]);
  });

  it('returns an empty array for zero bins', () => {
    expect(selectRampColors(SEQUENTIAL_RAMP_COLORS, 0)).toEqual([]);
  });
});

describe('computeSequentialClasses', () => {
  it('produces one fewer color than edges, matching distinctEdges', () => {
    const edges = [0, 10, 20, 30, 40, 50, 60, 70];
    const { edges: outEdges, colors } = computeSequentialClasses(edges);
    expect(outEdges).toEqual(edges);
    expect(colors.length).toBe(outEdges.length - 1);
    expect(colors).toEqual([...SEQUENTIAL_RAMP_COLORS]);
  });

  it('degenerates to 6 bins/colors for the real 高度急性期 x 実績病床数 case', () => {
    const rawEdges = [0, 0, 11.57, 40.86, 187.14, 409.86, 1073.71, 7764];
    const { edges, colors } = computeSequentialClasses(rawEdges);
    expect(edges).toEqual([0, 11.57, 40.86, 187.14, 409.86, 1073.71, 7764]);
    expect(colors.length).toBe(6);
    expect(colors).toEqual([0, 1, 2, 4, 5, 6].map((i) => SEQUENTIAL_RAMP_COLORS[i]));
  });

  it('degenerates to a single bin/color when every value is identical', () => {
    const rawEdges = new Array(8).fill(42);
    const { edges, colors } = computeSequentialClasses(rawEdges);
    expect(edges).toEqual([42, 42]);
    expect(colors).toEqual([SEQUENTIAL_RAMP_COLORS[0]]);
  });
});

describe('formatting', () => {
  it('formatInteger adds thousands separators', () => {
    expect(formatInteger(4995)).toBe('4,995');
    expect(formatInteger(0)).toBe('0');
  });

  it('formatRatio shows two decimal places with a 倍 suffix', () => {
    expect(formatRatio(1.0287)).toBe('1.03倍');
    expect(formatRatio(0.5)).toBe('0.50倍');
  });

  it('formatRatio shows the 算出不可 string for null', () => {
    expect(formatRatio(null)).toBe('—（必要数0）');
  });

  it('formatPercent shows the XXX 未算出 string for null', () => {
    expect(formatPercent(null)).toBe('未算出（原典 XXX）');
    expect(formatPercent(0.035)).toBe('3.5%');
  });

  it('formatDiff signs positive differences', () => {
    expect(formatDiff(120, 100)).toBe('+20');
    expect(formatDiff(80, 100)).toBe('-20');
    expect(formatDiff(100, 100)).toBe('0');
  });

  it('formatChangeRatio signs increases/decreases with one decimal place', () => {
    expect(formatChangeRatio(1.304)).toBe('+30.4%');
    expect(formatChangeRatio(0.828)).toBe('-17.2%');
    expect(formatChangeRatio(1)).toBe('0.0%');
  });

  it('formatChangeRatio rounds to one decimal place', () => {
    expect(formatChangeRatio(1.2465)).toBe('+24.6%'); // (ratio-1)*100 = 24.65 -> banker-free round via toFixed
  });

  it('formatChangeRatio normalizes changes that round to zero, in both directions', () => {
    // A minus sign next to a rounded zero reads as a decrease the digits do not
    // show. Both real occurrences in area_demand_R7.json are covered here.
    expect(formatChangeRatio(0.9999)).toBe('0.0%'); // -0.01% -> rounds away
    expect(formatChangeRatio(0.9996251416768416)).toBe('0.0%'); // 峡南・在宅2050年度
    expect(formatChangeRatio(0.9999236248381369)).toBe('0.0%'); // 宮崎東諸県・外来2035年度
    expect(formatChangeRatio(1.0001)).toBe('0.0%'); // +0.01% -> same treatment
    // Just outside the rounding boundary the sign must still be shown.
    expect(formatChangeRatio(0.9994)).toBe('-0.1%');
    expect(formatChangeRatio(1.0006)).toBe('+0.1%');
  });

  it('formatReceipts adds thousands separators and the 件/月 unit', () => {
    expect(formatReceipts(4382.75)).toBe('4,383 件/月');
    expect(formatReceipts(0)).toBe('0 件/月');
  });

  it('formatYoyRatio shows two decimal places with a 倍 suffix', () => {
    expect(formatYoyRatio(1.0287, 'yoy_plan_vs_actual')).toBe('1.03倍');
    expect(formatYoyRatio(0.5, 'yoy_actual_change')).toBe('0.50倍');
  });

  it('formatYoyRatio shows a metric-specific 算出不可 label for null (unlike formatRatio, which is bed-need-specific)', () => {
    expect(formatYoyRatio(null, 'yoy_plan_vs_actual')).toBe(YOY_UNAVAILABLE_CELL_LABEL.yoy_plan_vs_actual);
    expect(formatYoyRatio(null, 'yoy_actual_change')).toBe(YOY_UNAVAILABLE_CELL_LABEL.yoy_actual_change);
    expect(formatYoyRatio(null, 'yoy_plan_vs_actual')).not.toBe(formatYoyRatio(null, 'yoy_actual_change'));
  });

  it('formatYoyChangeRatio signs increases/decreases with one decimal place, like formatChangeRatio', () => {
    expect(formatYoyChangeRatio(1.03, 'yoy_plan_vs_actual')).toBe('+3.0%');
    expect(formatYoyChangeRatio(0.97, 'yoy_actual_change')).toBe('-3.0%');
  });

  it('formatYoyChangeRatio shows the same metric-specific 算出不可 label as formatYoyRatio for null', () => {
    expect(formatYoyChangeRatio(null, 'yoy_plan_vs_actual')).toBe(YOY_UNAVAILABLE_CELL_LABEL.yoy_plan_vs_actual);
    expect(formatYoyChangeRatio(null, 'yoy_actual_change')).toBe(YOY_UNAVAILABLE_CELL_LABEL.yoy_actual_change);
  });
});
