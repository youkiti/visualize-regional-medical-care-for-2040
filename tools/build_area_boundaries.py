# -*- coding: utf-8 -*-
"""国土数値情報 A38-20（医療圏）の一次医療圏（市区町村単位）レイヤから、
R7の339構想区域に対応した境界GeoJSON `data/processed/area_boundaries_R7.geojson`
を生成する。

## 背景・方針

339構想区域のうち331区域は、令和2年度の二次医療圏コード(`A38a_003`)と
構想区域コードが1対1で一致する(`tools/verify_area_join.py` で検証済み)。
残る8区域(三重県)は令和2年度の二次医療圏4圏域が細分化されたもので、対応する
境界を国土数値情報は公表していない。

331区域を二次医療圏レイヤ(`A38-20_2`、国土数値情報が公表済みのディゾルブ済み
ポリゴン)からそのまま使い、三重県8区域だけ一次医療圏レイヤ(`A38-20_1`、市区町村
ポリゴン)を新たにディゾルブして合成する手も考えられるが、簡略化(Visvalingam)の
挙動は入力ポリゴンの粒度に依存するため、二つの手法を混在させると三重県の県境
(331区域側と8区域側の接合線)に継ぎ目(隙間・重なり)が生じうる。これを避けるため、
**全339区域を`A38-20_1`(市区町村ポリゴン)から一度のディゾルブで生成する**
(同一ソース・同一簡略化条件)。

市区町村→構想区域コードの対応:
  - `data/reference/mie_area_municipalities.csv`(Chunk C1の成果物、三重県公式資料
    に基づく検証済み対応表、29市町)に載っている市区町村は、その`area_code`
    (2405〜2412)を使う。
  - それ以外(331区域に属する市区町村)は`A38a_003`(二次医療圏コード)を
    そのまま`area_code`として使う(二次医療圏コードと構想区域コードが1対1で
    一致することは`tools/verify_area_join.py`で検証済み)。

## 対応表の作り方について(採用した方式)

市区町村コード→構想区域コードの対応表をmapshaperに渡す方法として、
(a) 三重県29市町だけの対応表CSVを`-join`し、`-each`で
    「area_codeが空ならA38a_003を使う」という条件分岐で残りを埋める方式と、
(b) 観測された全市区町村について対応表CSVをPython側で先に作り、1回だけ
    全件`-join`する方式、の2通りが考えられた。

本スクリプトは **(b) を採用した**。理由: (a)の`-each`条件分岐は、CSVから
joinされた値が「空文字列」なのか「未定義(undefined)」なのかという型の扱いが
mapshaperのバージョンに依存しがちで、意図(「三重県だけ上書きし、それ以外は
A38a_003を使う」)がコード上からも監査しにくい。(b)であれば対応表CSV1枚を
見るだけで「どの市区町村がどの構想区域に属するか」を全件監査でき、mapshaper側は
単純な1回のjoin+dissolveで済む。

対応表構築の具体的な手順:
  1. zipから`A38-20_1.dbf`(属性のみ、235MBの本体`.shp`は展開しない)を展開し、
     mapshaperで標準入力形式のテーブルとしてCSVへ変換する(属性の確認だけなら
     ジオメトリを読む必要がないため、この段階では軽量に済む)。
  2. 属性テーブルから 市区町村コード(`A38a_001`) → 二次医療圏コード(`A38a_003`)
     の対応(既定値)を全市区町村分構築する。
  3. `data/reference/mie_area_municipalities.csv`の29市町コードが、上記の
     属性テーブルに実在することを検証する(1件でも欠けていれば中断。国土数値情報
     の市区町村界の年次と対応表の前提年度がずれていないかの検出)。
  4. 既定値を、三重県29市町だけ対応表の`area_code`で上書きした対応表CSV
     (観測された全市区町村分)を書き出す。
  5. `A38-20_1.shp`(本体、235MB)を展開し、上記対応表CSVを`A38a_001`キーで
     `-join`してから、`area_code`でディゾルブする。

処理内容(全体):
  1. `ksj/A38-20/A38-20_GML.zip`・`mie/001092203.pdf`のSHA-256を検証
  2. `data/processed/area_basic.csv`(339行)・
     `data/reference/mie_area_municipalities.csv`(29行)を読み込み
  3. 上記「対応表の作り方」の手順1〜5でディゾルブ済みGeoJSONを得る
     - 面積1km2未満の離島リングを除去
     - Visvalingam加重アルゴリズムで簡略化(既定2%、keep-shapes)
     - -clean でスリバー除去・位相修復
     - 座標を0.0001度(約11m)へ丸め
  4. 各フィーチャに`area_basic.csv`(R7側の正)から`area_name`/`pref_code`/
     `pref_name`を付与し、`boundary_source`(331区域=二次医療圏コード起源/
     8区域=三重県対応表起源)を設定
  5. 検証1〜6(下記)を行い、違反があれば中断
  6. 由来メタデータを埋め込み`data/processed/area_boundaries_R7.geojson`へ出力

## 検証1〜6

  1. 出力フィーチャ数がちょうど339であること
  2. `area_code`が一意(339件)で、`area_basic.csv`の339コードと集合として完全一致すること
  3. 三重県の8区域(2405〜2412)がすべて存在し、`boundary_source`が三重県用の値であること
  4. 対応表CSVの29市町コードが、実際にディゾルブ入力(A38-20_1の属性テーブル)の
     中に存在したこと(mapshaperの重い本体`-dissolve`を実行する前に検証する)
  5. 全フィーチャのジオメトリが`Polygon`または`MultiPolygon`で、空でないこと
  6. 三重県8区域の面積の合計が、旧4圏域(`iryoken2_A38-20.geojson`の2401〜2404)
     の面積の合計と近いこと(`TOLERANCE_PCT`のコメント参照)

面積計算(検証6)は、外部ライブラリを増やさないための球面近似(等距円筒図法に
よる簡易投影+シューレース公式)を本ファイル内に実装している(`feature_area_km2`)。
表示専用データの整合チェックが目的で、正確な面積値が必要なわけではない。

必要環境: Python 3.11+, Node.js（npx で mapshaper を取得）

使い方:
    PYTHONIOENCODING=utf-8 python tools/build_area_boundaries.py [--pct 2]
"""
import argparse
import csv
import datetime
import json
import math
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lib.codes import normalize_area_code, normalize_pref_code
from tools.lib.provenance import REPO_ROOT, recorded_hash, sha256, verify_source

SRC_ZIP = REPO_ROOT / "ksj" / "A38-20" / "A38-20_GML.zip"
OUT_PATH = REPO_ROOT / "data" / "processed" / "area_boundaries_R7.geojson"
AREA_BASIC_CSV = REPO_ROOT / "data" / "processed" / "area_basic.csv"
IRYOKEN2_PATH = REPO_ROOT / "data" / "processed" / "iryoken2_A38-20.geojson"
MIE_CSV = REPO_ROOT / "data" / "reference" / "mie_area_municipalities.csv"
MIE_CSV_META = Path(str(MIE_CSV) + ".meta.json")
MIE_PDF_PATH_IN_REPO = "mie/001092203.pdf"

SOURCE_PAGE = "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A38-v2_0.html"

# 三重県の構想区域8区域(旧4二次医療圏の細分化)。境界を市区町村ポリゴンから
# 合成する必要がある区域。
MIE_AREA_CODES = frozenset({"2405", "2406", "2407", "2408", "2409", "2410", "2411", "2412"})

BOUNDARY_SOURCE_DEFAULT = "A38-20_1 dissolve (二次医療圏コード)"
BOUNDARY_SOURCE_MIE = "A38-20_1 dissolve (三重県 構想区域別市町対応表)"

# 検証6の許容差。三重県の新8区域(A38-20_1を新区域単位でディゾルブ)と
# 旧4圏域(iryoken2_A38-20.geojson、A38-20_2を二次医療圏単位でディゾルブ済み)は、
# 同じ市区町村の集合を異なる単位でグルーピングしただけであり、理論上は面積が
# ほぼ一致するはずである。実際に `PYTHONIOENCODING=utf-8 python
# tools/build_area_boundaries.py` を実行して測った差は0.002%(旧5782.68km2 /
# 新5782.81km2)と極めて小さかった。これは離島除去・簡略化のパラメータが
# ソースレイヤ(A38-20_1と、あらかじめディゾルブ済みのA38-20_2)で完全に
# 同一ではない(簡略化は入力ポリゴンの粒度に依存する)ため、ある程度のずれは
# 起こりうる。実測値(0.002%)そのものを閾値にすると、mapshaper/GEOSの
# バージョン差による簡略化結果の揺らぎで将来再生成時に誤って落ちる恐れがある
# ため、実測値のおよそ500倍の安全域を確保しつつ、区域の取り違えや対応表の
# 誤りなど桁違いの実害があるバグは十分検出できる水準として1%とした。
TOLERANCE_PCT = 1.0

FIELD_DESCRIPTIONS = {
    "area_code": "構想区域コード(ゼロ埋め4桁の文字列)",
    "area_name": "構想区域名(area_basic.csvより。A38の二次医療圏名ではなくR7の構想区域名が正)",
    "pref_code": "都道府県コード(ゼロ埋め2桁の文字列)",
    "pref_name": "都道府県名",
    "boundary_source": (
        "境界の合成方法。"
        f"'{BOUNDARY_SOURCE_DEFAULT}'(331区域): A38-20_1(市区町村ポリゴン)を"
        "二次医療圏コード(A38a_003、R7の構想区域コードと1対1で一致)でディゾルブ。"
        f"'{BOUNDARY_SOURCE_MIE}'(三重県8区域): A38-20_1を"
        "data/reference/mie_area_municipalities.csv(三重県公式資料に基づく検証済み"
        "対応表)の構想区域コードでディゾルブ。国土数値情報がR7の8区域の境界を"
        "公表しているわけではなく、市区町村ポリゴンから合成した派生物である"
    ),
}


def _extract_members(zip_path: Path, prefix: str, suffixes: set, out_dir: Path) -> None:
    """`zip_path`内で、ファイル名(パス区切りを除いたベース名)が`prefix`で始まり
    拡張子が`suffixes`に含まれるメンバーだけを`out_dir`へ展開する。"""
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            base = name.replace("\\", "/").rsplit("/", 1)[-1]
            if base.startswith(prefix) and base.rsplit(".", 1)[-1] in suffixes:
                (out_dir / base).write_bytes(z.read(name))


def _run_mapshaper(npx: str, args: list) -> None:
    cmd = [npx, "-y", "mapshaper"] + args
    print("[run] " + " ".join(cmd))
    subprocess.run(cmd, check=True, shell=False)


def load_area_basic(path: Path = AREA_BASIC_CSV) -> dict:
    """`area_basic.csv`を読み、正規化済み構想区域コードをキーにした辞書を返す。

    戻り値: {area_code(正規化済み): {"area_name":..., "pref_code":..., "pref_name":...}}
    """
    with open(path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    area_by_code = {}
    for row in rows:
        code = normalize_area_code(row["area_code"])
        if code in area_by_code:
            raise ValueError(f"{path}: 構想区域コード{code}が重複しています")
        area_by_code[code] = {
            "area_name": row["area_name"],
            "pref_code": normalize_pref_code(row["pref_code"]),
            "pref_name": row["pref_name"],
        }
    return area_by_code


def load_mie_muni_map(path: Path = MIE_CSV):
    """`mie_area_municipalities.csv`を読み、市区町村コード→構想区域コードの
    辞書を返す(Chunk C1の成果物。三重県公式資料に基づく検証済み対応表)。

    戻り値: (muni_to_area, rows)
      muni_to_area: {muni_code: area_code(正規化済み)}
      rows: 全行(dictのリスト、CSV原文順)
    """
    with open(path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    muni_to_area = {}
    for row in rows:
        muni_code = row["muni_code"].strip()
        area_code = normalize_area_code(row["area_code"])
        if muni_code in muni_to_area and muni_to_area[muni_code] != area_code:
            raise ValueError(
                f"{path}: 市区町村コード{muni_code}が複数の構想区域コードに対応しています"
                f"({muni_to_area[muni_code]} と {area_code})"
            )
        muni_to_area[muni_code] = area_code
    return muni_to_area, rows


# --- 検証6用: 外部ライブラリを増やさない球面近似の面積計算 --------------------


_KM_PER_DEG_LAT = 111.32  # WGS84の平均的な緯度1度あたりの距離(km)の近似値


def _ring_area_deg2_signed(ring_km) -> float:
    """(x_km, y_km)座標列のシューレース公式による符号付き面積(km2)を返す。"""
    total = 0.0
    n = len(ring_km)
    for i in range(n):
        x1, y1 = ring_km[i]
        x2, y2 = ring_km[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _polygon_area_km2(rings, ref_lat_deg: float) -> float:
    """GeoJSON Polygonの`coordinates`(環のリスト、先頭が外環・以降が内環=穴)から
    面積(km2)を求める。等距円筒図法(基準緯度で経度方向をcos補正)による近似。

    符号(時計回り/反時計回り)には依存しない(各環の絶対値で外環+・内環-)ため、
    RFC 7946の巻き方向規則が厳密に守られていない入力でも安全に計算できる。
    """
    if not rings:
        return 0.0
    km_per_deg_lon = _KM_PER_DEG_LAT * math.cos(math.radians(ref_lat_deg))
    exterior_km = [(lon * km_per_deg_lon, lat * _KM_PER_DEG_LAT) for lon, lat in rings[0]]
    area = abs(_ring_area_deg2_signed(exterior_km))
    for hole in rings[1:]:
        hole_km = [(lon * km_per_deg_lon, lat * _KM_PER_DEG_LAT) for lon, lat in hole]
        area -= abs(_ring_area_deg2_signed(hole_km))
    return area


def feature_area_km2(geometry: dict, ref_lat_deg: float = 34.5) -> float:
    """GeoJSON geometry(Polygon/MultiPolygon)の面積(km2、球面近似)を返す。

    `ref_lat_deg`の既定値34.5は三重県付近の緯度(検証6で旧4圏域/新8区域を
    比較する用途にのみ使うため、日本全体で正確である必要はない)。
    """
    gtype = geometry["type"]
    if gtype == "Polygon":
        return _polygon_area_km2(geometry["coordinates"], ref_lat_deg)
    if gtype == "MultiPolygon":
        return sum(_polygon_area_km2(poly, ref_lat_deg) for poly in geometry["coordinates"])
    raise ValueError(f"Polygon/MultiPolygon以外のジオメトリです: {gtype!r}")


# --- 検証1・2・3・5 -----------------------------------------------------------


def validate_output(features: list, area_by_code: dict) -> None:
    """検証1・2・3・5を行う。違反があれば`SystemExit`で中断する。"""
    # 検証1: フィーチャ数
    if len(features) != 339:
        raise SystemExit(f"検証1失敗: 出力フィーチャ数が339ではありません({len(features)})")

    codes = [f["properties"]["area_code"] for f in features]

    # 検証2: 一意性 + area_basic.csvとの集合一致
    dup = sorted(c for c, n in Counter(codes).items() if n > 1)
    if dup:
        raise SystemExit(f"検証2失敗: area_codeが重複しています: {dup}")
    out_codes = set(codes)
    basic_codes = set(area_by_code)
    if out_codes != basic_codes:
        raise SystemExit(
            "検証2失敗: area_codeの集合がarea_basic.csvと一致しません。"
            f"出力のみ={sorted(out_codes - basic_codes)} area_basic.csvのみ={sorted(basic_codes - out_codes)}"
        )

    # 検証3: 三重県8区域の存在とboundary_source
    by_code = {f["properties"]["area_code"]: f for f in features}
    missing_mie = sorted(MIE_AREA_CODES - set(by_code))
    if missing_mie:
        raise SystemExit(f"検証3失敗: 三重県の構想区域が出力に存在しません: {missing_mie}")
    wrong_source = sorted(
        c for c in MIE_AREA_CODES if by_code[c]["properties"]["boundary_source"] != BOUNDARY_SOURCE_MIE
    )
    if wrong_source:
        raise SystemExit(f"検証3失敗: 三重県の区域のboundary_sourceが期待値と異なります: {wrong_source}")

    # 検証5: ジオメトリ型と非空
    for f in features:
        code = f["properties"]["area_code"]
        geom = f.get("geometry")
        if geom is None or geom.get("type") not in ("Polygon", "MultiPolygon"):
            raise SystemExit(
                f"検証5失敗: {code}のジオメトリがPolygon/MultiPolygonではありません"
                f"({geom.get('type') if geom else None})"
            )
        if not geom.get("coordinates"):
            raise SystemExit(f"検証5失敗: {code}のジオメトリが空です")


def validate_mie_area_close(features: list, tolerance_pct: float = TOLERANCE_PCT):
    """検証6: 三重県8区域の面積合計が、旧4圏域(iryoken2_A38-20.geojson)の
    面積合計と近いことを確認する。違反があれば`SystemExit`で中断する。

    戻り値: (old_total_km2, new_total_km2, diff_pct)
    """
    with open(IRYOKEN2_PATH, "r", encoding="utf-8") as f:
        old_gj = json.load(f)
    old_codes = {"2401", "2402", "2403", "2404"}
    old_total = sum(
        feature_area_km2(feat["geometry"])
        for feat in old_gj["features"]
        if normalize_area_code(feat["properties"]["A38b_003"]) in old_codes
    )
    new_total = sum(
        feature_area_km2(f["geometry"]) for f in features if f["properties"]["area_code"] in MIE_AREA_CODES
    )
    diff_pct = abs(new_total - old_total) / old_total * 100
    if diff_pct > tolerance_pct:
        raise SystemExit(
            f"検証6失敗: 三重県の新8区域合計({new_total:.2f}km2)と旧4圏域合計"
            f"({old_total:.2f}km2)の差({diff_pct:.2f}%)が許容差({tolerance_pct}%)を超えています"
        )
    return old_total, new_total, diff_pct


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pct", type=float, default=2.0, help="簡略化率（%%、既定2）")
    args = ap.parse_args()

    # 1. 生データの完全性検証
    expected = recorded_hash("ksj/A38-20/A38-20_GML.zip")
    actual = sha256(SRC_ZIP)
    if actual != expected:
        raise SystemExit(f"SHA-256不一致: {SRC_ZIP}\n  期待値: {expected}\n  実測値: {actual}")
    print(f"[ok] 生データ検証: {SRC_ZIP.name} = {actual[:16]}...")

    pdf_sha256 = verify_source(MIE_PDF_PATH_IN_REPO)
    print(f"[ok] 三重県一次資料PDFの完全性検証: {MIE_PDF_PATH_IN_REPO} ({pdf_sha256[:12]}…)")

    npx = shutil.which("npx")
    if npx is None:
        raise SystemExit("npx が見つかりません（Node.js をインストールしてください）")

    mapshaper_ver = subprocess.run(
        [npx, "-y", "mapshaper", "-v"], capture_output=True, text=True, check=True, shell=False
    ).stdout.strip()

    area_by_code = load_area_basic()
    print(f"[ok] area_basic.csv 読み込み: {len(area_by_code)}区域")

    mie_muni_to_area, mie_rows = load_mie_muni_map()
    print(f"[ok] mie_area_municipalities.csv 読み込み: {len(mie_muni_to_area)}市町")

    with open(MIE_CSV_META, "r", encoding="utf-8") as f:
        mie_meta = json.load(f)
    mie_pdf_source = mie_meta["source"]["inputs"][0]

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        attrs_dir = tmp / "attrs"
        shp_dir = tmp / "shp"
        attrs_dir.mkdir()
        shp_dir.mkdir()

        # 2. 属性テーブルのみ展開・CSV化(235MBの本体shpはまだ読まない)
        _extract_members(SRC_ZIP, "A38-20_1.", {"dbf"}, attrs_dir)
        print("[ok] A38-20_1.dbf を展開(属性のみ)")

        attrs_csv = attrs_dir / "attrs.csv"
        _run_mapshaper(npx, [str(attrs_dir / "A38-20_1.dbf"), "encoding=cp932", "-o", "format=csv", str(attrs_csv)])

        with open(attrs_csv, "r", encoding="utf-8", newline="") as f:
            attr_rows = list(csv.DictReader(f))
        print(f"[ok] 属性テーブル読み込み: {len(attr_rows)}パート")

        muni_to_default_area = {}
        inconsistent = set()
        for row in attr_rows:
            muni_code = row["A38a_001"].strip()
            default_area = normalize_area_code(row["A38a_003"])
            if muni_code in muni_to_default_area and muni_to_default_area[muni_code] != default_area:
                inconsistent.add(muni_code)
            muni_to_default_area[muni_code] = default_area
        if inconsistent:
            raise SystemExit(f"A38-20_1: 市区町村コードが複数の二次医療圏コードに対応しています: {sorted(inconsistent)}")
        print(f"[ok] 市区町村コード→二次医療圏コード(既定値)の対応を構築: {len(muni_to_default_area)}市区町村")

        # 3. 検証4: 対応表の29市町コードが実際にディゾルブ入力に存在するか
        missing_mie = sorted(set(mie_muni_to_area) - set(muni_to_default_area))
        if missing_mie:
            raise SystemExit(
                "検証4失敗: data/reference/mie_area_municipalities.csv の市町コードが "
                f"A38-20_1(令和2年度)のディゾルブ入力に見つかりません"
                f"(市区町村界の年次ずれの可能性): {missing_mie}"
            )
        print(f"[ok] 検証4: 対応表の{len(mie_muni_to_area)}市町コードがすべてA38-20_1のディゾルブ入力に存在することを確認")

        # 4. 全市区町村分の対応表CSVを構築(三重県29市町だけ上書き)
        correspondence = {
            muni_code: mie_muni_to_area.get(muni_code, default_area)
            for muni_code, default_area in muni_to_default_area.items()
        }
        correspondence_csv = tmp / "correspondence.csv"
        with open(correspondence_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(["muni_code", "area_code"])
            for muni_code in sorted(correspondence):
                writer.writerow([muni_code, correspondence[muni_code]])
        print(
            f"[ok] 市区町村コード→構想区域コード対応表を作成: {len(correspondence)}件"
            f"(うち{len(mie_muni_to_area)}件は三重県対応表で上書き)"
        )

        # 5. 本体shpの展開とmapshaperによるjoin+dissolve
        _extract_members(SRC_ZIP, "A38-20_1.", {"shp", "shx", "dbf", "prj"}, shp_dir)
        print("[ok] A38-20_1.*(shp/shx/dbf/prj)を展開")

        raw_out = tmp / "area_boundaries_raw.geojson"
        cmd = [
            str(shp_dir / "A38-20_1.shp"), "encoding=cp932",
            "-join", str(correspondence_csv), "keys=A38a_001,muni_code",
            "fields=area_code", "string-fields=muni_code,area_code",
            "-dissolve", "fields=area_code",
            "-filter-islands", "min-area=1km2",
            "-simplify", "visvalingam", "weighted", f"{args.pct}%", "keep-shapes",
            "-clean",
            "-o", "format=geojson", "precision=0.0001", str(raw_out),
        ]
        _run_mapshaper(npx, cmd)

        gj = json.loads(raw_out.read_text(encoding="utf-8"))

    features = gj["features"]
    print(f"[ok] ディゾルブ結果: {len(features)}フィーチャ")

    # 6. area_basic.csvから名称等を付与し、boundary_sourceを設定
    enriched = []
    for feat in features:
        raw_code = feat["properties"].get("area_code")
        if raw_code in (None, ""):
            raise SystemExit("ディゾルブ結果にarea_codeが空のフィーチャがあります(joinの対応漏れの可能性)")
        code = normalize_area_code(raw_code)
        info = area_by_code.get(code)
        if info is None:
            raise SystemExit(f"ディゾルブ結果にarea_basic.csvに無い構想区域コードがあります: {code}")
        boundary_source = BOUNDARY_SOURCE_MIE if code in MIE_AREA_CODES else BOUNDARY_SOURCE_DEFAULT
        enriched.append(
            {
                "type": "Feature",
                "properties": {
                    "area_code": code,
                    "area_name": info["area_name"],
                    "pref_code": info["pref_code"],
                    "pref_name": info["pref_name"],
                    "boundary_source": boundary_source,
                },
                "geometry": feat["geometry"],
            }
        )
    enriched.sort(key=lambda f: f["properties"]["area_code"])  # 決定的な出力順

    # 7. 検証1〜6
    validate_output(enriched, area_by_code)
    print("[ok] 検証1・2・3・5: フィーチャ数339・area_codeの一意性/完全一致・三重県8区域の存在とboundary_source・ジオメトリ型を確認")

    old_total, new_total, diff_pct = validate_mie_area_close(enriched)
    print(
        f"[ok] 検証6: 旧4圏域(2401-2404)合計={old_total:.2f}km2 新8区域(2405-2412)合計={new_total:.2f}km2 "
        f"差={diff_pct:.3f}%(許容差{TOLERANCE_PCT}%以内)"
    )

    # 8. 由来メタデータの埋め込み
    today = datetime.date.today().isoformat()
    metadata = {
        "title": "R7構想区域境界（339区域・A38-20_1ディゾルブ合成版）",
        "source": {
            "name": "国土数値情報 医療圏データ 第2.0版（A38-20）一次医療圏（市区町村単位）のディゾルブ",
            "publisher": "国土交通省 国土数値情報ダウンロードサービス",
            "url": SOURCE_PAGE,
            "data_year": "令和2年度（2020年度）市区町村界",
            "source_file": "ksj/A38-20/A38-20_GML.zip 内 A38-20_GML/A38-20_1.shp",
            "source_sha256": expected,
            "license": "国土数値情報ダウンロードサービス利用約款（オープンデータ）",
            "mie_correspondence": {
                "file": "data/reference/mie_area_municipalities.csv",
                "row_count": mie_meta["row_count"],
                "role": "三重県8区域(2405〜2412)の市区町村→構想区域コード対応(29市町)",
                "primary_source": {
                    "file": MIE_PDF_PATH_IN_REPO,
                    "title": mie_pdf_source["title"],
                    "publisher": mie_pdf_source["publisher"],
                    "source_sha256": pdf_sha256,
                },
            },
        },
        "processing": {
            "script": "tools/build_area_boundaries.py",
            "tool": f"mapshaper {mapshaper_ver} (npx)",
            "date": today,
            "method": (
                "339区域すべてをA38-20_1(市区町村ポリゴン)から一度のディゾルブで生成した"
                "(331区域=二次医療圏コード起源、8区域(三重県)=三重県対応表起源の区域を"
                "混在させず同一ソース・同一簡略化条件で処理することで、簡略化度合いの"
                "不揃いによる境界の継ぎ目(隙間・重なり)を避けている)"
            ),
            "correspondence_table_method": (
                "市区町村コード(A38a_001)→構想区域コードの対応表は、観測された全市区町村"
                f"({len(correspondence)}件)についてPython側で先に構築し(既定値=A38a_003、"
                f"うち三重県{len(mie_muni_to_area)}市町のみdata/reference/"
                "mie_area_municipalities.csvのarea_codeで上書き)、mapshaperには1回の"
                "-joinとして渡した(mapshaperの-eachによる条件分岐は、CSVからjoinされた値が"
                "空文字列か未定義かの扱いがバージョンに依存しがちで意図が監査しにくいため採用しなかった)"
            ),
            "steps": [
                "A38-20_1.dbf(属性のみ)を展開しCSV化、市区町村コード→構想区域コードの"
                "対応表(全市区町村分)をPython側で構築",
                "対応表の29市町コード(三重県)が実際にA38-20_1の属性テーブルに存在することを確認"
                "(検証4、市区町村界の年次ずれの検出)",
                "A38-20_1.shp(本体)にA38a_001キーで対応表をjoinし、全パートにarea_codeを付与",
                f"area_codeでディゾルブ({len(attr_rows)}パート→339区域)",
                "面積1km2未満の離島リングを除去",
                f"Visvalingam加重 {args.pct}% 簡略化(keep-shapes)",
                "-clean によるスリバー除去・位相修復",
                "座標を0.0001度(約11m)へ丸め",
            ],
            "crs_note": (
                "元データは JGD2011 地理座標（EPSG:6668）。WGS84 との差は"
                "cmオーダーのため RFC 7946 GeoJSON としてそのまま扱う"
            ),
            "caveat": (
                "簡略化・離島除去済みのため面積計算等の解析には用いず、表示専用とすること。"
                "境界の元データは令和2年度時点の市区町村界である。"
                "三重県8区域(2405桑員〜2412東紀州)の境界は国土数値情報が公表しているものでは"
                "なく、市区町村ポリゴンをdata/reference/mie_area_municipalities.csv"
                "(三重県公式資料に基づく検証済み対応表)の構想区域単位でディゾルブして合成した"
                "派生物である(boundary_sourceフィールドで区別できる)。331区域とR7の構想区域は"
                "コード・名称とも一致するが、令和2年度以降に市区町村合併等があった場合は"
                "反映されていない。"
            ),
        },
        "fields": FIELD_DESCRIPTIONS,
        "feature_count": len(enriched),
        "verification": {
            "feature_count": len(enriched),
            "mie_area_check_km2": {
                "old_iryoken2_2401_2404_total": round(old_total, 2),
                "new_area_2405_2412_total": round(new_total, 2),
                "diff_pct": round(diff_pct, 3),
                "tolerance_pct": TOLERANCE_PCT,
            },
        },
    }
    gj_out = {"type": "FeatureCollection", "metadata": metadata, "features": enriched}

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(gj_out, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    print(f"[ok] 出力: {OUT_PATH}")
    print(f"     フィーチャ数: {len(enriched)}")
    print(f"     サイズ: {OUT_PATH.stat().st_size / 1_000_000:.1f} MB")
    print(f"     sha256 = {sha256(OUT_PATH)}")


if __name__ == "__main__":
    main()
