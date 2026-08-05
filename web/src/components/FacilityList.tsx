import { Fragment, useMemo, useState } from 'react';

import { facilityLegendStatuses, formatFacilityValue, groupFacilityMetrics } from '../lib/facilityMetricGroups';
import type { FacilityShardStatus } from '../lib/facilityShard';
import type { Facility, FacilityMetric, FacilityValueStatus } from '../types';

interface FacilityListProps {
  status: FacilityShardStatus;
  facilities: Facility[] | null;
  error: string | null;
  onRetry: () => void;
  metrics: FacilityMetric[];
  valueStatusLabels: Record<FacilityValueStatus, string>;
  /** facility_summary.jsonのmetadata.geo_audit_source.reference_snapshot_date
   * （'2025-06-01'）。医療情報ネット由来の座標バッジ・カバレッジ行に使う。
   * buildFacilityCsv・SourceNotesと同じくmetadata由来で、コンポーネントに
   * 日付リテラルを持たせない（M13 must-fix）。 */
  referenceSnapshotDate: string;
  /** この区域の医療機関一覧をCSVでダウンロードする（lib/downloads.ts buildFacilityCsv）。 */
  onDownloadFacilities: () => void;
}

// 折りたたみ時の一覧に出す5列（施設名以外）。metrics配列の中からkeyで引く
// （21指標の並び順が将来変わっても、この5列自体は原典の位置に依存しない）。
const SUMMARY_COLUMN_KEYS = ['beds_total', 'beds_high_acute', 'beds_acute', 'beds_recovery', 'beds_chronic'] as const;
const SUMMARY_COLUMN_LABELS: Record<(typeof SUMMARY_COLUMN_KEYS)[number], string> = {
  beds_total: '病床数（休棟中等含む計）',
  beds_high_acute: '高度急性期',
  beds_acute: '急性期',
  beds_recovery: '回復期',
  beds_chronic: '慢性期',
};

/**
 * 欠測（value_status !== 'observed'）のセルは記号だけで意味を伝えない: 「—」に
 * title属性と視覚的に隠したテキストで日本語ラベルを必ず添える(CLAUDE.md
 * 「データ真正性のルール」/ brief「欠測の見せ方」)。
 */
function FacilityValueCell({
  value,
  status,
  labels,
}: {
  value: number | null;
  status: FacilityValueStatus | null;
  labels: Record<FacilityValueStatus, string>;
}) {
  if (status === 'observed' && value !== null) {
    return <>{formatFacilityValue(value)}</>;
  }
  const label = status ? labels[status] : '不明';
  return (
    <span title={label}>
      —<span className="visually-hidden">（{label}）</span>
    </span>
  );
}

function FacilityDetail({
  facility,
  metrics,
  valueStatusLabels,
}: {
  facility: Facility;
  metrics: FacilityMetric[];
  valueStatusLabels: Record<FacilityValueStatus, string>;
}) {
  // グループ分けはmetrics[].metricの文字列から機械的に導く(21個のkeyをハード
  // コードで並べ直さない。原典に指標が増減しても自動で追随する。詳細は
  // facilityMetricGroups.tsのコメント参照)。
  const groups = useMemo(() => groupFacilityMetrics(metrics), [metrics]);

  return (
    <div className="facility-detail">
      <p className="facility-detail-id">施設ID: {facility.record_id}</p>
      {/* M14: このIDの由来説明は展開したすべての施設行の先頭に出て嵩むため、
          IDそのものは常時表示のまま、説明文だけ折りたたむ（brief 2-4）。 */}
      <details className="note-caution-details">
        <summary>このIDについて</summary>
        <p>
          ※原典（病床機能報告個票）の行位置由来の識別子です。公表年度が変わると同じIDが別の施設を
          指しうるため、年度をまたぐ比較には使えません（同一年度内で同名施設を区別する用途には使えます）。
        </p>
      </details>
      {groups.map((group) => (
        <div className="facility-detail-group" key={group.key}>
          <h4>{group.label}</h4>
          <dl>
            {group.indices.map((idx) => (
              <Fragment key={metrics[idx].key}>
                <dt>{metrics[idx].label}</dt>
                <dd>
                  <FacilityValueCell
                    value={facility.values[idx]}
                    status={facility.value_status[idx]}
                    labels={valueStatusLabels}
                  />
                </dd>
              </Fragment>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}

/**
 * 「地図に出ていない分」の内訳を1行の日本語にする。0件の理由は書かない
 * （「座標が不一致 0件」のような、その区域には存在しない理由を出さないため）。
 */
export function coverageBreakdown(coverage: { unmatched: number; withdrawn: number }): string {
  const parts: string[] = [];
  if (coverage.unmatched > 0) parts.push(`名寄せで位置を特定できず ${coverage.unmatched}件`);
  if (coverage.withdrawn > 0) parts.push(`座標が不一致 ${coverage.withdrawn}件`);
  return parts.join('、');
}

/**
 * 座標カバレッジの集計。地図に出ない施設は2種類あり、理由が違うので分けて数える:
 * (a) 名寄せで位置を一意に特定できなかった（座標を与えていない）
 * (b) 名寄せでは座標が付いたが、別の公表物との検算で1km以上離れていたため
 *     この可視化サイトでは座標を出さない（coordinate_withdrawn。doc/FACILITY_GEO_AUDIT.md）
 * 地図に出る施設(mapped)のうち、医療情報ネットの公表座標を採用した件数
 * （coordinate_source==='iryojoho'）も別途 referenceGeocoded として数える
 * （P04名寄せで座標が得られなかった施設のみが対象、M13）。
 * **座標の有無は match_status ではなく coordinates の有無で判定する**
 * （(b)は match_status==='matched' のまま座標を持たない）。
 */
export function computeFacilityCoverage(facilities: Facility[] | null): {
  mapped: number;
  unmatched: number;
  withdrawn: number;
  referenceGeocoded: number;
  total: number;
} {
  const list = facilities ?? [];
  let mapped = 0;
  let unmatched = 0;
  let withdrawn = 0;
  let referenceGeocoded = 0;
  for (const f of list) {
    if (f.coordinates) {
      mapped += 1;
      if (f.coordinate_source === 'iryojoho') referenceGeocoded += 1;
    } else if (f.coordinate_withdrawn) {
      withdrawn += 1;
    } else {
      unmatched += 1;
    }
  }
  return { mapped, unmatched, withdrawn, referenceGeocoded, total: list.length };
}

/**
 * AreaPanel側のPanelSection（医療機関の章）のnoteに使う「地図に出ている件数」の
 * 一行サマリ（M14）。M10で「座標カバレッジは常設」と決めた情報が、章を畳むと
 * 見えなくなるのを防ぐため、summary行に出す（章を開けば本文の
 * .facility-coverage-noteにも同じ情報が改めて出る）。
 * このsummary行は章タイトル（「医療機関（{total}件）」）の隣に並ぶため、total件数は
 * 既にタイトル側に出ている。二重表示を避けるためtotalはここでは出さない。
 * - facilitiesが未取得(null)または0件 → undefined（noteを出さない）
 * - 全件が地図に出ている → 「地図に全件」
 * - 一部だけ地図に出ている → 「地図に{mapped}件」
 */
export function facilityCoverageSummary(coverage: ReturnType<typeof computeFacilityCoverage>): string | undefined {
  if (coverage.total === 0) return undefined;
  if (coverage.mapped === coverage.total) return '地図に全件';
  return `地図に${coverage.mapped}件`;
}

export default function FacilityList({
  status,
  facilities,
  error,
  onRetry,
  metrics,
  valueStatusLabels,
  referenceSnapshotDate,
  onDownloadFacilities,
}: FacilityListProps) {
  // 区域を切り替えるたびにこのコンポーネント自体がAreaPanel側でkey={area_code}
  // で再マウントされるため、展開状態はここでuseStateするだけで区域切替時に
  // 自動でリセットされる（別途useEffectでのリセットは不要）。
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());

  const summaryIndices = useMemo(
    () => SUMMARY_COLUMN_KEYS.map((key) => metrics.findIndex((m) => m.key === key)),
    [metrics]
  );

  // 凡例に出すvalue_status（'observed'は除外、順序はvalueStatusLabelsのキー順で
  // 固定）。facilityMetricGroups.tsの純関数に切り出してあるので、区域ごとの
  // 施設の出現順に語順が左右されない(vitestで検証済み)。
  const legendStatuses = useMemo(
    () => facilityLegendStatuses(facilities ?? [], valueStatusLabels),
    [facilities, valueStatusLabels]
  );

  const coverage = useMemo(() => computeFacilityCoverage(facilities), [facilities]);

  // 「一覧をCSV」は取得済み(status==='loaded')かつ1件以上のときだけ活性にする
  // （brief記載どおり）。非活性の理由はtitleで説明する。
  const facilitiesLoaded = status === 'loaded' && facilities !== null;
  const hasFacilities = facilitiesLoaded && facilities.length > 0;
  const downloadDisabledReason = !facilitiesLoaded
    ? '医療機関一覧の読み込みが完了してから利用できます'
    : !hasFacilities
      ? 'この区域には医療機関がありません'
      : null;

  const toggle = (recordId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(recordId)) next.delete(recordId);
      else next.add(recordId);
      return next;
    });
  };

  // M14: 外側の<section aria-label="医療機関一覧">と見出し行(.area-panel-
  // subheading-row、h3＋「一覧をCSV」ボタン)はAreaPanel側のPanelSectionへ移した
  // （見出し文字列と件数バッジはPanelSectionのtitle/noteが持つ）。ここでは中身
  // だけを返す。「一覧をCSV」ボタンは<summary>の中に置けない（クリックが開閉と
  // 二重発火する）ため、本文の先頭に移した。
  return (
    <>
      <div className="panel-section-actions">
        <button
          type="button"
          className="download-button"
          onClick={onDownloadFacilities}
          disabled={downloadDisabledReason !== null}
          title={downloadDisabledReason ?? 'この区域の医療機関一覧（21指標）をCSVでダウンロードします'}
        >
          一覧をCSV
        </button>
      </div>

      {status === 'loading' && <p className="area-panel-placeholder">医療機関一覧を読み込み中…</p>}

      {status === 'error' && (
        <p className="facility-list-error">
          <span>{error ?? '医療機関一覧の読み込みに失敗しました。'}</span>
          <button type="button" onClick={onRetry}>
            再試行
          </button>
        </p>
      )}

      {status === 'loaded' && facilities && (
        <>
          <div className="facility-table-wrap">
            <table className="facility-table">
              <thead>
                <tr>
                  <th>施設名</th>
                  {SUMMARY_COLUMN_KEYS.map((key) => (
                    <th key={key}>{SUMMARY_COLUMN_LABELS[key]}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {/* 並び順はshardの順（＝原典の病床数降順）で固定し、並べ替えUIは
                    作らない。欠測(value_status !== 'observed')を含む列は、値が
                    存在しない行をどこに置くかという順序自体を機械的に定義できず、
                    ソートを許すと恣意的な並びに見えてしまうため。 */}
                {facilities.map((facility) => {
                  const isOpen = expandedIds.has(facility.record_id);
                  return (
                    <Fragment key={facility.record_id}>
                      <tr>
                        <td>
                          {/* 行全体クリックではなくbuttonにする(キーボード操作・
                              スクリーンリーダー対応のため、brief記載どおり)。 */}
                          <button
                            type="button"
                            className="facility-name-toggle"
                            aria-expanded={isOpen}
                            onClick={() => toggle(facility.record_id)}
                          >
                            {facility.facility_name}
                          </button>
                          <div className="facility-subline">
                            {facility.municipality && <span>{facility.municipality}</span>}
                            {facility.functions?.map((fn) => (
                              <span key={fn} className="facility-function-badge">
                                {fn}
                              </span>
                            ))}
                            {facility.coordinates && facility.coordinate_source === 'iryojoho' && (
                              // 座標源は既定でP04名寄せ（無印）。医療情報ネット由来は
                              // P04名寄せで座標が得られなかった施設を補完したもの(758件)
                              // なので、出所が分かるようにバッジを付ける。「公表座標」の
                              // ような曖昧な語ではなく出典名（医療情報ネット・参照時点）を
                              // 明示する（briefの指示どおり）。参照時点はfacility_summary.json
                              // のmetadataから渡された値を使い、コンポーネントに日付リテラルを
                              // 持たせない（buildFacilityCsv・SourceNotesと同じ規律、M13 must-fix）。
                              <span
                                className="facility-badge-reference"
                                title={`この医療機関の座標は、国土数値情報P04との名寄せでは得られず、医療情報ネット（医療機能情報提供制度、${referenceSnapshotDate}時点の公表データ）の公表座標を採用したものです`}
                              >
                                座標: 医療情報ネット（{referenceSnapshotDate}）
                              </span>
                            )}
                            {!facility.coordinates &&
                              (facility.coordinate_withdrawn ? (
                                <span
                                  className="facility-badge-unmapped"
                                  title="別の公表物（医療情報ネットの公表座標）との検算で1km以上離れていたため、この可視化サイトでは座標を表示していません"
                                >
                                  地図に表示なし（座標が不一致）
                                </span>
                              ) : (
                                <span
                                  className="facility-badge-unmapped"
                                  title="名寄せで位置を一意に特定できなかったため座標を与えていません（位置の推測はしません）"
                                >
                                  地図に表示なし
                                </span>
                              ))}
                          </div>
                        </td>
                        {summaryIndices.map((idx, col) => (
                          <td key={SUMMARY_COLUMN_KEYS[col]}>
                            <FacilityValueCell
                              value={idx >= 0 ? facility.values[idx] : null}
                              status={idx >= 0 ? facility.value_status[idx] : null}
                              labels={valueStatusLabels}
                            />
                          </td>
                        ))}
                      </tr>
                      {isOpen && (
                        <tr className="facility-detail-row">
                          <td colSpan={SUMMARY_COLUMN_KEYS.length + 1}>
                            <FacilityDetail facility={facility} metrics={metrics} valueStatusLabels={valueStatusLabels} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* 欠測が1件も無い区域では凡例自体を出さない（「凡例：（該当なし）」
              のような意味の通らない行を避けるため）。 */}
          {legendStatuses.length > 0 && (
            <p className="facility-legend-note">
              凡例：{legendStatuses.map((s) => valueStatusLabels[s]).join('／')}
            </p>
          )}
          {/* 座標カバレッジ。点の数を施設数と読み違えさせないため、
              「地図に出ているのは全体のうち何件か」を常に明示する。 */}
          <p className="facility-coverage-note">
            地図に表示：<strong>{coverage.mapped}件</strong> / この区域の{coverage.total}件
            {coverage.mapped < coverage.total && `（${coverageBreakdown(coverage)}）`}
          </p>
          {/* うち医療情報ネット由来の件数。0件の区域では出さない（意味の無い
              「うち0件」を出さないため、coverageBreakdown()と同じ規律）。参照時点は
              referenceSnapshotDateプロパティ（metadata由来）を使う。 */}
          {coverage.referenceGeocoded > 0 && (
            <p className="facility-coverage-note">
              うち医療情報ネット（{referenceSnapshotDate}時点）の公表座標：<strong>{coverage.referenceGeocoded}件</strong>
              （国土数値情報P04との名寄せでは座標が得られなかった施設を補完）
            </p>
          )}
          {/* M14: 2本の長い説明段落を1つの折りたたみへまとめる（brief 2-3）。
              どちらの条件も0件ならdetails自体を出さない。中身は既存の2段落を
              そのまま、それぞれ従来どおり該当件数が0のときは出さない条件を
              維持する。 */}
          {(coverage.unmatched > 0 || coverage.withdrawn > 0) && (
            <details className="note-caution-details">
              <summary>「地図に表示なし」バッジの意味（詳細）</summary>
              {coverage.unmatched > 0 && (
                <p>
                  「地図に表示なし」＝名寄せで位置を一意に特定できなかったため座標を与えていない医療機関です（位置の推測はしません）。
                </p>
              )}
              {coverage.withdrawn > 0 && (
                <p>
                  「地図に表示なし（座標が不一致）」＝名寄せでは座標が付いたものの、別の公表物（医療情報ネットの公表座標）との
                  検算で1km以上離れていたため、座標を表示していない医療機関です（値の補正はせず、表示を控えています）。
                </p>
              )}
            </details>
          )}
        </>
      )}
    </>
  );
}
