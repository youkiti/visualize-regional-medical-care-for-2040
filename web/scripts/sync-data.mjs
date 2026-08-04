// Reads data/processed/area_indicators_R7.json and
// data/processed/area_boundaries_R7.geojson (the single source of truth,
// owned by the Python pipeline — see CLAUDE.md) and writes the three
// generated artifacts the frontend bundles/fetches:
//
//   web/src/generated/area_indicators.json  — verbatim copy
//   web/src/generated/area_map.json         — boundaries + flat indicator props
//   web/src/generated/area_index.json       — lightweight per-area bbox/boundary_source
//                                              lookup, used by App to resolve area
//                                              selection independent of the map's
//                                              load/viewport state (see App.tsx)
//
// Run via `npm run sync-data` (also wired into predev/prebuild). Exits
// non-zero on any consistency failure so a broken data pipeline fails the
// build instead of silently shipping a stale/partial site.

import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

import { buildAreaMap, buildAreaIndex, BED_FUNCTIONS } from './lib/merge.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const webDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(webDir, '..');

const indicatorsPath = path.join(repoRoot, 'data', 'processed', 'area_indicators_R7.json');
const boundariesPath = path.join(repoRoot, 'data', 'processed', 'area_boundaries_R7.geojson');
const generatedDir = path.join(webDir, 'src', 'generated');

const EXPECTED_FEATURE_COUNT = 339;

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

function main() {
  const indicators = readJson(indicatorsPath, 'area_indicators_R7.json');
  const boundaries = readJson(boundariesPath, 'area_boundaries_R7.geojson');

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

  let areaMap;
  try {
    areaMap = buildAreaMap(boundaries.data, indicators.data);
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

  fs.mkdirSync(generatedDir, { recursive: true });

  // 1. area_indicators.json — verbatim copy of the source (line-ending
  //    normalized to LF only; content/formatting otherwise untouched so this
  //    stays a faithful copy of the one source of truth in data/processed/).
  fs.writeFileSync(
    path.join(generatedDir, 'area_indicators.json'),
    indicators.raw.replace(/\r\n/g, '\n')
  );

  // 2. area_map.json — compact (no pretty-printing) to keep the fetched
  //    payload small; deterministic key order comes from buildAreaMap.
  fs.writeFileSync(path.join(generatedDir, 'area_map.json'), `${JSON.stringify(areaMap)}\n`);

  // 3. area_index.json — lightweight (area_code/boundary_source/bbox only)
  //    lookup table, bundled directly (not fetched) so App can resolve area
  //    selection without depending on the map's load/viewport state.
  fs.writeFileSync(path.join(generatedDir, 'area_index.json'), `${JSON.stringify(areaIndex)}\n`);

  console.log(
    `[sync-data] OK: wrote area_indicators.json (${areas.length} areas), ` +
      `area_map.json (${areaMap.features.length} features) and ` +
      `area_index.json (${areaIndex.length} entries) to ${path.relative(repoRoot, generatedDir)}`
  );
}

main();
