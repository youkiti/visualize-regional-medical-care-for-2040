# -*- coding: utf-8 -*-
"""国土数値情報 A38-20（医療圏）から二次医療圏境界の軽量GeoJSONを生成する。

処理内容:
  1. `ksj/A38-20/A38-20_GML.zip` の SHA-256 を `SHA256SUMS` と照合（改変検知）
  2. zip から二次医療圏シェープファイル（A38-20_2.*）を一時ディレクトリへ展開
  3. mapshaper（npx 経由）で以下を実行
     - 二次医療圏コード（A38b_003）でディゾルブ（116,365パート → 335医療圏）
     - 面積1km2未満の離島リングを除去
     - Visvalingam加重アルゴリズムで簡略化（既定 2%、keep-shapes）
     - -clean でスリバー除去・位相修復
     - 座標を0.0001度（約11m）へ丸めて GeoJSON 出力
  4. 由来メタデータ（出典・元ファイルハッシュ・加工手順）をトップレベル
     `metadata` メンバーとして埋め込み、`data/processed/iryoken2_A38-20.geojson`
     へ書き出す

必要環境: Python 3.11+, Node.js（npx で mapshaper を取得）

使い方:
    python tools/build_iryoken2_geojson.py [--pct 2]
"""
import argparse
import datetime
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lib.provenance import REPO_ROOT, recorded_hash, sha256

SRC_ZIP = REPO_ROOT / "ksj" / "A38-20" / "A38-20_GML.zip"
OUT_PATH = REPO_ROOT / "data" / "processed" / "iryoken2_A38-20.geojson"

SOURCE_PAGE = "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A38-v2_0.html"

COPY_FIELDS = ",".join(f"A38b_{i:03d}" for i in range(1, 12) if i != 3)

FIELD_DESCRIPTIONS = {
    "A38b_001": "構成市区町村の行政区域コード（カンマ区切り）",
    "A38b_002": "構成市区町村名（カンマ区切り）",
    "A38b_003": "二次医療圏コード（ゼロ埋め4桁文字列。例 '0101'）",
    "A38b_004": "二次医療圏名",
    "A38b_005": "面積・医療計画掲載値（m2）",
    "A38b_006": "面積・国土地理院「全国都道府県市区町村別面積調」合計値（m2）",
    "A38b_007": "人口・医療計画掲載値（人）",
    "A38b_008": "総人口・住民基本台帳（人）",
    "A38b_009": "人口15才未満・住民基本台帳（人）",
    "A38b_010": "人口15才以上65才未満・住民基本台帳（人）",
    "A38b_011": "人口65才以上・住民基本台帳（人）",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pct", type=float, default=2.0, help="簡略化率（%%、既定2）")
    args = ap.parse_args()

    # 1. 生データの完全性検証
    expected = recorded_hash("ksj/A38-20/A38-20_GML.zip")
    actual = sha256(SRC_ZIP)
    if actual != expected:
        raise SystemExit(
            f"SHA-256不一致: {SRC_ZIP}\n  期待値: {expected}\n  実測値: {actual}"
        )
    print(f"[ok] 生データ検証: {SRC_ZIP.name} = {actual[:16]}...")

    # Windowsではnpxはnpx.cmdのためwhichでフルパス解決する
    npx = shutil.which("npx")
    if npx is None:
        raise SystemExit("npx が見つかりません（Node.js をインストールしてください）")

    mapshaper_ver = subprocess.run(
        [npx, "-y", "mapshaper", "-v"],
        capture_output=True, text=True, check=True, shell=False,
    ).stdout.strip()

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # 2. 二次医療圏シェープファイルの展開
        with zipfile.ZipFile(SRC_ZIP) as z:
            for name in z.namelist():
                base = name.replace("\\", "/").rsplit("/", 1)[-1]
                if base.startswith("A38-20_2.") and base.rsplit(".", 1)[-1] in (
                    "shp", "shx", "dbf", "prj"
                ):
                    (tmp / base).write_bytes(z.read(name))
        print("[ok] A38-20_2.* を展開")

        # 3. mapshaper 実行
        raw_out = tmp / "iryoken2.geojson"
        cmd = [
            npx, "-y", "mapshaper", str(tmp / "A38-20_2.shp"), "encoding=cp932",
            "-dissolve", "fields=A38b_003", f"copy-fields={COPY_FIELDS}",
            "-filter-islands", "min-area=1km2",
            "-simplify", "visvalingam", "weighted", f"{args.pct}%", "keep-shapes",
            "-clean",
            "-o", "format=geojson", "precision=0.0001", str(raw_out),
        ]
        print("[run] " + " ".join(cmd))
        subprocess.run(cmd, check=True, shell=False)

        gj = json.loads(raw_out.read_text(encoding="utf-8"))

    # 4. 由来メタデータの埋め込み（GeoJSONの foreign member として許容される）
    features = gj["features"]
    codes = [f["properties"].get("A38b_003") for f in features]
    assert len(codes) == len(set(codes)), "二次医療圏コードが重複しています"

    metadata = {
        "title": "二次医療圏境界（簡略化版）",
        "source": {
            "name": "国土数値情報 医療圏データ 第2.0版（A38-20）二次医療圏",
            "publisher": "国土交通省 国土数値情報ダウンロードサービス",
            "url": SOURCE_PAGE,
            "data_year": "令和2年度（2020年度）",
            "source_file": "ksj/A38-20/A38-20_GML.zip 内 A38-20_GML/A38-20_2.shp",
            "source_sha256": expected,
            "license": "国土数値情報ダウンロードサービス利用約款（オープンデータ）",
        },
        "processing": {
            "script": "tools/build_iryoken2_geojson.py",
            "tool": f"mapshaper {mapshaper_ver} (npx)",
            "date": datetime.date.today().isoformat(),
            "steps": [
                "A38b_003（二次医療圏コード）でディゾルブ（116,365パート→335医療圏）",
                "面積1km2未満の離島リングを除去",
                f"Visvalingam加重 {args.pct}% 簡略化（keep-shapes）",
                "-clean によるスリバー除去・位相修復",
                "座標を0.0001度（約11m）へ丸め",
            ],
            "crs_note": (
                "元データは JGD2011 地理座標（EPSG:6668）。WGS84 との差は"
                "cmオーダーのため RFC 7946 GeoJSON としてそのまま扱う"
            ),
            "caveat": (
                "簡略化・離島除去済みのため面積計算等の解析には用いず、"
                "表示専用とすること。令和2年度時点の二次医療圏であり、"
                "R7 の339構想区域とは区割りが一致しない場合がある"
            ),
        },
        "fields": FIELD_DESCRIPTIONS,
        "feature_count": len(features),
    }
    gj_out = {"type": "FeatureCollection", "metadata": metadata, "features": features}

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(gj_out, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    print(f"[ok] 出力: {OUT_PATH}")
    print(f"     フィーチャ数: {len(features)}")
    print(f"     サイズ: {OUT_PATH.stat().st_size / 1_000_000:.1f} MB")
    print(f"     sha256 = {sha256(OUT_PATH)}")


if __name__ == "__main__":
    main()
