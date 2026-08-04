import {
  RATIO_BIN_COLORS,
  RATIO_BIN_LABELS,
  RATIO_UNAVAILABLE_LABEL,
  computeSequentialClasses,
  formatInteger,
} from '../lib/metrics';
import type { MetricKind } from '../types';

interface LegendProps {
  metric: MetricKind;
  functionLabel: string;
  /** computeQuantileEdges() の8値。実数指標(actual/need)のときのみ使用。 */
  quantileEdges: number[];
}

const METRIC_TITLES: Record<MetricKind, string> = {
  ratio: '過不足率（2025実績 ÷ 2025必要数）',
  actual: '2025年実績病床数',
  need: '2025年必要数',
};

export default function Legend({ metric, functionLabel, quantileEdges }: LegendProps) {
  // computeQuantileEdges() の生の8値は同値を含みうる(例: 高度急性期の実績
  // 病床数は339区域中69区域が0床)。地図の塗り分けと凡例の区分を必ず一致させる
  // ため、両方とも同じ computeSequentialClasses() から重複を除いた境界と、
  // それに合わせて間引いた色を取得する。
  const sequential = metric === 'ratio' ? null : computeSequentialClasses(quantileEdges);

  return (
    <div className="legend" aria-label="凡例">
      <h3>
        {METRIC_TITLES[metric]}（{functionLabel}）
      </h3>
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
            実データの最大値は合計で約2.83倍だが、凡例の区分は上記の範囲でクリップして表示する。
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
            339区域の現在値から実行時に算出した7分位（等区域数の区分）。病床機能を切り替えると区分も変わり、
            同じ値の区域が多い機能では区分が統合されて7未満になる。表示は整数に丸めている。
            実数（病床数）は区域の人口規模を強く反映するため、区域間の単純な大小比較には注意すること。
          </p>
        </>
      )}
    </div>
  );
}
