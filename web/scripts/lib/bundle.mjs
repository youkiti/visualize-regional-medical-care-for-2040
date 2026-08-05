// data/processed/ の加工済みCSV15本を1本のZIPにまとめて配布するための、
// ZIP本文（MANIFEST.tsv・README.md）を組み立てる純関数群。I/Oはしない
// （実際にファイルを読み書き・ZIP化するのは web/scripts/sync-data.mjs）。
//
// Kept dependency-free and side-effect-free so it can be unit-tested with
// vitest (web/src/lib/bundle.test.ts) and reused from web/scripts/sync-data.mjs.

/** ZIP内のルートフォルダ名。全エントリはこの下に置く（展開すると1フォルダにまとまる）。 */
export const BUNDLE_ROOT = 'chiiki-iryo-koso_processed-csv_R7';

/** web/public/downloads/ に書き出すZIPファイル名。 */
export const BUNDLE_FILE_NAME = 'chiiki-iryo-koso_processed-csv_R7.zip';

// data/processed/ にある加工済みCSV15本を明示的に列挙する（ディレクトリを走査
// して拾うのではなく、この配列を正とする）。sync-data.mjs はこの配列と実際の
// data/processed/*.csv の一覧を突合し、食い違ったらビルドを落とす
// （新しいCSVが増えたときに黙って配布物から漏れる／意図しないファイルが
// 混ざるのを防ぐため）。並びはファイル名の辞書順。
export const BUNDLE_CSV_FILES = [
  'area_basic.csv',
  'area_bed_report_rate.csv',
  'area_beds.csv',
  'area_geo_join.csv',
  'demand_forecast.csv',
  'demand_population.csv',
  'facility_basic.csv',
  'facility_functions.csv',
  'facility_geo_linkage.csv',
  'facility_observations.csv',
  'patient_flow.csv',
  'patient_flow_total.csv',
  'prefecture_basic.csv',
  'prefecture_bed_report_rate.csv',
  'prefecture_beds.csv',
];

/**
 * @typedef {{ name: string, bytes: number, sha256: string, rows: number | '' }} ManifestMember
 */

/**
 * MANIFEST.tsv（タブ区切り、1行目がヘッダー）を組み立てる。
 * `rows` は各CSVの行数（meta.jsonのrow_count）。meta.json自身の行は行数の
 * 概念を持たないため空文字にする（呼び出し側がその意図で `''` を渡す）。
 * 改行はLF固定。
 *
 * @param {ManifestMember[]} members
 * @returns {string}
 */
export function buildManifestTsv(members) {
  const lines = ['file\tbytes\tsha256\trows'];
  for (const member of members) {
    const rows = member.rows === '' || member.rows === null || member.rows === undefined ? '' : String(member.rows);
    lines.push(`${member.name}\t${member.bytes}\t${member.sha256}\t${rows}`);
  }
  return `${lines.join('\n')}\n`;
}

/**
 * @typedef {{
 *   file?: string,
 *   source_file?: string,
 *   source_sha256?: string,
 *   row_count?: number,
 *   feature_count?: number,
 *   role?: string,
 * }} BundleSourceInput
 */

/**
 * @typedef {{
 *   name: string,
 *   title: string,
 *   rows: number,
 *   source: {
 *     name: string,
 *     publisher?: string,
 *     source_file?: string,
 *     source_sha256?: string,
 *     page_url?: string,
 *     acquired_date?: string,
 *     license?: string,
 *     inputs?: BundleSourceInput[],
 *   },
 *   known_issues?: Array<{ id: string, summary: string, action: string, evidence?: unknown[] }>,
 * }} BundleCsvInfo
 */

/**
 * 原典（source_fileがある場合はそれ、無い場合はsource.name）でCSVをグルーピング
 * する。同じ原典を共有する複数CSVは1つの出典ブロックにまとめる。出現順を保つ。
 *
 * @param {BundleCsvInfo[]} files
 * @returns {Array<{ source: BundleCsvInfo['source'], members: string[] }>}
 */
function groupBySource(files) {
  /** @type {Map<string, { source: BundleCsvInfo['source'], members: string[] }>} */
  const groups = new Map();
  for (const file of files) {
    const key = file.source.source_file ?? `derived::${file.source.name}`;
    let group = groups.get(key);
    if (!group) {
      group = { source: file.source, members: [] };
      groups.set(key, group);
    }
    group.members.push(file.name);
  }
  return [...groups.values()];
}

/**
 * 派生CSVの `source.inputs` 1要素を箇条書きの1行に整形する。
 * `area_geo_join.csv` と `facility_geo_linkage.csv` とで要素が持つキーの
 * 組み合わせが異なる（前者は `row_count`/`feature_count` あり・`role` 無し、
 * 後者は逆）ため、キーの有無で分岐せず、存在するものだけ順に足していく。
 *
 * @param {BundleSourceInput} input
 * @returns {string}
 */
function formatSourceInputLine(input) {
  const details = [];
  if (typeof input.row_count === 'number') details.push(`${input.row_count}行`);
  if (typeof input.feature_count === 'number') details.push(`${input.feature_count}件`);
  if (input.role) details.push(input.role);
  if (input.source_file) details.push(`原典: ${input.source_file}`);
  if (input.source_sha256) details.push(`SHA-256: ${input.source_sha256}`);
  const suffix = details.length > 0 ? `（${details.join('、')}）` : '';
  return `  - ${input.file}${suffix}`;
}

/**
 * README.md（ZIPのルート直下に同梱するMarkdown）を組み立てる。日時のような
 * 可変値はこの関数の中で作らない（再生成のたびに差分が出るのを避けるため。
 * 呼び出し側が必要な値を全て引数で渡すこと）。
 *
 * @param {{ repoUrl: string, files: BundleCsvInfo[] }} input
 * @returns {string}
 */
export function buildBundleReadme(input) {
  const { repoUrl, files } = input;
  const lines = [];

  lines.push('# 地域医療構想データセット（加工済みCSV・令和7年度公表分）');
  lines.push('');
  lines.push(
    '厚生労働省「2040年に向けた地域医療構想」の公開データ（病床機能報告・医療需要推計等）を、' +
      '出典・完全性を保った形で機械可読な tidy（long形式）CSV へ整形したものです。' +
      '厚生労働省・国土交通省・三重県が公表する原典データそのものではなく、下記リポジトリによる' +
      '**非公式の加工物**です。値そのものは補正せず原典どおり収録しています（原典側の欠陥は' +
      '「原典側の既知の問題」節にまとめて記録し、値では補正していません）。'
  );
  lines.push('');
  lines.push(`- リポジトリ: ${repoUrl}`);
  lines.push('- このZIPは上記リポジトリが公開する可視化サイトのビルド成果物として配布しています。');
  lines.push('');

  lines.push('## 収録ファイル');
  lines.push('');
  lines.push('| ファイル | 内容 | 行数 |');
  lines.push('|---|---|---|');
  for (const file of files) {
    lines.push(`| ${file.name} | ${file.title} | ${file.rows} |`);
  }
  lines.push('');
  lines.push(
    '各CSVには同名の `<ファイル名>.meta.json` を同梱しています。列の定義・由来・処理手順・' +
      '既知の問題を機械可読な形で記録したもので、このREADMEの内容の一次情報です。'
  );
  lines.push('');

  lines.push('## 出典');
  lines.push('');
  const groups = groupBySource(files);
  for (const group of groups) {
    const { source, members } = group;
    lines.push(`### ${source.name}`);
    lines.push('');
    if (source.publisher) lines.push(`- 公表元: ${source.publisher}`);
    if (source.source_file && source.source_sha256) {
      lines.push(`- 原典ファイル: ${source.source_file}（SHA-256: ${source.source_sha256}）`);
    } else if (Array.isArray(source.inputs) && source.inputs.length > 0) {
      lines.push('- 原典ファイル: 単一のファイルではなく、以下の入力を突合した派生データです。');
      for (const input of source.inputs) {
        if (!input || typeof input !== 'object' || !input.file) continue;
        lines.push(formatSourceInputLine(input));
      }
    } else {
      lines.push('- 原典ファイル: 単一のファイルではなく、他の原典データ同士を突合した派生データです（下記の他の出典ブロックを参照）。');
    }
    if (source.page_url) lines.push(`- 掲載ページ: ${source.page_url}`);
    if (source.acquired_date) lines.push(`- 取得日: ${source.acquired_date}`);
    if (source.license) lines.push(`- 利用規約: ${source.license}`);
    lines.push(`- このZIPでの収録: ${members.join(', ')}`);
    lines.push('');
  }

  const knownIssues = files.flatMap((file) => file.known_issues ?? []);
  lines.push('## 原典側の既知の問題');
  lines.push('');
  if (knownIssues.length === 0) {
    lines.push('（現時点で登録されている既知の問題はありません）');
  } else {
    lines.push(
      '厚生労働省の公表物そのものが持つ欠陥（値の誤り・複製・未算出・公表物どうしの矛盾）です。' +
        '値は補正せず原典どおり収録しています。'
    );
    lines.push('');
    for (const issue of knownIssues) {
      lines.push(`- **[${issue.id}]** ${issue.summary}`);
      if (Array.isArray(issue.evidence)) {
        for (const item of issue.evidence) {
          if (typeof item !== 'string') continue;
          lines.push(`  - 根拠: ${item}`);
        }
      }
      lines.push(`  - 対応: ${issue.action}`);
    }
  }
  lines.push('');

  lines.push('## CSVの仕様');
  lines.push('');
  lines.push('- 文字コード: UTF-8（**BOMなし**）');
  lines.push('- 改行コード: **LF**（`\\n`）');
  lines.push('- 形式: tidy（long形式）。1行が1つの事実（区域×指標×年など）を表します');
  lines.push('- このZIP内のCSVは `data/processed/` の正本のバイト列をそのまま収録しています（MANIFEST.tsvのSHA-256で検証できます）');
  lines.push('');
  lines.push(
    '※本サイト画面の「表示中のデータをダウンロード」から出るCSV（1指標・1区域単位）は、' +
      'Excelで開く用途のため UTF-8 **BOM付き・CRLF** 改行です。このZIP内のCSV（BOMなし・LF）とは' +
      '文字コード・改行コードが異なる別物なので混同しないでください。'
  );
  lines.push('');

  lines.push('## 医療機関データの record_id について');
  lines.push('');
  lines.push(
    'facility_basic.csv・facility_observations.csv・facility_functions.csv の `record_id` は、' +
      '原典（001723127.xlsx）の行位置（病床数降順）に由来する**暫定的なID**です。公表年度が' +
      '変われば同じIDが別の医療機関を指す可能性があるため、**年度間の比較キーには使えません**。'
  );
  lines.push('');

  lines.push('## MANIFEST.tsv と完全性の検証');
  lines.push('');
  lines.push(
    'MANIFEST.tsv はタブ区切りで、1行目がヘッダー行（`file`, `bytes`, `sha256`, `rows`）です。' +
      '各ファイルのSHA-256を計算し、この一覧の値と一致することを確認すれば、改変されていないことを検証できます。'
  );
  lines.push('');
  lines.push('PowerShell:');
  lines.push('');
  lines.push('```powershell');
  lines.push('Get-FileHash -Algorithm SHA256 area_beds.csv');
  lines.push('```');
  lines.push('');
  lines.push('Git Bash / Linux:');
  lines.push('');
  lines.push('```bash');
  lines.push('sha256sum area_beds.csv');
  lines.push('```');
  lines.push('');

  lines.push('## 再生成する');
  lines.push('');
  lines.push(
    'このZIPは以下のリポジトリの `data/processed/` を正本として、可視化サイトのビルド時' +
      '（`npm run sync-data`）に自動生成しています。原データから同じ内容を手元で再現するには:'
  );
  lines.push('');
  lines.push(
    '国土数値情報「医療圏データ」`ksj/A38-20/A38-20_GML.zip`（約1.13GB）は容量の都合で' +
      'リポジトリに含まれていません（Git管理外）。このZIP内の15本のCSVのうち' +
      '**`area_geo_join.csv` を除く14本**はこのファイルなしで再現できます。'
  );
  lines.push('');

  lines.push('### 1. `area_geo_join.csv` を除く14本');
  lines.push('');
  lines.push('```bash');
  lines.push(`git clone ${repoUrl}.git`);
  lines.push('cd visualize-regional-medical-care-for-2040');
  lines.push('pip install -r requirements.txt');
  lines.push('PYTHONIOENCODING=utf-8 python tools/parse_prefecture_beds.py');
  lines.push('PYTHONIOENCODING=utf-8 python tools/parse_area_beds.py');
  lines.push('PYTHONIOENCODING=utf-8 python tools/parse_demand_forecast.py');
  lines.push('PYTHONIOENCODING=utf-8 python tools/parse_facility_beds.py');
  lines.push('PYTHONIOENCODING=utf-8 python tools/parse_patient_flow.py');
  lines.push('PYTHONIOENCODING=utf-8 python tools/build_mie_area_municipalities.py');
  lines.push('PYTHONIOENCODING=utf-8 python tools/build_facility_geo_linkage.py');
  lines.push('```');
  lines.push('');

  lines.push('### 2. `area_geo_join.csv`（追加で `ksj/A38-20` の取得と Node.js が必要）');
  lines.push('');
  lines.push(
    '`area_geo_join.csv` は `tools/verify_area_join.py` が生成しますが、その前提として' +
      '`data/processed/iryoken2_A38-20.geojson`（`tools/build_iryoken2_geojson.py` が' +
      '`ksj/A38-20/A38-20_GML.zip` から生成）が必要です。この生成には Node.js が要ります' +
      '（`mapshaper` を `npx` 経由で取得します）。'
  );
  lines.push('');
  lines.push('```bash');
  lines.push('PYTHONIOENCODING=utf-8 python tools/fetch_ksj_geodata.py    # ksj/A38-20/A38-20_GML.zip を取得（約1.13GB）');
  lines.push('PYTHONIOENCODING=utf-8 python tools/build_iryoken2_geojson.py    # → data/processed/iryoken2_A38-20.geojson');
  lines.push('PYTHONIOENCODING=utf-8 python tools/verify_area_join.py    # → area_geo_join.csv');
  lines.push('```');
  lines.push('');

  return lines.join('\n');
}
