import { computeRatio, formatDiff, formatInteger, formatKm2, formatPercent, formatRatio } from '../lib/metrics';
import type { AreaIndicator, BedFunctionKey } from '../types';

interface AreaPanelProps {
  area: AreaIndicator;
  boundarySource: string | null;
  functions: BedFunctionKey[];
  functionLabels: Record<BedFunctionKey, string>;
}

export default function AreaPanel({ area, boundarySource, functions, functionLabels }: AreaPanelProps) {
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
          <span>2020年人口</span>
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
      </ul>

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
