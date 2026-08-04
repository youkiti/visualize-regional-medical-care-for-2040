import { useMemo, useRef, useState } from 'react';

import MapView, { type MapViewHandle } from './components/MapView';
import Legend from './components/Legend';
import Controls from './components/Controls';
import AreaPanel from './components/AreaPanel';
import SourceNotes from './components/SourceNotes';
import { computeQuantileEdges } from './lib/metrics';
import mapDataUrl from './generated/area_map.json?url';
import indicatorsJson from './generated/area_indicators.json';
import areaIndexJson from './generated/area_index.json';
import type { AreaIndexEntry, AreaIndicatorsData, BedFunctionKey, MetricKind } from './types';

// generated/area_indicators.json is a verbatim copy of
// data/processed/area_indicators_R7.json (see CLAUDE.md / scripts/sync-data.mjs)
// — its shape is documented by AreaIndicatorsData in types.ts.
const indicators = indicatorsJson as unknown as AreaIndicatorsData;

// generated/area_index.json is the lightweight (bundled, not fetched)
// bbox/boundary_source lookup — see scripts/lib/merge.mjs buildAreaIndex()
// and types.ts AreaIndexEntry. Selection (from either 区域検索 or a map
// click) is resolved through this map, not through the map's own feature
// query, so it works regardless of the map's current load/viewport state.
const areaIndex = areaIndexJson as unknown as AreaIndexEntry[];
const areaIndexByCode = new Map(areaIndex.map((entry) => [entry.area_code, entry]));

export default function App() {
  const [bedFunction, setBedFunction] = useState<BedFunctionKey>('total');
  const [metric, setMetric] = useState<MetricKind>('ratio');
  const [selectedAreaCode, setSelectedAreaCode] = useState<string | null>(null);
  const mapRef = useRef<MapViewHandle>(null);

  const functionLabel = indicators.function_labels[bedFunction];

  // Quantile edges for the actual/need metrics are derived from
  // area_indicators.json (bundled, no need to parse area_map.json at
  // runtime) — the a_*/n_* values in area_map.json are the same numbers.
  const quantileEdges = useMemo(() => {
    if (metric === 'ratio') return [];
    const key = metric === 'actual' ? 'actual_2025' : 'need_2025';
    const values = indicators.areas.map((area) => area.beds[bedFunction][key]);
    return computeQuantileEdges(values);
  }, [bedFunction, metric]);

  const selectedArea = useMemo(() => {
    if (!selectedAreaCode) return null;
    return indicators.areas.find((area) => area.area_code === selectedAreaCode) ?? null;
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
        <h1>地域医療構想 病床可視化（2025年）</h1>
        <p>339構想区域ごとの2025年病床数（実績）と2025年の必要数を、病床機能別に比較します。</p>
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
          />
          <Legend metric={metric} functionLabel={functionLabel} quantileEdges={quantileEdges} />
        </div>
        <aside className="side-panel">
          {selectedArea ? (
            <AreaPanel
              area={selectedArea}
              boundarySource={selectedIndexEntry?.boundary_source ?? null}
              functions={indicators.functions}
              functionLabels={indicators.function_labels}
            />
          ) : (
            <p className="area-panel-placeholder">
              地図上の区域をクリックするか、区域検索で選ぶと詳細が表示されます。
            </p>
          )}
          <SourceNotes metadata={indicators.metadata} />
        </aside>
      </div>
    </div>
  );
}
