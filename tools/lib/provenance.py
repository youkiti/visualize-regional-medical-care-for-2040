# -*- coding: utf-8 -*-
"""生データの完全性検証と、由来メタデータ付きCSV出力の共通処理。

処理内容:
  1. `sha256()`: ファイルのSHA-256ハッシュを計算
  2. `recorded_hash()`: ルートの `SHA256SUMS` から指定パスの記録済みハッシュを取得
  3. `verify_source()`: 実測ハッシュと記録済みハッシュを照合し、不一致なら中断
  4. `write_csv_with_meta()`: tidy CSV と由来メタデータ(`<csv名>.meta.json`)を
     同時出力(UTF-8・BOMなし・改行LF固定)

`sha256()`/`recorded_hash()` はもともと `tools/build_iryoken2_geojson.py` に
実装されていたものをここへ集約し、各パーサから共通利用する。
"""
import csv
import hashlib
import json
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
SHA256SUMS = REPO_ROOT / "SHA256SUMS"


def sha256(path: Path) -> str:
    """ファイルのSHA-256ハッシュ(16進文字列)を計算する。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def recorded_hash(path_in_repo: str) -> str:
    """`SHA256SUMS` から `path_in_repo` に対応する記録済みハッシュを取得する。

    各行を `hash, path = line.split(maxsplit=1)` で分解し、`path` の先頭の
    `*`(`sha256sum` のバイナリモード表記)を除いた文字列が `path_in_repo`
    と完全一致した行のみを対象とする(`endswith` による部分一致では、将来
    パスの末尾が衝突する行(例 `R7/x.xlsx` と `data/R7/x.xlsx`)で誤った
    ハッシュを返しかねないため)。

    見つからない場合は SystemExit で中断する。
    """
    for line in SHA256SUMS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        digest, path = parts
        path = path.strip()
        if path.startswith("*"):
            path = path[1:]
        if path == path_in_repo:
            return digest
    raise SystemExit(f"SHA256SUMS に {path_in_repo} の記録がありません")


def verify_source(path_in_repo: str) -> str:
    """`path_in_repo`(リポジトリルートからの相対パス)の実測SHA-256を
    `SHA256SUMS` の記録値と照合する。

    一致すれば記録済みハッシュ(=実測値と同じ)を返す。不一致の場合は
    期待値・実測値の両方を表示して SystemExit で中断する。
    """
    expected = recorded_hash(path_in_repo)
    src = REPO_ROOT / path_in_repo
    actual = sha256(src)
    if actual != expected:
        raise SystemExit(
            f"SHA-256不一致: {src}\n  期待値: {expected}\n  実測値: {actual}"
        )
    return expected


def write_csv_with_meta(
    csv_path: Path,
    header: Sequence[str],
    rows,
    *,
    title: str,
    source: dict,
    processing: dict,
    fields: dict,
    known_issues=None,
):
    """tidy CSVと由来メタデータ(`<csv_path>.meta.json`)を同時に書き出す。

    - CSV: UTF-8・BOMなし・改行はLF固定(`csv.writer` の `lineterminator="\\n"`)
    - meta.json: UTF-8・LF・`ensure_ascii=False`・インデント2。
      `title` / `source` / `processing` / `fields` / `known_issues`(省略時は
      キー自体を出力しない) / `row_count` を持つ。

    `known_issues` は原典データ自体が抱える既知の品質問題(値は勝手に
    修正せず、機械可読な形で記録するためのもの)。省略時(`None`)は
    meta.json に `known_issues` キーを一切出力しない(既存出力とのバイト
    一致を壊さないため)。

    戻り値: (csv_path, meta_path) の Path タプル。
    """
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)

    meta = {
        "title": title,
        "source": source,
        "processing": processing,
        "fields": fields,
    }
    if known_issues is not None:
        meta["known_issues"] = known_issues
    meta["row_count"] = len(rows)
    meta_path = Path(str(csv_path) + ".meta.json")
    with open(meta_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return csv_path, meta_path
