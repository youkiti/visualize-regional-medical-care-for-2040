import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';

import type {
  AreaMapFeatureProperties,
  BedFunctionKey,
  DemandCategoryKey,
  MapLevel,
  MetricKind,
  PrefectureMapFeatureProperties,
} from '../types';
import {
  DEMAND_RATIO_BIN_EDGES,
  RATIO_BIN_COLORS,
  RATIO_BIN_EDGES,
  RATIO_UNAVAILABLE_COLOR,
  RATIO_UNAVAILABLE_OUTLINE_COLOR,
  computeSequentialClasses,
  demandCategoryOf,
  demandRatioKey,
  formatChangeRatio,
  formatInteger,
  formatMetricValue,
  formatReceipts,
  isDemandMetric,
  readDemandRatio,
  readDemandValue,
  readMetricValue,
} from '../lib/metrics';
import { EMPTY_FACILITY_POINTS, type FacilityPointFeatureCollection, type FacilityPointProperties } from '../lib/facilityPoints';

// 沖縄県〜北海道を含む初期表示範囲。東京都島しょ部(小笠原諸島・南鳥島)は範囲外
// (SourceNotes に注記あり)。
export const INITIAL_BOUNDS: [[number, number], [number, number]] = [
  [122.9, 24.0],
  [146.4, 45.6],
];
const INITIAL_FIT_OPTIONS: maplibregl.FitBoundsOptions = { padding: 16, animate: false };
const MAX_BOUNDS: [[number, number], [number, number]] = [
  [118, 19],
  [158, 50],
];

const SOURCE_ID = 'areas';
const LAYER_COAST_CASING = 'area-coast-casing';
const LAYER_FILL = 'area-fill';
const LAYER_UNAVAILABLE_OUTLINE = 'area-unavailable-outline';
const LAYER_OUTLINE = 'area-outline';
const LAYER_HOVER_OUTLINE = 'area-hover-outline';
const LAYER_SELECTED_OUTLINE = 'area-selected-outline';

// 概観レイヤ(47都道府県)。区域レイヤと同じ構成のレイヤ群を持ち、level に応じて
// visibility で排他表示する(ソースやレイヤを足し引きしない— 罠5と同種の
// StrictMode対策の作法)。pref-border は例外で、**区域表示中に**県境だけを
// 太線で重ねるためのレイヤ。
const PREF_SOURCE_ID = 'prefectures';
const LAYER_PREF_COAST_CASING = 'pref-coast-casing';
const LAYER_PREF_FILL = 'pref-fill';
const LAYER_PREF_UNAVAILABLE_OUTLINE = 'pref-unavailable-outline';
const LAYER_PREF_OUTLINE = 'pref-outline';
const LAYER_PREF_BORDER = 'pref-border';
const LAYER_PREF_HOVER_OUTLINE = 'pref-hover-outline';
const LAYER_PREF_SELECTED_OUTLINE = 'pref-selected-outline';

// 区域表示中に重ねる県境の色。区域境界(白・0.6px)より濃く太くして階層を
// 見分けられるようにしつつ、hover/selected の輪郭(#0b0b0b)とは別の色にして
// 「選択中の区域」と混同させない。
const PREF_BORDER_COLOR = '#4a5b6a';

// 県境の線幅はズームに追随させる。全国表示(zoom 4前後)で固定1.2pxにすると、
// 47本の県境が塗りの上に重なって地図全体が暗く濁る(区域の色の読み取りを
// 邪魔する)。逆に県へズームインしたときは、区域境界(白0.6px)との階層差が
// 分かる太さが要る。
const PREF_BORDER_WIDTH_EXPRESSION: unknown = [
  'interpolate',
  ['linear'],
  ['zoom'],
  4,
  0.5,
  6,
  1.0,
  8,
  1.8,
];

// 選択区域の医療機関ポイント。ソースは空のFeatureCollectionでスタイル定義時に
// 一度だけ追加し、以後は setData() で更新する(ソースを足し引きしない— 罠5と
// 同種のStrictMode対策の作法)。レイヤは区域レイヤ群より上に置く。
const FACILITIES_SOURCE_ID = 'facilities';
const LAYER_FACILITY_POINTS = 'facility-points';

const NO_MATCH_FILTER: maplibregl.FilterSpecification = ['==', ['get', 'area_code'], ''];
const PREF_NO_MATCH_FILTER: maplibregl.FilterSpecification = ['==', ['get', 'pref_code'], ''];

// 病床数(beds_total)による半径のinterpolate。観測値を持たない施設(['has',
// 'beds_total']がfalse)にも最小半径3pxで点を描く— 欠測を0床として扱わない
// (buildFacilityPoints()がbeds_totalキー自体を省略しているので、['get',...]は
// undefinedを返し、interpolateへ渡すと壊れるためcaseで先に分岐する)。
const FACILITY_RADIUS_EXPRESSION: unknown = [
  'case',
  ['has', 'beds_total'],
  ['interpolate', ['linear'], ['get', 'beds_total'], 0, 3, 50, 5, 200, 8, 500, 12, 1000, 16],
  3,
];

export interface MapViewHandle {
  /** 「全国表示に戻す」— 初期表示と同じ範囲・同じオプションで fitBounds する。 */
  resetView: () => void;
  /**
   * 渡された bbox([west, south, east, north])へ fitBounds するだけ。区域の
   * 存在確認・選択状態の管理は呼び出し側(App)の責務— area_index.json から
   * bbox を解決してから呼ぶこと。
   */
  selectArea: (bbox: [number, number, number, number]) => void;
}

interface MapViewProps {
  mapDataUrl: string;
  /** generated/pref_map.json の URL（概観レイヤ。区域と同じく MapLibre に fetch させる）。 */
  prefMapDataUrl: string;
  /** 表示単位。'pref' のときは都道府県を塗り、'area' のときは区域を塗って県境を線で重ねる。 */
  level: MapLevel;
  bedFunction: BedFunctionKey;
  metric: MetricKind;
  functionLabel: string;
  /** computeQuantileEdges() の8値。**現在の level のデータから算出したもの**を渡す
   * （47都道府県と339区域では分位が別物になるため）。metric が 'ratio' または
   * 需要指標のときは未使用。 */
  quantileEdges: number[];
  selectedAreaCode: string | null;
  /** 地図クリックで選ばれた区域の area_code（クリックが外れたら null）。 */
  onSelectArea: (areaCode: string | null) => void;
  selectedPrefCode: string | null;
  /** 地図クリックで選ばれた都道府県の pref_code（クリックが外れたら null）。 */
  onSelectPrefecture: (prefCode: string | null) => void;
  /** 需要指標選択中に使う選択年度（西暦）とそのラベル原文。bed指標選択中は未使用。 */
  demandYear: number;
  demandYearLabel: string;
  demandCategoryLabels: Record<DemandCategoryKey, string>;
  /** 選択区域の医療機関ポイント(App側でfacilityShardから組み立て済み)。未選択/未取得時は空のFeatureCollection。 */
  facilityPoints: FacilityPointFeatureCollection;
}

/** ホバー中のツールチップの種別を区別する。区域と施設のツールチップを同時に
 * 出さないための単一の状態にしている(施設ポイントは区域ポリゴンの真上に
 * 乗るため、両方のレイヤが同じ座標でヒットしうる)。 */
type HoverState =
  | { kind: 'area'; props: AreaMapFeatureProperties; x: number; y: number }
  | { kind: 'pref'; props: PrefectureMapFeatureProperties; x: number; y: number }
  | { kind: 'facility'; props: FacilityPointProperties; x: number; y: number };

function buildFillColorExpression(
  metric: MetricKind,
  bedFunction: BedFunctionKey,
  quantileEdges: number[],
  demandYear: number
): unknown {
  if (isDemandMetric(metric)) {
    // 需要指標は分位ではなく固定境界(DEMAND_RATIO_BIN_EDGES)を使う。年度スライダーで
    // 年度を切り替えても同じ値(例: 2024年度比+20%)が常に同じ色になるようにするため
    // ―分位だと年度ごとに区分の閾値が変わってしまい、色の意味が年度間で揺れる。
    // 値は scripts/lib/merge.mjs buildAreaMap が area_map.json に
    // <category>_r_<year> = value(year)/value(2024) として事前計算済みで、Pythonの
    // ビルド時検証(tools/build_web_demand.py 検証7)で基準年が全area×区分で0でない
    // ことを確認済みのため、'ratio'指標のような「算出不可」の case 分岐は不要
    // (罠2: step の stop は厳密昇順— DEMAND_RATIO_BIN_EDGES は固定の昇順定数)。
    const category = demandCategoryOf(metric);
    const key = demandRatioKey(category, demandYear);
    const stepExpr: unknown[] = ['step', ['get', key], RATIO_BIN_COLORS[0]];
    DEMAND_RATIO_BIN_EDGES.forEach((edge, i) => {
      stepExpr.push(edge, RATIO_BIN_COLORS[i + 1]);
    });
    return stepExpr;
  }

  if (metric === 'ratio') {
    const key = `r_${bedFunction}`;
    const stepExpr: unknown[] = ['step', ['get', key], RATIO_BIN_COLORS[0]];
    RATIO_BIN_EDGES.forEach((edge, i) => {
      stepExpr.push(edge, RATIO_BIN_COLORS[i + 1]);
    });
    return ['case', ['!', ['has', key]], RATIO_UNAVAILABLE_COLOR, stepExpr];
  }

  const key = metric === 'actual' ? `a_${bedFunction}` : `n_${bedFunction}`;
  const { edges, colors } = computeSequentialClasses(quantileEdges);
  const stepExpr: unknown[] = ['step', ['get', key], colors[0]];
  for (let i = 1; i < edges.length - 1; i++) {
    stepExpr.push(edges[i], colors[i]);
  }
  return stepExpr;
}

/** ホバー中のツールチップ本文（1行）。bed指標/需要指標で別の組み立て方をする。 */
function formatHoverTooltip(
  props: Record<string, unknown>,
  metric: MetricKind,
  bedFunction: BedFunctionKey,
  functionLabel: string,
  demandYear: number,
  demandYearLabel: string,
  demandCategoryLabels: Record<DemandCategoryKey, string>
): string {
  if (isDemandMetric(metric)) {
    const category = demandCategoryOf(metric);
    const value = readDemandValue(props, category, demandYear);
    const ratio = readDemandRatio(props, category, demandYear);
    const valueText = value === null ? '—' : formatReceipts(value);
    const ratioText = ratio === null ? '' : `（2024年度比 ${formatChangeRatio(ratio)}）`;
    return `${demandCategoryLabels[category]} ${demandYearLabel}: ${valueText}${ratioText}`;
  }
  return `${functionLabel}: ${formatMetricValue(metric, readMetricValue(props, metric, bedFunction))}`;
}

/** 施設ホバーのツールチップ本文（1行）。beds_totalは観測値の施設にしか無いキーなので存在チェックする。 */
function formatFacilityTooltipBody(props: FacilityPointProperties): string {
  const bedsText =
    props.beds_total === undefined ? '病床数（休棟中等含む計） —' : `病床数（休棟中等含む計） ${formatInteger(props.beds_total)} 床`;
  return props.municipality ? `${props.municipality} ・ ${bedsText}` : bedsText;
}

const MapView = forwardRef<MapViewHandle, MapViewProps>(function MapView(
  {
    mapDataUrl,
    prefMapDataUrl,
    level,
    bedFunction,
    metric,
    functionLabel,
    quantileEdges,
    selectedAreaCode,
    onSelectArea,
    selectedPrefCode,
    onSelectPrefecture,
    demandYear,
    demandYearLabel,
    demandCategoryLabels,
    facilityPoints,
  },
  ref
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(true);
  // initError: `new maplibregl.Map` itself threw — there is no map, so the
  // full-screen error overlay is the only option.
  // runtimeError: a (potentially recoverable) 'error' event fired after the
  // map was created — shown as a small non-blocking notice instead, and
  // cleared automatically once the source finishes loading successfully.
  const [initError, setInitError] = useState<string | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [hover, setHover] = useState<HoverState | null>(null);

  // Event handlers below are registered once (map is created once) but need
  // the latest callback/prop values — route them through refs to avoid
  // stale closures without re-creating the map on every prop change.
  const onSelectAreaRef = useRef(onSelectArea);
  onSelectAreaRef.current = onSelectArea;
  const onSelectPrefectureRef = useRef(onSelectPrefecture);
  onSelectPrefectureRef.current = onSelectPrefecture;
  // イベントハンドラは一度だけ登録されるので、level も ref 経由で最新値を読む
  // (level が変わるたびに地図を作り直さない)。
  const levelRef = useRef(level);
  levelRef.current = level;

  useEffect(() => {
    if (!containerRef.current) return undefined;

    let map: maplibregl.Map;
    try {
      const style: maplibregl.StyleSpecification = {
        version: 8,
        sources: {
          [SOURCE_ID]: {
            type: 'geojson',
            data: mapDataUrl,
          },
          [PREF_SOURCE_ID]: {
            type: 'geojson',
            data: prefMapDataUrl,
          },
          // 空のFeatureCollectionで一度だけ追加し、以後はsetData()で更新する
          // (選択区域が変わるたびにソースを足し引きしない)。
          [FACILITIES_SOURCE_ID]: {
            type: 'geojson',
            data: EMPTY_FACILITY_POINTS,
          },
        },
        layers: [
          { id: 'background', type: 'background', paint: { 'background-color': '#dde5ec' } },
          // 海岸線のケーシング。全区域の境界を太めの線で「塗りの下に」描くと、
          // 内陸の境界は隣接区域の塗りに覆われて消え、海に面した外周だけが縁として
          // 残る。塗りの色そのもので陸と海を分けるのは原理的に無理なため
          // (発散配色の中立 #e1e0d9 も連続配色の淡端 #cde2fb も海 #dde5ec に対して
          // 1.04:1 しかなく、海をどの明度にしてもランプのどこかと必ず衝突する)、
          // 陸の輪郭は線で担保する。
          {
            id: LAYER_COAST_CASING,
            type: 'line',
            source: SOURCE_ID,
            paint: { 'line-color': '#7d93a5', 'line-width': 2.4 },
          },
          {
            id: LAYER_FILL,
            type: 'fill',
            source: SOURCE_ID,
            // ケーシングを内陸側で完全に覆うため不透明にする(検証済みの配色を
            // そのままの値で表示することにもなる)。
            paint: { 'fill-color': RATIO_UNAVAILABLE_COLOR, 'fill-opacity': 1 },
          },
          {
            id: LAYER_UNAVAILABLE_OUTLINE,
            type: 'line',
            source: SOURCE_ID,
            filter: ['!', ['has', `r_${bedFunction}`]],
            paint: {
              'line-color': RATIO_UNAVAILABLE_OUTLINE_COLOR,
              'line-width': 1,
              'line-dasharray': [2, 2],
            },
          },
          {
            id: LAYER_OUTLINE,
            type: 'line',
            source: SOURCE_ID,
            paint: { 'line-color': '#ffffff', 'line-width': 0.6 },
          },
          // --- 概観レイヤ(47都道府県) ---
          // 区域レイヤ群の「上」に置く。level==='pref' のときは塗り・ケーシング・
          // 白縁を出して区域レイヤを隠し、level==='area' のときは
          // LAYER_PREF_BORDER(県境の線)だけを残して区域の塗りの上に重ねる。
          // 初期 visibility は下の同期effectが level に合わせて上書きする。
          {
            id: LAYER_PREF_COAST_CASING,
            type: 'line',
            source: PREF_SOURCE_ID,
            paint: { 'line-color': '#7d93a5', 'line-width': 2.4 },
          },
          {
            id: LAYER_PREF_FILL,
            type: 'fill',
            source: PREF_SOURCE_ID,
            paint: { 'fill-color': RATIO_UNAVAILABLE_COLOR, 'fill-opacity': 1 },
          },
          {
            id: LAYER_PREF_UNAVAILABLE_OUTLINE,
            type: 'line',
            source: PREF_SOURCE_ID,
            filter: ['!', ['has', `r_${bedFunction}`]],
            paint: {
              'line-color': RATIO_UNAVAILABLE_OUTLINE_COLOR,
              'line-width': 1,
              'line-dasharray': [2, 2],
            },
          },
          {
            id: LAYER_PREF_OUTLINE,
            type: 'line',
            source: PREF_SOURCE_ID,
            paint: { 'line-color': '#ffffff', 'line-width': 0.8 },
          },
          {
            id: LAYER_PREF_BORDER,
            type: 'line',
            source: PREF_SOURCE_ID,
            paint: {
              'line-color': PREF_BORDER_COLOR,
              'line-width': PREF_BORDER_WIDTH_EXPRESSION as maplibregl.PropertyValueSpecification<number>,
              'line-opacity': 0.85,
            },
          },
          {
            id: LAYER_HOVER_OUTLINE,
            type: 'line',
            source: SOURCE_ID,
            filter: NO_MATCH_FILTER,
            paint: { 'line-color': '#0b0b0b', 'line-width': 1.5 },
          },
          {
            id: LAYER_SELECTED_OUTLINE,
            type: 'line',
            source: SOURCE_ID,
            filter: NO_MATCH_FILTER,
            paint: { 'line-color': '#0b0b0b', 'line-width': 2.5 },
          },
          {
            id: LAYER_PREF_HOVER_OUTLINE,
            type: 'line',
            source: PREF_SOURCE_ID,
            filter: PREF_NO_MATCH_FILTER,
            paint: { 'line-color': '#0b0b0b', 'line-width': 1.5 },
          },
          {
            id: LAYER_PREF_SELECTED_OUTLINE,
            type: 'line',
            source: PREF_SOURCE_ID,
            filter: PREF_NO_MATCH_FILTER,
            paint: { 'line-color': '#0b0b0b', 'line-width': 2.5 },
          },
          // 選択区域の医療機関ポイント。区域レイヤ群より上に置く。塗りは
          // 病床の過不足率・需要比の配色(発散7色+連続配色の淡青〜濃青)の
          // どれとも極端に明度が近くなりにくい白 + 濃い縁取り(#0b0b0b、既存の
          // hover/selected-outlineと同じ色)にして、下敷きの色が何であっても
          // 縁で視認できるようにする(罠4と同じ理屈: 塗りの色一色では
          // 全パターンを避けられないので、輪郭で担保する)。
          {
            id: LAYER_FACILITY_POINTS,
            type: 'circle',
            source: FACILITIES_SOURCE_ID,
            paint: {
              'circle-radius': FACILITY_RADIUS_EXPRESSION as maplibregl.PropertyValueSpecification<number>,
              'circle-color': '#ffffff',
              'circle-opacity': 0.9,
              'circle-stroke-color': '#0b0b0b',
              'circle-stroke-width': 1.5,
            },
          },
        ],
      };

      map = new maplibregl.Map({
        container: containerRef.current,
        style,
        bounds: INITIAL_BOUNDS,
        fitBoundsOptions: INITIAL_FIT_OPTIONS,
        maxBounds: MAX_BOUNDS,
        minZoom: 3,
        maxZoom: 10,
        dragRotate: false,
        attributionControl: false,
      });
    } catch (err) {
      setInitError(`地図の初期化に失敗しました: ${err instanceof Error ? err.message : String(err)}`);
      setLoading(false);
      return undefined;
    }

    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

    // 破棄済み(この effect のクリーンアップが既に走った)インスタンスからの
    // 遅延イベントを無視する。React 18 StrictMode の開発時二重実行
    // (生成→破棄→生成)で、破棄された旧インスタンスの GeoJSON リクエストが
    // 中断されて 'error' が非同期に飛んでくることがあり、無視しないと
    // 正常に動いている新しい地図の上に古いエラー状態が残ってしまう。
    const isCurrent = () => mapRef.current === map;

    map.on('error', (e) => {
      if (!isCurrent()) return;
      const message = e && e.error ? e.error.message : '不明なエラー';
      setRuntimeError(`地図の読み込み中にエラーが発生しました: ${message}`);
      // maplibre-gl's runtime ErrorEvent carries `sourceId` when the error
      // originated from a specific source, but the bundled .d.ts aliases
      // this event to the global DOM ErrorEvent type (which has no such
      // field) — see node_modules/maplibre-gl/dist/maplibre-gl.d.ts
      // `error: ErrorEvent`. Cast narrowly just to read it.
      const sourceId = (e as unknown as { sourceId?: string }).sourceId;
      // ソース読み込み自体が失敗した(または原因不明の汎用エラー)場合は、
      // 読み込み中インジケータを永久に出したままにしない。
      if (!sourceId || sourceId === SOURCE_ID) {
        setLoading(false);
      }
    });

    map.on('load', () => {
      if (!isCurrent()) return;
      setReady(true);
    });

    map.on('sourcedata', (e) => {
      if (!isCurrent()) return;
      if (e.sourceId === SOURCE_ID && map.isSourceLoaded(SOURCE_ID)) {
        setLoading(false);
        // ソースの読み込みが(再試行等で)成功したので、以前の一時的なエラー
        // 通知が残っていれば解除する。
        setRuntimeError(null);
      }
    });

    // 施設ポイントは区域ポリゴンの真上に描かれるため、同じ座標で区域レイヤと
    // 施設レイヤの両方がヒットしうる。区域用・施設用にper-layerのmousemove/
    // mouseleaveをそれぞれ独立登録すると、どちらが最後にsetHover()するかが
    // レイヤ登録順に依存してしまい、施設ツールチップと区域ツールチップが
    // 同時に(あるいは交互に)出うる。単一のmousemoveハンドラで
    // queryRenderedFeaturesを施設→区域の優先順に呼び、常にどちらか一方だけを
    // 選ぶ(クリックハンドラが既にqueryRenderedFeaturesで区域を解決している
    // のと同じ書き方)。
    map.on('mousemove', (e) => {
      const facilityFeature = map.queryRenderedFeatures(e.point, { layers: [LAYER_FACILITY_POINTS] })[0];
      if (facilityFeature) {
        map.getCanvas().style.cursor = 'pointer';
        map.setFilter(LAYER_HOVER_OUTLINE, NO_MATCH_FILTER);
        map.setFilter(LAYER_PREF_HOVER_OUTLINE, PREF_NO_MATCH_FILTER);
        setHover({
          kind: 'facility',
          props: facilityFeature.properties as unknown as FacilityPointProperties,
          x: e.point.x,
          y: e.point.y,
        });
        return;
      }

      // 塗りは level に応じてどちらか一方しか表示していないので、今の level の
      // 塗りレイヤだけを引く(非表示レイヤは queryRenderedFeatures に出てこないが、
      // 明示的に分岐して「どちらを指しているか」をコード上でも一意にする)。
      if (levelRef.current === 'pref') {
        const prefFeature = map.queryRenderedFeatures(e.point, { layers: [LAYER_PREF_FILL] })[0];
        if (prefFeature) {
          map.getCanvas().style.cursor = 'pointer';
          const code = prefFeature.properties?.pref_code as string | undefined;
          map.setFilter(
            LAYER_PREF_HOVER_OUTLINE,
            code ? ['==', ['get', 'pref_code'], code] : PREF_NO_MATCH_FILTER
          );
          setHover({
            kind: 'pref',
            props: prefFeature.properties as unknown as PrefectureMapFeatureProperties,
            x: e.point.x,
            y: e.point.y,
          });
          return;
        }
      } else {
        const areaFeature = map.queryRenderedFeatures(e.point, { layers: [LAYER_FILL] })[0];
        if (areaFeature) {
          map.getCanvas().style.cursor = 'pointer';
          const code = areaFeature.properties?.area_code as string | undefined;
          map.setFilter(LAYER_HOVER_OUTLINE, code ? ['==', ['get', 'area_code'], code] : NO_MATCH_FILTER);
          setHover({
            kind: 'area',
            props: areaFeature.properties as unknown as AreaMapFeatureProperties,
            x: e.point.x,
            y: e.point.y,
          });
          return;
        }
      }

      map.getCanvas().style.cursor = '';
      map.setFilter(LAYER_HOVER_OUTLINE, NO_MATCH_FILTER);
      map.setFilter(LAYER_PREF_HOVER_OUTLINE, PREF_NO_MATCH_FILTER);
      setHover(null);
    });

    // 上のmousemoveはcanvas内でのみ発火するため、カーソルがcanvasごと地図の
    // 外へ一気に抜けた場合の保険(mousemoveが1回も追加発火しないまま
    // ツールチップが表示されっぱなしになるのを防ぐ)。
    map.on('mouseout', () => {
      map.getCanvas().style.cursor = '';
      map.setFilter(LAYER_HOVER_OUTLINE, NO_MATCH_FILTER);
      map.setFilter(LAYER_PREF_HOVER_OUTLINE, PREF_NO_MATCH_FILTER);
      setHover(null);
    });

    map.on('click', (e) => {
      if (levelRef.current === 'pref') {
        const feature = map.queryRenderedFeatures(e.point, { layers: [LAYER_PREF_FILL] })[0];
        const code = feature ? ((feature.properties?.pref_code as string | undefined) ?? null) : null;
        onSelectPrefectureRef.current(code);
        return;
      }
      const feats = map.queryRenderedFeatures(e.point, { layers: [LAYER_FILL] });
      const feature = feats[0];
      const code = feature ? ((feature.properties?.area_code as string | undefined) ?? null) : null;
      onSelectAreaRef.current(code);
    });

    return () => {
      // Null out the ref *before* calling remove() so that any error/sourcedata
      // events fired synchronously as part of teardown are already recognized
      // as stale by isCurrent() above.
      mapRef.current = null;
      map.remove();
      setReady(false);
    };
    // Map is created once; mapDataUrl/prefMapDataUrl are stable for the app's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapDataUrl, prefMapDataUrl]);

  // Fill color / unavailable-outline visibility depend on the selected bed
  // function & metric, and which of the two layer sets is on depends on level.
  // Applied imperatively so we don't tear down the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    const isPref = level === 'pref';
    const fillLayer = isPref ? LAYER_PREF_FILL : LAYER_FILL;
    const unavailableLayer = isPref ? LAYER_PREF_UNAVAILABLE_OUTLINE : LAYER_UNAVAILABLE_OUTLINE;

    // 表示中の層の塗りだけを更新する(隠れている層の塗り式は次に表示へ切り替わる
    // ときにこのeffectが走って更新される。分位境界は層ごとに別物なので、
    // 隠れている層へ今の quantileEdges を適用してはいけない)。
    map.setPaintProperty(
      fillLayer,
      'fill-color',
      buildFillColorExpression(metric, bedFunction, quantileEdges, demandYear)
    );
    map.setFilter(unavailableLayer, ['!', ['has', `r_${bedFunction}`]]);

    // 排他表示。level==='area' のときだけ県境(LAYER_PREF_BORDER)を区域の塗りの
    // 上に重ねる。level==='pref' では県境は塗りの白縁(LAYER_PREF_OUTLINE)が
    // 担うので重ねない。
    const areaVisibility = isPref ? 'none' : 'visible';
    const prefVisibility = isPref ? 'visible' : 'none';
    for (const layerId of [LAYER_COAST_CASING, LAYER_FILL, LAYER_OUTLINE]) {
      map.setLayoutProperty(layerId, 'visibility', areaVisibility);
    }
    for (const layerId of [LAYER_PREF_COAST_CASING, LAYER_PREF_FILL, LAYER_PREF_OUTLINE]) {
      map.setLayoutProperty(layerId, 'visibility', prefVisibility);
    }
    map.setLayoutProperty(LAYER_PREF_BORDER, 'visibility', isPref ? 'none' : 'visible');

    // 「算出不可」の破線レイヤは 'ratio' 選択時のみ意味を持つ（need=0で比が算出不可の
    // 区域を示す）。実績/必要数の実数指標でも、需要指標（基準年が全区域で0でないこと
    // をPython側で検証済み — 算出不可の区域はそもそも存在しない）でも非表示にする。
    // 表示していない層の破線は常に非表示にする。
    const showUnavailable = metric === 'ratio';
    map.setLayoutProperty(
      LAYER_UNAVAILABLE_OUTLINE,
      'visibility',
      showUnavailable && !isPref ? 'visible' : 'none'
    );
    map.setLayoutProperty(
      LAYER_PREF_UNAVAILABLE_OUTLINE,
      'visibility',
      showUnavailable && isPref ? 'visible' : 'none'
    );
  }, [bedFunction, metric, quantileEdges, demandYear, level, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setFilter(
      LAYER_SELECTED_OUTLINE,
      selectedAreaCode ? ['==', ['get', 'area_code'], selectedAreaCode] : NO_MATCH_FILTER
    );
  }, [selectedAreaCode, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setFilter(
      LAYER_PREF_SELECTED_OUTLINE,
      selectedPrefCode ? ['==', ['get', 'pref_code'], selectedPrefCode] : PREF_NO_MATCH_FILTER
    );
  }, [selectedPrefCode, ready]);

  // 表示単位を切り替えた瞬間に、直前の層に対するホバー状態(ツールチップと
  // ホバー輪郭)を消す。切替はボタン操作なのでカーソルは地図の外にあり、
  // mousemove が追加で発火しないまま「区域のツールチップだけが都道府県表示の
  // 上に残る」ことがある。
  useEffect(() => {
    const map = mapRef.current;
    setHover(null);
    if (!map || !ready) return;
    map.setFilter(LAYER_HOVER_OUTLINE, NO_MATCH_FILTER);
    map.setFilter(LAYER_PREF_HOVER_OUTLINE, PREF_NO_MATCH_FILTER);
  }, [level, ready]);

  // 選択区域の医療機関ポイント。ソース自体はスタイル定義時に空の
  // FeatureCollectionで一度だけ追加済みなので、ここではsetData()で中身だけ
  // 差し替える(App側がselectedAreaCode===nullや区域切替の度に空/新しい
  // FeatureCollectionを渡してくるので、前区域の点が残る心配はない)。
  // !ready の間は反映しない(=破棄済みインスタンスへsetDataしない。他の
  // imperativeな効果と同じ作法)。
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const source = map.getSource(FACILITIES_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;
    source?.setData(facilityPoints);
  }, [facilityPoints, ready]);

  useImperativeHandle(
    ref,
    () => ({
      resetView: () => {
        mapRef.current?.fitBounds(INITIAL_BOUNDS, INITIAL_FIT_OPTIONS);
      },
      selectArea: (bbox: [number, number, number, number]) => {
        const map = mapRef.current;
        if (!map) return;
        const [w, s, e, n] = bbox;
        map.fitBounds(
          [
            [w, s],
            [e, n],
          ],
          { padding: 48, animate: true }
        );
      },
    }),
    []
  );

  return (
    <div className="map-container-wrap">
      <div
        ref={containerRef}
        className="map-container"
        role="application"
        aria-label={level === 'pref' ? '都道府県の病床マップ' : '構想区域の病床マップ'}
      />
      {initError && <div className="map-overlay map-overlay-error">{initError}</div>}
      {!initError && loading && <div className="map-overlay">地図データを読み込み中…</div>}
      {!initError && runtimeError && (
        <div className="map-notice" role="alert">
          {runtimeError}
        </div>
      )}
      {hover && !initError && hover.kind === 'facility' && (
        <div className="tooltip" style={{ left: hover.x, top: hover.y }}>
          <div className="tooltip-title">{hover.props.facility_name}</div>
          <div>{formatFacilityTooltipBody(hover.props)}</div>
        </div>
      )}
      {hover && !initError && hover.kind === 'pref' && (
        <div className="tooltip" style={{ left: hover.x, top: hover.y }}>
          <div className="tooltip-title">{hover.props.pref_name}</div>
          <div>
            {formatHoverTooltip(
              hover.props as unknown as Record<string, unknown>,
              metric,
              bedFunction,
              functionLabel,
              demandYear,
              demandYearLabel,
              demandCategoryLabels
            )}
          </div>
        </div>
      )}
      {hover && !initError && hover.kind === 'area' && (
        <div className="tooltip" style={{ left: hover.x, top: hover.y }}>
          <div className="tooltip-title">
            {hover.props.pref_name} {hover.props.area_name}
          </div>
          <div>
            {formatHoverTooltip(
              hover.props as unknown as Record<string, unknown>,
              metric,
              bedFunction,
              functionLabel,
              demandYear,
              demandYearLabel,
              demandCategoryLabels
            )}
          </div>
        </div>
      )}
    </div>
  );
});

export default MapView;
