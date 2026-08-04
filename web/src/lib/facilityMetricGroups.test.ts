import { describe, expect, it } from 'vitest';
import {
  classifyFacilityMetricGroup,
  facilityLegendStatuses,
  formatFacilityValue,
  groupFacilityMetrics,
} from './facilityMetricGroups';
import type { Facility, FacilityMetric, FacilityValueStatus } from '../types';

// Mirrors tools/build_web_facilities.py's METRICS (metric/bed_function values
// only — see that file for the authoritative 21-entry list). Inlined here
// rather than imported: this test must not depend on generated output (see
// facilityShard.test.ts's note on CLAUDE.md 罠8), and the whole point of
// classifyFacilityMetricGroup is to derive groups mechanically from the
// `metric` string, so a hand-written fixture also doubles as a regression
// check against the real pipeline's metric labels drifting silently.
const REAL_METRICS: FacilityMetric[] = [
  { key: 'beds_total', metric: '病床数', bed_function: '休棟中等含む計', label: '病床数（休棟中等含む計）' },
  { key: 'beds_high_acute', metric: '病床数', bed_function: '高度急性期', label: '病床数（高度急性期）' },
  { key: 'beds_acute', metric: '病床数', bed_function: '急性期', label: '病床数（急性期）' },
  { key: 'beds_recovery', metric: '病床数', bed_function: '回復期', label: '病床数（回復期）' },
  { key: 'beds_chronic', metric: '病床数', bed_function: '慢性期', label: '病床数（慢性期）' },
  { key: 'beds_suspended', metric: '病床数', bed_function: '休棟中等', label: '病床数（休棟中等）' },
  { key: 'doctors_fulltime', metric: '医師数（常勤）', bed_function: '', label: '医師数（常勤）' },
  { key: 'doctors_parttime', metric: '医師数（非常勤）', bed_function: '', label: '医師数（非常勤）' },
  { key: 'doctors_per_100beds', metric: '医師数（100床当たり）', bed_function: '', label: '医師数（100床当たり）' },
  { key: 'ambulance', metric: '救急車の受入件数', bed_function: '', label: '救急車の受入件数' },
  { key: 'general_anesthesia', metric: '全身麻酔手術件数', bed_function: '', label: '全身麻酔手術件数' },
  { key: 'deliveries', metric: '分娩件数', bed_function: '', label: '分娩件数' },
  { key: 'surgeries_total', metric: '手術総数', bed_function: '', label: '手術総数' },
  { key: 'alos_high_acute', metric: '平均在棟日数', bed_function: '高度急性期', label: '平均在棟日数（高度急性期）' },
  { key: 'alos_acute', metric: '平均在棟日数', bed_function: '急性期', label: '平均在棟日数（急性期）' },
  { key: 'alos_recovery', metric: '平均在棟日数', bed_function: '回復期', label: '平均在棟日数（回復期）' },
  { key: 'alos_chronic', metric: '平均在棟日数', bed_function: '慢性期', label: '平均在棟日数（慢性期）' },
  { key: 'new_admissions_high_acute', metric: '新規入棟患者', bed_function: '高度急性期', label: '新規入棟患者（高度急性期）' },
  { key: 'new_admissions_acute', metric: '新規入棟患者', bed_function: '急性期', label: '新規入棟患者（急性期）' },
  { key: 'new_admissions_recovery', metric: '新規入棟患者', bed_function: '回復期', label: '新規入棟患者（回復期）' },
  { key: 'new_admissions_chronic', metric: '新規入棟患者', bed_function: '慢性期', label: '新規入棟患者（慢性期）' },
];

describe('classifyFacilityMetricGroup', () => {
  it('classifies each of the 21 real metric strings into the expected group', () => {
    expect(classifyFacilityMetricGroup('病床数')).toBe('beds');
    expect(classifyFacilityMetricGroup('医師数（常勤）')).toBe('doctors');
    expect(classifyFacilityMetricGroup('医師数（非常勤）')).toBe('doctors');
    expect(classifyFacilityMetricGroup('医師数（100床当たり）')).toBe('doctors');
    expect(classifyFacilityMetricGroup('平均在棟日数')).toBe('alos');
    expect(classifyFacilityMetricGroup('新規入棟患者')).toBe('new_admissions');
    expect(classifyFacilityMetricGroup('救急車の受入件数')).toBe('clinical');
    expect(classifyFacilityMetricGroup('全身麻酔手術件数')).toBe('clinical');
    expect(classifyFacilityMetricGroup('分娩件数')).toBe('clinical');
    expect(classifyFacilityMetricGroup('手術総数')).toBe('clinical');
  });

  it('falls back to "other" for an unrecognized metric string (原典に指標が増えた場合でも落とさない)', () => {
    expect(classifyFacilityMetricGroup('未知の指標')).toBe('other');
  });

  it('a future 医師数-prefixed variant is still classified as doctors without code changes', () => {
    expect(classifyFacilityMetricGroup('医師数（当直）')).toBe('doctors');
  });
});

describe('groupFacilityMetrics', () => {
  const groups = groupFacilityMetrics(REAL_METRICS);

  it('produces exactly the 5 groups from the brief (no "other") for the real 21-metric set', () => {
    expect(groups.map((g) => g.key)).toEqual(['beds', 'doctors', 'alos', 'new_admissions', 'clinical']);
  });

  it('sizes each group per the brief (6/3/4/4/4 = 21 total)', () => {
    const sizes = Object.fromEntries(groups.map((g) => [g.key, g.indices.length]));
    expect(sizes).toEqual({ beds: 6, doctors: 3, alos: 4, new_admissions: 4, clinical: 4 });
    expect(groups.reduce((sum, g) => sum + g.indices.length, 0)).toBe(21);
  });

  it('keeps indices in the original metrics array order within each group', () => {
    const bedsGroup = groups.find((g) => g.key === 'beds')!;
    expect(bedsGroup.indices).toEqual([0, 1, 2, 3, 4, 5]);
    const doctorsGroup = groups.find((g) => g.key === 'doctors')!;
    expect(doctorsGroup.indices).toEqual([6, 7, 8]);
  });

  it('includes an "other" group (last) when an unrecognized metric is present, without dropping it', () => {
    const withUnknown = [...REAL_METRICS, { key: 'mystery', metric: '未知の指標', bed_function: '', label: '未知の指標' }];
    const result = groupFacilityMetrics(withUnknown);
    expect(result.map((g) => g.key)).toEqual(['beds', 'doctors', 'alos', 'new_admissions', 'clinical', 'other']);
    const other = result.find((g) => g.key === 'other')!;
    expect(other.indices).toEqual([21]);
  });

  it('omits empty groups entirely rather than returning them with 0 indices', () => {
    const onlyBeds = REAL_METRICS.slice(0, 1);
    const result = groupFacilityMetrics(onlyBeds);
    expect(result).toEqual([{ key: 'beds', label: '病床数', indices: [0] }]);
  });
});

describe('formatFacilityValue', () => {
  it('formats integers without a decimal point', () => {
    expect(formatFacilityValue(582)).toBe('582');
    expect(formatFacilityValue(0)).toBe('0');
  });

  it('rounds decimals to at most 2 digits for readability', () => {
    expect(formatFacilityValue(22.371134020618552)).toBe('22.37');
    expect(formatFacilityValue(12.156827048114435)).toBe('12.16');
    expect(formatFacilityValue(0.2)).toBe('0.2');
  });
});

// value_status_labelsのキー順(observed -> source_dash -> not_disclosed ->
// not_reported -> blank)を基準にした固定順。実際のfacility_summary.jsonの
// value_status_labelsと同じキー集合(build_web_facilities.pyのVALUE_STATUS_LABELS参照)。
const REAL_VALUE_STATUS_LABELS: Record<FacilityValueStatus, string> = {
  observed: '実測値',
  source_dash: '原典が「-」',
  not_disclosed: '非公表（NDBの利用に関するガイドラインにより一部非公表）',
  not_reported: '未報告（病床機能報告を未報告の医療機関）',
  blank: '空欄（原典セルが空欄）',
};

function withStatuses(...statuses: FacilityValueStatus[]): Pick<Facility, 'value_status'> {
  return { value_status: statuses };
}

describe('facilityLegendStatuses', () => {
  it('excludes "observed" even when every facility reports it', () => {
    const facilities = [withStatuses('observed', 'observed'), withStatuses('observed')];
    expect(facilityLegendStatuses(facilities, REAL_VALUE_STATUS_LABELS)).toEqual([]);
  });

  it('excludes "observed" alongside other statuses (not just when it is the only one present)', () => {
    const facilities = [withStatuses('observed', 'source_dash')];
    expect(facilityLegendStatuses(facilities, REAL_VALUE_STATUS_LABELS)).toEqual(['source_dash']);
  });

  it('returns statuses in valueStatusLabels key order, regardless of the order facilities appear in', () => {
    const expected: FacilityValueStatus[] = ['source_dash', 'not_disclosed', 'not_reported', 'blank'];

    const orderA = [
      withStatuses('blank', 'observed'),
      withStatuses('not_reported'),
      withStatuses('not_disclosed'),
      withStatuses('source_dash'),
    ];
    const orderB = [
      withStatuses('source_dash'),
      withStatuses('not_disclosed', 'observed'),
      withStatuses('blank'),
      withStatuses('not_reported'),
    ];

    expect(facilityLegendStatuses(orderA, REAL_VALUE_STATUS_LABELS)).toEqual(expected);
    expect(facilityLegendStatuses(orderB, REAL_VALUE_STATUS_LABELS)).toEqual(expected);
    // Same set, reversed facility array — must not change the legend's word order.
    expect(facilityLegendStatuses([...orderA].reverse(), REAL_VALUE_STATUS_LABELS)).toEqual(expected);
  });

  it('returns only the subset of statuses that actually appear (not the full label set)', () => {
    const facilities = [withStatuses('observed', 'not_reported')];
    expect(facilityLegendStatuses(facilities, REAL_VALUE_STATUS_LABELS)).toEqual(['not_reported']);
  });

  it('returns an empty array when every value is observed (no missing values in this area)', () => {
    const facilities = [withStatuses('observed', 'observed', 'observed'), withStatuses('observed')];
    expect(facilityLegendStatuses(facilities, REAL_VALUE_STATUS_LABELS)).toEqual([]);
  });

  it('returns an empty array for an empty facilities list', () => {
    expect(facilityLegendStatuses([], REAL_VALUE_STATUS_LABELS)).toEqual([]);
  });
});
