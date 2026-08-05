# -*- coding: utf-8 -*-
"""厚労省 令和6年度版一括DL zip(001723128.zip)を取得し、zip内の別添４・別添５
(pdf/xlsx計5ファイル)のSHA-256を `SHA256SUMS` の `R6/...` 記録値と照合する。

`R6/` 配下のxlsx/pdf実体は既にコミット済みだが、その入手元(取得URL)を
裏付けるための再現スクリプト。`tools/fetch_ksj_geodata.py` と同じ流儀
(取得手順そのものをスクリプトとしてリポジトリに残し、再検証できるように
する)。

zipは一時ディレクトリへダウンロードし、リポジトリ内へは絶対に置かない
(R6のxlsx/pdf実体は既にコミット済みで、zip自体は4.7MB程度の重複データの
ため)。

処理内容:
  1. zipを取得する(既定はネットワークからダウンロード。`--zip` で取得済み
     ファイルを渡せばネットワーク無しで再検証できる)
  2. zip自身のSHA-256を計算して表示する
  3. zip内の各エントリ名を復元する。エントリの言語エンコーディングフラグ
     (UTF-8フラグ、ZIP仕様の第3章4.4.4)が立っていなければ、zipfileは既定で
     cp437としてデコードしている(実際のバイト列はcp932(Shift_JIS)のため
     文字化けする)。`name.encode("cp437").decode("cp932")` で日本語へ戻す
  4. 各エントリのSHA-256を計算し、`tools.lib.provenance.recorded_hash(
     f"R6/{basename}")` の記録値と照合する。1件でも不一致、または
     `SHA256SUMS` に記録の無いエントリがあれば `SystemExit` で中断する
     (静かに握りつぶさない)
  5. 照合できた件数を標準出力へ出す

必要環境: Python 3.11+ (標準ライブラリのみ)

使い方:
    python tools/verify_r6_bundle.py                 # ネットワークからダウンロードして検証
    python tools/verify_r6_bundle.py --zip <path>     # 取得済みzipで検証(ネットワーク不要)
"""
import argparse
import hashlib
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lib.provenance import recorded_hash

# 令和6年度版一括DL zip。R6/ 配下の別添４・別添５(pdf/xlsx計5ファイル)を
# 同梱する。xlsx単体の直リンクではない(doc/DATA_SOURCES.mdの「R6/」節参照)。
ZIP_URL = "https://www.mhlw.go.jp/content/10800000/001723128.zip"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str, dest: Path) -> None:
    print(f"[..] ダウンロード中: {url}")
    urllib.request.urlretrieve(url, dest)
    print(f"[ok] 保存: {dest} ({dest.stat().st_size:,} bytes)")


def verify(zip_path: Path) -> int:
    """zip自身とzip内エントリのSHA-256を検証する。照合できた件数を返す。"""
    zip_bytes = zip_path.read_bytes()
    zip_sha256 = sha256_bytes(zip_bytes)
    print(f"[ok] zip自身のSHA-256: {zip_sha256} ({len(zip_bytes):,} bytes)")

    verified = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            # UTF-8フラグ(0x800)が立っていればzipfileは既にUTF-8として正しく
            # デコード済み。立っていなければ既定のcp437デコードのままなので、
            # 実際のバイト列(cp932/Shift_JIS)へcp437->cp932で復元する
            # (そのままだと日本語ファイル名が文字化けする)。
            if info.flag_bits & 0x800:
                name = info.filename
            else:
                name = info.filename.encode("cp437").decode("cp932")
            basename = name.split("/")[-1]

            # SHA256SUMSに記録の無いエントリがあれば recorded_hash() が
            # SystemExitで中断する(静かに握りつぶさない、このリポジトリの流儀)。
            recorded = recorded_hash(f"R6/{basename}")
            actual = sha256_bytes(zf.read(info))
            if actual != recorded:
                raise SystemExit(
                    f"SHA-256不一致: R6/{basename}\n"
                    f"  SHA256SUMS記録値: {recorded}\n"
                    f"  zip内実測値     : {actual}"
                )
            print(f"[ok] 一致: R6/{basename} = {actual[:16]}...")
            verified += 1

    print(f"[ok] {verified}件のエントリがSHA256SUMSの記録値と一致しました")
    return verified


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--zip",
        type=Path,
        default=None,
        help="取得済みのzipファイルパス(省略時はネットワークからダウンロード)",
    )
    args = ap.parse_args()

    if args.zip is not None:
        verify(args.zip)
        return

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "001723128.zip"
        download(ZIP_URL, zip_path)
        verify(zip_path)


if __name__ == "__main__":
    main()
