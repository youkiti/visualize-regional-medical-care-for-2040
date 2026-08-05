// Pure functions for merging area_boundaries_R7.geojson with area_indicators_R7.json
// into the flat-properties FeatureCollection used by the map (area_map.json).
//
// Kept dependency-free and side-effect-free so it can be unit-tested with vitest
// (web/src/lib/merge.test.ts) and reused from web/scripts/sync-data.mjs.

export const BED_FUNCTIONS = ['total', 'high_acute', 'acute', 'recovery', 'chronic'];

/**
 * Flat property key for a single (category, year) demand value.
 * Kept as a function (rather than hardcoded strings) so web/src/lib/metrics.ts
 * can build/read the exact same key — a vitest in metrics.test.ts checks the
 * two implementations agree (see M4 brief: key rules must not drift between
 * the two files).
 * @param {string} category
 * @param {number} year
 * @returns {string}
 */
export function demandValueKey(category, year) {
  return `${category}_${year}`;
}

/**
 * Flat property key for a single (category, year) demand change ratio
 * (value(year) / value(baseline_year)). See demandValueKey.
 * @param {string} category
 * @param {number} year
 * @returns {string}
 */
export function demandRatioKey(category, year) {
  return `${category}_r_${year}`;
}

// ---- YoY (R6→R7 公表年度間比較) flat property keys -------------------------
//
// Kept as functions (not hardcoded strings) so web/src/lib/metrics.ts can
// build/read the exact same keys — merge.test.ts checks the two
// implementations agree (see M9 brief, same drift trap as
// demandValueKey/demandRatioKey above — CLAUDE.md 罠10).

/** 実績2025(R7) ÷ 見込量2025(R6) の比。 @param {string} fn @returns {string} */
export function yoyPlanRatioKey(fn) {
  return `y_pa_${fn}`;
}

/** 実績2025(R7) ÷ 実績2024(R6) の比。 @param {string} fn @returns {string} */
export function yoyChangeRatioKey(fn) {
  return `y_yy_${fn}`;
}

/** 見込量2025(R6)の生値。 @param {string} fn @returns {string} */
export function yoyPlanValueKey(fn) {
  return `y_plan_${fn}`;
}

/** 実績2024(R6)の生値。 @param {string} fn @returns {string} */
export function yoyActual2024Key(fn) {
  return `y_a24_${fn}`;
}

/**
 * Compute the [west, south, east, north] bounding box of a Polygon or
 * MultiPolygon geometry.
 * @param {{type: string, coordinates: unknown}} geometry
 * @returns {[number, number, number, number]}
 */
export function computeBBox(geometry) {
  let w = Infinity;
  let s = Infinity;
  let e = -Infinity;
  let n = -Infinity;

  const visitRing = (ring) => {
    for (const [x, y] of ring) {
      if (x < w) w = x;
      if (x > e) e = x;
      if (y < s) s = y;
      if (y > n) n = y;
    }
  };

  if (geometry.type === 'Polygon') {
    for (const ring of geometry.coordinates) visitRing(ring);
  } else if (geometry.type === 'MultiPolygon') {
    for (const polygon of geometry.coordinates) {
      for (const ring of polygon) visitRing(ring);
    }
  } else {
    throw new Error(`computeBBox: unsupported geometry type "${geometry.type}"`);
  }

  return [w, s, e, n];
}

/**
 * Merge the 339-feature area boundary FeatureCollection with the
 * area_indicators_R7.json areas and area_demand_R7.json areas into a
 * flat-properties FeatureCollection ready for MapLibre.
 *
 * @param {{features: Array<{properties: Record<string, unknown>, geometry: unknown}>}} boundaries
 * @param {{areas: Array<Record<string, unknown>>}} indicators
 * @param {{categories: string[], years: number[], baseline_year: number, areas: Array<Record<string, unknown>>}} demand
 * @param {{functions: string[], areas: Array<Record<string, unknown>>}} yoy
 * @returns {{
 *   type: 'FeatureCollection',
 *   features: Array<{type: 'Feature', properties: Record<string, string | number>, geometry: unknown}>
 * }}
 */
export function buildAreaMap(boundaries, indicators, demand, yoy) {
  const boundaryCodes = boundaries.features.map((f) => f.properties.area_code);
  const boundaryCodeSet = new Set(boundaryCodes);
  const indicatorCodeSet = new Set(indicators.areas.map((a) => a.area_code));

  const missingInIndicators = [...boundaryCodeSet].filter((c) => !indicatorCodeSet.has(c));
  const missingInBoundaries = [...indicatorCodeSet].filter((c) => !boundaryCodeSet.has(c));
  if (missingInIndicators.length > 0 || missingInBoundaries.length > 0) {
    throw new Error(
      'buildAreaMap: area_code sets differ between boundaries and indicators. ' +
        `missing_in_indicators=${JSON.stringify(missingInIndicators)} ` +
        `missing_in_boundaries=${JSON.stringify(missingInBoundaries)}`
    );
  }

  const demandCodeSet = new Set(demand.areas.map((a) => a.area_code));
  const missingInDemand = [...boundaryCodeSet].filter((c) => !demandCodeSet.has(c));
  const missingInBoundariesFromDemand = [...demandCodeSet].filter((c) => !boundaryCodeSet.has(c));
  if (missingInDemand.length > 0 || missingInBoundariesFromDemand.length > 0) {
    throw new Error(
      'buildAreaMap: area_code sets differ between boundaries and demand. ' +
        `missing_in_demand=${JSON.stringify(missingInDemand)} ` +
        `missing_in_boundaries=${JSON.stringify(missingInBoundariesFromDemand)}`
    );
  }

  const yoyCodeSet = new Set(yoy.areas.map((a) => a.area_code));
  const missingInYoy = [...boundaryCodeSet].filter((c) => !yoyCodeSet.has(c));
  const missingInBoundariesFromYoy = [...yoyCodeSet].filter((c) => !boundaryCodeSet.has(c));
  if (missingInYoy.length > 0 || missingInBoundariesFromYoy.length > 0) {
    throw new Error(
      'buildAreaMap: area_code sets differ between boundaries and yoy. ' +
        `missing_in_yoy=${JSON.stringify(missingInYoy)} ` +
        `missing_in_boundaries=${JSON.stringify(missingInBoundariesFromYoy)}`
    );
  }

  const indicatorByCode = new Map(indicators.areas.map((a) => [a.area_code, a]));
  const demandByCode = new Map(demand.areas.map((a) => [a.area_code, a]));
  const yoyByCode = new Map(yoy.areas.map((a) => [a.area_code, a]));

  const features = boundaries.features.map((feature) => {
    const area = indicatorByCode.get(feature.properties.area_code);
    const demandArea = demandByCode.get(feature.properties.area_code);
    const yoyArea = yoyByCode.get(feature.properties.area_code);

    /** @type {Record<string, string | number>} */
    const props = {
      area_code: feature.properties.area_code,
      area_name: feature.properties.area_name,
      pref_code: feature.properties.pref_code,
      pref_name: feature.properties.pref_name,
      boundary_source: feature.properties.boundary_source,
    };

    for (const fn of BED_FUNCTIONS) {
      const beds = area.beds[fn];
      props[`a_${fn}`] = beds.actual_2025;
      props[`n_${fn}`] = beds.need_2025;
      // need_2025 === 0 => ratio is not computable (not 0, not Infinity):
      // omit the key entirely so MapLibre's ["has", "r_<fn>"] can detect it.
      if (beds.need_2025 !== 0) {
        props[`r_${fn}`] = beds.actual_2025 / beds.need_2025;
      }
    }

    // Demand forecast (在宅/外来): flat value + change-ratio-vs-baseline-year
    // properties per (category, year). The Python pipeline already verified
    // baseline_year values are non-zero for every area x category
    // (tools/build_web_demand.py 検証7), so no need=0-style branch is needed
    // here — only missing/non-numeric data is treated as a hard error.
    for (const category of demand.categories) {
      const categoryDemand = demandArea && demandArea.demand ? demandArea.demand[category] : undefined;
      if (!categoryDemand || typeof categoryDemand !== 'object') {
        throw new Error(
          `buildAreaMap: demand.${category} missing for area ${feature.properties.area_code}`
        );
      }
      const baseline = categoryDemand[String(demand.baseline_year)];
      if (typeof baseline !== 'number' || !Number.isFinite(baseline)) {
        throw new Error(
          `buildAreaMap: demand.${category}[${demand.baseline_year}] missing/non-numeric for area ${feature.properties.area_code}`
        );
      }
      for (const year of demand.years) {
        const value = categoryDemand[String(year)];
        if (typeof value !== 'number' || !Number.isFinite(value)) {
          throw new Error(
            `buildAreaMap: demand.${category}[${year}] missing/non-numeric for area ${feature.properties.area_code}`
          );
        }
        props[demandValueKey(category, year)] = value;
        props[demandRatioKey(category, year)] = value / baseline;
      }
    }

    // YoY (R6→R7 公表年度間比較): raw plan_2025(R6)/actual_2024(R6) values are
    // always emitted (never zero-denominator issues on their own), while the
    // two ratio properties are omitted when their denominator is 0 — same
    // "no key" convention as r_<fn> above (not 0, not Infinity; the reader
    // must treat a missing key as 算出不可, not as 0).
    for (const fn of yoy.functions) {
      const beds = yoyArea.beds[fn];
      props[yoyPlanValueKey(fn)] = beds.plan_2025;
      props[yoyActual2024Key(fn)] = beds.actual_2024;
      if (beds.plan_2025 !== 0) {
        props[yoyPlanRatioKey(fn)] = beds.actual_2025 / beds.plan_2025;
      }
      if (beds.actual_2024 !== 0) {
        props[yoyChangeRatioKey(fn)] = beds.actual_2025 / beds.actual_2024;
      }
    }

    const [w, s, e, n] = computeBBox(feature.geometry);
    props.bb_w = w;
    props.bb_s = s;
    props.bb_e = e;
    props.bb_n = n;

    return {
      type: 'Feature',
      properties: props,
      geometry: feature.geometry,
    };
  });

  return {
    type: 'FeatureCollection',
    features,
  };
}

/**
 * Merge the 47-feature prefecture boundary FeatureCollection with
 * prefecture_indicators_R7.json into a flat-properties FeatureCollection ready
 * for MapLibre (pref_map.json) — the overview layer's counterpart to
 * buildAreaMap above.
 *
 * Deliberately a separate function rather than a generalization of
 * buildAreaMap: the prefecture dataset carries beds AND demand in one object
 * keyed by pref_code (build_web_prefecture.py), whereas the area side merges
 * two separately-keyed datasets. The flat property names are the same on both
 * (a_/n_/r_<fn>, demandValueKey/demandRatioKey), so web/src/lib/metrics.ts can
 * read either layer's features with the same helpers.
 *
 * @param {{features: Array<{properties: Record<string, unknown>, geometry: unknown}>}} boundaries
 * @param {{categories: string[], years: number[], baseline_year: number, prefectures: Array<Record<string, unknown>>}} indicators
 * @param {{functions: string[], prefectures: Array<Record<string, unknown>>}} yoy
 * @returns {{
 *   type: 'FeatureCollection',
 *   features: Array<{type: 'Feature', properties: Record<string, string | number>, geometry: unknown}>
 * }}
 */
export function buildPrefectureMap(boundaries, indicators, yoy) {
  const boundaryCodes = boundaries.features.map((f) => f.properties.pref_code);
  const boundaryCodeSet = new Set(boundaryCodes);
  const indicatorCodeSet = new Set(indicators.prefectures.map((p) => p.pref_code));

  // 年度間比較(prefecture_yoy_R6_R7.json)も同じ47都道府県を持つ。全国は
  // national キーにあり prefectures 配列には無いので、集合は指標側と一致する。
  const yoyCodeSet = new Set(yoy.prefectures.map((p) => p.pref_code));
  const missingInYoy = [...boundaryCodeSet].filter((c) => !yoyCodeSet.has(c));
  const missingInBoundariesFromYoy = [...yoyCodeSet].filter((c) => !boundaryCodeSet.has(c));
  if (missingInYoy.length > 0 || missingInBoundariesFromYoy.length > 0) {
    throw new Error(
      'buildPrefectureMap: pref_code sets differ between boundaries and yoy. ' +
        `missing_in_yoy=${JSON.stringify(missingInYoy)} ` +
        `missing_in_boundaries=${JSON.stringify(missingInBoundariesFromYoy)}`
    );
  }
  const yoyByCode = new Map(yoy.prefectures.map((p) => [p.pref_code, p]));

  const missingInIndicators = [...boundaryCodeSet].filter((c) => !indicatorCodeSet.has(c));
  const missingInBoundaries = [...indicatorCodeSet].filter((c) => !boundaryCodeSet.has(c));
  if (missingInIndicators.length > 0 || missingInBoundaries.length > 0) {
    throw new Error(
      'buildPrefectureMap: pref_code sets differ between boundaries and indicators. ' +
        `missing_in_indicators=${JSON.stringify(missingInIndicators)} ` +
        `missing_in_boundaries=${JSON.stringify(missingInBoundaries)}`
    );
  }

  const indicatorByCode = new Map(indicators.prefectures.map((p) => [p.pref_code, p]));

  const features = boundaries.features.map((feature) => {
    const pref = indicatorByCode.get(feature.properties.pref_code);
    const yoyPref = yoyByCode.get(feature.properties.pref_code);

    /** @type {Record<string, string | number>} */
    const props = {
      pref_code: feature.properties.pref_code,
      pref_name: feature.properties.pref_name,
      boundary_source: feature.properties.boundary_source,
    };

    for (const fn of BED_FUNCTIONS) {
      const beds = pref.beds[fn];
      if (!beds || typeof beds.actual_2025 !== 'number' || typeof beds.need_2025 !== 'number') {
        throw new Error(`buildPrefectureMap: beds.${fn} missing/non-numeric for prefecture ${pref.pref_code}`);
      }
      props[`a_${fn}`] = beds.actual_2025;
      props[`n_${fn}`] = beds.need_2025;
      // Same omit-when-need-is-zero rule as buildAreaMap: no prefecture
      // actually has need_2025 === 0 (tools/build_web_prefecture.py 検証13
      // logs the count, observed 0), but the map/legend code path for
      // "算出不可" is shared with the area layer, so don't diverge here.
      if (beds.need_2025 !== 0) {
        props[`r_${fn}`] = beds.actual_2025 / beds.need_2025;
      }
    }

    for (const category of indicators.categories) {
      const categoryDemand = pref.demand ? pref.demand[category] : undefined;
      if (!categoryDemand || typeof categoryDemand !== 'object') {
        throw new Error(`buildPrefectureMap: demand.${category} missing for prefecture ${pref.pref_code}`);
      }
      const baseline = categoryDemand[String(indicators.baseline_year)];
      if (typeof baseline !== 'number' || !Number.isFinite(baseline)) {
        throw new Error(
          `buildPrefectureMap: demand.${category}[${indicators.baseline_year}] missing/non-numeric for prefecture ${pref.pref_code}`
        );
      }
      for (const year of indicators.years) {
        const value = categoryDemand[String(year)];
        if (typeof value !== 'number' || !Number.isFinite(value)) {
          throw new Error(
            `buildPrefectureMap: demand.${category}[${year}] missing/non-numeric for prefecture ${pref.pref_code}`
          );
        }
        props[demandValueKey(category, year)] = value;
        props[demandRatioKey(category, year)] = value / baseline;
      }
    }

    // YoY (R6→R7 公表年度間比較)。プロパティ名は区域層と同一なので、地図・凡例・
    // ツールチップ(MapView/Legend/metrics.ts)は層を意識せずそのまま読める。
    // 分母0のときキー自体を省く規約も buildAreaMap と揃える(実データでは都道府県層に
    // 分母0は無いが、規約を分岐させない ―― r_<fn> と同じ理由)。
    for (const fn of yoy.functions) {
      const beds = yoyPref.beds[fn];
      if (
        !beds ||
        typeof beds.plan_2025 !== 'number' ||
        typeof beds.actual_2025 !== 'number' ||
        typeof beds.actual_2024 !== 'number'
      ) {
        throw new Error(`buildPrefectureMap: yoy beds.${fn} missing/non-numeric for prefecture ${pref.pref_code}`);
      }
      // ツールチップは分子(実績2025)を a_<fn>(指標データセット由来)から読み、
      // 分母を y_plan_/y_a24_(年度間比較データセット由来)から読む。2つのデータセットは
      // 同じ prefecture_beds.csv のR7実績2025から作られるので必ず一致するはずで、
      // 一致しないなら片方の生成が古い。黙って別々の数字を並べるより落とす。
      if (pref.beds[fn].actual_2025 !== beds.actual_2025) {
        throw new Error(
          `buildPrefectureMap: actual_2025 differs between indicators and yoy for prefecture ` +
            `${pref.pref_code} ${fn}: indicators=${pref.beds[fn].actual_2025} yoy=${beds.actual_2025}`
        );
      }
      props[yoyPlanValueKey(fn)] = beds.plan_2025;
      props[yoyActual2024Key(fn)] = beds.actual_2024;
      if (beds.plan_2025 !== 0) {
        props[yoyPlanRatioKey(fn)] = beds.actual_2025 / beds.plan_2025;
      }
      if (beds.actual_2024 !== 0) {
        props[yoyChangeRatioKey(fn)] = beds.actual_2025 / beds.actual_2024;
      }
    }

    const [w, s, e, n] = computeBBox(feature.geometry);
    props.bb_w = w;
    props.bb_s = s;
    props.bb_e = e;
    props.bb_n = n;

    return {
      type: 'Feature',
      properties: props,
      geometry: feature.geometry,
    };
  });

  return {
    type: 'FeatureCollection',
    features,
  };
}

/**
 * Build the lightweight per-area index (area_index.json) used by App to
 * resolve a bbox/boundary_source for a given area_code without depending on
 * the map's current load/viewport state (see web/src/App.tsx selectArea
 * flow). One entry per boundary feature, in the same order as `boundaries`.
 *
 * @param {{features: Array<{properties: Record<string, unknown>, geometry: unknown}>}} boundaries
 * @returns {Array<{area_code: string, boundary_source: string, bb_w: number, bb_s: number, bb_e: number, bb_n: number}>}
 */
export function buildAreaIndex(boundaries) {
  return boundaries.features.map((feature) => {
    const [w, s, e, n] = computeBBox(feature.geometry);
    return {
      area_code: feature.properties.area_code,
      boundary_source: feature.properties.boundary_source,
      bb_w: w,
      bb_s: s,
      bb_e: e,
      bb_n: n,
    };
  });
}
