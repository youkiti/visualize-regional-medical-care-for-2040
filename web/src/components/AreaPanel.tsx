import { Fragment } from 'react';

import {
  computeRatio,
  formatChangeRatio,
  formatDiff,
  formatInteger,
  formatKm2,
  formatPercent,
  formatRatio,
  formatReceipts,
} from '../lib/metrics';
import type { AreaDemandArea, AreaIndicator, BedFunctionKey, DemandCategoryKey } from '../types';

interface AreaPanelProps {
  area: AreaIndicator;
  boundarySource: string | null;
  functions: BedFunctionKey[];
  functionLabels: Record<BedFunctionKey, string>;
  /** area_demand.json から area_code で引いた当該区域の需要データ。339区域全件に
   * 存在するはずだが(sync-data.mjsが突合検証済み)、型上は見つからない場合に備える。 */
  demandArea: AreaDemandArea | null;
  demandCategories: DemandCategoryKey[];
  demandCategoryLabels: Record<DemandCategoryKey, string>;
  demandYears: number[];
  demandYearLabels: Record<string, string>;
  demandBaselineYear: number;
}

export default function AreaPanel({
  area,
  boundarySource,
  functions,
  functionLabels,
  demandArea,
  demandCategories,
  demandCategoryLabels,
  demandYears,
  demandYearLabels,
  demandBaselineYear,
}: AreaPanelProps) {
  const isSyntheticBoundary = boundarySource != null && boundarySource.includes('三重県');

  return (
    <section aria-label="区域の詳細">
      <h2>
        {area.pref_name} / {area.area_name}
      </h2>
      <p className="area-panel-code">構想区域コード: {area.area_code}</p>

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
              <span>人口（2024年度、医療需要推計）</span>
              <span>{formatInteger(demandArea.population_2024)} 人</span>
            </li>
            <li>
              <span>人口（2040年、医療需要推計）</span>
              <span>{formatInteger(demandArea.population_2040)} 人</span>
            </li>
          </>
        )}
      </ul>

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
