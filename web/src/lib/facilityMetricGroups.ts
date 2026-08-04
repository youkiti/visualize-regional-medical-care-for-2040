// Pure helpers for FacilityList's expanded-row view: grouping the 21
// facility metrics into display sections, formatting their raw values, and
// selecting which value_status labels to show in the below-table legend.
// No React — kept trivially unit-testable (see facilityMetricGroups.test.ts).

import type { Facility, FacilityMetric, FacilityValueStatus } from '../types';

export type FacilityMetricGroupKey = 'beds' | 'doctors' | 'alos' | 'new_admissions' | 'clinical' | 'other';

export const FACILITY_METRIC_GROUP_LABELS: Record<FacilityMetricGroupKey, string> = {
  beds: '病床数',
  doctors: '医師数',
  alos: '平均在棟日数',
  new_admissions: '新規入棟患者',
  clinical: '診療実績',
  other: 'その他',
};

// グループの表示順（brief記載の1〜5の順。「その他」は最後）。
export const FACILITY_METRIC_GROUP_ORDER: FacilityMetricGroupKey[] = [
  'beds',
  'doctors',
  'alos',
  'new_admissions',
  'clinical',
  'other',
];

// 「診療実績」の4指標（救急車の受入件数・全身麻酔手術件数・分娩件数・手術総数）は
// 「病床数」「医師数」のような共通の接頭辞を持たないため、metric文字列の完全一致で
// 判定する。他の4グループは接頭辞（病床数／医師数／平均在棟日数／新規入棟患者）で
// 判定できるので、ここに列挙が必要なのはこの4件のみ。
const CLINICAL_METRIC_NAMES = new Set(['救急車の受入件数', '全身麻酔手術件数', '分娩件数', '手術総数']);

/**
 * metrics[].metric の文字列からグループを機械的に導く。21個のkeyをハードコードで
 * 並べ直すのではなく文字列パターンで判定しているため、原典に指標が増減しても
 * 「病床数」「医師数」等の接頭辞を持つ新しい指標は自動でグループに追随する。
 * どのグループにも一致しない指標は「その他」に落ち、表から消えない。
 */
export function classifyFacilityMetricGroup(metric: string): FacilityMetricGroupKey {
  if (metric === '病床数') return 'beds';
  if (metric.startsWith('医師数')) return 'doctors';
  if (metric === '平均在棟日数') return 'alos';
  if (metric === '新規入棟患者') return 'new_admissions';
  if (CLINICAL_METRIC_NAMES.has(metric)) return 'clinical';
  return 'other';
}

export interface FacilityMetricGroup {
  key: FacilityMetricGroupKey;
  label: string;
  /** metrics配列内でのインデックス（Facility.values/value_statusを引くために使う）。metrics配列の元の順序を保つ。 */
  indices: number[];
}

/**
 * metrics配列（表示順）を FACILITY_METRIC_GROUP_ORDER の順にグループ分けする。
 * グループ内の指標順序はmetrics配列の元の順序を保つ。該当する指標が1件も無い
 * グループ（現状は基本的に「その他」のみ）は返り値から除外するので、呼び出し側
 * (FacilityList)は空グループの表示を心配しなくてよい。
 */
export function groupFacilityMetrics(metrics: Array<Pick<FacilityMetric, 'metric'>>): FacilityMetricGroup[] {
  const indicesByGroup = new Map<FacilityMetricGroupKey, number[]>();
  metrics.forEach((m, index) => {
    const group = classifyFacilityMetricGroup(m.metric);
    const indices = indicesByGroup.get(group);
    if (indices) {
      indices.push(index);
    } else {
      indicesByGroup.set(group, [index]);
    }
  });

  return FACILITY_METRIC_GROUP_ORDER.filter((key) => indicesByGroup.has(key)).map((key) => ({
    key,
    label: FACILITY_METRIC_GROUP_LABELS[key],
    indices: indicesByGroup.get(key) as number[],
  }));
}

/**
 * Facility.values の1要素（value_status==='observed'のときのみ数値）を表示用に
 * 整形する。整数はそのまま、小数は読みやすさのため最大2桁に丸める（元データ
 * 自体は丸めない方針＝data/processed側の話であり、これは表示専用の整形）。
 */
export function formatFacilityValue(value: number): string {
  return value.toLocaleString('ja-JP', { maximumFractionDigits: 2 });
}

/**
 * 一覧の表下に出す凡例に含める value_status を求める。
 * - 'observed'（実測値）は除外する: 凡例の目的は表中の「—」が何を意味するかの
 *   説明であり、数値がそのまま出ているセルには説明が要らない。含めると
 *   「凡例：実測値／原典が「-」／…」のように読み手を混乱させる
 * - 返り値の順序は valueStatusLabels のキー順（固定）。facilities配列を走査した
 *   Setの挿入順に依存すると、区域ごとに施設の並びが違うため凡例の語順が
 *   ばらついてしまう
 * - 一覧内に欠測が1件も無ければ空配列を返す。呼び出し側(FacilityList)はこれを
 *   「凡例の行自体を描画しない」判断に使う（「凡例：（該当なし）」のような
 *   意味の通らない行を出さないため）
 */
export function facilityLegendStatuses(
  facilities: Array<Pick<Facility, 'value_status'>>,
  valueStatusLabels: Record<FacilityValueStatus, string>
): FacilityValueStatus[] {
  const present = new Set<FacilityValueStatus>();
  for (const facility of facilities) {
    for (const status of facility.value_status) present.add(status);
  }
  return (Object.keys(valueStatusLabels) as FacilityValueStatus[]).filter(
    (status) => status !== 'observed' && present.has(status)
  );
}
