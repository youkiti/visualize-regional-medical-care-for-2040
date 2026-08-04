import AreaSearch from './AreaSearch';
import type { AreaIndicator, BedFunctionKey, MetricKind } from '../types';

interface ControlsProps {
  bedFunction: BedFunctionKey;
  onBedFunctionChange: (fn: BedFunctionKey) => void;
  functions: BedFunctionKey[];
  functionLabels: Record<BedFunctionKey, string>;
  metric: MetricKind;
  onMetricChange: (metric: MetricKind) => void;
  areas: AreaIndicator[];
  onSelectArea: (areaCode: string) => void;
  onResetView: () => void;
}

const METRIC_OPTIONS: Array<{ value: MetricKind; label: string }> = [
  { value: 'ratio', label: '過不足率' },
  { value: 'actual', label: '実績病床数' },
  { value: 'need', label: '必要数' },
];

export default function Controls({
  bedFunction,
  onBedFunctionChange,
  functions,
  functionLabels,
  metric,
  onMetricChange,
  areas,
  onSelectArea,
  onResetView,
}: ControlsProps) {
  return (
    <div className="controls">
      <div className="controls-group">
        <label htmlFor="bed-function-select">病床機能</label>
        <select
          id="bed-function-select"
          value={bedFunction}
          onChange={(e) => onBedFunctionChange(e.target.value as BedFunctionKey)}
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
          {METRIC_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      <div className="controls-group">
        <AreaSearch areas={areas} onSelect={onSelectArea} />
      </div>
      <div className="controls-group">
        <button type="button" onClick={onResetView}>
          全国表示に戻す
        </button>
      </div>
    </div>
  );
}
