// CSVシリアライザ（DOM非依存の純関数）。lib/downloads.ts から使う。
//
// 正本 data/processed/*.csv は BOMなし・LF固定（sha256の再現性テストが
// バイト一致を要求するため。CLAUDE.md参照）。一方このファイルが組み立てる
// CSVは「ユーザーがブラウザからダウンロードしてExcelで開く」用途であり、
// 正本とは目的が異なるため意図的に既定値を変えている: UTF-8 BOM付き・
// CRLF改行（BOM無し・LFのままだとExcelで文字化け/1列にまとまるおそれがある）。

export type CsvValue = string | number | null;

/**
 * RFC4180に沿ったCSVフィールドのエスケープ。
 * `"`・`,`・CR・LF のいずれかを含む場合のみ `"` で囲み、内部の `"` は `""` にする。
 */
export function escapeCsvField(value: string): string {
  if (/["\r\n,]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

/**
 * CsvValue を1フィールド分のCSV文字列へ変換する。
 * - `null` → 空文字（欠測。`0` と必ず区別する）
 * - `number` → `String(v)`（桁区切りは入れない。画面表示用の `formatInteger()` は使わない）
 * - `string` → `escapeCsvField` を通す
 */
export function formatCsvValue(value: CsvValue): string {
  if (value === null) return '';
  if (typeof value === 'number') return String(value);
  return escapeCsvField(value);
}

export interface ToCsvOptions {
  /** 先頭にUTF-8 BOM（U+FEFF）を付けるか。既定 `true`（Excelで開く前提）。 */
  bom?: boolean;
  /** 改行コード。既定 `'\r\n'`（Excelで開く前提）。 */
  eol?: string;
  /**
   * ヘッダー行の前に出す注記行（由来情報等）。各行の先頭に `# ` を前置して出力する。
   * 行内のCR・LFは半角スペースへ潰す（原典metadataのcaveatが改行を含みうるため）。
   */
  preamble?: string[];
}

/**
 * ヘッダー行・データ行からCSVテキストを組み立てる。
 * 各行の長さが `header.length` と異なる場合は throw する
 * （このリポジトリの方針: 静かに壊れるより落とす）。
 */
export function toCsvText(header: string[], rows: CsvValue[][], options: ToCsvOptions = {}): string {
  const { bom = true, eol = '\r\n', preamble = [] } = options;

  rows.forEach((row, i) => {
    if (row.length !== header.length) {
      throw new Error(
        `toCsvText: row ${i} has ${row.length} field(s), expected ${header.length} (header: ${header.join(', ')})`
      );
    }
    // tsconfigにnoUncheckedIndexedAccessが無いため、Record/配列への添字アクセス
    // （例: area.demand[category][yearKey]）が実行時にundefinedを返す経路が
    // 型チェックを素通りしうる。formatCsvValueはundefinedをescapeCsvFieldへ渡して
    // しまい文字列"undefined"を出力するため、ここで検出して落とす
    // （静かに壊れたCSVを配るより例外を優先する、このリポジトリの方針）。
    row.forEach((field, j) => {
      if (field === undefined) {
        throw new Error(`toCsvText: row ${i} field "${header[j]}" (column ${j}) is undefined`);
      }
    });
  });

  const lines: string[] = [];
  for (const note of preamble) {
    lines.push(`# ${note.replace(/\r\n|\r|\n/g, ' ')}`);
  }
  lines.push(header.map(escapeCsvField).join(','));
  for (const row of rows) {
    lines.push(row.map(formatCsvValue).join(','));
  }

  // 正本 data/processed/*.csv は csv.writer(lineterminator='\n') で最終行にも
  // 改行が付く。ここも末尾にeolを1つ足して揃える。
  const text = lines.join(eol) + eol;
  return bom ? `\uFEFF${text}` : text;
}
