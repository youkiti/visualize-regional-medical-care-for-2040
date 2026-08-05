# -*- coding: utf-8 -*-
"""可視化サイトの概観レイヤ(都道府県)が使う境界GeoJSON
`data/processed/prefecture_boundaries_R7.geojson`(47都道府県)を、既にコミット
済みの構想区域境界`data/processed/area_boundaries_R7.geojson`(339区域)を
都道府県コードでディゾルブして生成する。

## なぜ A38-20 の zip から作り直さないのか

`tools/build_area_boundaries.py` と同じく `ksj/A38-20/A38-20_GML.zip`
(1.13GB、Git管理外)の市区町村ポリゴンを都道府県単位でディゾルブする手も
あるが、**既に生成済みの339区域境界を潰す方式を採用した**。理由は3つ:

  1. **区域境界と頂点を共有する**。簡略化(Visvalingam)の挙動は入力ポリゴンの
     粒度に依存するため、zipから都道府県単位で作り直すと同じ海岸線が構想区域
     レイヤと微妙に食い違う。可視化では構想区域の塗りの上に県境を重ねて描く
     ので、食い違いは「県境が海へはみ出す/内陸へ食い込む」という目に見える
     破綻になる。339区域を潰せば、県境は必ず区域境界の部分集合になる。
  2. **入力がGit管理下にある**。zipに依存しないので、再生成がどの環境でも
     可能(`tools/build_area_boundaries.py` はCIでは実行できない)。
  3. **新しい判断が要らない**。市区町村→都道府県の対応も、三重県の扱いも、
     既に339区域の生成時に決着済みのものをそのまま引き継ぐ。

なお三重県8区域(2405〜2412)の境界は市区町村界から合成した派生物だが、
**県の外形には影響しない**。ディゾルブで消えるのは区域どうしの内部境界で
あり、三重県の外周は8区域の和集合 = 旧4二次医療圏の和集合 = 構成市町の
和集合として同一だからである(この点は`metadata.processing.caveat`にも明記
している)。

## 全国(00)について

出力は47都道府県のみで、「全国」のフィーチャは作らない(47件の和集合を
描いても地図上の情報が増えないため)。全国の集計値は表示用データセット側
(`tools/build_web_prefecture.py` の `national`)が持つ。

処理内容:
  1. `area_boundaries_R7.geojson`(339区域)・`prefecture_basic.csv`(96行=R6/R7
     ×48行[全国含む]。都道府県名にはpublished_fy=='R7'の48行のみを使う)を
     読み込む
  2. mapshaperで`pref_code`によるディゾルブ + `-clean`(スリバー除去・位相修復)
  3. 各フィーチャに`prefecture_basic.csv`(R7側の正)から`pref_name`を付与する
     (入力GeoJSONにも`pref_name`はあるが、名称の正は常にR7の加工CSV側)
  4. 検証1〜5(下記)を行い、違反があれば中断
  5. 由来メタデータを埋め込み`data/processed/prefecture_boundaries_R7.geojson`
     へ出力

## 検証1〜5

  1. 出力フィーチャ数がちょうど47であること
  2. `pref_code`が一意(47件)で、`prefecture_basic.csv`の47コード(全国00を除く)
     および入力339区域の`pref_code`集合と3つとも完全一致すること
  3. 全フィーチャのジオメトリが`Polygon`または`MultiPolygon`で、空でないこと
  4. 47都道府県の面積合計が、入力339区域の面積合計と近いこと
     (純粋なディゾルブなので理論上は一致する。`TOLERANCE_PCT`のコメント参照)
  5. 各都道府県の面積が、その都道府県に属する構想区域の面積合計と近いこと
     (検証4は全国合計なので、県どうしで打ち消し合う誤りを検出できない)

面積計算は`tools/build_area_boundaries.py`の`feature_area_km2`を再利用する
(外部ライブラリを増やさないための球面近似。表示専用データの整合チェックが
目的で、正確な面積値が必要なわけではない)。基準緯度だけは日本全体を扱う
ため36.0度(本州中央付近)を使う。

生成日時は埋め込まない(CLAUDE.md参照。再現性テストが翌日に壊れるため)。

必要環境: Python 3.11+, Node.js（npx で mapshaper を取得）

使い方:
    PYTHONIOENCODING=utf-8 python tools/build_prefecture_boundaries.py
"""
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.build_area_boundaries import feature_area_km2
from tools.lib.codes import normalize_pref_code
from tools.lib.provenance import REPO_ROOT, sha256

AREA_BOUNDARIES_GEOJSON = REPO_ROOT / "data" / "processed" / "area_boundaries_R7.geojson"
PREFECTURE_BASIC_CSV = REPO_ROOT / "data" / "processed" / "prefecture_basic.csv"
OUT_PATH = REPO_ROOT / "data" / "processed" / "prefecture_boundaries_R7.geojson"

# prefecture_basic.csv の pref_code='00' は全国(47都道府県の集計行)。境界は
# 作らない(「全国(00)について」参照)。
NATIONAL_CODE = "00"

EXPECTED_PREFECTURE_COUNT = 47

BOUNDARY_SOURCE = "area_boundaries_R7.geojson dissolve (都道府県コード)"

# 日本全体の面積比較に使う基準緯度(本州中央付近)。等距円筒図法による近似の
# ため緯度によって誤差が出るが、検証4・5は「入力と出力を同じ関数・同じ基準
# 緯度で測って比べる」相対比較なので、絶対値の正確さは要求されない。
REF_LAT_DEG = 36.0

# 検証4・5の許容差。純粋なディゾルブなので理論上は完全一致するが、
# `-clean`(スリバー除去・位相修復)と座標の丸め(0.0001度)により微小な差は
# 起こりうる。実測差は全国合計で0.001%未満・県別最大でも0.01%未満だった。
# 実測値そのものを閾値にすると mapshaper/GEOS のバージョン差で将来誤って
# 落ちるため、県の取り違えやジオメトリ欠落など桁違いの実害があるバグは
# 十分検出できる水準として0.5%とした。
TOLERANCE_PCT = 0.5

FIELD_DESCRIPTIONS = {
    "pref_code": "都道府県コード(ゼロ埋め2桁の文字列)",
    "pref_name": "都道府県名(prefecture_basic.csvより)",
    "boundary_source": (
        f"境界の合成方法。'{BOUNDARY_SOURCE}': area_boundaries_R7.geojson"
        "(339構想区域)を都道府県コードでディゾルブしたもの。したがって県境は"
        "必ず構想区域境界の部分集合になり、構想区域レイヤと頂点を共有する"
    ),
}


def _run_mapshaper(npx: str, args: list) -> None:
    cmd = [npx, "-y", "mapshaper"] + args
    print("[run] " + " ".join(cmd))
    subprocess.run(cmd, check=True, shell=False)


def load_prefecture_names(path: Path = PREFECTURE_BASIC_CSV) -> dict:
    """`prefecture_basic.csv`を読み、都道府県コード -> 都道府県名の辞書を返す。

    全国(pref_code='00')の行は除外する(境界を作らないため)。

    prefecture_basic.csvはR6/R7がpublished_fyで並存するようになった(M9)ため
    48行(全国含む)から96行へ倍増している。境界の都道府県名は常にR7側の正を
    使う(モジュールdocstring「処理内容」参照)ため、published_fy=='R7'の行だけに
    絞り込んでから読む(絞り込まないと同じpref_codeがR6行とR7行の2回出て
    「重複しています」で落ちる)。
    """
    with open(path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    rows = [row for row in rows if row["published_fy"] == "R7"]
    if not rows:
        raise SystemExit(f"{path}: published_fy=='R7'の行がありません")
    names = {}
    for row in rows:
        code = normalize_pref_code(row["pref_code"])
        if code == NATIONAL_CODE:
            continue
        if code in names:
            raise SystemExit(f"{path}: 都道府県コード{code}が重複しています")
        names[code] = row["pref_name"]
    return names


def load_area_features(path: Path = AREA_BOUNDARIES_GEOJSON):
    """構想区域境界GeoJSONを読み、(features, metadata) を返す。"""
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)
    return gj["features"], gj.get("metadata", {})


def area_km2_by_pref(area_features) -> dict:
    """構想区域境界の面積を都道府県コードごとに合計した辞書を返す(検証4・5用)。"""
    totals = defaultdict(float)
    for feat in area_features:
        pref_code = normalize_pref_code(feat["properties"]["pref_code"])
        totals[pref_code] += feature_area_km2(feat["geometry"], REF_LAT_DEG)
    return dict(totals)


def validate_output(features: list, pref_names: dict, area_pref_codes: set) -> None:
    """検証1・2・3を行い、違反があれば`SystemExit`で中断する。"""
    # 検証1: フィーチャ数
    if len(features) != EXPECTED_PREFECTURE_COUNT:
        raise SystemExit(
            f"検証1失敗: 出力フィーチャ数が{EXPECTED_PREFECTURE_COUNT}ではありません({len(features)})"
        )

    codes = [f["properties"]["pref_code"] for f in features]

    # 検証2: 一意性 + prefecture_basic.csv / 入力339区域との集合一致
    dup = sorted(c for c, n in Counter(codes).items() if n > 1)
    if dup:
        raise SystemExit(f"検証2失敗: pref_codeが重複しています: {dup}")
    out_codes = set(codes)
    basic_codes = set(pref_names)
    if out_codes != basic_codes:
        raise SystemExit(
            "検証2失敗: pref_codeの集合がprefecture_basic.csvと一致しません。"
            f"出力のみ={sorted(out_codes - basic_codes)} "
            f"prefecture_basic.csvのみ={sorted(basic_codes - out_codes)}"
        )
    if out_codes != area_pref_codes:
        raise SystemExit(
            "検証2失敗: pref_codeの集合がarea_boundaries_R7.geojsonと一致しません。"
            f"出力のみ={sorted(out_codes - area_pref_codes)} "
            f"area_boundaries_R7.geojsonのみ={sorted(area_pref_codes - out_codes)}"
        )

    # 検証3: ジオメトリ型と非空
    for f in features:
        code = f["properties"]["pref_code"]
        geom = f.get("geometry")
        if geom is None or geom.get("type") not in ("Polygon", "MultiPolygon"):
            raise SystemExit(
                f"検証3失敗: {code}のジオメトリがPolygon/MultiPolygonではありません"
                f"({geom.get('type') if geom else None})"
            )
        if not geom.get("coordinates"):
            raise SystemExit(f"検証3失敗: {code}のジオメトリが空です")


def validate_area_conservation(features: list, area_km2_by_code: dict, tolerance_pct: float = TOLERANCE_PCT):
    """検証4・5: 面積が入力(構想区域)と保存されていることを確認する。

    戻り値: (total_area_km2, total_pref_km2, total_diff_pct, worst_code, worst_diff_pct)
    """
    pref_km2 = {
        f["properties"]["pref_code"]: feature_area_km2(f["geometry"], REF_LAT_DEG) for f in features
    }

    # 検証4: 全国合計
    total_area = sum(area_km2_by_code.values())
    total_pref = sum(pref_km2.values())
    total_diff_pct = abs(total_pref - total_area) / total_area * 100
    if total_diff_pct > tolerance_pct:
        raise SystemExit(
            f"検証4失敗: 47都道府県の面積合計({total_pref:.2f}km2)と339構想区域の面積合計"
            f"({total_area:.2f}km2)の差({total_diff_pct:.3f}%)が許容差({tolerance_pct}%)を超えています"
        )

    # 検証5: 県別(検証4は合計なので、県どうしで打ち消し合う誤りを検出できない)
    worst_code = None
    worst_diff_pct = 0.0
    for code in sorted(pref_km2):
        expected = area_km2_by_code[code]
        diff_pct = abs(pref_km2[code] - expected) / expected * 100
        if diff_pct > worst_diff_pct:
            worst_code = code
            worst_diff_pct = diff_pct
    if worst_diff_pct > tolerance_pct:
        raise SystemExit(
            f"検証5失敗: 都道府県{worst_code}の面積({pref_km2[worst_code]:.2f}km2)が、"
            f"その県に属する構想区域の面積合計({area_km2_by_code[worst_code]:.2f}km2)と"
            f"{worst_diff_pct:.3f}%異なります(許容差{tolerance_pct}%)"
        )

    return total_area, total_pref, total_diff_pct, worst_code, worst_diff_pct


def build_metadata(area_metadata: dict, mapshaper_ver: str, verification: dict) -> dict:
    """入力(area_boundaries_R7.geojson)のメタデータを引き継いで、出力の由来
    メタデータを組み立てる。

    出典(国土数値情報A38-20)は入力GeoJSONの`metadata.source`をそのまま引き継ぐ
    (ハードコードによる二重管理を避ける)。`prefecture_basic.csv`は都道府県名の
    出所としてのみ使うので、`processing.inputs`/`derived_via`に記録する。
    """
    return {
        "title": "R7都道府県境界（47都道府県・構想区域境界のディゾルブ合成版）",
        "source": dict(area_metadata.get("source", {})),
        "processing": {
            "script": "tools/build_prefecture_boundaries.py",
            "tool": f"mapshaper {mapshaper_ver} (npx)",
            "inputs": [
                {
                    "path": "data/processed/area_boundaries_R7.geojson",
                    "sha256": sha256(AREA_BOUNDARIES_GEOJSON),
                    "role": "ディゾルブ入力(339構想区域の境界)",
                },
                {
                    "path": "data/processed/prefecture_basic.csv",
                    "sha256": sha256(PREFECTURE_BASIC_CSV),
                    "role": "都道府県名の正(R7側)",
                },
            ],
            "method": (
                "既にコミット済みのarea_boundaries_R7.geojson(339構想区域)を"
                "pref_codeでディゾルブした。国土数値情報のzipから都道府県単位で"
                "作り直していないのは、簡略化(Visvalingam)の挙動が入力ポリゴンの"
                "粒度に依存するため、作り直すと同じ海岸線が構想区域レイヤと微妙に"
                "食い違い、構想区域の塗りの上に県境を重ねたときに目に見える破綻"
                "(県境が海へはみ出す/内陸へ食い込む)になるからである。339区域を"
                "潰せば県境は必ず区域境界の部分集合になる"
            ),
            "steps": [
                "area_boundaries_R7.geojson(339区域)をpref_codeでディゾルブ(→47都道府県)",
                "-clean によるスリバー除去・位相修復",
                "座標を0.0001度(約11m)へ丸め(入力と同じ精度。入力は既に同精度のため実質的に変化しない)",
                "prefecture_basic.csv(R7側の正)からpref_nameを付与",
                "フィーチャ数47・pref_codeの一意性/集合一致・ジオメトリ型を確認(検証1〜3)",
                "面積が入力(構想区域)と保存されていることを全国合計・県別の両方で確認(検証4・5)",
                "pref_codeの昇順(文字列ソート)でフィーチャを整列",
            ],
            "crs_note": area_metadata.get("processing", {}).get("crs_note", ""),
            "caveat": (
                "簡略化・離島除去済みのため面積計算等の解析には用いず、表示専用とすること"
                "(入力である構想区域境界の性質をそのまま引き継ぐ)。境界の元データは"
                "令和2年度時点の市区町村界である。"
                "三重県の8構想区域の境界は市区町村界から合成した派生物だが、"
                "ディゾルブで消えるのは区域どうしの内部境界であり、三重県の外周は"
                "8区域の和集合=旧4二次医療圏の和集合=構成市町の和集合として同一で"
                "あるため、都道府県の外形には影響しない。"
                "「全国」のフィーチャは含まない(47都道府県のみ)。"
            ),
            "derived_via": [
                {
                    "geojson": "data/processed/area_boundaries_R7.geojson",
                    "script": "tools/build_area_boundaries.py",
                },
                {
                    "csv": "data/processed/prefecture_basic.csv",
                    "meta": "data/processed/prefecture_basic.csv.meta.json",
                },
            ],
        },
        "fields": FIELD_DESCRIPTIONS,
        "feature_count": EXPECTED_PREFECTURE_COUNT,
        "verification": verification,
    }


def build_and_write(out_path: Path) -> Path:
    """入力を読み込み・ディゾルブ・検証し、`out_path`へGeoJSONを書き出す。

    戻り値: 書き出したファイルのPath。
    """
    npx = shutil.which("npx")
    if npx is None:
        raise SystemExit("npx が見つかりません（Node.js をインストールしてください）")

    mapshaper_ver = subprocess.run(
        [npx, "-y", "mapshaper", "-v"], capture_output=True, text=True, check=True, shell=False
    ).stdout.strip()

    pref_names = load_prefecture_names()
    print(f"[ok] prefecture_basic.csv 読み込み: {len(pref_names)}都道府県(全国を除く)")

    area_features, area_metadata = load_area_features()
    print(f"[ok] area_boundaries_R7.geojson 読み込み: {len(area_features)}区域")

    area_pref_codes = {normalize_pref_code(f["properties"]["pref_code"]) for f in area_features}
    area_km2_by_code = area_km2_by_pref(area_features)

    with tempfile.TemporaryDirectory() as td:
        raw_out = Path(td) / "prefecture_boundaries_raw.geojson"
        _run_mapshaper(
            npx,
            [
                str(AREA_BOUNDARIES_GEOJSON),
                "-dissolve", "fields=pref_code",
                "-clean",
                "-o", "format=geojson", "precision=0.0001", str(raw_out),
            ],
        )
        gj = json.loads(raw_out.read_text(encoding="utf-8"))

    features = gj["features"]
    print(f"[ok] ディゾルブ結果: {len(features)}フィーチャ")

    enriched = []
    for feat in features:
        raw_code = feat["properties"].get("pref_code")
        if raw_code in (None, ""):
            raise SystemExit("ディゾルブ結果にpref_codeが空のフィーチャがあります")
        code = normalize_pref_code(raw_code)
        name = pref_names.get(code)
        if name is None:
            raise SystemExit(
                f"ディゾルブ結果にprefecture_basic.csvに無い都道府県コードがあります: {code}"
            )
        enriched.append(
            {
                "type": "Feature",
                "properties": {
                    "pref_code": code,
                    "pref_name": name,
                    "boundary_source": BOUNDARY_SOURCE,
                },
                "geometry": feat["geometry"],
            }
        )
    enriched.sort(key=lambda f: f["properties"]["pref_code"])  # 決定的な出力順

    validate_output(enriched, pref_names, area_pref_codes)
    print(
        f"[ok] 検証1〜3: フィーチャ数{EXPECTED_PREFECTURE_COUNT}・pref_codeの一意性/"
        "集合一致(prefecture_basic.csv・area_boundaries_R7.geojson)・ジオメトリ型を確認"
    )

    total_area, total_pref, total_diff_pct, worst_code, worst_diff_pct = validate_area_conservation(
        enriched, area_km2_by_code
    )
    print(
        f"[ok] 検証4・5: 面積保存 全国 構想区域合計={total_area:.2f}km2 "
        f"都道府県合計={total_pref:.2f}km2 差={total_diff_pct:.4f}% / "
        f"県別最大差={worst_diff_pct:.4f}%({worst_code})(許容差{TOLERANCE_PCT}%以内)"
    )

    verification = {
        "feature_count": len(enriched),
        "area_conservation_km2": {
            "areas_339_total": round(total_area, 2),
            "prefectures_47_total": round(total_pref, 2),
            "total_diff_pct": round(total_diff_pct, 4),
            "worst_prefecture": worst_code,
            "worst_prefecture_diff_pct": round(worst_diff_pct, 4),
            "tolerance_pct": TOLERANCE_PCT,
        },
    }
    metadata = build_metadata(area_metadata, mapshaper_ver, verification)
    gj_out = {"type": "FeatureCollection", "metadata": metadata, "features": enriched}

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(gj_out, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    print(f"[ok] 出力: {out_path}")
    print(f"     フィーチャ数: {len(enriched)}")
    print(f"     サイズ: {out_path.stat().st_size / 1_000_000:.1f} MB")
    print(f"     sha256 = {sha256(out_path)}")

    return out_path


def main() -> None:
    build_and_write(OUT_PATH)


if __name__ == "__main__":
    main()
