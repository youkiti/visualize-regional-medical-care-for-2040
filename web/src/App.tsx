import { useMemo, useRef, useState } from 'react';

import MapView, { type MapViewHandle } from './components/MapView';
import Legend from './components/Legend';
import Controls from './components/Controls';
import AreaPanel from './components/AreaPanel';
import SourceNotes from './components/SourceNotes';
import { computeQuantileEdges, isDemandMetric } from './lib/metrics';
import mapDataUrl from './generated/area_map.json?url';
import indicatorsJson from './generated/area_indicators.json';
import demandJson from './generated/area_demand.json';
import areaIndexJson from './generated/area_index.json';
import type { AreaDemandData, AreaIndexEntry, AreaIndicatorsData, BedFunctionKey, MetricKind } from './types';

// generated/area_indicators.json is a verbatim copy of
// data/processed/area_indicators_R7.json (see CLAUDE.md / scripts/sync-data.mjs)
// — its shape is documented by AreaIndicatorsData in types.ts.
const indicators = indicatorsJson as unknown as AreaIndicatorsData;

// generated/area_demand.json is a verbatim copy of
// data/processed/area_demand_R7.json (same treatment as area_indicators.json
// above) — its shape is documented by AreaDemandData in types.ts.
const demand = demandJson as unknown as AreaDemandData;

// generated/area_index.json is the lightweight (bundled, not fetched)
// bbox/boundary_source lookup — see scripts/lib/merge.mjs buildAreaIndex()
// and types.ts AreaIndexEntry. Selection (from either 区域検索 or a map
// click) is resolved through this map, not through the map's own feature
// query, so it works regardless of the map's current load/viewport state.
const areaIndex = areaIndexJson as unknown as AreaIndexEntry[];
const areaIndexByCode = new Map(areaIndex.map((entry) => [entry.area_code, entry]));

// サイトの主題(「2040年に向けた地域医療構想」)に合わせ、需要指標選択時の初期年度は
// 2040年度にする(バックアップとしてyearsに2040が無い場合は先頭年度)。
const DEFAULT_YEAR_INDEX = Math.max(demand.years.indexOf(2040), 0);

export default function App() {
  const [bedFunction, setBedFunction] = useState<BedFunctionKey>('total');
  const [metric, setMetric] = useState<MetricKind>('ratio');
  const [yearIndex, setYearIndex] = useState<number>(DEFAULT_YEAR_INDEX);
  const [selectedAreaCode, setSelectedAreaCode] = useState<string | null>(null);
  const mapRef = useRef<MapViewHandle>(null);

  const functionLabel = indicators.function_labels[bedFunction];
  const selectedYear = demand.years[yearIndex];
  const selectedYearLabel = demand.year_labels[String(selectedYear)] ?? String(selectedYear);

  // Quantile edges for the actual/need metrics are derived from
  // area_indicators.json (bundled, no need to parse area_map.json at
  // runtime) — the a_*/n_* values in area_map.json are the same numbers.
  // Demand metrics use their own fixed (non-quantile) bins (see
  // DEMAND_RATIO_BIN_EDGES in lib/metrics.ts), so they don't need this at all.
  const quantileEdges = useMemo(() => {
    if (metric === 'ratio' || isDemandMetric(metric)) return [];
    const key = metric === 'actual' ? 'actual_2025' : 'need_2025';
    const values = indicators.areas.map((area) => area.beds[bedFunction][key]);
    return computeQuantileEdges(values);
  }, [bedFunction, metric]);

  const selectedArea = useMemo(() => {
    if (!selectedAreaCode) return null;
    return indicators.areas.find((area) => area.area_code === selectedAreaCode) ?? null;
  }, [selectedAreaCode]);

  const selectedDemandArea = useMemo(() => {
    if (!selectedAreaCode) return null;
    return demand.areas.find((area) => area.area_code === selectedAreaCode) ?? null;
  }, [selectedAreaCode]);

  const selectedIndexEntry = useMemo(() => {
    if (!selectedAreaCode) return null;
    return areaIndexByCode.get(selectedAreaCode) ?? null;
  }, [selectedAreaCode]);

  const handleResetView = () => {
    mapRef.current?.resetView();
    setSelectedAreaCode(null);
  };

  // Map click: MapView already resolved the area_code from the clicked
  // feature (or null on a miss) — just record the selection. The view
  // itself doesn't move (unchanged from before this fix).
  const handleMapSelectArea = (areaCode: string | null) => {
    setSelectedAreaCode(areaCode);
  };

  // 区域検索: selection no longer depends on the map's load/viewport state
  // (see MapView.selectArea) — App resolves the bbox itself from
  // area_index.json and only asks the map to fitBounds.
  const handleSearchSelect = (areaCode: string) => {
    setSelectedAreaCode(areaCode);
    const entry = areaIndexByCode.get(areaCode);
    if (entry) {
      mapRef.current?.selectArea([entry.bb_w, entry.bb_s, entry.bb_e, entry.bb_n]);
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>地域医療構想 可視化（2040年に向けて）</h1>
        <p>
          339構想区域ごとに、2025年病床数（実績・必要数）と、在宅（訪問診療）・外来の医療需要推計
          （2024〜2050年度、2024年度比）を比較します。
        </p>
      </header>
      <div className="app-body">
        <div className="map-pane">
          <MapView
            ref={mapRef}
            mapDataUrl={mapDataUrl}
            bedFunction={bedFunction}
            metric={metric}
            functionLabel={functionLabel}
            quantileEdges={quantileEdges}
            selectedAreaCode={selectedAreaCode}
            onSelectArea={handleMapSelectArea}
            demandYear={selectedYear}
            demandYearLabel={selectedYearLabel}
            demandCategoryLabels={demand.category_labels}
          />
          <Controls
            bedFunction={bedFunction}
            onBedFunctionChange={setBedFunction}
            functions={indicators.functions}
            functionLabels={indicators.function_labels}
            metric={metric}
            onMetricChange={setMetric}
            areas={indicators.areas}
            onSelectArea={handleSearchSelect}
            onResetView={handleResetView}
            years={demand.years}
            yearLabels={demand.year_labels}
            yearIndex={yearIndex}
            onYearIndexChange={setYearIndex}
          />
          <Legend
            metric={metric}
            functionLabel={functionLabel}
            quantileEdges={quantileEdges}
            demandYearLabel={selectedYearLabel}
          />
        </div>
        <aside className="side-panel">
          {selectedArea ? (
            <AreaPanel
              area={selectedArea}
              boundarySource={selectedIndexEntry?.boundary_source ?? null}
              functions={indicators.functions}
              functionLabels={indicators.function_labels}
              demandArea={selectedDemandArea}
              demandCategories={demand.categories}
              demandCategoryLabels={demand.category_labels}
              demandYears={demand.years}
              demandYearLabels={demand.year_labels}
              demandBaselineYear={demand.baseline_year}
            />
          ) : (
            <p className="area-panel-placeholder">
              地図上の区域をクリックするか、区域検索で選ぶと詳細が表示されます。
            </p>
          )}
          <SourceNotes metadata={indicators.metadata} demandMetadata={demand.metadata} />
        </aside>
      </div>
    </div>
  );
}
