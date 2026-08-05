import { Fragment } from 'react';

import PanelSection from './PanelSection';
import {
  computeRatio,
  formatChangeRatio,
  formatDiff,
  formatInteger,
  formatKm2,
  formatRatio,
  formatReceipts,
  formatReportRate,
  formatYoyChangeRatio,
  formatYoyRatio,
} from '../lib/metrics';
import type {
  BedFunctionKey,
  DemandCategoryKey,
  PrefectureIndicator,
  PrefectureYoyEntry,
} from '../types';

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
  /** prefecture_indicators.json の metadata.processing.caveat.beds（要件§6の
   * 病床比較の必須注記、単一文字列）。ハードコードせずmetadataから引く
   * （CLAUDE.md罠39）。病床テーブルの直下に常時表示する（M14）。 */
  bedsCaveat: string;
  /** prefecture_yoy.json から pref_code で引いた当該県の年度間比較データ（R6→R7）。
   * 47都道府県すべてに存在するはずだが、型上は見つからない場合に備える。 */
  yoyEntry: PrefectureYoyEntry | null;
  /** 「この都道府県の構想区域を見る」— 表示単位を区域へ切り替えて当該県へズームする。 */
  onDrillDown: () => void;
  /** この都道府県の指標（基礎情報・病床・医療需要推計）をCSVでダウンロードする（lib/downloads.ts buildPrefectureDetailCsv）。 */
  onDownloadDetail: () => void;
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
  bedsCaveat,
  yoyEntry,
  onDrillDown,
  onDownloadDetail,
}: PrefecturePanelProps) {
  return (
    <section aria-label="都道府県の詳細">
      <h2>{prefecture.pref_name}</h2>
      <p className="area-panel-code">
        <span>
          都道府県コード: {prefecture.pref_code} ／ 構想区域 {prefecture.area_count} 区域
        </span>
        <button
          type="button"
          className="download-button"
          onClick={onDownloadDetail}
          title="この都道府県の指標（基礎情報・病床・医療需要推計）をCSVでダウンロードします"
        >
          この都道府県の指標をCSV
        </button>
      </p>

      <PanelSection title="病床（2025実績 / 2025必要数）" defaultOpen>
        <BedTable entry={prefecture} functions={functions} functionLabels={functionLabels} />
        {/* 要件§6「病床数と必要量の併記時の比較上の注意書き」— 折りたたんではならない
            必須注記なので、出典欄(SourceNotes)ではなく表のすぐ下に置く(M14)。
            文言はmetadata由来でハードコードしない(CLAUDE.md罠39)。 */}
        <p className="note-alert">{bedsCaveat}</p>

        {/* 全国は境界を持たない(地図では選べない)ので、都道府県を選んだときに
            並べて出すのが唯一の導線。既定は畳んでおき、県の数字を邪魔しない。 */}
        <details className="national-reference">
          <summary>{national.pref_name}（参考）</summary>
          <BedTable entry={national} functions={functions} functionLabels={functionLabels} />
        </details>
      </PanelSection>

      <PanelSection title="基礎情報" defaultOpen>
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
            食い違っているため、ラベルからは年を外している(SourceNotes参照)。
            M14: 常時表示の段落から「1行サマリ＋折りたたみ」へ変更（全文は変更なし）。 */}
        <details className="note-caution-details">
          <summary>※ 基準人口の年は原典間で一致しません（詳細）</summary>
          <p>
            ※ 基準人口の年は原典間で一致しません。原典Excel（001728462.xlsx）の見出しは
            「人口(2024年度)」ですが、同じ公表回の公式説明書（001728467.pdf）は「人口(2025年)」
            （総務省「住民基本台帳人口」2025年）と記載しています。本サイトは原典Excelの値を
            そのまま表示しており、どちらかへの読み替えはしていません。
          </p>
        </details>
      </PanelSection>

      <PanelSection title="医療需要推計（レセプト件数/月）" defaultOpen>
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
            避けるため)。病床は公表値そのものなので、この注記は需要表の下だけに置く。
            CLAUDE.md罠25「派生であることは値の真横にも注記を置く」により、
            折りたたまない（畳んではいけない注記、brief記載どおり）。 */}
        <p className="derived-note">
          ※ 医療需要推計と基準人口は、厚生労働省が構想区域単位でのみ公表しているものを、
          本サイトが都道府県単位で合計した派生値です（病床数は厚生労働省の都道府県別公表値そのもの）。
        </p>
      </PanelSection>

      {/* 年度間比較（R6→R7）。区域パネルと同じ指標・同じ列構成にしてあるので、
          層を切り替えても読み方が変わらない。都道府県層では分母0が無いため
          「算出不可」の行は原理的に出ない（tools/build_web_prefecture_yoy.py 検証10）。 */}
      <PanelSection title="年度間比較（R6→R7）" defaultOpen={false}>
        {yoyEntry ? (
          <>
            {/* 報告率は病床数の年間の変化に混ざりうるため、表とは別に必ず併記する
                （区域パネルと同じ扱い）。都道府県では2024年の報告率がR6公表分と
                R7公表分で全県一致する（相違するのは全国値のみ）。 */}
            <ul className="meta-list">
              <li>
                <span>病床機能報告の報告率（2024年・R6公表）</span>
                <span>{formatReportRate(yoyEntry.report_rate_2024)}</span>
              </li>
              <li>
                <span>病床機能報告の報告率（2025年・R7公表）</span>
                <span>{formatReportRate(yoyEntry.report_rate_2025)}</span>
              </li>
            </ul>
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
                    const beds = yoyEntry.beds[fn];
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
            {/* M14: 常時表示の段落から「1行サマリ＋折りたたみ」へ変更（全文は変更なし）。 */}
            <details className="note-caution-details">
              <summary>※ 「見込量比」と「前年比」は別々の比較です（詳細）</summary>
              <p>
                ※ 「見込量比（実績2025÷見込量2025）」と「前年比（実績2025÷実績2024）」は別々の比較であり、
                同じ量の2通りの見せ方ではない。見込量2025はR6公表時点の見込みで、実績2025（R7公表分）とは
                公表回が異なる。実績2024はR6公表分だが、都道府県では R7公表分と全ての値が一致するため
                どちらから採っても同じである（構想区域では R7公表分の2024年実績が2025年実績の複製という
                既知の原典の欠陥があり、この点が層によって異なる）。報告率が年により異なるため（上記参照）、
                病床数の年間の変化には報告率の変動も混ざりうる。
              </p>
            </details>
          </>
        ) : (
          <p className="area-panel-placeholder">この都道府県の年度間比較データが見つかりません。</p>
        )}
      </PanelSection>

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
