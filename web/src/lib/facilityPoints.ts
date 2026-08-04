// Pure helper that turns a selected area's facility shard into the GeoJSON
// MapView renders as circle points. No React, no MapLibre — kept trivially
// unit-testable (see facilityPoints.test.ts), matching the split used by
// facilityShard.ts/facilityMetricGroups.ts.
//
// Only the SELECTED area's facilities become points (see M5後半 Chunk C2
// brief): a nationwide 10,244-point layer is deliberately out of scope
// (duplicate coordinates/names/record_id vs. the per-area shards, and
// unreadable at low zoom — doc/REQUIREMENTS.md §3.2 drill-down design).

import type { Facility, FacilityMetric } from '../types';

/**
 * Flat scalar properties for a single facility circle-layer feature
 * (CLAUDE.md「可視化実装で判明した罠」7 — MapLibre feature properties must be
 * flat scalars, never nested arrays/objects).
 */
export interface FacilityPointProperties {
  record_id: string;
  facility_name: string;
  municipality: string;
  /** 病床数（休棟中等含む計）。原典が観測値(value_status==='observed')でない
   * 施設ではキー自体を省略する（0で表現しない — MapView側は['has','beds_total']で分岐する）。 */
  beds_total?: number;
}

export type FacilityPointFeature = GeoJSON.Feature<GeoJSON.Point, FacilityPointProperties>;
export type FacilityPointFeatureCollection = GeoJSON.FeatureCollection<GeoJSON.Point, FacilityPointProperties>;

/**
 * 施設が0件（未選択・shard未取得・選択区域に該当なし）のときに使う空の
 * FeatureCollection。MapViewのスタイル定義時の初期値と、buildFacilityPoints()
 * の入力が空/nullのときの返り値の両方に使う共通の定数。
 */
export const EMPTY_FACILITY_POINTS: FacilityPointFeatureCollection = { type: 'FeatureCollection', features: [] };

/**
 * 選択区域のfacilities配列から、地図の circle レイヤに渡すGeoJSONを組み立てる。
 * - `coordinates` を持たない施設(match_status !== 'matched'、位置を推測しない
 *   方針— doc/REQUIREMENTS.md §4.3)は除外する
 * - プロパティはフラットなスカラーのみ(CLAUDE.md罠7)
 * - `beds_total` は metrics 配列から 'beds_total' キーの位置を引き、その施設の
 *   value_status が 'observed' のときだけ持たせる(未観測を0にしない)
 * - facilities が空/null、または座標付きが0件でも例外を投げず空の
 *   FeatureCollection を返す
 */
export function buildFacilityPoints(
  facilities: Facility[] | null | undefined,
  metrics: Array<Pick<FacilityMetric, 'key'>>
): FacilityPointFeatureCollection {
  if (!facilities || facilities.length === 0) return EMPTY_FACILITY_POINTS;

  const bedsTotalIndex = metrics.findIndex((m) => m.key === 'beds_total');
  const features: FacilityPointFeature[] = [];

  for (const facility of facilities) {
    if (!facility.coordinates) continue;

    const properties: FacilityPointProperties = {
      record_id: facility.record_id,
      facility_name: facility.facility_name,
      municipality: facility.municipality,
    };

    if (bedsTotalIndex >= 0 && facility.value_status[bedsTotalIndex] === 'observed') {
      const value = facility.values[bedsTotalIndex];
      if (value !== null) {
        properties.beds_total = value;
      }
    }

    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: facility.coordinates },
      properties,
    });
  }

  if (features.length === 0) return EMPTY_FACILITY_POINTS;
  return { type: 'FeatureCollection', features };
}
