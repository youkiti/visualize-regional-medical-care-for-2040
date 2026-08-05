import AreaSearch from './AreaSearch';
import { isDemandMetric } from '../lib/metrics';
import type {
  AreaIndicator,
  BedFunctionKey,
  BedMetricKind,
  DemandMetricKind,
  MapLevel,
  MetricKind,
} from '../types';

interface ControlsProps {
  /** 地図の表示単位（'pref'=47都道府県の概観、'area'=339構想区域）。 */
  level: MapLevel;
  onLevelChange: (level: MapLevel) => void;
  bedFunction: BedFunctionKey;
  onBedFunctionChange: (fn: BedFunctionKey) => void;
  functions: BedFunctionKey[];
  functionLabels: Record<BedFunctionKey, string>;
  metric: MetricKind;
  onMetricChange: (metric: MetricKind) => void;
  areas: AreaIndicator[];
  onSelectArea: (areaCode: string) => void;
  onResetView: () => void;
  /** 今の指標・病床機能・年度のまま、全339区域ぶんをCSVでダウンロードする（lib/downloads.ts buildAreaTableCsv）。 */
  onDownloadAreaTable: () => void;
  /** area_demand.json の years/year_labels（西暦の配列と、年の文字列 -> 年度ラベル原文）。 */
  years: number[];
  yearLabels: Record<string, string>;
  /** 現在選択中の年度の、years 配列内でのインデックス（年度そのものではない）。 */
  yearIndex: number;
  onYearIndexChange: (index: number) => void;
}

const BED_METRIC_OPTIONS: Array<{ value: BedMetricKind; label: string }> = [
  { value: 'ratio', label: '過不足率' },
  { value: 'actual', label: '実績病床数' },
  { value: 'need', label: '必要数' },
];

const DEMAND_METRIC_OPTIONS: Array<{ value: DemandMetricKind; label: string }> = [
  { value: 'demand_home_care', label: '在宅（訪問診療）' },
  { value: 'demand_outpatient', label: '外来' },
];

const LEVEL_OPTIONS: Array<{ value: MapLevel; label: string; title: string }> = [
  {
    value: 'pref',
    label: '都道府県',
    title: '47都道府県で概観する（病床は厚生労働省の都道府県別公表値、医療需要は構想区域からの集計）',
  },
  { value: 'area', label: '構想区域', title: '339構想区域で見る（医療機関のドリルダウンはこちら）' },
];

export default function Controls({
  level,
  onLevelChange,
  bedFunction,
  onBedFunctionChange,
  functions,
  functionLabels,
  metric,
  onMetricChange,
  areas,
  onSelectArea,
  onResetView,
  onDownloadAreaTable,
  years,
  yearLabels,
  yearIndex,
  onYearIndexChange,
}: ControlsProps) {
  const demandSelected = isDemandMetric(metric);
  const currentYear = years[yearIndex];
  const currentYearLabel = yearLabels[String(currentYear)] ?? String(currentYear);

  return (
    <div className="controls">
      <div className="controls-group">
        <span className="controls-legend" id="level-toggle-label">
          表示単位
        </span>
        <div className="level-toggle" role="group" aria-labelledby="level-toggle-label">
          {LEVEL_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={level === opt.value ? 'level-toggle-button is-active' : 'level-toggle-button'}
              aria-pressed={level === opt.value}
              title={opt.title}
              onClick={() => onLevelChange(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
      <div className="controls-group">
        <label htmlFor="bed-function-select">病床機能</label>
        <select
          id="bed-function-select"
          value={bedFunction}
          onChange={(e) => onBedFunctionChange(e.target.value as BedFunctionKey)}
          disabled={demandSelected}
        >
          {functions.map((fn) => (
            <option key={fn} value={fn}>
              {functionLabels[fn]}
            </option>
          ))}
        </select>
      </div>
      <div className="controls-group">
        <label htmlFor="metric-select">指標</label>
        <select id="metric-select" value={metric} onChange={(e) => onMetricChange(e.target.value as MetricKind)}>
          <optgroup label="病床（2025年）">
            {BED_METRIC_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </optgroup>
          <optgroup label="医療需要（2024年度比）">
            {DEMAND_METRIC_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </optgroup>
        </select>
      </div>
      <div className="controls-group controls-group-year">
        <label htmlFor="year-slider">
          年度
          <span className="year-slider-value">{currentYearLabel}</span>
        </label>
        <input
          id="year-slider"
          type="range"
          min={0}
          max={years.length - 1}
          step={1}
          value={yearIndex}
          disabled={!demandSelected}
          onChange={(e) => onYearIndexChange(Number(e.target.value))}
          aria-label={`表示年度: ${currentYearLabel}`}
        />
        <div className="year-slider-ticks" aria-hidden="true">
          {years.map((y) => (
            <span key={y}>{y}</span>
          ))}
        </div>
        <p className="controls-note">
          目盛りは年度の実際の間隔ではなく等間隔（インデックス）で並んでいます。
        </p>
      </div>
      <div className="controls-group">
        <AreaSearch areas={areas} onSelect={onSelectArea} />
      </div>
      <div className="controls-group">
        <button type="button" onClick={onResetView}>
          全国表示に戻す
        </button>
        {/* CSVは常に339構想区域ぶんを出す（都道府県ぶんのCSVはまだ無い）。
            表示単位が都道府県のときにラベルを変えないと、出てくる中身と食い違う。 */}
        <button
          type="button"
          onClick={onDownloadAreaTable}
          title={
            level === 'pref'
              ? '現在の病床機能・指標・年度のまま、全339構想区域ぶんをCSVでダウンロードします（都道府県ぶんの集計CSVは未対応）'
              : '地図に表示中の指標（現在の病床機能・指標・年度）を、全339構想区域ぶんCSVでダウンロードします'
          }
        >
          {level === 'pref' ? '構想区域のデータをCSV' : '表示中のデータをCSV'}
        </button>
      </div>
    </div>
  );
}
