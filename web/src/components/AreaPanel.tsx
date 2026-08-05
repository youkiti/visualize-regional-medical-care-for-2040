import { Fragment } from 'react';

import FacilityList from './FacilityList';
import FlowPanel from './FlowPanel';
import {
  computeRatio,
  formatChangeRatio,
  formatDiff,
  formatInteger,
  formatKm2,
  formatPercent,
  formatRatio,
  formatReceipts,
  formatReportRate,
  formatYoyChangeRatio,
  formatYoyRatio,
} from '../lib/metrics';
import type { FacilityShardStatus } from '../lib/facilityShard';
import type { FlowDataStatus } from '../lib/flowData';
import type {
  AreaDemandArea,
  AreaFlowEntry,
  AreaIndicator,
  AreaYoyArea,
  BedFunctionKey,
  DemandCategoryKey,
  Facility,
  FacilityMetric,
  FacilityValueStatus,
  FlowDirectionKey,
  FlowPhaseKey,
} from '../types';

interface AreaPanelProps {
  area: AreaIndicator;
  boundarySource: string | null;
  functions: BedFunctionKey[];
  functionLabels: Record<BedFunctionKey, string>;
  /** area_demand.json から area_code で引いた当該区域の需要データ。339区域全件に
   * 存在するはずだが(sync-data.mjsが突合検証済み)、型上は見つからない場合に備える。 */
  demandArea: AreaDemandArea | null;
  /** area_yoy.json から area_code で引いた当該区域の年度間比較データ(R6→R7)。
   * demandArea同様339区域全件に存在するはずだが、型上は見つからない場合に備える。 */
  yoyArea: AreaYoyArea | null;
  demandCategories: DemandCategoryKey[];
  demandCategoryLabels: Record<DemandCategoryKey, string>;
  demandYears: number[];
  demandYearLabels: Record<string, string>;
  demandBaselineYear: number;
  /** facility_summary.json（バンドル済み）由来。shard未取得でも件数だけは出せる。 */
  facilityCount: number;
  facilityStatus: FacilityShardStatus;
  /** useFacilityShard(App.tsx)の取得結果。取得前/失敗時はnull。 */
  facilities: Facility[] | null;
  facilityError: string | null;
  onRetryFacilities: () => void;
  facilityMetrics: FacilityMetric[];
  facilityValueStatusLabels: Record<FacilityValueStatus, string>;
  /** facility_summary.jsonのmetadata.geo_audit_source.reference_snapshot_date（'2025-06-01'）。
   * FacilityListの医療情報ネット由来バッジ・カバレッジ行に使う。CSV(buildFacilityCsv)・
   * SourceNotesと同じくmetadata由来にし、コンポーネントに日付リテラルを持たせない
   * （M13 must-fix、参照時点が変わってもここだけ食い違わないようにする）。 */
  facilityReferenceSnapshotDate: string;
  /** この区域の指標（基礎情報・病床・医療需要推計）をCSVでダウンロードする（lib/downloads.ts buildAreaDetailCsv）。 */
  onDownloadAreaDetail: () => void;
  /** この区域の医療機関一覧をCSVでダウンロードする（lib/downloads.ts buildFacilityCsv）。FacilityListへそのまま渡す。 */
  onDownloadFacilities: () => void;
  /** useFlowData(App.tsx)の取得結果。区域を選ぶまでidle/loadingのままFlowPanelへそのまま渡す。 */
  flowStatus: FlowDataStatus;
  /** area_flow.jsonから area_code で引いた選択区域のエントリ。取得前/失敗時/該当なしはnull。 */
  flowEntry: AreaFlowEntry | null;
  flowError: string | null;
  onRetryFlow: () => void;
  flowDirection: FlowDirectionKey;
  flowPhase: FlowPhaseKey;
  onFlowDirectionChange: (direction: FlowDirectionKey) => void;
  onFlowPhaseChange: (phase: FlowPhaseKey) => void;
  flowDirectionLabels: Record<FlowDirectionKey, string>;
  flowPhaseLabels: Record<FlowPhaseKey, string>;
  /** 相手区域の名前・都道府県名を引くための一覧（area_indicators.json由来）。FlowPanelへそのまま渡す。 */
  indicatorAreas: AreaIndicator[];
  /** 選択中の方向・区分の流入出内訳をCSVでダウンロードする（lib/downloads.ts buildAreaFlowCsv）。FlowPanelへそのまま渡す。 */
  onDownloadFlow: () => void;
  /** 地図に「相手区域のコロプレス」オーバーレイを表示中か（App.tsxのstate）。FlowPanelの「この内訳を地図に表示」トグルへそのまま渡す。 */
  flowMapEnabled: boolean;
  onToggleFlowMap: () => void;
}

export default function AreaPanel({
  area,
  boundarySource,
  functions,
  functionLabels,
  demandArea,
  yoyArea,
  demandCategories,
  demandCategoryLabels,
  demandYears,
  demandYearLabels,
  demandBaselineYear,
  facilityCount,
  facilityStatus,
  facilities,
  facilityError,
  onRetryFacilities,
  facilityMetrics,
  facilityValueStatusLabels,
  facilityReferenceSnapshotDate,
  onDownloadAreaDetail,
  onDownloadFacilities,
  flowStatus,
  flowEntry,
  flowError,
  onRetryFlow,
  flowDirection,
  flowPhase,
  onFlowDirectionChange,
  onFlowPhaseChange,
  flowDirectionLabels,
  flowPhaseLabels,
  indicatorAreas,
  onDownloadFlow,
  flowMapEnabled,
  onToggleFlowMap,
}: AreaPanelProps) {
  const isSyntheticBoundary = boundarySource != null && boundarySource.includes('三重県');

  return (
    <section aria-label="区域の詳細">
      <h2>
        {area.pref_name} / {area.area_name}
      </h2>
      <p className="area-panel-code">
        <span>構想区域コード: {area.area_code}</span>
        <button
          type="button"
          className="download-button"
          onClick={onDownloadAreaDetail}
          title="この区域の指標（基礎情報・病床・医療需要推計）をCSVでダウンロードします"
        >
          この区域の指標をCSV
        </button>
      </p>

      <table className="bed-table">
        <thead>
          <tr>
            <th>病床機能</th>
            <th>2025実績</th>
            <th>2025必要数</th>
            <th>差(実績−必要数)</th>
            <th>比</th>
          </tr>
        </thead>
        <tbody>
          {functions.map((fn) => {
            const beds = area.beds[fn];
            const ratio = computeRatio(beds.actual_2025, beds.need_2025);
            return (
              <tr key={fn}>
                <td>{functionLabels[fn]}</td>
                <td>{formatInteger(beds.actual_2025)}</td>
                <td>{formatInteger(beds.need_2025)}</td>
                <td>{formatDiff(beds.actual_2025, beds.need_2025)}</td>
                <td>{formatRatio(ratio)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <ul className="meta-list">
        <li>
          <span>2020年人口（国勢調査）</span>
          <span>{formatInteger(area.population_2020)} 人</span>
        </li>
        <li>
          <span>面積</span>
          <span>{formatKm2(area.area_km2)}</span>
        </li>
        <li>
          <span>推計流出患者割合</span>
          <span>{formatPercent(area.outflow_rate)}</span>
        </li>
        <li>
          <span>推計流入患者割合</span>
          <span>{formatPercent(area.inflow_rate)}</span>
        </li>
        {demandArea && (
          <>
            <li>
              <span>人口（医療需要推計の基準人口）※</span>
              <span>{formatInteger(demandArea.population_2024)} 人</span>
            </li>
            <li>
              <span>人口（2040年、医療需要推計）</span>
              <span>{formatInteger(demandArea.population_2040)} 人</span>
            </li>
          </>
        )}
        {/* 報告率は年間の病床数の変化に混ざりうるため、年度間比較の表とは別に
            必ず併記する（339区域中105区域でR6とR7の2024年報告率が異なる。brief記載
            どおり）。ラベルは「年」（原典どおり）— area_bed_report_rate.csvの
            fieldsは「報告率の対象年(実績年のみ)」であり「年度」ではない
            （CLAUDE.md、修正3）。 */}
        {yoyArea && (
          <>
            <li>
              <span>病床機能報告の報告率（2024年・R6公表）</span>
              <span>{formatReportRate(yoyArea.report_rate_2024)}</span>
            </li>
            <li>
              <span>病床機能報告の報告率（2025年・R7公表）</span>
              <span>{formatReportRate(yoyArea.report_rate_2025)}</span>
            </li>
          </>
        )}
      </ul>

      {/* 基準人口の年は厚生労働省の公表物どうしで食い違っている。どちらかを黙って
          採用すると誤った基準年を断定してしまうため、ラベルからは年を外し、不一致を
          明示する(詳細は SourceNotes の「人口（参考情報）について」= 原典メタデータの
          caveat)。2040年の列は両者一致するのでラベルに年を残している。 */}
      {demandArea && (
        <p className="population-basis-note">
          ※ 基準人口の年は原典間で一致しません。原典Excel（001728462.xlsx）の見出しは
          「人口(2024年度)」ですが、同じ公表回の公式説明書（001728467.pdf）は「人口(2025年)」
          （総務省「住民基本台帳人口」2025年）と記載しています。本サイトは原典Excelの値を
          そのまま表示しており、どちらかへの読み替えはしていません。
        </p>
      )}

      <h3 className="area-panel-subheading">医療需要推計（レセプト件数/月）</h3>
      {demandArea ? (
        <table className="demand-table">
          <thead>
            <tr>
              <th>年度</th>
              {demandCategories.map((cat) => (
                <Fragment key={cat}>
                  <th>{demandCategoryLabels[cat]}</th>
                  <th>2024年度比</th>
                </Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {demandYears.map((year) => {
              const isBaseline = year === demandBaselineYear;
              return (
                <tr key={year} className={isBaseline ? 'demand-row-baseline' : undefined}>
                  <td>
                    {demandYearLabels[String(year)]}
                    {isBaseline && <span className="demand-baseline-tag">（基準年）</span>}
                  </td>
                  {demandCategories.map((cat) => {
                    const value = demandArea.demand[cat][String(year)];
                    const baseline = demandArea.demand[cat][String(demandBaselineYear)];
                    return (
                      <Fragment key={cat}>
                        <td>{formatReceipts(value)}</td>
                        <td>{isBaseline ? '基準年' : formatChangeRatio(value / baseline)}</td>
                      </Fragment>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="area-panel-placeholder">この区域の医療需要推計データが見つかりません。</p>
      )}

      <h3 className="area-panel-subheading">年度間比較（R6→R7）</h3>
      {yoyArea ? (
        <>
          <div className="yoy-table-wrap">
            <table className="yoy-table">
              <thead>
                <tr>
                  <th>病床機能</th>
                  <th>見込量2025(R6)</th>
                  <th>実績2025(R7)</th>
                  <th>実績2024(R6)</th>
                  <th>見込量比（実績2025÷見込量2025）</th>
                  <th>前年比（実績2025÷実績2024）</th>
                </tr>
              </thead>
              <tbody>
                {functions.map((fn) => {
                  const beds = yoyArea.beds[fn];
                  const planRatio = computeRatio(beds.actual_2025, beds.plan_2025);
                  const changeRatio = computeRatio(beds.actual_2025, beds.actual_2024);
                  return (
                    <tr key={fn}>
                      <td>{functionLabels[fn]}</td>
                      <td>{formatInteger(beds.plan_2025)}</td>
                      <td>{formatInteger(beds.actual_2025)}</td>
                      <td>{formatInteger(beds.actual_2024)}</td>
                      <td>{formatYoyRatio(planRatio, 'yoy_plan_vs_actual')}</td>
                      <td>{formatYoyChangeRatio(changeRatio, 'yoy_actual_change')}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="population-basis-note">
            ※ 「見込量比（実績2025÷見込量2025）」と「前年比（実績2025÷実績2024）」は別々の比較であり、
            同じ量の2通りの見せ方ではない。見込量2025はR6公表時点の見込みで、実績2025（R7公表分）とは
            公表回が異なる。実績2024はR6公表分を採用している（R7公表分の同列は2025年実績の複製という
            既知の原典の欠陥があるため使用していない）。報告率が年により異なるため（上記参照）、
            病床数の年間の変化には報告率の変動も混ざりうる。
          </p>
        </>
      ) : (
        <p className="area-panel-placeholder">この区域の年度間比較データが見つかりません。</p>
      )}

      <FlowPanel
        area={area}
        status={flowStatus}
        entry={flowEntry}
        error={flowError}
        onRetry={onRetryFlow}
        direction={flowDirection}
        phase={flowPhase}
        onDirectionChange={onFlowDirectionChange}
        onPhaseChange={onFlowPhaseChange}
        directionLabels={flowDirectionLabels}
        phaseLabels={flowPhaseLabels}
        indicatorAreas={indicatorAreas}
        onDownloadFlow={onDownloadFlow}
        flowMapEnabled={flowMapEnabled}
        onToggleFlowMap={onToggleFlowMap}
      />

      {/* keyにarea_codeを指定して区域切替のたびに再マウントさせることで、
          FacilityList内部の行展開状態(useState)を自動でリセットする
          (brief「区域を切り替えたら展開状態をリセットする」)。 */}
      <FacilityList
        key={area.area_code}
        facilityCount={facilityCount}
        status={facilityStatus}
        facilities={facilities}
        error={facilityError}
        onRetry={onRetryFacilities}
        metrics={facilityMetrics}
        valueStatusLabels={facilityValueStatusLabels}
        referenceSnapshotDate={facilityReferenceSnapshotDate}
        onDownloadFacilities={onDownloadFacilities}
      />

      {boundarySource && (
        <p className={`boundary-note ${isSyntheticBoundary ? 'boundary-note-synthetic' : ''}`}>
          境界の出所: {boundarySource}
          {isSyntheticBoundary && (
            <>
              <br />
              ※この区域の境界は国土数値情報が公表しているものではなく、市区町村界から構想区域単位で合成した派生物です。
            </>
          )}
        </p>
      )}
    </section>
  );
}
