import { Fragment } from 'react';

import {
  computeRatio,
  formatChangeRatio,
  formatDiff,
  formatInteger,
  formatKm2,
  formatRatio,
  formatReceipts,
} from '../lib/metrics';
import type { BedFunctionKey, DemandCategoryKey, PrefectureIndicator } from '../types';

interface PrefecturePanelProps {
  prefecture: PrefectureIndicator;
  /** 全国（pref_code='00'）。同じ指標を並べて「全国と比べてどうか」を出すために使う。 */
  national: PrefectureIndicator;
  functions: BedFunctionKey[];
  functionLabels: Record<BedFunctionKey, string>;
  demandCategories: DemandCategoryKey[];
  demandCategoryLabels: Record<DemandCategoryKey, string>;
  demandYears: number[];
  demandYearLabels: Record<string, string>;
  demandBaselineYear: number;
  /** 「この都道府県の構想区域を見る」— 表示単位を区域へ切り替えて当該県へズームする。 */
  onDrillDown: () => void;
}

/** 1エンティティ（都道府県 or 全国）ぶんの病床表。県と全国で同じ列・同じ整形にする。 */
function BedTable({
  entry,
  functions,
  functionLabels,
}: {
  entry: PrefectureIndicator;
  functions: BedFunctionKey[];
  functionLabels: Record<BedFunctionKey, string>;
}) {
  return (
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
          const beds = entry.beds[fn];
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
  );
}

export default function PrefecturePanel({
  prefecture,
  national,
  functions,
  functionLabels,
  demandCategories,
  demandCategoryLabels,
  demandYears,
  demandYearLabels,
  demandBaselineYear,
  onDrillDown,
}: PrefecturePanelProps) {
  return (
    <section aria-label="都道府県の詳細">
      <h2>{prefecture.pref_name}</h2>
      <p className="area-panel-code">
        都道府県コード: {prefecture.pref_code} ／ 構想区域 {prefecture.area_count} 区域
      </p>

      <BedTable entry={prefecture} functions={functions} functionLabels={functionLabels} />

      {/* 全国は境界を持たない(地図では選べない)ので、都道府県を選んだときに
          並べて出すのが唯一の導線。既定は畳んでおき、県の数字を邪魔しない。 */}
      <details className="national-reference">
        <summary>{national.pref_name}（参考）</summary>
        <BedTable entry={national} functions={functions} functionLabels={functionLabels} />
      </details>

      <ul className="meta-list">
        <li>
          <span>2020年人口（国勢調査）</span>
          <span>{formatInteger(prefecture.population_2020)} 人</span>
        </li>
        <li>
          <span>面積</span>
          <span>{formatKm2(prefecture.area_km2)}</span>
        </li>
        <li>
          <span>人口（医療需要推計の基準人口）※</span>
          <span>{formatInteger(prefecture.population_2024)} 人</span>
        </li>
        <li>
          <span>人口（2040年、医療需要推計）</span>
          <span>{formatInteger(prefecture.population_2040)} 人</span>
        </li>
      </ul>

      {/* 区域パネルと同じ注記。基準人口の年は厚生労働省の公表物どうしで
          食い違っているため、ラベルからは年を外している(SourceNotes参照)。 */}
      <p className="population-basis-note">
        ※ 基準人口の年は原典間で一致しません。原典Excel（001728462.xlsx）の見出しは
        「人口(2024年度)」ですが、同じ公表回の公式説明書（001728467.pdf）は「人口(2025年)」
        （総務省「住民基本台帳人口」2025年）と記載しています。本サイトは原典Excelの値を
        そのまま表示しており、どちらかへの読み替えはしていません。
      </p>

      <h3 className="area-panel-subheading">医療需要推計（レセプト件数/月）</h3>
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
                  const value = prefecture.demand[cat][String(year)];
                  const baseline = prefecture.demand[cat][String(demandBaselineYear)];
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

      {/* 需要が派生値であることは出典欄(SourceNotes)の known_issues にも出るが、
          値の真横でも一度言っておく(合計であることに気付かないまま読まれるのを
          避けるため)。病床は公表値そのものなので、この注記は需要表の下だけに置く。 */}
      <p className="derived-note">
        ※ 医療需要推計と基準人口は、厚生労働省が構想区域単位でのみ公表しているものを、
        本サイトが都道府県単位で合計した派生値です（病床数は厚生労働省の都道府県別公表値そのもの）。
      </p>

      <button type="button" className="drilldown-button" onClick={onDrillDown}>
        {prefecture.pref_name}の構想区域（{prefecture.area_count} 区域）を見る
      </button>

      <p className="boundary-note">
        境界の出所: 構想区域境界（国土数値情報 A38-20 由来）を都道府県コードでディゾルブしたもの。
        県境は必ず構想区域境界の部分集合になります。
      </p>
    </section>
  );
}
