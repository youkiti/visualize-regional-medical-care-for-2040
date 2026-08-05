// Reads data/processed/area_indicators_R7.json,
// data/processed/area_demand_R7.json,
// data/processed/area_boundaries_R7.geojson,
// data/processed/area_facilities_R7.json (the single source of truth,
// owned by the Python pipeline — see CLAUDE.md) and the 15 tidy CSVs +
// .meta.json files under data/processed/, and writes the generated
// artifacts the frontend bundles/fetches:
//
//   web/src/generated/area_indicators.json    — verbatim copy
//   web/src/generated/area_demand.json        — verbatim copy
//   web/src/generated/area_map.json           — boundaries + flat indicator/demand props
//   web/src/generated/area_index.json         — lightweight per-area bbox/boundary_source
//                                                lookup, used by App to resolve area
//                                                selection independent of the map's
//                                                load/viewport state (see App.tsx)
//   web/src/generated/prefecture_indicators.json — verbatim copy (overview layer)
//   web/src/generated/pref_map.json           — 47 prefecture boundaries + the same flat
//                                                indicator/demand props as area_map.json
//   web/src/generated/facility_summary.json   — bundled, lightweight (no facilities[])
//                                                summary of area_facilities_R7.json
//   web/public/facilities/<area_code>.json    — per-area facility shard (339 files),
//                                                fetched lazily by the frontend when an
//                                                area is selected (not bundled — see the
//                                                design note above the facility-shard
//                                                section below)
//   web/public/flow/area_flow.json            — verbatim copy of area_flow_R7.json
//                                                (patient inflow/outflow rates by area ×
//                                                phase). Fetched once when an area is
//                                                first selected; not bundled, and (unlike
//                                                the facility shards above) not split per
//                                                area either — see the design note above
//                                                the flow-data write step below for why
//   web/public/downloads/<bundle>.zip         — the 15 processed CSVs (+ their
//                                                .meta.json + README.md + MANIFEST.tsv)
//                                                packed as one bulk-download archive
//   web/public/downloads/area_boundaries_R7.geojson — verbatim copy, for standalone
//                                                map-tool use (not packed into the zip)
//   web/src/generated/download_manifest.json  — bundled, lightweight (size/sha256/
//                                                member list) so the UI can describe
//                                                the bulk download without fetching it
//
// Run via `npm run sync-data` (also wired into predev/prebuild). Exits
// non-zero on any consistency failure so a broken data pipeline fails the
// build instead of silently shipping a stale/partial site.

import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
import crypto from 'node:crypto';

import {
  buildAreaMap,
  buildAreaIndex,
  buildPrefectureMap,
  demandValueKey,
  demandRatioKey,
  BED_FUNCTIONS,
} from './lib/merge.mjs';
import { buildAreaShard, buildFacilitySummary, shardFileName } from './lib/facilities.mjs';
import { createZip, readZip } from './lib/zip.mjs';
import { BUNDLE_ROOT, BUNDLE_FILE_NAME, BUNDLE_CSV_FILES, buildManifestTsv, buildBundleReadme } from './lib/bundle.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const webDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(webDir, '..');

const indicatorsPath = path.join(repoRoot, 'data', 'processed', 'area_indicators_R7.json');
const demandPath = path.join(repoRoot, 'data', 'processed', 'area_demand_R7.json');
const boundariesPath = path.join(repoRoot, 'data', 'processed', 'area_boundaries_R7.geojson');
const facilitiesPath = path.join(repoRoot, 'data', 'processed', 'area_facilities_R7.json');
const flowPath = path.join(repoRoot, 'data', 'processed', 'area_flow_R7.json');
const prefIndicatorsPath = path.join(repoRoot, 'data', 'processed', 'prefecture_indicators_R7.json');
const prefBoundariesPath = path.join(repoRoot, 'data', 'processed', 'prefecture_boundaries_R7.geojson');
const processedDir = path.join(repoRoot, 'data', 'processed');
const generatedDir = path.join(webDir, 'src', 'generated');
const facilitiesOutDir = path.join(webDir, 'public', 'facilities');
const flowOutDir = path.join(webDir, 'public', 'flow');
const downloadsOutDir = path.join(webDir, 'public', 'downloads');

// リポジトリの正本URL。README.md記載のURLと揃える（.git無し）。
const REPO_URL = 'https://github.com/youkiti/visualize-regional-medical-care-for-2040';

const EXPECTED_FEATURE_COUNT = 339;
const EXPECTED_PREFECTURE_COUNT = 47;
const EXPECTED_FACILITY_TOTAL = 11760;
const EXPECTED_GEOCODED_TOTAL = 10244;
// 339区域 × directions(2) × phases(3)。area_flow_R7.json のグループ総数
// （tools/build_web_flow.py の検証13と同じ数）。
const EXPECTED_FLOW_GROUPS = 2034;

function fail(message) {
  console.error(`[sync-data] ERROR: ${message}`);
  process.exit(1);
}

function readJson(filePath, label) {
  if (!fs.existsSync(filePath)) {
    fail(`${label} not found: ${filePath}`);
  }
  const raw = fs.readFileSync(filePath, 'utf8');
  try {
    return { raw, data: JSON.parse(raw) };
  } catch (err) {
    fail(`${label} is not valid JSON (${filePath}): ${err.message}`);
    throw err; // unreachable, keeps TS/JS control-flow analysis happy
  }
}

/**
 * createZip() が書いたZIPバッファを readZip() で読み直し、渡された元データ
 * (sourceEntries)とバイト一致すること・エントリ数が一致することを検証する。
 * 自前のZIP実装（web/scripts/lib/zip.mjs）を書きっぱなしにしないための検証
 * ステップ。不一致はすべて fail() で中断する。
 *
 * @param {Buffer} zipBuf
 * @param {{name: string, data: Buffer}[]} sourceEntries createZip()へ渡したのと同じ配列
 */
function verifyZip(zipBuf, sourceEntries) {
  const readEntries = readZip(zipBuf);

  if (readEntries.length !== sourceEntries.length) {
    fail(`verifyZip: entry count mismatch: zip has ${readEntries.length}, expected ${sourceEntries.length}`);
  }

  const sourceByName = new Map(sourceEntries.map((e) => [e.name, e.data]));
  const seenNames = new Set();

  for (const entry of readEntries) {
    if (seenNames.has(entry.name)) {
      fail(`verifyZip: duplicate entry name in central directory: ${entry.name}`);
    }
    seenNames.add(entry.name);

    const expected = sourceByName.get(entry.name);
    if (!expected) {
      fail(`verifyZip: entry ${entry.name} not found among source entries`);
    } else if (!entry.data.equals(expected)) {
      fail(`verifyZip: extracted bytes for ${entry.name} do not match the source buffer`);
    }
  }

  const missingNames = [...sourceByName.keys()].filter((n) => !seenNames.has(n));
  if (missingNames.length > 0) {
    fail(`verifyZip: entries missing from the written zip: ${JSON.stringify(missingNames)}`);
  }
}

function main() {
  const indicators = readJson(indicatorsPath, 'area_indicators_R7.json');
  const demand = readJson(demandPath, 'area_demand_R7.json');
  const boundaries = readJson(boundariesPath, 'area_boundaries_R7.geojson');
  const facilitiesData = readJson(facilitiesPath, 'area_facilities_R7.json');
  const flowData = readJson(flowPath, 'area_flow_R7.json');
  const prefIndicators = readJson(prefIndicatorsPath, 'prefecture_indicators_R7.json');
  const prefBoundaries = readJson(prefBoundariesPath, 'prefecture_boundaries_R7.geojson');

  const features = boundaries.data.features;
  if (!Array.isArray(features) || features.length !== EXPECTED_FEATURE_COUNT) {
    fail(
      `boundaries feature count must be exactly ${EXPECTED_FEATURE_COUNT}, got ${
        Array.isArray(features) ? features.length : typeof features
      }`
    );
  }

  const boundaryCodes = features.map((f) => f.properties.area_code);
  if (new Set(boundaryCodes).size !== boundaryCodes.length) {
    fail('duplicate area_code found among boundary features');
  }

  const areas = indicators.data.areas;
  if (!Array.isArray(areas)) {
    fail('area_indicators_R7.json: "areas" is not an array');
  }

  const boundaryCodeSet = new Set(boundaryCodes);
  const indicatorCodeSet = new Set(areas.map((a) => a.area_code));
  const missingInIndicators = [...boundaryCodeSet].filter((c) => !indicatorCodeSet.has(c));
  const missingInBoundaries = [...indicatorCodeSet].filter((c) => !boundaryCodeSet.has(c));
  if (missingInIndicators.length > 0 || missingInBoundaries.length > 0) {
    fail(
      'area_code sets differ between boundaries and indicators. ' +
        `missing_in_indicators=${JSON.stringify(missingInIndicators)} ` +
        `missing_in_boundaries=${JSON.stringify(missingInBoundaries)}`
    );
  }

  const demandAreas = demand.data.areas;
  if (!Array.isArray(demandAreas) || demandAreas.length !== EXPECTED_FEATURE_COUNT) {
    fail(
      `area_demand_R7.json: "areas" must have exactly ${EXPECTED_FEATURE_COUNT} entries, got ${
        Array.isArray(demandAreas) ? demandAreas.length : typeof demandAreas
      }`
    );
  }

  const demandCodeSet = new Set(demandAreas.map((a) => a.area_code));
  if (demandCodeSet.size !== demandAreas.length) {
    fail('duplicate area_code found among area_demand_R7.json areas');
  }

  const demandMissingVsBoundaries = [...boundaryCodeSet].filter((c) => !demandCodeSet.has(c));
  const boundariesMissingVsDemand = [...demandCodeSet].filter((c) => !boundaryCodeSet.has(c));
  if (demandMissingVsBoundaries.length > 0 || boundariesMissingVsDemand.length > 0) {
    fail(
      'area_demand_R7.json area_code set differs from boundaries. ' +
        `missing_in_demand=${JSON.stringify(demandMissingVsBoundaries)} ` +
        `missing_in_boundaries=${JSON.stringify(boundariesMissingVsDemand)}`
    );
  }
  const demandMissingVsIndicators = [...indicatorCodeSet].filter((c) => !demandCodeSet.has(c));
  const indicatorsMissingVsDemand = [...demandCodeSet].filter((c) => !indicatorCodeSet.has(c));
  if (demandMissingVsIndicators.length > 0 || indicatorsMissingVsDemand.length > 0) {
    fail(
      'area_demand_R7.json area_code set differs from area_indicators_R7.json. ' +
        `missing_in_demand=${JSON.stringify(demandMissingVsIndicators)} ` +
        `missing_in_indicators=${JSON.stringify(indicatorsMissingVsDemand)}`
    );
  }

  const demandCategories = demand.data.categories;
  const demandYears = demand.data.years;
  if (!Array.isArray(demandCategories) || demandCategories.length === 0) {
    fail('area_demand_R7.json: "categories" must be a non-empty array');
  }
  if (!Array.isArray(demandYears) || demandYears.length === 0) {
    fail('area_demand_R7.json: "years" must be a non-empty array');
  }

  for (const area of demandAreas) {
    for (const category of demandCategories) {
      const categoryDemand = area.demand ? area.demand[category] : undefined;
      if (!categoryDemand || typeof categoryDemand !== 'object') {
        fail(`area_demand_R7.json: area ${area.area_code} is missing demand.${category}`);
      }
      for (const year of demandYears) {
        const value = categoryDemand[String(year)];
        if (typeof value !== 'number' || !Number.isFinite(value)) {
          fail(
            `area_demand_R7.json: area ${area.area_code} has a non-finite demand.${category}[${year}]: ${value}`
          );
        }
      }
    }
  }

  // --- area_facilities_R7.json validation ------------------------------
  // area_facilities_R7.json is produced by tools/build_web_facilities.py
  // (Chunk A), which already validates the CSV inputs it was built from.
  // These checks instead validate the JSON this script is about to fan out
  // into per-area shards, so a corrupted/truncated file (or a future bug in
  // this script's own splitting logic) fails the build loudly instead of
  // shipping partial facility data.
  const facilityAreas = facilitiesData.data.areas;
  if (!Array.isArray(facilityAreas) || facilityAreas.length !== EXPECTED_FEATURE_COUNT) {
    fail(
      `area_facilities_R7.json: "areas" must have exactly ${EXPECTED_FEATURE_COUNT} entries, got ${
        Array.isArray(facilityAreas) ? facilityAreas.length : typeof facilityAreas
      }`
    );
  }

  const facilityCodeSet = new Set(facilityAreas.map((a) => a.area_code));
  if (facilityCodeSet.size !== facilityAreas.length) {
    fail('duplicate area_code found among area_facilities_R7.json areas');
  }

  const facilitiesMissingVsBoundaries = [...boundaryCodeSet].filter((c) => !facilityCodeSet.has(c));
  const boundariesMissingVsFacilities = [...facilityCodeSet].filter((c) => !boundaryCodeSet.has(c));
  if (facilitiesMissingVsBoundaries.length > 0 || boundariesMissingVsFacilities.length > 0) {
    fail(
      'area_facilities_R7.json area_code set differs from boundaries. ' +
        `missing_in_facilities=${JSON.stringify(facilitiesMissingVsBoundaries)} ` +
        `missing_in_boundaries=${JSON.stringify(boundariesMissingVsFacilities)}`
    );
  }

  const facilityMetricsCount = facilitiesData.data.metrics.length;
  let totalFacilityCount = 0;
  let totalGeocodedCount = 0;
  for (const area of facilityAreas) {
    if (!Array.isArray(area.facilities) || area.facilities.length !== area.facility_count) {
      fail(
        `area_facilities_R7.json: area ${area.area_code} facilities.length (${
          Array.isArray(area.facilities) ? area.facilities.length : typeof area.facilities
        }) does not match facility_count (${area.facility_count})`
      );
    }
    totalFacilityCount += area.facility_count;

    let actualGeocoded = 0;
    for (const facility of area.facilities) {
      if (facility.values.length !== facilityMetricsCount || facility.value_status.length !== facilityMetricsCount) {
        fail(
          `area_facilities_R7.json: facility ${facility.record_id} in area ${area.area_code} has ` +
            `values.length=${facility.values.length} value_status.length=${facility.value_status.length}, ` +
            `expected ${facilityMetricsCount}`
        );
      }

      if ('coordinates' in facility) {
        actualGeocoded += 1;
        if (facility.match_status !== 'matched') {
          fail(
            `area_facilities_R7.json: facility ${facility.record_id} in area ${area.area_code} has ` +
              `coordinates but match_status=${JSON.stringify(facility.match_status)} (expected "matched")`
          );
        }
        const coords = facility.coordinates;
        if (
          !Array.isArray(coords) ||
          coords.length !== 2 ||
          !Number.isFinite(coords[0]) ||
          !Number.isFinite(coords[1])
        ) {
          fail(
            `area_facilities_R7.json: facility ${facility.record_id} in area ${area.area_code} has ` +
              `non-finite/malformed coordinates: ${JSON.stringify(coords)}`
          );
        }
      }
    }

    if (actualGeocoded !== area.geocoded_count) {
      fail(
        `area_facilities_R7.json: area ${area.area_code} geocoded_count (${area.geocoded_count}) does not ` +
          `match the number of facilities with coordinates (${actualGeocoded})`
      );
    }
    totalGeocodedCount += area.geocoded_count;
  }

  if (totalFacilityCount !== EXPECTED_FACILITY_TOTAL) {
    fail(
      `area_facilities_R7.json: total facility_count across areas must be exactly ${EXPECTED_FACILITY_TOTAL}, ` +
        `got ${totalFacilityCount}`
    );
  }
  if (totalGeocodedCount !== EXPECTED_GEOCODED_TOTAL) {
    fail(
      `area_facilities_R7.json: total geocoded_count across areas must be exactly ${EXPECTED_GEOCODED_TOTAL}, ` +
        `got ${totalGeocodedCount}`
    );
  }
  // --- end area_facilities_R7.json validation ---------------------------

  // --- area_flow_R7.json validation --------------------------------------
  // area_flow_R7.json is produced by tools/build_web_flow.py, which already
  // validates the CSVs it was built from (13 checks — see its docstring).
  // These checks instead validate the JSON this script is about to copy
  // verbatim into web/public/flow/area_flow.json, so a corrupted/truncated
  // file fails the build loudly instead of shipping broken patient-flow data.
  const flowAreas = flowData.data.areas;
  if (!Array.isArray(flowAreas) || flowAreas.length !== EXPECTED_FEATURE_COUNT) {
    fail(
      `area_flow_R7.json: "areas" must have exactly ${EXPECTED_FEATURE_COUNT} entries, got ${
        Array.isArray(flowAreas) ? flowAreas.length : typeof flowAreas
      }`
    );
  }

  const flowCodeSet = new Set(flowAreas.map((a) => a.area_code));
  if (flowCodeSet.size !== flowAreas.length) {
    fail('duplicate area_code found among area_flow_R7.json areas');
  }

  const flowMissingVsBoundaries = [...boundaryCodeSet].filter((c) => !flowCodeSet.has(c));
  const boundariesMissingVsFlow = [...flowCodeSet].filter((c) => !boundaryCodeSet.has(c));
  if (flowMissingVsBoundaries.length > 0 || boundariesMissingVsFlow.length > 0) {
    fail(
      'area_flow_R7.json area_code set differs from boundaries. ' +
        `missing_in_flow=${JSON.stringify(flowMissingVsBoundaries)} ` +
        `missing_in_boundaries=${JSON.stringify(boundariesMissingVsFlow)}`
    );
  }

  const flowDirections = flowData.data.directions;
  const flowPhases = flowData.data.phases;
  if (!Array.isArray(flowDirections) || flowDirections.length === 0) {
    fail('area_flow_R7.json: "directions" must be a non-empty array');
  }
  if (!Array.isArray(flowPhases) || flowPhases.length === 0) {
    fail('area_flow_R7.json: "phases" must be a non-empty array');
  }

  let flowGroupCount = 0;
  for (const area of flowAreas) {
    for (const direction of flowDirections) {
      const directionEntry = area.flows ? area.flows[direction] : undefined;
      if (!directionEntry || typeof directionEntry !== 'object') {
        fail(`area_flow_R7.json: area ${area.area_code} is missing flows.${direction}`);
      }
      for (const phase of flowPhases) {
        const group = directionEntry.phases ? directionEntry.phases[phase] : undefined;
        if (!group || typeof group !== 'object') {
          fail(`area_flow_R7.json: area ${area.area_code} is missing flows.${direction}.phases.${phase}`);
        }
        flowGroupCount += 1;

        const selfRateIsNull = group.self_rate === null;
        const selfRankIsNull = group.self_rank === null;
        if (selfRateIsNull !== selfRankIsNull) {
          fail(
            `area_flow_R7.json: area ${area.area_code} flows.${direction}.phases.${phase} has ` +
              `self_rate=${JSON.stringify(group.self_rate)} but self_rank=${JSON.stringify(group.self_rank)} ` +
              '(must both be null or both be numbers)'
          );
        } else if (!selfRateIsNull) {
          if (typeof group.self_rate !== 'number' || !Number.isFinite(group.self_rate)) {
            fail(
              `area_flow_R7.json: area ${area.area_code} flows.${direction}.phases.${phase} has a ` +
                `non-finite self_rate: ${group.self_rate}`
            );
          }
          if (typeof group.self_rank !== 'number' || !Number.isInteger(group.self_rank)) {
            fail(
              `area_flow_R7.json: area ${area.area_code} flows.${direction}.phases.${phase} has a ` +
                `non-integer self_rank: ${group.self_rank}`
            );
          }
        }

        if (!Array.isArray(group.partners)) {
          fail(
            `area_flow_R7.json: area ${area.area_code} flows.${direction}.phases.${phase}.partners is not an array`
          );
        } else {
          for (const partner of group.partners) {
            if (!Array.isArray(partner) || partner.length !== 2) {
              fail(
                `area_flow_R7.json: area ${area.area_code} flows.${direction}.phases.${phase} has a ` +
                  `malformed partner entry: ${JSON.stringify(partner)}`
              );
            }
            const [partnerCode, rate] = partner;
            if (typeof partnerCode !== 'string' || !boundaryCodeSet.has(partnerCode)) {
              fail(
                `area_flow_R7.json: area ${area.area_code} flows.${direction}.phases.${phase} has a ` +
                  `partner area_code not present in boundaries: ${JSON.stringify(partnerCode)}`
              );
            }
            if (partnerCode === area.area_code) {
              fail(
                `area_flow_R7.json: area ${area.area_code} flows.${direction}.phases.${phase} lists itself ` +
                  'as a partner (partners must exclude the area itself)'
              );
            }
            if (typeof rate !== 'number' || !Number.isFinite(rate) || rate < 0 || rate > 1) {
              fail(
                `area_flow_R7.json: area ${area.area_code} flows.${direction}.phases.${phase} has a ` +
                  `partner rate outside [0,1]: ${JSON.stringify(rate)}`
              );
            }
          }
        }

        if (!Number.isInteger(group.value_error_count) || group.value_error_count < 0) {
          fail(
            `area_flow_R7.json: area ${area.area_code} flows.${direction}.phases.${phase} has a ` +
              `non-negative-integer value_error_count: ${JSON.stringify(group.value_error_count)}`
          );
        }
      }
    }
  }

  if (flowGroupCount !== EXPECTED_FLOW_GROUPS) {
    fail(
      `area_flow_R7.json: expected ${EXPECTED_FLOW_GROUPS} direction×phase groups across all areas, got ${flowGroupCount}`
    );
  }
  // --- end area_flow_R7.json validation -----------------------------------

  let areaMap;
  try {
    areaMap = buildAreaMap(boundaries.data, indicators.data, demand.data);
  } catch (err) {
    fail(`buildAreaMap failed: ${err.message}`);
    return; // unreachable
  }

  for (const feature of areaMap.features) {
    const props = feature.properties;
    for (const fn of BED_FUNCTIONS) {
      if (typeof props[`a_${fn}`] !== 'number' || typeof props[`n_${fn}`] !== 'number') {
        fail(`feature ${props.area_code} is missing a_${fn}/n_${fn}`);
      }
    }
    for (const key of ['bb_w', 'bb_s', 'bb_e', 'bb_n']) {
      if (!Number.isFinite(props[key])) {
        fail(`feature ${props.area_code} has a non-finite ${key}: ${props[key]}`);
      }
    }
    for (const category of demandCategories) {
      for (const year of demandYears) {
        for (const key of [demandValueKey(category, year), demandRatioKey(category, year)]) {
          if (typeof props[key] !== 'number' || !Number.isFinite(props[key])) {
            fail(`feature ${props.area_code} has a non-finite ${key}: ${props[key]}`);
          }
        }
      }
    }
  }

  let areaIndex;
  try {
    areaIndex = buildAreaIndex(boundaries.data);
  } catch (err) {
    fail(`buildAreaIndex failed: ${err.message}`);
    return; // unreachable
  }

  if (areaIndex.length !== EXPECTED_FEATURE_COUNT) {
    fail(`area_index entry count must be exactly ${EXPECTED_FEATURE_COUNT}, got ${areaIndex.length}`);
  }
  const areaIndexCodeSet = new Set(areaIndex.map((a) => a.area_code));
  if (areaIndexCodeSet.size !== areaIndex.length) {
    fail('duplicate area_code found among area_index entries');
  }
  const areaIndexMissingVsBoundaries = [...boundaryCodeSet].filter((c) => !areaIndexCodeSet.has(c));
  const boundariesMissingVsAreaIndex = [...areaIndexCodeSet].filter((c) => !boundaryCodeSet.has(c));
  if (areaIndexMissingVsBoundaries.length > 0 || boundariesMissingVsAreaIndex.length > 0) {
    fail(
      'area_index area_code set differs from boundaries. ' +
        `missing_in_area_index=${JSON.stringify(areaIndexMissingVsBoundaries)} ` +
        `missing_in_boundaries=${JSON.stringify(boundariesMissingVsAreaIndex)}`
    );
  }
  for (const entry of areaIndex) {
    for (const key of ['bb_w', 'bb_s', 'bb_e', 'bb_n']) {
      if (!Number.isFinite(entry[key])) {
        fail(`area_index entry ${entry.area_code} has a non-finite ${key}: ${entry[key]}`);
      }
    }
  }

  // --- prefecture (overview layer) validation ---------------------------
  // 都道府県レイヤは構想区域レイヤと同じ形の検証をかける。ここが黙って
  // 通ると「概観層と主表示層で数字が食い違う」という最も分かりにくい事故に
  // なるため、値そのものの整合(都道府県=構想区域の合計)は
  // tools/build_web_prefecture.py の検証8・9で既に担保してある。
  const prefFeatures = prefBoundaries.data.features;
  if (!Array.isArray(prefFeatures) || prefFeatures.length !== EXPECTED_PREFECTURE_COUNT) {
    fail(
      `prefecture_boundaries_R7.geojson feature count must be exactly ${EXPECTED_PREFECTURE_COUNT}, got ${
        Array.isArray(prefFeatures) ? prefFeatures.length : typeof prefFeatures
      }`
    );
  }

  const prefBoundaryCodes = prefFeatures.map((f) => f.properties.pref_code);
  const prefBoundaryCodeSet = new Set(prefBoundaryCodes);
  if (prefBoundaryCodeSet.size !== prefBoundaryCodes.length) {
    fail('duplicate pref_code found among prefecture boundary features');
  }

  const prefectures = prefIndicators.data.prefectures;
  if (!Array.isArray(prefectures) || prefectures.length !== EXPECTED_PREFECTURE_COUNT) {
    fail(
      `prefecture_indicators_R7.json: "prefectures" must have exactly ${EXPECTED_PREFECTURE_COUNT} entries, got ${
        Array.isArray(prefectures) ? prefectures.length : typeof prefectures
      }`
    );
  }
  if (!prefIndicators.data.national || prefIndicators.data.national.pref_code !== '00') {
    fail('prefecture_indicators_R7.json: "national" is missing or is not pref_code "00"');
  }

  const prefIndicatorCodeSet = new Set(prefectures.map((p) => p.pref_code));
  const prefMissingInIndicators = [...prefBoundaryCodeSet].filter((c) => !prefIndicatorCodeSet.has(c));
  const prefMissingInBoundaries = [...prefIndicatorCodeSet].filter((c) => !prefBoundaryCodeSet.has(c));
  if (prefMissingInIndicators.length > 0 || prefMissingInBoundaries.length > 0) {
    fail(
      'pref_code sets differ between prefecture boundaries and indicators. ' +
        `missing_in_indicators=${JSON.stringify(prefMissingInIndicators)} ` +
        `missing_in_boundaries=${JSON.stringify(prefMissingInBoundaries)}`
    );
  }

  // 構想区域側の pref_code(area_map の上2桁ではなく boundaries の属性)と
  // 都道府県レイヤが覆う範囲が一致すること。片方だけ区域が増減したら気付ける。
  const areaPrefCodeSet = new Set(features.map((f) => f.properties.pref_code));
  const prefMissingVsAreas = [...areaPrefCodeSet].filter((c) => !prefBoundaryCodeSet.has(c));
  const areasMissingVsPref = [...prefBoundaryCodeSet].filter((c) => !areaPrefCodeSet.has(c));
  if (prefMissingVsAreas.length > 0 || areasMissingVsPref.length > 0) {
    fail(
      'pref_code sets differ between prefecture boundaries and area boundaries. ' +
        `missing_in_prefectures=${JSON.stringify(prefMissingVsAreas)} ` +
        `missing_in_areas=${JSON.stringify(areasMissingVsPref)}`
    );
  }

  // 需要の区分・年度が構想区域側と同一であること(片方だけ年度が増えると、
  // 地図のプロパティキーが層によって食い違って静かに無色になる)。
  if (JSON.stringify(prefIndicators.data.categories) !== JSON.stringify(demandCategories)) {
    fail(
      'prefecture_indicators_R7.json categories differ from area_demand_R7.json: ' +
        `${JSON.stringify(prefIndicators.data.categories)} vs ${JSON.stringify(demandCategories)}`
    );
  }
  if (JSON.stringify(prefIndicators.data.years) !== JSON.stringify(demandYears)) {
    fail(
      'prefecture_indicators_R7.json years differ from area_demand_R7.json: ' +
        `${JSON.stringify(prefIndicators.data.years)} vs ${JSON.stringify(demandYears)}`
    );
  }
  if (prefIndicators.data.baseline_year !== demand.data.baseline_year) {
    fail(
      'prefecture_indicators_R7.json baseline_year differs from area_demand_R7.json: ' +
        `${prefIndicators.data.baseline_year} vs ${demand.data.baseline_year}`
    );
  }

  let prefMap;
  try {
    prefMap = buildPrefectureMap(prefBoundaries.data, prefIndicators.data);
  } catch (err) {
    fail(`buildPrefectureMap failed: ${err.message}`);
    return; // unreachable
  }

  for (const feature of prefMap.features) {
    const props = feature.properties;
    for (const fn of BED_FUNCTIONS) {
      if (typeof props[`a_${fn}`] !== 'number' || typeof props[`n_${fn}`] !== 'number') {
        fail(`prefecture feature ${props.pref_code} is missing a_${fn}/n_${fn}`);
      }
    }
    for (const key of ['bb_w', 'bb_s', 'bb_e', 'bb_n']) {
      if (!Number.isFinite(props[key])) {
        fail(`prefecture feature ${props.pref_code} has a non-finite ${key}: ${props[key]}`);
      }
    }
    for (const category of demandCategories) {
      for (const year of demandYears) {
        for (const key of [demandValueKey(category, year), demandRatioKey(category, year)]) {
          if (typeof props[key] !== 'number' || !Number.isFinite(props[key])) {
            fail(`prefecture feature ${props.pref_code} has a non-finite ${key}: ${props[key]}`);
          }
        }
      }
    }
  }
  // --- end prefecture validation ----------------------------------------

  fs.mkdirSync(generatedDir, { recursive: true });

  // 1. area_indicators.json — verbatim copy of the source (line-ending
  //    normalized to LF only; content/formatting otherwise untouched so this
  //    stays a faithful copy of the one source of truth in data/processed/).
  fs.writeFileSync(
    path.join(generatedDir, 'area_indicators.json'),
    indicators.raw.replace(/\r\n/g, '\n')
  );

  // 1b. area_demand.json — verbatim copy (same treatment as area_indicators.json
  //     above): bundled directly and used by the area panel/legend for the
  //     demand-forecast metric.
  fs.writeFileSync(
    path.join(generatedDir, 'area_demand.json'),
    demand.raw.replace(/\r\n/g, '\n')
  );

  // 2. area_map.json — compact (no pretty-printing) to keep the fetched
  //    payload small; deterministic key order comes from buildAreaMap.
  fs.writeFileSync(path.join(generatedDir, 'area_map.json'), `${JSON.stringify(areaMap)}\n`);

  // 3. area_index.json — lightweight (area_code/boundary_source/bbox only)
  //    lookup table, bundled directly (not fetched) so App can resolve area
  //    selection without depending on the map's load/viewport state.
  fs.writeFileSync(path.join(generatedDir, 'area_index.json'), `${JSON.stringify(areaIndex)}\n`);

  // 3b. prefecture_indicators.json — verbatim copy (same treatment as
  //     area_indicators.json): 47都道府県+全国ぶんで75KBしかないので、区域側と
  //     同じくバンドルしてパネル・分位計算・出典表示に使う。
  fs.writeFileSync(
    path.join(generatedDir, 'prefecture_indicators.json'),
    prefIndicators.raw.replace(/\r\n/g, '\n')
  );

  // 3c. pref_map.json — 概観レイヤの地図データ。area_map.json と同じく
  //     `?url` インポートでMapLibreにfetchさせる(メインスレッドでパースしない)。
  fs.writeFileSync(path.join(generatedDir, 'pref_map.json'), `${JSON.stringify(prefMap)}\n`);

  // 4. web/public/facilities/<area_code>.json — one shard per area, fetched
  //    lazily by the frontend when an area is selected. Written under
  //    web/public/ (not src/generated/) rather than bundled via
  //    `import.meta.glob(..., {query: '?url', eager: true})`, because that
  //    approach has three failure modes: (a) Vite inlines assets under 4KB
  //    as base64 into the JS bundle by default, so the smallest ~1KB shards
  //    would end up embedded in the initial JS anyway; (b) getting just the
  //    URL (not the inlined content) requires `import: 'default'`; and
  //    (c) a 339-entry URL table would still ship in the initial JS. Writing
  //    to public/ sidesteps all three: Vite just copies the directory to
  //    dist/ verbatim, and the frontend fetches shards by URL at run time.
  //
  //    The directory is wiped and recreated on every run (rather than
  //    overwritten in place) so that shrinking the number of areas doesn't
  //    leave stale shards on disk for area codes that no longer exist.
  fs.rmSync(facilitiesOutDir, { recursive: true, force: true });
  fs.mkdirSync(facilitiesOutDir, { recursive: true });

  let totalShardBytes = 0;
  let maxShardBytes = 0;
  for (const area of facilityAreas) {
    const shard = buildAreaShard(area);
    let fileName;
    try {
      fileName = shardFileName(area.area_code);
    } catch (err) {
      fail(`shardFileName failed for area ${area.area_code}: ${err.message}`);
      return; // unreachable
    }
    const text = `${JSON.stringify(shard)}\n`;
    fs.writeFileSync(path.join(facilitiesOutDir, fileName), text);
    const bytes = Buffer.byteLength(text, 'utf8');
    totalShardBytes += bytes;
    if (bytes > maxShardBytes) maxShardBytes = bytes;
  }

  // 5. facility_summary.json — bundled (like area_index.json above): gives
  //    the frontend per-area facility/geocoded counts and the metric
  //    definitions without paying for the full facilities[] payload.
  const facilitySummary = buildFacilitySummary(facilitiesData.data);
  fs.writeFileSync(
    path.join(generatedDir, 'facility_summary.json'),
    `${JSON.stringify(facilitySummary)}\n`
  );

  // 5b. web/public/flow/area_flow.json — verbatim copy of area_flow_R7.json
  //     (line-ending normalized to LF only, like area_indicators.json/
  //     area_demand.json above). NOT bundled into src/generated/: like the
  //     facility shards above, this is area-detail data only needed once an
  //     area is selected (doc/REQUIREMENTS.md §6「区域詳細はオンデマンド取得」),
  //     and at ~499KB (gzip ~126KB) it would bloat the initial JS bundle.
  //     Unlike the facility shards, it is NOT split per area: the whole
  //     dataset is a single file, so switching the selected area never
  //     changes the fetch target — race condition #14 (CLAUDE.md「可視化実装で
  //     判明した罠」) cannot occur here by construction, since one
  //     loadFlowData() call is cached and reused for every area.
  //
  //     Directory is wiped and recreated (same reasoning as facilitiesOutDir
  //     above): a shrinking dataset must not leave a stale file on disk.
  fs.rmSync(flowOutDir, { recursive: true, force: true });
  fs.mkdirSync(flowOutDir, { recursive: true });
  const flowText = flowData.raw.replace(/\r\n/g, '\n');
  fs.writeFileSync(path.join(flowOutDir, 'area_flow.json'), flowText);
  const flowBytes = Buffer.byteLength(flowText, 'utf8');

  console.log(
    `[sync-data] OK: wrote area_indicators.json (${areas.length} areas), ` +
      `area_demand.json (${demandAreas.length} areas), ` +
      `area_map.json (${areaMap.features.length} features), ` +
      `area_index.json (${areaIndex.length} entries), ` +
      `prefecture_indicators.json (${prefectures.length} prefectures + national), ` +
      `pref_map.json (${prefMap.features.length} features) to ${path.relative(repoRoot, generatedDir)}; ` +
      `wrote ${facilityAreas.length} facility shards ` +
      `(total ${totalShardBytes.toLocaleString('en-US')} bytes, max ${maxShardBytes.toLocaleString('en-US')} bytes) ` +
      `to ${path.relative(repoRoot, facilitiesOutDir)} and facility_summary.json ` +
      `(${facilitySummary.areas.length} areas) to ${path.relative(repoRoot, generatedDir)}`
  );

  // 6. web/public/downloads/<BUNDLE_FILE_NAME> — data/processed/ の加工済み
  //    CSV15本を1本のZIPにまとめた一括ダウンロード配布物。web/public/facilities/
  //    と同じ理由でディレクトリを一掃してから作り直す(収録物が減ったときに
  //    古いファイルがdistへ残らないようにするため)。
  fs.rmSync(downloadsOutDir, { recursive: true, force: true });
  fs.mkdirSync(downloadsOutDir, { recursive: true });

  // BUNDLE_CSV_FILES(web/scripts/lib/bundle.mjs)と実際のdata/processed/*.csvの
  // 一覧を突合する。食い違ったら中断する(新しいCSVが増えたときに黙って配布物
  // から漏れる/意図しないファイルが混ざるのを防ぐため)。
  const actualCsvFiles = fs
    .readdirSync(processedDir)
    .filter((name) => name.endsWith('.csv'))
    .sort();
  const expectedCsvFiles = [...BUNDLE_CSV_FILES].sort();
  if (JSON.stringify(actualCsvFiles) !== JSON.stringify(expectedCsvFiles)) {
    fail(
      'BUNDLE_CSV_FILES (web/scripts/lib/bundle.mjs) does not match data/processed/*.csv. ' +
        `expected=${JSON.stringify(expectedCsvFiles)} actual=${JSON.stringify(actualCsvFiles)}`
    );
  }

  // 各CSVとその<csv>.meta.jsonを読み、SHA-256を計算してZIPエントリ・
  // MANIFEST.tsv・README.md・download_manifest.jsonの材料を組み立てる。
  // CSVの中身は正本のバイト列をそのまま格納する(BOM付与・改行変換はしない。
  // ZIP内のCSVのSHA-256がdata/processed/のそれと一致することが真正性の担保)。
  const zipEntries = [];
  const manifestMembers = [];
  const readmeFiles = [];
  const downloadManifestMembers = [];

  for (const csvName of BUNDLE_CSV_FILES) {
    const csvPath = path.join(processedDir, csvName);
    const metaPath = `${csvPath}.meta.json`;
    const csvBuf = fs.readFileSync(csvPath);
    const meta = readJson(metaPath, `${csvName}.meta.json`).data;
    const csvSha256 = crypto.createHash('sha256').update(csvBuf).digest('hex');

    zipEntries.push({ name: `${BUNDLE_ROOT}/${csvName}`, data: csvBuf });
    manifestMembers.push({ name: csvName, bytes: csvBuf.length, sha256: csvSha256, rows: meta.row_count });
    readmeFiles.push({
      name: csvName,
      title: meta.title,
      rows: meta.row_count,
      source: meta.source,
      known_issues: meta.known_issues,
    });
    downloadManifestMembers.push({
      name: csvName,
      title: meta.title,
      bytes: csvBuf.length,
      rows: meta.row_count,
      sha256: csvSha256,
    });

    const metaBuf = fs.readFileSync(metaPath);
    const metaSha256 = crypto.createHash('sha256').update(metaBuf).digest('hex');
    zipEntries.push({ name: `${BUNDLE_ROOT}/${csvName}.meta.json`, data: metaBuf });
    manifestMembers.push({ name: `${csvName}.meta.json`, bytes: metaBuf.length, sha256: metaSha256, rows: '' });
  }

  const readmeBuf = Buffer.from(buildBundleReadme({ repoUrl: REPO_URL, files: readmeFiles }), 'utf8');
  zipEntries.push({ name: `${BUNDLE_ROOT}/README.md`, data: readmeBuf });

  const manifestBuf = Buffer.from(buildManifestTsv(manifestMembers), 'utf8');
  zipEntries.push({ name: `${BUNDLE_ROOT}/MANIFEST.tsv`, data: manifestBuf });

  let zipBuf;
  try {
    zipBuf = createZip(zipEntries);
  } catch (err) {
    fail(`createZip failed: ${err.message}`);
    return; // unreachable
  }

  // 書きっぱなしにしない: 自前のZIP実装なので、書いたバッファを読み直して
  // 各エントリが元データとバイト一致することを検証する。
  verifyZip(zipBuf, zipEntries);

  const bundlePath = path.join(downloadsOutDir, BUNDLE_FILE_NAME);
  fs.writeFileSync(bundlePath, zipBuf);
  const bundleSha256 = crypto.createHash('sha256').update(zipBuf).digest('hex');

  // 7. web/public/downloads/area_boundaries_R7.geojson — ZIPには入れず単体で
  //    コピーする(地図ツール等での単体利用のため)。
  const boundariesBuf = fs.readFileSync(boundariesPath);
  fs.writeFileSync(path.join(downloadsOutDir, 'area_boundaries_R7.geojson'), boundariesBuf);
  const boundariesSha256 = crypto.createHash('sha256').update(boundariesBuf).digest('hex');

  // 8. web/src/generated/download_manifest.json — UIがサイズ・SHA-256・収録物
  //    を表示するための軽量な一覧(bundle実体を取得しなくても内容を説明できる
  //    ようにする)。membersは15本のCSVのみ(meta.jsonは含めない)。
  const downloadManifest = {
    bundle: {
      file: BUNDLE_FILE_NAME,
      bytes: zipBuf.length,
      sha256: bundleSha256,
      entry_count: zipEntries.length,
      csv_count: BUNDLE_CSV_FILES.length,
    },
    boundaries: {
      file: 'area_boundaries_R7.geojson',
      bytes: boundariesBuf.length,
      sha256: boundariesSha256,
    },
    members: downloadManifestMembers,
  };
  fs.writeFileSync(
    path.join(generatedDir, 'download_manifest.json'),
    `${JSON.stringify(downloadManifest, null, 2)}\n`
  );

  console.log(
    `[sync-data] OK: wrote ${BUNDLE_FILE_NAME} ` +
      `(${zipBuf.length.toLocaleString('en-US')} bytes, ${zipEntries.length} entries) and ` +
      `area_boundaries_R7.geojson (${boundariesBuf.length.toLocaleString('en-US')} bytes) ` +
      `to ${path.relative(repoRoot, downloadsOutDir)}; wrote download_manifest.json ` +
      `(${downloadManifest.members.length} CSV members) to ${path.relative(repoRoot, generatedDir)}; ` +
      `wrote area_flow.json (${flowAreas.length} areas, ${flowBytes.toLocaleString('en-US')} bytes) ` +
      `to ${path.relative(repoRoot, flowOutDir)}`
  );
}

main();
