import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';

import type { AreaMapFeatureProperties, BedFunctionKey, MetricKind } from '../types';
import {
  RATIO_BIN_COLORS,
  RATIO_BIN_EDGES,
  RATIO_UNAVAILABLE_COLOR,
  RATIO_UNAVAILABLE_OUTLINE_COLOR,
  computeSequentialClasses,
  formatMetricValue,
  readMetricValue,
} from '../lib/metrics';

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

const NO_MATCH_FILTER: maplibregl.FilterSpecification = ['==', ['get', 'area_code'], ''];

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
  bedFunction: BedFunctionKey;
  metric: MetricKind;
  functionLabel: string;
  /** computeQuantileEdges() の8値。metric が 'ratio' のときは未使用。 */
  quantileEdges: number[];
  selectedAreaCode: string | null;
  /** 地図クリックで選ばれた区域の area_code（クリックが外れたら null）。 */
  onSelectArea: (areaCode: string | null) => void;
}

function buildFillColorExpression(
  metric: MetricKind,
  bedFunction: BedFunctionKey,
  quantileEdges: number[]
): unknown {
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

const MapView = forwardRef<MapViewHandle, MapViewProps>(function MapView(
  { mapDataUrl, bedFunction, metric, functionLabel, quantileEdges, selectedAreaCode, onSelectArea },
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
  const [hover, setHover] = useState<{ props: AreaMapFeatureProperties; x: number; y: number } | null>(null);

  // Event handlers below are registered once (map is created once) but need
  // the latest callback/prop values — route them through refs to avoid
  // stale closures without re-creating the map on every prop change.
  const onSelectAreaRef = useRef(onSelectArea);
  onSelectAreaRef.current = onSelectArea;

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

    map.on('mousemove', LAYER_FILL, (e) => {
      const feature = e.features && e.features[0];
      if (!feature) return;
      map.getCanvas().style.cursor = 'pointer';
      const code = feature.properties?.area_code as string | undefined;
      map.setFilter(LAYER_HOVER_OUTLINE, code ? ['==', ['get', 'area_code'], code] : NO_MATCH_FILTER);
      setHover({
        props: feature.properties as unknown as AreaMapFeatureProperties,
        x: e.point.x,
        y: e.point.y,
      });
    });

    map.on('mouseleave', LAYER_FILL, () => {
      map.getCanvas().style.cursor = '';
      map.setFilter(LAYER_HOVER_OUTLINE, NO_MATCH_FILTER);
      setHover(null);
    });

    map.on('click', (e) => {
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
    // Map is created once; mapDataUrl is stable for the app's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapDataUrl]);

  // Fill color / unavailable-outline visibility depend on the selected bed
  // function & metric. Applied imperatively so we don't tear down the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    map.setPaintProperty(LAYER_FILL, 'fill-color', buildFillColorExpression(metric, bedFunction, quantileEdges));
    map.setFilter(LAYER_UNAVAILABLE_OUTLINE, ['!', ['has', `r_${bedFunction}`]]);
    map.setLayoutProperty(LAYER_UNAVAILABLE_OUTLINE, 'visibility', metric === 'ratio' ? 'visible' : 'none');
  }, [bedFunction, metric, quantileEdges, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setFilter(
      LAYER_SELECTED_OUTLINE,
      selectedAreaCode ? ['==', ['get', 'area_code'], selectedAreaCode] : NO_MATCH_FILTER
    );
  }, [selectedAreaCode, ready]);

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
      <div ref={containerRef} className="map-container" role="application" aria-label="構想区域の病床マップ" />
      {initError && <div className="map-overlay map-overlay-error">{initError}</div>}
      {!initError && loading && <div className="map-overlay">地図データを読み込み中…</div>}
      {!initError && runtimeError && (
        <div className="map-notice" role="alert">
          {runtimeError}
        </div>
      )}
      {hover && !initError && (
        <div className="tooltip" style={{ left: hover.x, top: hover.y }}>
          <div className="tooltip-title">
            {hover.props.pref_name} {hover.props.area_name}
          </div>
          <div>
            {functionLabel}:{' '}
            {formatMetricValue(
              metric,
              readMetricValue(hover.props as unknown as Record<string, unknown>, metric, bedFunction)
            )}
          </div>
        </div>
      )}
    </div>
  );
});

export default MapView;
