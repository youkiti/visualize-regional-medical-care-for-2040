import { useMemo, useState } from 'react';

import { formatPercent } from '../lib/metrics';
import type { FlowDataStatus } from '../lib/flowData';
import { FLOW_DIRECTIONS, FLOW_PHASES } from '../types';
import type { AreaFlowEntry, AreaIndicator, FlowDirectionKey, FlowPhaseGroup, FlowPhaseKey } from '../types';

interface FlowPanelProps {
  area: AreaIndicator;
  status: FlowDataStatus;
  /** useFlowData(App.tsx)の取得結果から area_code で引いた選択区域のエントリ。取得前/失敗時/該当なしはnull。 */
  entry: AreaFlowEntry | null;
  error: string | null;
  onRetry: () => void;
  direction: FlowDirectionKey;
  phase: FlowPhaseKey;
  onDirectionChange: (direction: FlowDirectionKey) => void;
  onPhaseChange: (phase: FlowPhaseKey) => void;
  /** area_flow.json の direction_labels（原典シート名そのままのラベル）。「原典の全体値」行にのみ使う
   * （方向トグルのボタン文言「流入元」「流出先」はこれとは別の固定文言 — DIRECTION_BUTTON_LABELS参照）。 */
  directionLabels: Record<FlowDirectionKey, string>;
  /** area_flow.json の phase_labels。区分トグルのボタン文言そのもの。 */
  phaseLabels: Record<FlowPhaseKey, string>;
  /** 相手区域の名前・都道府県名を引くための一覧（area_indicators.json由来、Appが既に保持）。 */
  indicatorAreas: AreaIndicator[];
  /** 選択中の方向・区分の内訳をCSVでダウンロードする（lib/downloads.ts buildAreaFlowCsv）。 */
  onDownloadFlow: () => void;
  /** 地図に「相手区域のコロプレス」オーバーレイを表示中か（App.tsxのstate、D2）。 */
  flowMapEnabled: boolean;
  /** オーバーレイのON/OFFを切り替える。指標セレクタ・病床機能・年度スライダーの
   * 操作や区域選択解除でApp側が自動的にOFFへ戻すことがある（App.tsx参照）。 */
  onToggleFlowMap: () => void;
}

// 方向トグルのボタン文言。area_flow.json の direction_labels（原典シート名
// そのままの「流入率」「流出率」）とは別の、この区域を主語にした固定文言
// （brief記載どおり）。titleに定義文を添える。
const DIRECTION_BUTTON_LABELS: Record<FlowDirectionKey, string> = {
  inflow: '流入元',
  outflow: '流出先',
};

const DIRECTION_TITLES: Record<FlowDirectionKey, string> = {
  inflow: 'この区域の医療機関に入院した患者の住所地の構成比（原典「流入率」）',
  outflow: 'この区域に住む患者が入院した医療機関の所在地の構成比（原典「流出率」）',
};

const PARTNER_DEFAULT_LIMIT = 5;

/**
 * 率に比例した幅の横棒（aria-hidden、数値は呼び出し側がテキストで別途出す）。
 * スケールは常に絶対値（rate×100%）で、呼び出し側どうしで最大値に正規化する
 * ようなことはしない（区域・区分をまたいで棒の意味が変わらないようにするため
 * — brief「棒のスケールは絶対のまま変えないこと」）。
 * `variant='self'` は自区域内完結の行だと分かる配色にする（相手区域行と同じ
 * 絶対スケールの棒を、実機で「最大の値にだけ棒が無い」という指摘を受けて追加した — D1修正）。
 */
function FlowBar({ rate, variant }: { rate: number; variant?: 'self' }) {
  const widthPct = Math.max(0, Math.min(rate * 100, 100));
  return (
    <div className="flow-partner-bar-track">
      <div
        className={`flow-partner-bar-fill${variant === 'self' ? ' flow-partner-bar-fill-self' : ''}`}
        style={{ width: `${widthPct}%` }}
        aria-hidden="true"
      />
    </div>
  );
}

/**
 * 相手区域1件ぶんの行。区域名は indicatorsByCode から引き、選択中の区域と
 * 都道府県が違う場合のみ都道府県名を前置する。横棒は率に比例した幅の
 * div（aria-hidden）＋数値は必ずテキストとして出す。
 */
function FlowPartnerRow({
  code,
  rate,
  selfPrefCode,
  indicatorsByCode,
}: {
  code: string;
  rate: number;
  selfPrefCode: string;
  indicatorsByCode: Map<string, AreaIndicator>;
}) {
  const partnerArea = indicatorsByCode.get(code);
  const name = partnerArea?.area_name ?? code;
  const label = partnerArea && partnerArea.pref_code !== selfPrefCode ? `${partnerArea.pref_name} ${name}` : name;

  return (
    <li className="flow-partner-row">
      <div className="flow-partner-row-label">
        <span>{label}</span>
        <span>{formatPercent(rate, 1)}</span>
      </div>
      <FlowBar rate={rate} />
    </li>
  );
}

/**
 * 選択中の方向×区分1グループぶんの内訳（自区域内で完結・相手区域リスト・
 * 表示分以外）。showAll(上位5件/すべて表示)はこのコンポーネント内のローカル
 * stateで持ち、呼び出し側が area_code/direction/phase を合成したkeyを
 * 渡すことで区域・方向・区分の切り替え時に自動でリセットされる
 * （FacilityListの行展開状態と同じ仕掛け — AreaPanel.tsxのkey={area.area_code}参照）。
 */
function FlowBreakdown({
  area,
  group,
  indicatorsByCode,
}: {
  area: AreaIndicator;
  group: FlowPhaseGroup;
  indicatorsByCode: Map<string, AreaIndicator>;
}) {
  const [showAll, setShowAll] = useState(false);
  const { self_rate: selfRate, self_rank: selfRank, partners, value_error_count: valueErrorCount } = group;

  const partnersSum = useMemo(() => partners.reduce((sum, [, rate]) => sum + rate, 0), [partners]);
  // 浮動小数の誤差で負になりうるため0で切る(ビルド時にself+Σpartners<=1+1e-9を
  // 検証済みだが、そのマージン分がここで負として現れることがある)。
  const remainder = selfRate === null ? null : Math.max(0, 1 - selfRate - partnersSum);
  const visiblePartners = showAll ? partners : partners.slice(0, PARTNER_DEFAULT_LIMIT);

  return (
    <div className="flow-breakdown">
      <div className="flow-self-block">
        <div className="flow-self-row">
          <span>自区域内で完結</span>
          <span>
            {selfRate === null ? (
              <>
                —<span className="flow-inline-note">（原典に自区域の行がありません）</span>
              </>
            ) : (
              <>
                {formatPercent(selfRate, 1)}
                {selfRank !== null && <span className="flow-inline-note">（原典の並びで{selfRank}位）</span>}
              </>
            )}
          </span>
        </div>
        {/* self_rate===nullのときは棒を出さない（原典に行が無いだけで0とは限らない
            ため「—」のまま）。それ以外は相手区域と同じ絶対スケールの棒を出す
            （D1修正: 最大の値である自区域だけ棒が無いと構成比として読めない）。 */}
        {selfRate !== null && <FlowBar rate={selfRate} variant="self" />}
      </div>

      {partners.length > 0 ? (
        <>
          <ul className="flow-partner-list">
            {visiblePartners.map(([code, rate]) => (
              <FlowPartnerRow key={code} code={code} rate={rate} selfPrefCode={area.pref_code} indicatorsByCode={indicatorsByCode} />
            ))}
          </ul>
          {partners.length > PARTNER_DEFAULT_LIMIT && (
            <button type="button" className="flow-toggle-more" onClick={() => setShowAll((v) => !v)}>
              {showAll ? '上位5件だけ表示' : `すべて表示（${partners.length}件）`}
            </button>
          )}
        </>
      ) : (
        <p className="flow-partner-empty">該当する区域が原典に表示されていません。</p>
      )}

      <div className="flow-remainder-row">
        <span>表示分以外（原典で非表示）</span>
        <span>{remainder === null ? '—' : formatPercent(remainder, 1)}</span>
      </div>

      <p className="flow-note">
        ※ 原典は「一定数以上の患者がいる区域のみ表示」しているため、表示分の合計は100%になりません。
      </p>
      {valueErrorCount > 0 && (
        <p className="flow-note">
          ※ 原典にExcelのエラー値（#VALUE!）の行が{valueErrorCount}件あり、その分の内訳は表示できません。
        </p>
      )}
    </div>
  );
}

export default function FlowPanel({
  area,
  status,
  entry,
  error,
  onRetry,
  direction,
  phase,
  onDirectionChange,
  onPhaseChange,
  directionLabels,
  phaseLabels,
  indicatorAreas,
  onDownloadFlow,
  flowMapEnabled,
  onToggleFlowMap,
}: FlowPanelProps) {
  const indicatorsByCode = useMemo(() => new Map(indicatorAreas.map((a) => [a.area_code, a])), [indicatorAreas]);

  const loaded = status === 'loaded' && entry !== null;
  const downloadDisabledReason = !loaded ? 'この内訳の読み込みが完了してから利用できます' : null;

  return (
    <section aria-label="患者の流入・流出">
      <h3 className="area-panel-subheading">患者の流入・流出（NDB 2024年度）</h3>
      <p className="flow-subnote">
        ※ 上の「推計流出患者割合」「推計流入患者割合」（患者調査2023年）とは出典・対象年が異なる別の統計です。
      </p>

      <div className="flow-toggle-group" role="group" aria-label="方向">
        {FLOW_DIRECTIONS.map((d) => (
          <button
            key={d}
            type="button"
            aria-pressed={direction === d}
            title={DIRECTION_TITLES[d]}
            onClick={() => onDirectionChange(d)}
          >
            {DIRECTION_BUTTON_LABELS[d]}
          </button>
        ))}
      </div>

      {loaded && entry && (
        <>
          <p className="flow-overall">
            原典の「全体の{directionLabels[direction]}」: {formatPercent(entry.flows[direction].overall_rate, 1)}
          </p>
          <p className="flow-note">
            ※ 3区分の合計ではなく、「高度急性期+急性期」の自区域シェアの余事象です（下の「データの既知の問題」参照）。
          </p>
        </>
      )}

      <div className="flow-toggle-group" role="group" aria-label="区分">
        {FLOW_PHASES.map((p) => (
          <button key={p} type="button" aria-pressed={phase === p} onClick={() => onPhaseChange(p)}>
            {phaseLabels[p]}
          </button>
        ))}
      </div>

      {/* データ取得完了前は地図に出す内容が無いため出さない。ONのまま指標
          セレクタ等を操作するとApp側がflowMapEnabledをfalseへ戻す(D2)ので、
          ここでは現在のflowMapEnabledをそのまま反映するだけでよい。 */}
      {status === 'loaded' && (
        <div className="flow-toggle-group">
          <button type="button" aria-pressed={flowMapEnabled} onClick={onToggleFlowMap}>
            {flowMapEnabled ? '地図表示を解除' : 'この内訳を地図に表示'}
          </button>
        </div>
      )}

      {(status === 'idle' || status === 'loading') && <p className="area-panel-placeholder">読み込み中…</p>}

      {status === 'error' && (
        <p className="facility-list-error">
          <span>{error ?? '患者の流入出データの読み込みに失敗しました。'}</span>
          <button type="button" onClick={onRetry}>
            再試行
          </button>
        </p>
      )}

      {status === 'loaded' && !entry && (
        <p className="area-panel-placeholder">この区域の流入・流出データが見つかりません。</p>
      )}

      {loaded && entry && (
        <FlowBreakdown
          key={`${area.area_code}-${direction}-${phase}`}
          area={area}
          group={entry.flows[direction].phases[phase]}
          indicatorsByCode={indicatorsByCode}
        />
      )}

      <button
        type="button"
        className="download-button flow-download-button"
        onClick={onDownloadFlow}
        disabled={!loaded}
        title={downloadDisabledReason ?? 'この内訳（選択中の方向・区分）をCSVでダウンロードします'}
      >
        この内訳をCSV
      </button>
    </section>
  );
}
