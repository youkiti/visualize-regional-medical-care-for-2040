// web/public/downloads/ 配下（加工済みCSV一括ダウンロードZIP・区域境界GeoJSON単体
// コピー）のURL組み立てとサイズ表記の整形。facilityShard.ts の facilityShardUrl()
// と同じ役割・同じ作法をこちらにも適用している。

/**
 * web/public/downloads/<fileName> のURL。import.meta.env.BASE_URL を起点に
 * 組み立てる（vite.config.ts が base: './' を設定しているため）。
 *
 * なぜ絶対パス（"/downloads/..."）ではだめか: このサイトはGitHub Pagesの
 * サブパス（例: https://<user>.github.io/<repo>/）にデプロイされる。絶対パスは
 * オリジン直下を指してしまい、サブパス配下の実際の配置場所を素通りして404に
 * なる。BASE_URLはビルド時にサブパスへ解決されるため、これを起点にすれば
 * ルート直下・サブパスどちらの配置でも正しいURLになる
 * （facilityShard.ts facilityShardUrl() と同じ理由）。
 */
export function bulkDownloadUrl(fileName: string): string {
  return `${import.meta.env.BASE_URL}downloads/${fileName}`;
}

/**
 * バイト数をMB表記（小数第1位まで）に整形する。1024*1024で除算する
 * （OSのファイルサイズ表示やこのリポジトリのCSVサイズ感覚に合わせ、
 * 1000*1000ではなく2進接頭辞の値を使う。表記自体は慣例どおり「MB」とする）。
 */
export function formatBytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
