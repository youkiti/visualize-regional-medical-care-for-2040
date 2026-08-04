// ダウンロード実行の唯一のDOM依存部分。lib/downloads.ts が組み立てた
// { filename, text } を実際にブラウザからダウンロードさせる副作用関数。
// 副作用のみのためテストは書かない（M6ブリーフの指示どおり）。

/**
 * text を filename としてブラウザにダウンロードさせる。
 * Blob → createObjectURL → 一時的な <a download> をクリック、の順で行う。
 * revokeObjectURL は同期で呼ばず setTimeout(..., 0) で次tickに回す
 * （同期revokeはSafariでダウンロードが失敗することがあるため）。
 */
export function triggerDownload(filename: string, text: string, mimeType: string = 'text/csv;charset=utf-8'): void {
  const blob = new Blob([text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 0);
}
