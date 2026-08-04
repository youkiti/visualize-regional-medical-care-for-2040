import { Fragment, useMemo, useState } from 'react';

import { facilityLegendStatuses, formatFacilityValue, groupFacilityMetrics } from '../lib/facilityMetricGroups';
import type { FacilityShardStatus } from '../lib/facilityShard';
import type { Facility, FacilityMetric, FacilityValueStatus } from '../types';

interface FacilityListProps {
  /** バンドル済み facility_summary.json 由来。shard未取得でも読み込み中から出せる。 */
  facilityCount: number;
  status: FacilityShardStatus;
  facilities: Facility[] | null;
  error: string | null;
  onRetry: () => void;
  metrics: FacilityMetric[];
  valueStatusLabels: Record<FacilityValueStatus, string>;
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
      <p className="facility-detail-id">
        施設ID: {facility.record_id}
        <br />
        ※原典（病床機能報告個票）の行位置由来の識別子です。公表年度が変わると同じIDが別の施設を
        指しうるため、年度をまたぐ比較には使えません（同一年度内で同名施設を区別する用途には使えます）。
      </p>
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

export default function FacilityList({
  facilityCount,
  status,
  facilities,
  error,
  onRetry,
  metrics,
  valueStatusLabels,
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

  const hasUnmappedFacility = useMemo(
    () => (facilities ?? []).some((f) => f.match_status !== 'matched'),
    [facilities]
  );

  const toggle = (recordId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(recordId)) next.delete(recordId);
      else next.add(recordId);
      return next;
    });
  };

  return (
    <section aria-label="医療機関一覧">
      <h3 className="area-panel-subheading">医療機関（{facilityCount}件）</h3>

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
                            {facility.match_status !== 'matched' && (
                              <span className="facility-badge-unmapped">地図に表示なし</span>
                            )}
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
          {hasUnmappedFacility && (
            <p className="facility-legend-note">
              「地図に表示なし」＝名寄せで位置を一意に特定できなかったため座標を与えていない医療機関です（位置の推測はしません）。
            </p>
          )}
        </>
      )}
    </section>
  );
}
