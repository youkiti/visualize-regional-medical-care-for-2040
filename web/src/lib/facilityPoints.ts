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
  /** 座標の出所。'ksj_p04'=国土数値情報P04-20とのP04名寄せ由来 /
   * 'iryojoho'=医療情報ネットの公表座標を採用（P04名寄せで座標が得られなかった施設、
   * M13）。地図上での見た目は出所で描き分けない（原典に無い「質の違い」を示唆しない
   * ため）が、ツールチップでは出所を示す（brief記載どおり）。**元データ
   * （Facility['coordinate_source']）が無い施設ではキー自体を省略する**（beds_total
   * と同じ規律。原典が言っていないことを"ksj_p04"と決め打ちで発明しない —
   * CLAUDE.md「パース時の注意」の罠20「公表物が言っていない年を出力に足さない」と
   * 同じ理由）。 */
  coordinate_source?: 'ksj_p04' | 'iryojoho';
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
 * - `coordinates` を持たない施設は除外する。理由は2通りあり、どちらも
 *   除外する: (a) どちらの座標源からも位置を一意に特定できなかった
 *   (位置を推測しない方針 — doc/REQUIREMENTS.md §4.3)、
 *   (b) P04名寄せでは座標が付いたが検算で否定された(coordinate_withdrawn。
 *   doc/FACILITY_GEO_AUDIT.md)。**座標の有無は`coordinates`キーの有無で判定し、
 *   match_status では判定しない**（match_status==='matched'でも(b)により座標を
 *   持たないことがあり、逆にmatch_status!=='matched'でも医療情報ネットの公表座標を
 *   採用していれば(coordinate_source==='iryojoho')座標を持つ、M13。
 *   CLAUDE.md「可視化実装で判明した罠」36）
 * - プロパティはフラットなスカラーのみ(CLAUDE.md罠7)。`coordinate_source`は
 *   `facility.coordinate_source`があるときだけ転記し、無ければキー自体を省略する
 *   （`beds_total`と同じ規律 — 元データが言っていない値を決め打ちで発明しない）
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

    // coordinatesを持つ施設は実データ上は必ずcoordinate_sourceも持つ
    // （sync-data.mjsが生成時に検証済み）。ただしここで無いものを決め打ちで
    // 補わない（beds_totalと同じ規律）: あれば転記し、無ければキー自体を省略する。
    if (facility.coordinate_source !== undefined) {
      properties.coordinate_source = facility.coordinate_source;
    }

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
