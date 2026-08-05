import { describe, expect, it } from 'vitest';
import {
  BUNDLE_CSV_FILES,
  BUNDLE_FILE_NAME,
  BUNDLE_ROOT,
  buildBundleReadme,
  buildManifestTsv,
} from '../../scripts/lib/bundle.mjs';

// Inline fixtures only — this mirrors data/processed/*.csv.meta.json shapes
// closely enough to exercise buildBundleReadme/buildManifestTsv, but does not
// read data/processed/ itself (see web/scripts/lib/facilities.mjs's test file
// for why: no pre* hook runs before `npm run test`).

describe('BUNDLE_CSV_FILES', () => {
  it('lists exactly the 15 processed CSVs, with no duplicates', () => {
    expect(BUNDLE_CSV_FILES).toHaveLength(15);
    expect(new Set(BUNDLE_CSV_FILES).size).toBe(15);
    expect(BUNDLE_CSV_FILES).toContain('area_beds.csv');
    expect(BUNDLE_CSV_FILES).toContain('facility_observations.csv');
    expect(BUNDLE_CSV_FILES).toContain('patient_flow.csv');
    expect(BUNDLE_CSV_FILES).toContain('patient_flow_total.csv');
    expect(BUNDLE_CSV_FILES).toContain('prefecture_beds.csv');
  });

  it('every entry ends with .csv (no meta.json / directories smuggled in)', () => {
    for (const name of BUNDLE_CSV_FILES) {
      expect(name.endsWith('.csv')).toBe(true);
      expect(name).not.toContain('/');
    }
  });
});

describe('BUNDLE_ROOT / BUNDLE_FILE_NAME', () => {
  it('the zip file name is the root folder name plus .zip', () => {
    expect(BUNDLE_FILE_NAME).toBe(`${BUNDLE_ROOT}.zip`);
  });
});

describe('buildManifestTsv', () => {
  it('starts with the tab-separated header row', () => {
    const tsv = buildManifestTsv([]);
    expect(tsv.startsWith('file\tbytes\tsha256\trows\n')).toBe(true);
  });

  it('renders one tab-separated row per member', () => {
    const tsv = buildManifestTsv([
      { name: 'area_beds.csv', bytes: 1082798, sha256: 'abc123', rows: 18645 },
    ]);
    const lines = tsv.split('\n');
    expect(lines[1]).toBe('area_beds.csv\t1082798\tabc123\t18645');
  });

  it('renders an empty rows field (not "undefined"/"null") for meta.json-like members', () => {
    const tsv = buildManifestTsv([{ name: 'area_beds.csv.meta.json', bytes: 4806, sha256: 'def456', rows: '' }]);
    const lines = tsv.split('\n');
    expect(lines[1]).toBe('area_beds.csv.meta.json\t4806\tdef456\t');
  });

  it('uses LF line endings and ends with a trailing newline', () => {
    const tsv = buildManifestTsv([{ name: 'a.csv', bytes: 1, sha256: 'x', rows: 1 }]);
    expect(tsv.includes('\r')).toBe(false);
    expect(tsv.endsWith('\n')).toBe(true);
  });
});

function makeFile(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    name: 'area_beds.csv',
    title: '構想区域別 病床数(実績/見込量/必要数)',
    rows: 18645,
    source: {
      name: '②構想区域の病床数等（別添４）',
      publisher: '厚生労働省',
      source_file: 'R7/001723349.xlsx',
      source_sha256: 'f7e0e1495c05f3d3fe7456d9e6250cb639d9f70305b391d7d6ba3d230762eca9',
      page_url: 'https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000080850_00014.html',
      acquired_date: '2026-08-04',
      license: '厚生労働省ホームページ利用規約',
    },
    known_issues: [
      {
        id: 'area_beds_2024_actual_duplicated_as_2025',
        summary: '「2024実績」列が「2025実績」列と全セルで完全に同一な値になっている',
        evidence: [
          '2024実績列と2025実績列が339区域×5機能=1695セル全てで一致',
          '構想区域の実績を都道府県コードで集計し都道府県版と突合すると、2585キー中230キーが2024年に集中して不一致になる',
        ],
        action: '値は原典どおり出力している(勝手に補正しない)',
      },
    ],
    ...overrides,
  };
}

function makeDerivedFile(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    name: 'area_geo_join.csv',
    title: '構想区域 × 二次医療圏境界 突合結果',
    rows: 343,
    source: {
      name: '構想区域(area_basic.csv) × 二次医療圏境界(iryoken2_A38-20.geojson) の完全外部結合',
      license: '厚生労働省ホームページ利用規約 / 国土数値情報ダウンロードサービス利用約款',
      inputs: [
        {
          file: 'data/processed/area_basic.csv',
          row_count: 339,
          source_file: 'R7/001723349.xlsx',
          source_sha256: 'f7e0e1495c05f3d3fe7456d9e6250cb639d9f70305b391d7d6ba3d230762eca9',
        },
        {
          file: 'data/processed/iryoken2_A38-20.geojson',
          feature_count: 335,
          source_file: 'ksj/A38-20/A38-20_GML.zip 内 A38-20_GML/A38-20_2.shp',
          source_sha256: '40a0be3688cd129dfd86fef7508e563b1f34259b5b37a521ebf7a01295013b5d',
        },
      ],
    },
    ...overrides,
  };
}

// facility_geo_linkage.csv's meta.json has a differently-shaped source.inputs
// (role instead of row_count/feature_count, no source_file on every element)
// from area_geo_join.csv's — see doc note in bundle.mjs's formatSourceInputLine.
function makeFacilityLinkageFile(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    name: 'facility_geo_linkage.csv',
    title: '構想区域別医療機関(facility_basic.csv) × 国土数値情報P04-20 の座標突合結果',
    rows: 11760,
    source: {
      name: 'facility_basic.csv(構想区域別医療機関一覧) × 国土数値情報P04-20(医療機関データ点)のレコードリンケージ',
      license: '厚生労働省ホームページ利用規約 / 国土数値情報ダウンロードサービス利用約款',
      inputs: [
        {
          file: 'ksj/P04-20/P04-20_GML.zip',
          role: '座標の付与元(国土数値情報 医療機関データ、令和2年度)',
          source_sha256: '24d49390c0760416223784ab2dbb6ad852dbda9a07a5d3b769fba91be91c9732',
        },
        {
          file: 'data/processed/facility_basic.csv',
          role: '突合対象そのもの(コミット済みデータのハッシュ、再現性の監査用)',
          source_sha256: '632270d517977e37abb8af079f76dccdaec6f1dd174d36eea448cd14a1892116',
        },
      ],
    },
    ...overrides,
  };
}

describe('buildBundleReadme', () => {
  const repoUrl = 'https://github.com/youkiti/visualize-regional-medical-care-for-2040';

  it('(a) lists every file name and its row count', () => {
    const readme = buildBundleReadme({ repoUrl, files: [makeFile(), makeDerivedFile()] });
    expect(readme).toContain('area_beds.csv');
    expect(readme).toContain('18645');
    expect(readme).toContain('area_geo_join.csv');
    expect(readme).toContain('343');
  });

  it('(b) includes the original file SHA-256 and the page URL', () => {
    const readme = buildBundleReadme({ repoUrl, files: [makeFile()] });
    expect(readme).toContain('f7e0e1495c05f3d3fe7456d9e6250cb639d9f70305b391d7d6ba3d230762eca9');
    expect(readme).toContain('https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000080850_00014.html');
  });

  it('(c) includes known_issues summary and action text', () => {
    const readme = buildBundleReadme({ repoUrl, files: [makeFile()] });
    expect(readme).toContain('area_beds_2024_actual_duplicated_as_2025');
    expect(readme).toContain('「2024実績」列が「2025実績」列と全セルで完全に同一な値になっている');
    expect(readme).toContain('値は原典どおり出力している(勝手に補正しない)');
  });

  it('(c2) renders each known_issue evidence entry as its own bullet, in array order', () => {
    const readme = buildBundleReadme({ repoUrl, files: [makeFile()] });
    const lines = readme.split('\n');
    const summaryIdx = lines.findIndex((l) => l.includes('area_beds_2024_actual_duplicated_as_2025'));
    expect(summaryIdx).toBeGreaterThanOrEqual(0);
    // The two evidence bullets should appear, in order, before the "対応"
    // line (so a reader sees summary -> evidence -> action, matching the
    // source array order).
    const evidence1Idx = lines.findIndex((l) => l.includes('339区域×5機能=1695セル全てで一致'));
    const evidence2Idx = lines.findIndex((l) => l.includes('2585キー中230キーが2024年に集中して不一致'));
    const actionIdx = lines.findIndex((l) => l.includes('対応: 値は原典どおり出力している'));
    expect(evidence1Idx).toBeGreaterThan(summaryIdx);
    expect(evidence2Idx).toBeGreaterThan(evidence1Idx);
    expect(actionIdx).toBeGreaterThan(evidence2Idx);
    // scope is an object, not a string — it must never be rendered even
    // though it lives right next to evidence in the meta.json shape.
    expect(readme).not.toContain('[object Object]');
  });

  it('(c3) skips non-string evidence entries without crashing or rendering them, but keeps the string ones', () => {
    const file = makeFile({
      known_issues: [
        {
          id: 'mixed_evidence_issue',
          summary: 'テスト用の要約',
          evidence: ['文字列の根拠1', { csv: 'not-a-string-evidence-entry' }, 42, null, '文字列の根拠2'],
          action: 'テスト用の対応',
        },
      ],
    });
    const readme = buildBundleReadme({ repoUrl, files: [file] });
    expect(readme).toContain('文字列の根拠1');
    expect(readme).toContain('文字列の根拠2');
    expect(readme).not.toContain('not-a-string-evidence-entry');
    expect(readme).not.toContain('[object Object]');
  });

  it('(c4) omits evidence entirely when a known_issue has no evidence key', () => {
    const file = makeFile({
      known_issues: [
        {
          id: 'no_evidence_issue',
          summary: 'evidenceキーなしの要約',
          action: 'evidenceキーなしの対応',
        },
      ],
    });
    const readme = buildBundleReadme({ repoUrl, files: [file] });
    expect(readme).toContain('no_evidence_issue');
    expect(readme).toContain('evidenceキーなしの要約');
    expect(readme).toContain('evidenceキーなしの対応');
    expect(readme).not.toContain('根拠:');
  });

  it('(d) documents "no BOM / LF" for the CSVs in this bundle', () => {
    const readme = buildBundleReadme({ repoUrl, files: [makeFile()] });
    expect(readme).toContain('BOMなし');
    expect(readme).toContain('LF');
  });

  it('(e) warns that record_id is not a stable cross-year key', () => {
    const readme = buildBundleReadme({ repoUrl, files: [makeFile()] });
    expect(readme).toContain('record_id');
    expect(readme).toMatch(/年度間.*(比較|使えません)|使えません.*年度間/);
  });

  it('does not embed a generation timestamp or other run-to-run-variable value', () => {
    const readme = buildBundleReadme({ repoUrl, files: [makeFile(), makeDerivedFile()] });
    // No ISO-ish date/time patterns beyond the fixed, caller-supplied
    // acquired_date ("2026-08-04") — i.e. no ranges like YYYY-MM-DDTHH:MM,
    // and no "generated at"/"生成日時"-style wording.
    expect(readme).not.toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/);
    expect(readme).not.toContain('生成日時');
    expect(readme).not.toContain('生成日');
  });

  it('produces byte-identical output for the same input (determinism)', () => {
    const input = { repoUrl, files: [makeFile(), makeDerivedFile()] };
    expect(buildBundleReadme(input)).toBe(buildBundleReadme(input));
  });

  it('groups CSVs that share the same source_file into a single source block', () => {
    const readme = buildBundleReadme({
      repoUrl,
      files: [makeFile(), makeFile({ name: 'area_bed_report_rate.csv', title: '構想区域別 病床機能報告の報告率' })],
    });
    // The source name header should appear exactly once even though two CSVs
    // share it.
    const occurrences = readme.split('### ②構想区域の病床数等（別添４）').length - 1;
    expect(occurrences).toBe(1);
    expect(readme).toContain('area_beds.csv, area_bed_report_rate.csv');
  });

  it('handles a derived CSV with no source_file/source_sha256 without crashing', () => {
    const readme = buildBundleReadme({ repoUrl, files: [makeDerivedFile()] });
    expect(readme).toContain('area_geo_join.csv');
    expect(readme).not.toContain('undefined');
  });

  it('handles a file with no known_issues at all', () => {
    const file = makeFile({ known_issues: undefined });
    const readme = buildBundleReadme({ repoUrl, files: [file] });
    expect(readme).not.toContain('undefined');
  });

  it('(f) lists source.inputs file/row_count/source_file/SHA-256 for a derived CSV (area_geo_join.csv shape)', () => {
    const readme = buildBundleReadme({ repoUrl, files: [makeDerivedFile()] });
    expect(readme).toContain('data/processed/area_basic.csv');
    expect(readme).toContain('339行');
    expect(readme).toContain('R7/001723349.xlsx');
    expect(readme).toContain('f7e0e1495c05f3d3fe7456d9e6250cb639d9f70305b391d7d6ba3d230762eca9');
    expect(readme).toContain('data/processed/iryoken2_A38-20.geojson');
    expect(readme).toContain('335件');
    expect(readme).toContain('ksj/A38-20/A38-20_GML.zip 内 A38-20_GML/A38-20_2.shp');
    expect(readme).toContain('40a0be3688cd129dfd86fef7508e563b1f34259b5b37a521ebf7a01295013b5d');
    // The old catch-all "参照してください"-style fallback must not appear
    // once inputs are available to render directly.
    expect(readme).not.toContain('下記の他の出典ブロックを参照');
  });

  it('(g) lists source.inputs file/role/SHA-256 for a derived CSV with a differently-shaped inputs array (facility_geo_linkage.csv shape)', () => {
    const readme = buildBundleReadme({ repoUrl, files: [makeFacilityLinkageFile()] });
    expect(readme).toContain('facility_geo_linkage.csv');
    expect(readme).toContain('ksj/P04-20/P04-20_GML.zip');
    expect(readme).toContain('座標の付与元(国土数値情報 医療機関データ、令和2年度)');
    expect(readme).toContain('24d49390c0760416223784ab2dbb6ad852dbda9a07a5d3b769fba91be91c9732');
    expect(readme).toContain('data/processed/facility_basic.csv');
    expect(readme).toContain('突合対象そのもの(コミット済みデータのハッシュ、再現性の監査用)');
    expect(readme).not.toContain('undefined');
    expect(readme).not.toContain('[object Object]');
  });

  it('(h) skips a malformed source.inputs entry (missing file) without crashing', () => {
    const file = makeDerivedFile({
      source: {
        name: 'テスト用の派生ソース',
        inputs: [
          { role: 'ファイル名が無い壊れた要素' },
          { file: 'data/processed/area_basic.csv', row_count: 339 },
        ],
      },
    });
    const readme = buildBundleReadme({ repoUrl, files: [file] });
    expect(readme).toContain('data/processed/area_basic.csv');
    expect(readme).toContain('339行');
    expect(readme).not.toContain('ファイル名が無い壊れた要素');
    expect(readme).not.toContain('undefined');
  });

  it('falls back to the "no single source file" note when a derived CSV has no source.inputs at all', () => {
    const file = makeDerivedFile({
      source: {
        name: 'inputsを持たない派生ソース',
        license: 'テスト用ライセンス',
      },
    });
    const readme = buildBundleReadme({ repoUrl, files: [file] });
    expect(readme).toContain('下記の他の出典ブロックを参照');
  });

  it('re-generation instructions cover fetching ksj/A38-20 and building iryoken2_A38-20.geojson, and say it is not committed to the repo', () => {
    const readme = buildBundleReadme({ repoUrl, files: [makeFile(), makeDerivedFile()] });
    expect(readme).toContain('tools/fetch_ksj_geodata.py');
    expect(readme).toContain('tools/build_iryoken2_geojson.py');
    expect(readme).toContain('ksj/A38-20/A38-20_GML.zip');
    expect(readme).toMatch(/Git管理外|含まれていません/);
    // The order matters: build_iryoken2_geojson.py must run before
    // verify_area_join.py, since the latter reads the former's output.
    // Match the actual shell invocation lines (not the prose paragraph
    // above the code block, which mentions both script names on one line).
    const lines = readme.split('\n');
    const buildIdx = lines.findIndex((l) => l.includes('python tools/build_iryoken2_geojson.py'));
    const verifyIdx = lines.findIndex((l) => l.includes('python tools/verify_area_join.py'));
    expect(buildIdx).toBeGreaterThanOrEqual(0);
    expect(verifyIdx).toBeGreaterThan(buildIdx);
  });

  it('re-generation instructions state that 14 of the 15 CSVs (all but area_geo_join.csv) do not require ksj/A38-20', () => {
    const readme = buildBundleReadme({ repoUrl, files: [makeFile(), makeDerivedFile()] });
    expect(readme).toContain('area_geo_join.csv');
    expect(readme).toMatch(/14本/);
  });
});
