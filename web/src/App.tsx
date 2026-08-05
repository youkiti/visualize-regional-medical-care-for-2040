import { useCallback, useMemo, useRef, useState } from 'react';

import MapView, { type MapViewHandle } from './components/MapView';
import Legend from './components/Legend';
import Controls from './components/Controls';
import AreaPanel from './components/AreaPanel';
import BulkDownload from './components/BulkDownload';
import SourceNotes from './components/SourceNotes';
import { computeQuantileEdges, isDemandMetric } from './lib/metrics';
import { useFacilityShard } from './lib/facilityShard';
import { buildFacilityPoints } from './lib/facilityPoints';
import { buildAreaDetailCsv, buildAreaTableCsv, buildFacilityCsv } from './lib/downloads';
import { triggerDownload } from './lib/triggerDownload';
import mapDataUrl from './generated/area_map.json?url';
import indicatorsJson from './generated/area_indicators.json';
import demandJson from './generated/area_demand.json';
import areaIndexJson from './generated/area_index.json';
import facilitySummaryJson from './generated/facility_summary.json';
import downloadManifestJson from './generated/download_manifest.json';
import type {
  AreaDemandData,
  AreaIndexEntry,
  AreaIndicatorsData,
  BedFunctionKey,
  DownloadManifest,
  FacilitySummaryData,
  MetricKind,
} from './types';

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

// generated/facility_summary.json is the bundled, lightweight (no facilities[])
// summary of data/processed/area_facilities_R7.json — see types.ts
// FacilitySummaryData for why this isn't reusing AreaIndicatorsData/AreaDemandData.
// The per-area facility list itself is fetched lazily per selected area via
// useFacilityShard (web/public/facilities/<area_code>.json), not bundled here.
const facilitySummary = facilitySummaryJson as unknown as FacilitySummaryData;
const facilitySummaryByCode = new Map(facilitySummary.areas.map((a) => [a.area_code, a]));

// generated/download_manifest.json describes the bulk-download build
// artifacts under web/public/downloads/ (the processed-CSV ZIP and the
// standalone boundaries GeoJSON copy) — see types.ts DownloadManifest for why
// this isn't reusing any of the *_R7.json-derived types above (it has no
// source/processing/known_issues block; it's a manifest of build outputs,
// not a copy/summary of a data/processed/ source of truth).
const downloadManifest = downloadManifestJson as unknown as DownloadManifest;

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

  // 医療機関shardは選択中の区域1本だけを取得する(339区域ぶんをバンドルしない)。
  // 競合状態対策・メモリキャッシュはuseFacilityShard内部で完結している
  // (facilityShard.ts参照)。
  const { status: facilityStatus, shard: facilityShard, error: facilityError, retry: retryFacilities } =
    useFacilityShard(selectedAreaCode);
  const selectedFacilitySummary = selectedAreaCode ? facilitySummaryByCode.get(selectedAreaCode) ?? null : null;

  // 地図に出す医療機関ポイント。選択区域のshardが変わったときだけ組み立て
  // 直す(facilitySummary.metricsはモジュールスコープの定数で参照が変わらない)。
  // shard===null(未選択/未取得)のときは buildFacilityPoints 側が空の
  // FeatureCollectionを返すので、区域選択を解除すると地図の点も消える。
  const facilityPoints = useMemo(
    () => buildFacilityPoints(facilityShard?.facilities ?? null, facilitySummary.metrics),
    [facilityShard]
  );

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

  // 以下3つのダウンロードハンドラは、いずれもlib/downloads.tsの純関数で
  // CSV本文を組み立て、lib/triggerDownload.tsでブラウザに保存させるだけ
  // （新しいデータ処理はここに書かない）。ボタン側で無効化される条件
  // （選択区域なし・shard未取得）を、念のためハンドラ内でも防御的に握る。

  // 今の指標・病床機能・年度のまま、全339区域ぶんをCSVにする(Controls「表示中のデータをCSV」)。
  const handleDownloadAreaTable = useCallback(() => {
    const { filename, text } = buildAreaTableCsv({ indicators, demand, metric, bedFunction, year: selectedYear });
    triggerDownload(filename, text);
  }, [metric, bedFunction, selectedYear]);

  // 選択中の区域1つの指標をCSVにする(AreaPanel「この区域の指標をCSV」)。
  const handleDownloadAreaDetail = useCallback(() => {
    if (!selectedArea) return;
    const { filename, text } = buildAreaDetailCsv({
      area: selectedArea,
      demandArea: selectedDemandArea,
      indicatorsMetadata: indicators.metadata,
      demandMetadata: demand.metadata,
      functions: indicators.functions,
      functionLabels: indicators.function_labels,
      demandCategories: demand.categories,
      demandCategoryLabels: demand.category_labels,
      demandYears: demand.years,
      demandYearLabels: demand.year_labels,
      baselineYear: demand.baseline_year,
    });
    triggerDownload(filename, text);
  }, [selectedArea, selectedDemandArea]);

  // 選択中の区域の医療機関一覧をCSVにする(FacilityList「一覧をCSV」)。
  const handleDownloadFacilities = useCallback(() => {
    if (!facilityShard) return;
    const { filename, text } = buildFacilityCsv({
      shard: facilityShard,
      metrics: facilitySummary.metrics,
      valueStatusLabels: facilitySummary.value_status_labels,
      facilitySummaryMetadata: facilitySummary.metadata,
    });
    triggerDownload(filename, text);
  }, [facilityShard]);

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
            facilityPoints={facilityPoints}
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
            onDownloadAreaTable={handleDownloadAreaTable}
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
            showFacilityNote={selectedAreaCode !== null}
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
              facilityCount={selectedFacilitySummary?.facility_count ?? 0}
              facilityStatus={facilityStatus}
              facilities={facilityShard?.facilities ?? null}
              facilityError={facilityError}
              onRetryFacilities={retryFacilities}
              facilityMetrics={facilitySummary.metrics}
              facilityValueStatusLabels={facilitySummary.value_status_labels}
              onDownloadAreaDetail={handleDownloadAreaDetail}
              onDownloadFacilities={handleDownloadFacilities}
            />
          ) : (
            <p className="area-panel-placeholder">
              地図上の区域をクリックするか、区域検索で選ぶと詳細が表示されます。
            </p>
          )}
          <BulkDownload manifest={downloadManifest} />
          <SourceNotes
            metadata={indicators.metadata}
            demandMetadata={demand.metadata}
            facilityMetadata={facilitySummary.metadata}
          />
        </aside>
      </div>
    </div>
  );
}
