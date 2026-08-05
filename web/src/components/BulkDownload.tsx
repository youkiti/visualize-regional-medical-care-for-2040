import PanelSection from './PanelSection';
import { bulkDownloadUrl, formatBytes } from '../lib/downloadAssets';
import { formatInteger } from '../lib/metrics';
import type { DownloadManifest } from '../types';

interface BulkDownloadProps {
  manifest: DownloadManifest;
}

/**
 * SHA-256の全64桁をそのまま出すと1行に収まらず折り返しが汚くなるため、
 * 先頭16桁＋`…`だけ表示する。全桁はtitle属性に入れる（ホバーで確認できる）。
 * コピーしやすいよう<code>で囲む。
 */
function ShaCode({ sha256 }: { sha256: string }) {
  return (
    <code className="download-sha" title={sha256}>
      {sha256.slice(0, 16)}…
    </code>
  );
}

/**
 * 加工済みデータ（data/processed/ の正本）の一括ダウンロード導線。
 * download_manifest.json（バンドル済み。ZIP本体は取得しなくても内容を
 * 説明できる）を表示するだけで、ZIP/GeoJSONの取得・解凍等は行わない
 * （リンク先はブラウザの通常のダウンロードに任せる）。
 */
export default function BulkDownload({ manifest }: BulkDownloadProps) {
  const { bundle, boundaries, members } = manifest;

  // M14: 外側の<section aria-label>とh3見出しをPanelSectionへ置き換え、
  // 章として折りたためるようにした（既定は閉じる）。中身は従来どおり
  // <div className="bulk-download">で包み、既存のスタイルをそのまま維持する。
  return (
    <PanelSection title="加工済みデータの一括ダウンロード" defaultOpen={false}>
      <div className="bulk-download">
        <ul className="bulk-download-list">
          <li>
            <a href={bulkDownloadUrl(bundle.file)} download>
              {bundle.file}
            </a>
            <span className="bulk-download-meta">
              {formatBytes(bundle.bytes)}／CSV {bundle.csv_count}本＋各.meta.json＋README.md＋MANIFEST.tsv（計
              {bundle.entry_count}件）
            </span>
            <span className="bulk-download-sha">
              SHA-256: <ShaCode sha256={bundle.sha256} />
            </span>
          </li>
          <li>
            <a href={bulkDownloadUrl(boundaries.file)} download>
              {boundaries.file}
            </a>
            <span className="bulk-download-meta">{formatBytes(boundaries.bytes)}／構想区域境界GeoJSON（339区域）</span>
            <span className="bulk-download-sha">
              SHA-256: <ShaCode sha256={boundaries.sha256} />
            </span>
          </li>
        </ul>

        <details className="bulk-download-members">
          <summary>収録CSV一覧（{members.length}本）</summary>
          <div className="bulk-download-table-wrap">
            <table className="bulk-download-table">
              <thead>
                <tr>
                  <th>ファイル</th>
                  <th>内容</th>
                  <th>行数</th>
                  <th>バイト数</th>
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.name}>
                    <td>{member.name}</td>
                    <td>{member.title}</td>
                    <td>{formatInteger(member.rows)}</td>
                    <td>{formatInteger(member.bytes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>

        <p className="bulk-download-note">
          注記: ZIP内のCSVは <code>data/processed/</code> の正本そのまま（UTF-8 BOMなし・改行LF）です。画面のボタンから出るCSV（表示中のデータ／区域の指標／医療機関一覧）はExcelで開く用途のため
          BOM付き・CRLF で別物です。
        </p>
      </div>
    </PanelSection>
  );
}
