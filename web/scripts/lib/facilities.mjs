// Pure functions for splitting data/processed/area_facilities_R7.json (the
// single source of truth for medical facility data, produced by
// tools/build_web_facilities.py) into the artifacts web/scripts/sync-data.mjs
// writes for the frontend to fetch/bundle:
//
//   - one per-area "shard" (web/public/facilities/<area_code>.json), fetched
//     lazily by the frontend when an area is selected
//   - one lightweight bundled summary (web/src/generated/facility_summary.json)
//     that does NOT include the facilities array itself
//
// Kept dependency-free and side-effect-free so it can be unit-tested with
// vitest (web/src/lib/facilities.test.ts) and reused from
// web/scripts/sync-data.mjs.

/**
 * Build the per-area shard object written to
 * web/public/facilities/<area_code>.json. Fields are passed through verbatim
 * from the source-of-truth area object — this is a reshape (pick fields),
 * not a value transformation, and must never slice/reformat strings.
 *
 * @param {{
 *   area_code: string,
 *   area_name: string,
 *   pref_code: string,
 *   pref_name: string,
 *   facility_count: number,
 *   geocoded_count: number,
 *   reference_geocoded_count: number,
 *   coordinate_withdrawn_count: number,
 *   facilities: Array<Record<string, unknown>>,
 * }} area one entry of area_facilities_R7.json's `areas` array
 * @returns {{
 *   area_code: string,
 *   area_name: string,
 *   pref_code: string,
 *   pref_name: string,
 *   facility_count: number,
 *   geocoded_count: number,
 *   reference_geocoded_count: number,
 *   coordinate_withdrawn_count: number,
 *   facilities: Array<Record<string, unknown>>,
 * }}
 */
export function buildAreaShard(area) {
  return {
    area_code: area.area_code,
    area_name: area.area_name,
    pref_code: area.pref_code,
    pref_name: area.pref_name,
    facility_count: area.facility_count,
    geocoded_count: area.geocoded_count,
    reference_geocoded_count: area.reference_geocoded_count,
    coordinate_withdrawn_count: area.coordinate_withdrawn_count,
    facilities: area.facilities,
  };
}

/**
 * Build the lightweight bundled summary (facility_summary.json). Deliberately
 * excludes the `facilities` array of each area — including it here would
 * defeat the point of sharding the data per area. Callers (the frontend) use
 * this to show per-area facility/geocoded counts before fetching a shard.
 *
 * @param {{
 *   metadata: Record<string, unknown>,
 *   metrics: Array<Record<string, unknown>>,
 *   value_status_labels: Record<string, string>,
 *   areas: Array<Record<string, unknown>>,
 * }} facilitiesData the full parsed area_facilities_R7.json (each area also
 *   carries a `facilities` array, deliberately typed loosely here since this
 *   function never reads it — see the return type below for what's kept)
 * @returns {{
 *   metadata: Record<string, unknown>,
 *   metrics: Array<Record<string, unknown>>,
 *   value_status_labels: Record<string, string>,
 *   areas: Array<{area_code: string, facility_count: number, geocoded_count: number,
 *     reference_geocoded_count: number, coordinate_withdrawn_count: number}>,
 * }}
 */
export function buildFacilitySummary(facilitiesData) {
  return {
    metadata: facilitiesData.metadata,
    metrics: facilitiesData.metrics,
    value_status_labels: facilitiesData.value_status_labels,
    areas: facilitiesData.areas.map((area) => ({
      area_code: area.area_code,
      facility_count: area.facility_count,
      geocoded_count: area.geocoded_count,
      reference_geocoded_count: area.reference_geocoded_count,
      coordinate_withdrawn_count: area.coordinate_withdrawn_count,
    })),
  };
}

/**
 * File name for an area's facility shard. Throws if `areaCode` is not
 * exactly 4 digits, so a malformed code can never smuggle unexpected
 * characters (e.g. path separators) into the generated output path.
 *
 * @param {string} areaCode
 * @returns {string}
 */
export function shardFileName(areaCode) {
  if (typeof areaCode !== 'string' || !/^\d{4}$/.test(areaCode)) {
    throw new Error(`shardFileName: area_code must be exactly 4 digits, got ${JSON.stringify(areaCode)}`);
  }
  return `${areaCode}.json`;
}
