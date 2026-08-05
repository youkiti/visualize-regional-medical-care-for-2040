// Pure functions for the "相手区域のコロプレス" (patient-flow choropleth)
// overlay on the area map. No React, no MapLibre runtime dependency — only
// plain data in, plain MapLibre expression arrays / strings out — so this is
// trivially unit-testable with vitest (same split as lib/metrics.ts:
// classifyBin/computeSequentialClasses are the model this file follows).
//
// Deliberately does NOT import web/src/generated/* or web/public/* (CLAUDE.md
// 罠8): npm run test has no pre* hook to generate those files first.

import { classifyBin, RATIO_UNAVAILABLE_COLOR, SEQUENTIAL_RAMP_COLORS } from './metrics';
import type { FlowDirectionKey, FlowPartner, FlowPhaseKey } from '../types';

// 固定境界（分位にしない）。区域を切り替えるたびに閾値が動くと色の意味が
// 比較不能になるため、地図の指標(需要2024年度比)と同じ理由で固定にする
// （CLAUDE.md「可視化実装で判明した罠」9）。6境界+7色で classifyBin() が使える。
export const FLOW_BIN_EDGES = [0.01, 0.03, 0.05, 0.1, 0.2, 0.4] as const;

// 既存の連続配色ランプ(SEQUENTIAL_RAMP_COLORS、実績/必要数の地図で使用中)を
// そのまま再利用する。新しい配色を増やさない。
export const FLOW_BIN_COLORS = SEQUENTIAL_RAMP_COLORS;

export const FLOW_BIN_LABELS = ['1%未満', '1〜3%', '3〜5%', '5〜10%', '10〜20%', '20〜40%', '40%以上'] as const;

// 原典が「一定数以上の患者がいる区域のみ表示」しているために表に現れない
// 区域の色。0%ではなく「不明」を表すため、既存の「算出不可」色
// (海#dde5ecとの対比が罠4で検証済み)を意味だけ転用する。新しい色は増やさない。
export const FLOW_UNLISTED_COLOR = RATIO_UNAVAILABLE_COLOR;

/** MapView/App が組み立てて渡す、患者の流入・流出オーバーレイの表示内容。 */
export interface FlowOverlay {
  /** 選択中(起点)の区域コード。 */
  selfCode: string;
  /** 自区域内完結率。原典に自区域行が無いグループはnull。 */
  selfRate: number | null;
  /** 相手区域のみ（自区域を除く）。AreaFlowEntry.flows[direction].phases[phase].partners をそのまま渡せる。 */
  entries: FlowPartner[];
  direction: FlowDirectionKey;
  phase: FlowPhaseKey;
  /** 選択中の区域名（area_indicators.json由来）。凡例タイトルに使う。 */
  areaName: string;
  /** 「流入元」「流出先」の役割ラベル（area_flow.jsonのdirection_labelsとは別 —
   * FlowPanel.tsxのDIRECTION_BUTTON_LABELSと同じ語彙。凡例タイトル・ツールチップに使う。 */
  directionLabel: string;
  /** 区分ラベル（area_flow.jsonのphase_labelsそのまま）。凡例タイトルに使う。 */
  phaseLabel: string;
}

/** rate(0〜1)をFLOW_BIN_EDGESの7分位のどれかへ分類し、対応する色を返す。 */
export function flowRateColor(rate: number): string {
  return FLOW_BIN_COLORS[classifyBin(rate, FLOW_BIN_EDGES)];
}

/**
 * 'fill-color' に setPaintProperty する MapLibre 式（もしくは単色の文字列）を
 * 組み立てる。自区域も相手区域と同じランプで塗る（自区域内完結率も同じ
 * 「率」であり、別配色にする理由がない。どの区域が選択中かは既存の選択
 * ハイライトレイヤ(area-selected-outline、MapView.tsx)が太枠で示している）。
 *
 * entries が空かつ selfRate が null（＝塗る対象が1件も無い）のときは match
 * 式を作らず FLOW_UNLISTED_COLOR の文字列をそのまま返す — ['match', input,
 * fallback] のようにケースが0個の match 式は MapLibre で不正なため。
 */
export function buildFlowFillColor(entries: FlowPartner[], selfCode: string, selfRate: number | null): unknown {
  const pairs: FlowPartner[] = selfRate === null ? entries : [...entries, [selfCode, selfRate]];
  if (pairs.length === 0) return FLOW_UNLISTED_COLOR;

  const expr: unknown[] = ['match', ['get', 'area_code']];
  for (const [code, rate] of pairs) {
    expr.push(code, flowRateColor(rate));
  }
  expr.push(FLOW_UNLISTED_COLOR);
  return expr;
}

/**
 * ツールチップ用の area_code -> rate 参照表（自区域を含む）。
 * selfRate が null のときは自区域を含めない（原典に自区域の行が無い＝
 * 「非表示」であって「0%」ではないため、他の非表示区域と同じ扱いにする）。
 */
export function buildFlowRateLookup(entries: FlowPartner[], selfCode: string, selfRate: number | null): Map<string, number> {
  const map = new Map<string, number>(entries);
  if (selfRate !== null) map.set(selfCode, selfRate);
  return map;
}
