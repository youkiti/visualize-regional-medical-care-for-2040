import {
  DEMAND_RATIO_BIN_LABELS,
  RATIO_BIN_COLORS,
  RATIO_BIN_LABELS,
  RATIO_UNAVAILABLE_LABEL,
  computeSequentialClasses,
  formatInteger,
  isDemandMetric,
} from '../lib/metrics';
import type { MapLevel, MetricKind } from '../types';

interface LegendProps {
  /** 表示単位。分位の母集団と、注記に書く「区域/都道府県」の語を切り替える。 */
  level: MapLevel;
  metric: MetricKind;
  functionLabel: string;
  /** computeQuantileEdges() の8値。実数指標(actual/need)のときのみ使用。 */
  quantileEdges: number[];
  /** 需要指標選択中の見出しに使う選択年度ラベル原文（例: "2040年度（現状投影）"）。bed指標選択中は未使用。 */
  demandYearLabel: string;
  /** 区域選択中（＝地図に医療機関ポイントを表示しうる状態）かどうか。trueのときだけ末尾に凡例を1行足す。 */
  showFacilityNote: boolean;
}

const METRIC_TITLES: Record<MetricKind, string> = {
  ratio: '過不足率（2025実績 ÷ 2025必要数）',
  actual: '2025年実績病床数',
  need: '2025年必要数',
  demand_home_care: '在宅（訪問診療）需要の2024年度比',
  demand_outpatient: '外来需要の2024年度比',
};

export default function Legend({
  level,
  metric,
  functionLabel,
  quantileEdges,
  demandYearLabel,
  showFacilityNote,
}: LegendProps) {
  const isPref = level === 'pref';
  // 注記に出す表示単位の呼び名。分位・配色の説明は同じ仕組みだが、母集団の
  // 件数と実データの範囲は層によって別物なので言い換える。
  const unitLabel = isPref ? '都道府県' : '区域';
  const unitCountLabel = isPref ? '47都道府県' : '339区域';
  // computeQuantileEdges() の生の8値は同値を含みうる(例: 高度急性期の実績
  // 病床数は339区域中69区域が0床)。地図の塗り分けと凡例の区分を必ず一致させる
  // ため、両方とも同じ computeSequentialClasses() から重複を除いた境界と、
  // それに合わせて間引いた色を取得する。実数指標(actual/need)のときのみ使う。
  const sequential = metric === 'ratio' || isDemandMetric(metric) ? null : computeSequentialClasses(quantileEdges);

  const title = isDemandMetric(metric)
    ? `${METRIC_TITLES[metric]}（${demandYearLabel}）`
    : `${METRIC_TITLES[metric]}（${functionLabel}）`;

  return (
    <div className="legend" aria-label="凡例">
      <h3>{title}</h3>
      {metric === 'ratio' ? (
        <>
          {RATIO_BIN_COLORS.map((color, i) => (
            <div className="legend-row" key={color}>
              <span className="legend-swatch" style={{ background: color }} />
              <span>{RATIO_BIN_LABELS[i]}</span>
            </div>
          ))}
          <div className="legend-row">
            <span className="legend-swatch legend-swatch-unavailable" />
            <span>{RATIO_UNAVAILABLE_LABEL}</span>
          </div>
          <p className="legend-note">
            区分は病床機能によらず同じ意味を保つよう、1.0倍を中心に固定した境界（対辺が互いに逆数）を使用。
            {isPref
              ? '都道府県の実データは機能別で約0.36〜2.03倍の範囲に収まる。'
              : '実データの最大値は合計で約2.83倍だが、凡例の区分は上記の範囲でクリップして表示する。'}
            {isPref && '区分は構想区域表示と共通のため、層を切り替えても同じ色は同じ比を意味する。'}
          </p>
        </>
      ) : isDemandMetric(metric) ? (
        <>
          {RATIO_BIN_COLORS.map((color, i) => (
            <div className="legend-row" key={color}>
              <span className="legend-swatch" style={{ background: color }} />
              <span>{DEMAND_RATIO_BIN_LABELS[i]}</span>
            </div>
          ))}
          <p className="legend-note">
            区分は在宅・外来・年度によらず固定した境界（2024年度比1.0倍を中心）を使用するため、
            年度スライダーを動かしても色の意味は変わらない。2024年度（基準年）を選択すると、定義上
            すべての{unitLabel}が中立色（-5%〜+5%）になる。値は「レセプト件数/月」であり、患者数・人数
            そのものではない。2030年度以降はいずれも現状投影値。
            {isPref && '都道府県の値は構想区域の値を合計した派生値（厚生労働省は構想区域単位でのみ公表）。'}
          </p>
        </>
      ) : (
        <>
          {sequential!.colors.map((color, i) => {
            const lo = sequential!.edges[i];
            const hi = sequential!.edges[i + 1];
            return (
              <div className="legend-row" key={`bin-${i}`}>
                <span className="legend-swatch" style={{ background: color }} />
                <span>
                  {formatInteger(lo)} 〜 {formatInteger(hi)} 床
                </span>
              </div>
            );
          })}
          <p className="legend-note">
            {unitCountLabel}の現在値から実行時に算出した7分位（等件数の区分）。病床機能や表示単位を
            切り替えると区分も変わり、同じ値の{unitLabel}が多い機能では区分が統合されて7未満になる。
            表示は整数に丸めている。 実数（病床数）は{unitLabel}の人口規模を強く反映するため、
            {unitLabel}間の単純な大小比較には注意すること。
          </p>
        </>
      )}
      {showFacilityNote && (
        <p className="legend-note legend-facility-note">
          点の大きさは施設の病床数（休棟中等含む計）。座標を特定できた施設のみを点として表示しており、
          特定できなかった施設は医療機関一覧にのみ表示されます。
        </p>
      )}
    </div>
  );
}
