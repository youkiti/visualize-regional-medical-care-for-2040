import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import MapView, { type MapViewHandle } from './components/MapView';
import Legend from './components/Legend';
import Controls from './components/Controls';
import AreaPanel from './components/AreaPanel';
import PrefecturePanel from './components/PrefecturePanel';
import BulkDownload from './components/BulkDownload';
import SourceNotes from './components/SourceNotes';
import { computeQuantileEdges, isDemandMetric, isYoyMetric } from './lib/metrics';
import { useFacilityShard } from './lib/facilityShard';
import { useFlowData } from './lib/flowData';
import type { FlowOverlay } from './lib/flowMap';
import { buildFacilityPoints } from './lib/facilityPoints';
import {
  buildAreaDetailCsv,
  buildAreaFlowCsv,
  buildAreaTableCsv,
  buildFacilityCsv,
  buildPrefectureDetailCsv,
  buildPrefectureTableCsv,
} from './lib/downloads';
import { triggerDownload } from './lib/triggerDownload';
import mapDataUrl from './generated/area_map.json?url';
import prefMapDataUrl from './generated/pref_map.json?url';
import indicatorsJson from './generated/area_indicators.json';
import demandJson from './generated/area_demand.json';
import yoyJson from './generated/area_yoy.json';
import areaIndexJson from './generated/area_index.json';
import prefectureIndicatorsJson from './generated/prefecture_indicators.json';
import prefectureYoyJson from './generated/prefecture_yoy.json';
import facilitySummaryJson from './generated/facility_summary.json';
import downloadManifestJson from './generated/download_manifest.json';
import type {
  AreaDemandData,
  AreaIndexEntry,
  AreaIndicatorsData,
  AreaYoyData,
  BedFunctionKey,
  DownloadManifest,
  FacilitySummaryData,
  FlowDirectionKey,
  FlowPhaseKey,
  MapLevel,
  MetricKind,
  PrefectureIndicatorsData,
  PrefectureYoyData,
} from './types';

// generated/area_indicators.json is a verbatim copy of
// data/processed/area_indicators_R7.json (see CLAUDE.md / scripts/sync-data.mjs)
// — its shape is documented by AreaIndicatorsData in types.ts.
const indicators = indicatorsJson as unknown as AreaIndicatorsData;

// generated/area_demand.json is a verbatim copy of
// data/processed/area_demand_R7.json (same treatment as area_indicators.json
// above) — its shape is documented by AreaDemandData in types.ts.
const demand = demandJson as unknown as AreaDemandData;

// generated/area_yoy.json is a verbatim copy of
// data/processed/area_yoy_R6_R7.json (same treatment as area_indicators.json
// above; small enough — ~290KB — to bundle without sharding) — its shape is
// documented by AreaYoyData in types.ts.
const yoy = yoyJson as unknown as AreaYoyData;

// generated/area_index.json is the lightweight (bundled, not fetched)
// bbox/boundary_source lookup — see scripts/lib/merge.mjs buildAreaIndex()
// and types.ts AreaIndexEntry. Selection (from either 区域検索 or a map
// click) is resolved through this map, not through the map's own feature
// query, so it works regardless of the map's current load/viewport state.
const areaIndex = areaIndexJson as unknown as AreaIndexEntry[];
const areaIndexByCode = new Map(areaIndex.map((entry) => [entry.area_code, entry]));

// generated/prefecture_indicators.json is a verbatim copy of
// data/processed/prefecture_indicators_R7.json — the overview (都道府県) layer's
// beds + demand, plus the 全国 row that has no boundary of its own. Its shape
// is documented by PrefectureIndicatorsData in types.ts (it deliberately does
// NOT reuse the AreaIndicators*/AreaDemand* types — see the comment there).
const prefectureIndicators = prefectureIndicatorsJson as unknown as PrefectureIndicatorsData;
const prefectureByCode = new Map(prefectureIndicators.prefectures.map((p) => [p.pref_code, p]));

// generated/prefecture_yoy.json is a verbatim copy of
// data/processed/prefecture_yoy_R6_R7.json (tools/build_web_prefecture_yoy.py).
// 区域側の area_yoy.json と指標の定義は同一だが、エンティティが pref_code で
// 全国が national キーに分かれているため型は別（types.ts の PrefectureYoyData）。
const prefectureYoy = prefectureYoyJson as unknown as PrefectureYoyData;
const prefectureYoyByCode = new Map(prefectureYoy.prefectures.map((p) => [p.pref_code, p]));

// 都道府県のbboxは pref_map.json 側にあるが、地図の読み込み状態に依存せず
// 「県を選んで区域表示へ降りる」を成立させるため、区域と同じくバンドル済み
// データ(area_index.json)から算出する。区域のbboxの和集合＝県のbboxになる
// (県境は区域境界のディゾルブなので、両者の外周は一致する)。
const prefBBoxByCode = new Map<string, [number, number, number, number]>();
for (const entry of areaIndex) {
  const prefCode = entry.area_code.slice(0, 2);
  const current = prefBBoxByCode.get(prefCode);
  if (!current) {
    prefBBoxByCode.set(prefCode, [entry.bb_w, entry.bb_s, entry.bb_e, entry.bb_n]);
    continue;
  }
  current[0] = Math.min(current[0], entry.bb_w);
  current[1] = Math.min(current[1], entry.bb_s);
  current[2] = Math.max(current[2], entry.bb_e);
  current[3] = Math.max(current[3], entry.bb_n);
}

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

// area_flow.json は区域を選ぶまで遅延取得しない(useFlowData)ため、取得完了前
// (idle/loading/error)はFlowPanelへ渡す direction_labels/phase_labels が無い。
// これらは原典シート名・区分ヘッダーそのままの固定語彙(area_flow.jsonのfields
// 説明に明記)であり取得結果と食い違うことはないため、取得前はこのフォールバック
// を渡してFlowPanel側の型をnon-nullに保つ(実際に使われるのは「原典の全体値」
// 行のみで、そこはstatus==='loaded'のときにしか描画されない)。
const FLOW_DIRECTION_LABELS_FALLBACK: Record<FlowDirectionKey, string> = { inflow: '流入率', outflow: '流出率' };
const FLOW_PHASE_LABELS_FALLBACK: Record<FlowPhaseKey, string> = {
  acute: '高度急性期+急性期',
  comprehensive: '包括期',
  chronic: '慢性期',
};

// 地図オーバーレイ・凡例・ツールチップで使う「役割」ラベル。area_flow.jsonの
// direction_labels（原典シート名そのままの「流入率」「流出率」）とは別の語彙で、
// FlowPanel.tsxの方向トグルの文言（DIRECTION_BUTTON_LABELS）と同じ
// 「流入元」「流出先」を使う（凡例タイトル例「患者の流出先の構成比」に合わせる）。
const FLOW_ROLE_LABELS: Record<FlowDirectionKey, string> = { inflow: '流入元', outflow: '流出先' };

export default function App() {
  // 既定は構想区域(要件 §3.1 で「主役の表示単位」とされている方)。都道府県は
  // 概観用のレイヤとしてトグルで切り替える。
  const [level, setLevel] = useState<MapLevel>('area');
  const [bedFunction, setBedFunction] = useState<BedFunctionKey>('total');
  const [metric, setMetric] = useState<MetricKind>('ratio');
  const [yearIndex, setYearIndex] = useState<number>(DEFAULT_YEAR_INDEX);
  const [selectedAreaCode, setSelectedAreaCode] = useState<string | null>(null);
  // 患者の流入・流出パネルの表示状態。地図オーバーレイ(次のチャンク)がこの2つを
  // 読むため、FlowPanel内のローカルstateにせずAppで持つ(brief記載どおり)。
  const [flowDirection, setFlowDirection] = useState<FlowDirectionKey>('outflow');
  const [flowPhase, setFlowPhase] = useState<FlowPhaseKey>('acute');
  // 地図に「相手区域のコロプレス」オーバーレイを出すかどうか。地図の塗りが
  // 指標(病床/需要)と流入出の2つの意味を同時に持たないよう、指標セレクタ・
  // 病床機能・年度スライダーを操作したらfalseに戻す(handleBedFunctionChange等)。
  // 区域選択を解除したときもfalseに戻すが、別区域を選び直したとき(nullを経由
  // しない切替)は維持し、オーバーレイが新しい区域に追随するようにする
  // (下のuseEffect、brief記載どおり)。
  const [flowMapEnabled, setFlowMapEnabled] = useState(false);
  const [selectedPrefCode, setSelectedPrefCode] = useState<string | null>(null);
  const mapRef = useRef<MapViewHandle>(null);

  const functionLabel = indicators.function_labels[bedFunction];
  const selectedYear = demand.years[yearIndex];
  const selectedYearLabel = demand.year_labels[String(selectedYear)] ?? String(selectedYear);

  // Quantile edges for the actual/need metrics are derived from
  // area_indicators.json (bundled, no need to parse area_map.json at
  // runtime) — the a_*/n_* values in area_map.json are the same numbers.
  // Demand metrics use their own fixed (non-quantile) bins (see
  // DEMAND_RATIO_BIN_EDGES in lib/metrics.ts), and YoY metrics likewise use
  // fixed bins (YOY_RATIO_BIN_EDGES), so none of them need this at all.
  // 分位は表示単位ごとに別物にする（47都道府県の分位を339区域へ、あるいはその逆を
  // 当てると、凡例の区分と地図の色が実データの分布から外れる）。固定境界の
  // 'ratio'・需要指標・YoY指標には影響しない。
  const quantileEdges = useMemo(() => {
    if (metric === 'ratio' || isDemandMetric(metric) || isYoyMetric(metric)) return [];
    const key = metric === 'actual' ? 'actual_2025' : 'need_2025';
    const values =
      level === 'pref'
        ? prefectureIndicators.prefectures.map((pref) => pref.beds[bedFunction][key])
        : indicators.areas.map((area) => area.beds[bedFunction][key]);
    return computeQuantileEdges(values);
  }, [bedFunction, metric, level]);

  const selectedArea = useMemo(() => {
    if (!selectedAreaCode) return null;
    return indicators.areas.find((area) => area.area_code === selectedAreaCode) ?? null;
  }, [selectedAreaCode]);

  const selectedDemandArea = useMemo(() => {
    if (!selectedAreaCode) return null;
    return demand.areas.find((area) => area.area_code === selectedAreaCode) ?? null;
  }, [selectedAreaCode]);

  const selectedYoyArea = useMemo(() => {
    if (!selectedAreaCode) return null;
    return yoy.areas.find((area) => area.area_code === selectedAreaCode) ?? null;
  }, [selectedAreaCode]);

  const selectedIndexEntry = useMemo(() => {
    if (!selectedAreaCode) return null;
    return areaIndexByCode.get(selectedAreaCode) ?? null;
  }, [selectedAreaCode]);

  const selectedPrefecture = useMemo(() => {
    if (!selectedPrefCode) return null;
    return prefectureByCode.get(selectedPrefCode) ?? null;
  }, [selectedPrefCode]);

  const selectedPrefectureYoy = useMemo(() => {
    if (!selectedPrefCode) return null;
    return prefectureYoyByCode.get(selectedPrefCode) ?? null;
  }, [selectedPrefCode]);

  // 医療機関shardは選択中の区域1本だけを取得する(339区域ぶんをバンドルしない)。
  // 競合状態対策・メモリキャッシュはuseFacilityShard内部で完結している
  // (facilityShard.ts参照)。
  const { status: facilityStatus, shard: facilityShard, error: facilityError, retry: retryFacilities } =
    useFacilityShard(selectedAreaCode);
  const selectedFacilitySummary = selectedAreaCode ? facilitySummaryByCode.get(selectedAreaCode) ?? null : null;

  // 患者の流入・流出データセット(area_flow.json、約499KB)は339区域ぶん全体で
  // 1本のファイルだが、区域が一度も選ばれていない間は取得しない
  // (useFlowDataのenabled引数、flowData.ts参照)。
  const { status: flowStatus, data: flowData, error: flowError, retry: retryFlow } = useFlowData(
    selectedAreaCode !== null
  );
  const selectedFlowEntry = useMemo(() => {
    if (!flowData || !selectedAreaCode) return null;
    return flowData.areas.find((a) => a.area_code === selectedAreaCode) ?? null;
  }, [flowData, selectedAreaCode]);

  // 区域選択が解除されたら地図オーバーレイも解除する。selectedAreaCodeが
  // (nullを経由せず)別の区域へ変わるだけのときはこの条件に触れないので
  // flowMapEnabledは維持され、オーバーレイは新しい区域へ自動的に追随する。
  useEffect(() => {
    if (selectedAreaCode === null) setFlowMapEnabled(false);
  }, [selectedAreaCode]);

  // 地図に渡す患者の流入・流出オーバーレイ。オーバーレイON・区域選択あり・
  // 流入出データ取得済みの3条件が揃ったときだけ組み立てる。
  const flowOverlay: FlowOverlay | null = useMemo(() => {
    // 流入出は構想区域単位のデータなので、都道府県表示中(level==='pref')は
    // オーバーレイ自体を無効にする。ここでnullにしないと、地図の塗りは
    // 都道府県の指標のまま凡例だけ流入出の説明が残り、両者が食い違う
    // （M8の階層トグルとの統合時に実機で見つけた）。構想区域表示へ戻せば
    // flowMapEnabled は維持されているのでオーバーレイも復帰する。
    if (level !== 'area') return null;
    if (!flowMapEnabled || !selectedAreaCode || !selectedArea || !selectedFlowEntry) return null;
    const group = selectedFlowEntry.flows[flowDirection].phases[flowPhase];
    return {
      selfCode: selectedAreaCode,
      selfRate: group.self_rate,
      entries: group.partners,
      direction: flowDirection,
      phase: flowPhase,
      areaName: selectedArea.area_name,
      directionLabel: FLOW_ROLE_LABELS[flowDirection],
      phaseLabel: (flowData?.phase_labels ?? FLOW_PHASE_LABELS_FALLBACK)[flowPhase],
    };
  }, [level, flowMapEnabled, selectedAreaCode, selectedArea, selectedFlowEntry, flowDirection, flowPhase, flowData]);

  // 地図に出す医療機関ポイント。選択区域のshardが変わったときだけ組み立て
  // 直す(facilitySummary.metricsはモジュールスコープの定数で参照が変わらない)。
  // shard===null(未選択/未取得)のときは buildFacilityPoints 側が空の
  // FeatureCollectionを返すので、区域選択を解除すると地図の点も消える。
  // 都道府県表示中は医療機関の点を出さない（区域を選んだまま概観へ切り替えても、
  // 前の区域の点が県の塗りの上に残らないようにする）。区域へ戻せば
  // useFacilityShard のキャッシュから再取得なしで復帰する。
  const facilityPoints = useMemo(
    () =>
      level === 'area'
        ? buildFacilityPoints(facilityShard?.facilities ?? null, facilitySummary.metrics)
        : buildFacilityPoints(null, facilitySummary.metrics),
    [facilityShard, level]
  );

  const handleResetView = () => {
    mapRef.current?.resetView();
    setSelectedAreaCode(null);
    setSelectedPrefCode(null);
  };

  // 指標セレクタ・病床機能・年度スライダーは地図の塗りの意味そのものを
  // 変える操作なので、流入出オーバーレイがONのままだと塗りが2つの意味を
  // 同時に持ってしまう。この3操作のいずれかで必ずオーバーレイを解除する
  // (brief記載どおり)。
  const handleBedFunctionChange = useCallback((fn: BedFunctionKey) => {
    setBedFunction(fn);
    setFlowMapEnabled(false);
  }, []);

  const handleMetricChange = useCallback((m: MetricKind) => {
    setMetric(m);
    setFlowMapEnabled(false);
  }, []);

  const handleYearIndexChange = useCallback((idx: number) => {
    setYearIndex(idx);
    setFlowMapEnabled(false);
  }, []);

  // FlowPanel「この内訳を地図に表示」トグル。
  const handleToggleFlowMap = useCallback(() => {
    setFlowMapEnabled((v) => !v);
  }, []);

  // Map click: MapView already resolved the area_code from the clicked
  // feature (or null on a miss) — just record the selection. The view
  // itself doesn't move (unchanged from before this fix).
  const handleMapSelectArea = (areaCode: string | null) => {
    setSelectedAreaCode(areaCode);
  };

  // 地図クリック（都道府県表示中）。区域と同じく選択を記録するだけで視点は動かさない。
  const handleMapSelectPrefecture = (prefCode: string | null) => {
    setSelectedPrefCode(prefCode);
  };

  // 区域検索: selection no longer depends on the map's load/viewport state
  // (see MapView.selectArea) — App resolves the bbox itself from
  // area_index.json and only asks the map to fitBounds.
  // 検索の対象は構想区域なので、都道府県表示中に選ばれたら表示単位も区域へ切り替える
  // （切り替えないと、選んだ区域が塗られていない地図の上で選択だけが起きる）。
  const handleSearchSelect = (areaCode: string) => {
    setLevel('area');
    setSelectedAreaCode(areaCode);
    const entry = areaIndexByCode.get(areaCode);
    if (entry) {
      mapRef.current?.selectArea([entry.bb_w, entry.bb_s, entry.bb_e, entry.bb_n]);
    }
  };

  // 都道府県パネルの「この県の構想区域を見る」。表示単位を区域へ落として当該県へ
  // ズームし、区域の選択は空にする（どの区域かはまだ選ばれていないため）。
  const handleDrillDownToAreas = () => {
    if (!selectedPrefCode) return;
    setLevel('area');
    setSelectedAreaCode(null);
    const bbox = prefBBoxByCode.get(selectedPrefCode);
    if (bbox) {
      mapRef.current?.selectArea(bbox);
    }
  };

  // 以下3つのダウンロードハンドラは、いずれもlib/downloads.tsの純関数で
  // CSV本文を組み立て、lib/triggerDownload.tsでブラウザに保存させるだけ
  // （新しいデータ処理はここに書かない）。ボタン側で無効化される条件
  // （選択区域なし・shard未取得）を、念のためハンドラ内でも防御的に握る。

  // 今の指標・病床機能・年度のまま、地図に出ている表示単位ぶんをCSVにする
  // (Controls「表示中のデータをCSV」)。表示単位が都道府県なら47都道府県、
  // 構想区域なら339区域を出す。都道府県×年度間比較の組み合わせは
  // buildPrefectureTableCsv が throw するため、Controls側でボタンを無効化して
  // ある(データセットが無い旨をtitleで説明している)。
  const handleDownloadTable = useCallback(() => {
    const { filename, text } =
      level === 'pref'
        ? buildPrefectureTableCsv({
            prefectures: prefectureIndicators,
            prefectureYoy,
            metric,
            bedFunction,
            year: selectedYear,
          })
        : buildAreaTableCsv({ indicators, demand, yoy, metric, bedFunction, year: selectedYear });
    triggerDownload(filename, text);
  }, [level, metric, bedFunction, selectedYear]);

  // 選択中の都道府県1つの指標をCSVにする(PrefecturePanel「この都道府県の指標をCSV」)。
  const handleDownloadPrefectureDetail = useCallback(() => {
    if (!selectedPrefecture) return;
    const { filename, text } = buildPrefectureDetailCsv({
      prefecture: selectedPrefecture,
      metadata: prefectureIndicators.metadata,
      yoyEntry: selectedPrefectureYoy,
      yoyMetadata: prefectureYoy.metadata,
      functions: prefectureIndicators.functions,
      functionLabels: prefectureIndicators.function_labels,
      demandCategories: prefectureIndicators.categories,
      demandCategoryLabels: prefectureIndicators.category_labels,
      demandYears: prefectureIndicators.years,
      demandYearLabels: prefectureIndicators.year_labels,
      baselineYear: prefectureIndicators.baseline_year,
    });
    triggerDownload(filename, text);
  }, [selectedPrefecture, selectedPrefectureYoy]);

  // 選択中の区域1つの指標をCSVにする(AreaPanel「この区域の指標をCSV」)。
  const handleDownloadAreaDetail = useCallback(() => {
    if (!selectedArea) return;
    const { filename, text } = buildAreaDetailCsv({
      area: selectedArea,
      demandArea: selectedDemandArea,
      yoyArea: selectedYoyArea,
      indicatorsMetadata: indicators.metadata,
      demandMetadata: demand.metadata,
      yoyMetadata: yoy.metadata,
      functions: indicators.functions,
      functionLabels: indicators.function_labels,
      demandCategories: demand.categories,
      demandCategoryLabels: demand.category_labels,
      demandYears: demand.years,
      demandYearLabels: demand.year_labels,
      baselineYear: demand.baseline_year,
    });
    triggerDownload(filename, text);
  }, [selectedArea, selectedDemandArea, selectedYoyArea]);

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

  // 選択中の区域・方向・区分の流入出内訳をCSVにする(FlowPanel「この内訳をCSV」)。
  const handleDownloadFlow = useCallback(() => {
    if (!selectedArea || !selectedFlowEntry || !flowData) return;
    const { filename, text } = buildAreaFlowCsv({
      area: selectedArea,
      flowEntry: selectedFlowEntry,
      direction: flowDirection,
      phase: flowPhase,
      directionLabels: flowData.direction_labels,
      phaseLabels: flowData.phase_labels,
      flowMetadata: flowData.metadata,
      areas: indicators.areas,
    });
    triggerDownload(filename, text);
  }, [selectedArea, selectedFlowEntry, flowData, flowDirection, flowPhase]);

  return (
    <div className="app">
      <header className="app-header">
        <h1>地域医療構想 可視化（2040年に向けて）</h1>
        <p>
          47都道府県／339構想区域ごとに、2025年病床数（実績・必要数）と、在宅（訪問診療）・外来の医療需要推計
          （2024〜2050年度、2024年度比）を比較します。構想区域を選ぶと個別の医療機関まで辿れます。
        </p>
      </header>
      <div className="app-body">
        <div className="map-pane">
          <MapView
            ref={mapRef}
            mapDataUrl={mapDataUrl}
            prefMapDataUrl={prefMapDataUrl}
            level={level}
            bedFunction={bedFunction}
            metric={metric}
            functionLabel={functionLabel}
            quantileEdges={quantileEdges}
            selectedAreaCode={selectedAreaCode}
            onSelectArea={handleMapSelectArea}
            selectedPrefCode={selectedPrefCode}
            onSelectPrefecture={handleMapSelectPrefecture}
            demandYear={selectedYear}
            demandYearLabel={selectedYearLabel}
            demandCategoryLabels={demand.category_labels}
            facilityPoints={facilityPoints}
            flowOverlay={flowOverlay}
          />
          <Controls
            level={level}
            onLevelChange={setLevel}
            bedFunction={bedFunction}
            onBedFunctionChange={handleBedFunctionChange}
            functions={indicators.functions}
            functionLabels={indicators.function_labels}
            metric={metric}
            onMetricChange={handleMetricChange}
            areas={indicators.areas}
            onSelectArea={handleSearchSelect}
            onResetView={handleResetView}
            onDownloadTable={handleDownloadTable}
            years={demand.years}
            yearLabels={demand.year_labels}
            yearIndex={yearIndex}
            onYearIndexChange={handleYearIndexChange}
          />
          <Legend
            level={level}
            metric={metric}
            functionLabel={functionLabel}
            quantileEdges={quantileEdges}
            demandYearLabel={selectedYearLabel}
            showFacilityNote={level === 'area' && selectedAreaCode !== null}
            flowOverlay={flowOverlay}
          />
        </div>
        <aside className="side-panel">
          {level === 'pref' ? (
            selectedPrefecture ? (
              <PrefecturePanel
                prefecture={selectedPrefecture}
                national={prefectureIndicators.national}
                functions={prefectureIndicators.functions}
                functionLabels={prefectureIndicators.function_labels}
                demandCategories={prefectureIndicators.categories}
                demandCategoryLabels={prefectureIndicators.category_labels}
                demandYears={prefectureIndicators.years}
                demandYearLabels={prefectureIndicators.year_labels}
                demandBaselineYear={prefectureIndicators.baseline_year}
                bedsCaveat={prefectureIndicators.metadata.processing.caveat.beds}
                yoyEntry={selectedPrefectureYoy}
                onDrillDown={handleDrillDownToAreas}
                onDownloadDetail={handleDownloadPrefectureDetail}
              />
            ) : (
              <p className="area-panel-placeholder">
                地図上の都道府県をクリックすると詳細が表示されます。個別の医療機関まで見るには
                「表示単位」を構想区域に切り替えてください。
              </p>
            )
          ) : selectedArea ? (
            <AreaPanel
              area={selectedArea}
              boundarySource={selectedIndexEntry?.boundary_source ?? null}
              functions={indicators.functions}
              functionLabels={indicators.function_labels}
              demandArea={selectedDemandArea}
              yoyArea={selectedYoyArea}
              demandCategories={demand.categories}
              demandCategoryLabels={demand.category_labels}
              demandYears={demand.years}
              demandYearLabels={demand.year_labels}
              demandBaselineYear={demand.baseline_year}
              bedsCaveat={indicators.metadata.processing.caveat}
              facilityCount={selectedFacilitySummary?.facility_count ?? 0}
              facilityStatus={facilityStatus}
              facilities={facilityShard?.facilities ?? null}
              facilityError={facilityError}
              onRetryFacilities={retryFacilities}
              facilityMetrics={facilitySummary.metrics}
              facilityValueStatusLabels={facilitySummary.value_status_labels}
              facilityReferenceSnapshotDate={facilitySummary.metadata.geo_audit_source.reference_snapshot_date}
              onDownloadAreaDetail={handleDownloadAreaDetail}
              onDownloadFacilities={handleDownloadFacilities}
              flowStatus={flowStatus}
              flowEntry={selectedFlowEntry}
              flowError={flowError}
              onRetryFlow={retryFlow}
              flowDirection={flowDirection}
              flowPhase={flowPhase}
              onFlowDirectionChange={setFlowDirection}
              onFlowPhaseChange={setFlowPhase}
              flowDirectionLabels={flowData?.direction_labels ?? FLOW_DIRECTION_LABELS_FALLBACK}
              flowPhaseLabels={flowData?.phase_labels ?? FLOW_PHASE_LABELS_FALLBACK}
              indicatorAreas={indicators.areas}
              onDownloadFlow={handleDownloadFlow}
              flowMapEnabled={flowMapEnabled}
              onToggleFlowMap={handleToggleFlowMap}
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
            yoyMetadata={yoy.metadata}
            flowMetadata={flowData?.metadata ?? null}
            prefectureMetadata={prefectureIndicators.metadata}
            prefectureYoyMetadata={prefectureYoy.metadata}
            level={level}
            showFacilitySources={level === 'area' && selectedAreaCode !== null}
          />
        </aside>
      </div>
    </div>
  );
}
