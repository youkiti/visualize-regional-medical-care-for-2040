import { describe, expect, it } from 'vitest';
import {
  buildFlowFillColor,
  buildFlowRateLookup,
  flowRateColor,
  FLOW_BIN_COLORS,
  FLOW_BIN_EDGES,
  FLOW_BIN_LABELS,
  FLOW_UNLISTED_COLOR,
} from './flowMap';
import { RATIO_UNAVAILABLE_COLOR, SEQUENTIAL_RAMP_COLORS } from './metrics';
import type { FlowPartner } from '../types';

describe('flowRateColor', () => {
  it('classifies boundary values into the expected bin (lower-bound inclusive, upper exclusive)', () => {
    // 0.0099 < 0.01 (最初の境界) -> bin0
    expect(flowRateColor(0.0099)).toBe(FLOW_BIN_COLORS[0]);
    // 0.01 は境界そのもの(inclusive lower) -> bin1
    expect(flowRateColor(0.01)).toBe(FLOW_BIN_COLORS[1]);
    // 0.4 は最後の境界そのもの -> 最終bin(6)
    expect(flowRateColor(0.4)).toBe(FLOW_BIN_COLORS[6]);
    // 1.0(理論上の最大)も同じ最終binに収まる
    expect(flowRateColor(1.0)).toBe(FLOW_BIN_COLORS[6]);
  });

  it('uses SEQUENTIAL_RAMP_COLORS verbatim (7 colors for FLOW_BIN_EDGES.length(6)+1 bins)', () => {
    expect(FLOW_BIN_COLORS).toBe(SEQUENTIAL_RAMP_COLORS);
    expect(FLOW_BIN_COLORS).toHaveLength(FLOW_BIN_EDGES.length + 1);
    expect(FLOW_BIN_LABELS).toHaveLength(FLOW_BIN_EDGES.length + 1);
  });

  it('reuses RATIO_UNAVAILABLE_COLOR for FLOW_UNLISTED_COLOR (罠4で検証済みの海との対比を再利用)', () => {
    expect(FLOW_UNLISTED_COLOR).toBe(RATIO_UNAVAILABLE_COLOR);
  });
});

describe('buildFlowFillColor', () => {
  const entries: FlowPartner[] = [
    ['0102', 0.075],
    ['0103', 0.03],
  ];

  it('builds a match expression that includes the self row on the same absolute ramp as partners', () => {
    const expr = buildFlowFillColor(entries, '0101', 0.658) as unknown[];
    expect(expr[0]).toBe('match');
    expect(expr[1]).toEqual(['get', 'area_code']);

    // ['match', input, code1, color1, code2, color2, ..., fallback]
    const body = expr.slice(2, -1);
    const codes = body.filter((_, i) => i % 2 === 0);
    expect(codes.sort()).toEqual(['0101', '0102', '0103'].sort());
    // 自区域(0101)も相手区域と同じ FLOW_BIN_COLORS のいずれかで塗られる（別配色にしない）
    const selfIdx = codes.indexOf('0101');
    expect(FLOW_BIN_COLORS as readonly string[]).toContain(body[selfIdx * 2 + 1]);

    // fallbackは末尾
    expect(expr[expr.length - 1]).toBe(FLOW_UNLISTED_COLOR);
  });

  it('has no duplicate area_code cases in the match expression', () => {
    const expr = buildFlowFillColor(entries, '0101', 0.658) as unknown[];
    const body = expr.slice(2, -1);
    const codes = body.filter((_, i) => i % 2 === 0);
    expect(new Set(codes).size).toBe(codes.length);
  });

  it('excludes the self row when selfRate is null (原典に自区域行が無いグループ)', () => {
    const expr = buildFlowFillColor(entries, '0101', null) as unknown[];
    const body = expr.slice(2, -1);
    const codes = body.filter((_, i) => i % 2 === 0);
    expect(codes).not.toContain('0101');
    expect(codes.sort()).toEqual(['0102', '0103']);
  });

  it('returns the fallback color string (not a match expression) when there is nothing to color', () => {
    expect(buildFlowFillColor([], '0101', null)).toBe(FLOW_UNLISTED_COLOR);
  });

  it('still returns a match expression when entries is empty but selfRate is present', () => {
    const result = buildFlowFillColor([], '0101', 0.9);
    expect(Array.isArray(result)).toBe(true);
    const expr = result as unknown[];
    expect(expr[0]).toBe('match');
    expect(expr[expr.length - 1]).toBe(FLOW_UNLISTED_COLOR);
  });
});

describe('buildFlowRateLookup', () => {
  const entries: FlowPartner[] = [
    ['0102', 0.075],
    ['0103', 0.03],
  ];

  it('includes both partners and the self row keyed by area_code', () => {
    const lookup = buildFlowRateLookup(entries, '0101', 0.658);
    expect(lookup.get('0101')).toBe(0.658);
    expect(lookup.get('0102')).toBe(0.075);
    expect(lookup.get('0103')).toBe(0.03);
    expect(lookup.size).toBe(3);
  });

  it('omits the self row when selfRate is null', () => {
    const lookup = buildFlowRateLookup(entries, '0101', null);
    expect(lookup.has('0101')).toBe(false);
    expect(lookup.size).toBe(2);
  });
});
