import { describe, expect, it } from 'vitest';
import {
  classifyRatioBin,
  computeQuantileEdges,
  computeRatio,
  computeSequentialClasses,
  distinctEdges,
  formatDiff,
  formatInteger,
  formatPercent,
  formatRatio,
  RATIO_BIN_COLORS,
  RATIO_BIN_EDGES,
  RATIO_BIN_LABELS,
  SEQUENTIAL_RAMP_COLORS,
  selectRampColors,
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
});
