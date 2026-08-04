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
 * @returns {{
 *   type: 'FeatureCollection',
 *   features: Array<{type: 'Feature', properties: Record<string, string | number>, geometry: unknown}>
 * }}
 */
export function buildAreaMap(boundaries, indicators, demand) {
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

  const indicatorByCode = new Map(indicators.areas.map((a) => [a.area_code, a]));
  const demandByCode = new Map(demand.areas.map((a) => [a.area_code, a]));

  const features = boundaries.features.map((feature) => {
    const area = indicatorByCode.get(feature.properties.area_code);
    const demandArea = demandByCode.get(feature.properties.area_code);

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
