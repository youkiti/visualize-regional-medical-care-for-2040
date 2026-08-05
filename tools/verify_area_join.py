# -*- coding: utf-8 -*-
"""339構想区域(`data/processed/area_basic.csv`)と335二次医療圏境界
(`data/processed/iryoken2_A38-20.geojson`)の突合を検証する。

M2チャンクB。入力はすべて `data/processed/` 配下の加工済みデータのみで、
生Excel(`R7/`)や1.13GBの元zip(`ksj/A38-20/A38-20_GML.zip`)には一切触れない
(zipはGit管理外でありCI(Ubuntu)に存在しないため、このスクリプトが依存すると
CIで必ず失敗する)。由来情報は各CSVの `.meta.json` と geojson内 `metadata` の
既に確定済みの値を読むだけで、`verify_source()`(SHA-256再計算)は呼ばない。

処理内容:
  1. `area_basic.csv`(339行)と `iryoken2_A38-20.geojson`(335フィーチャ)を
     読み込み、構想区域コード(`area_code`)と二次医療圏コード(`A38b_003`)を
     `tools.lib.codes.normalize_area_code` で正規化してから完全外部結合する
  2. 突合結果(matched/area_only/geo_only)を `data/processed/area_geo_join.csv`
     (+ `.meta.json`)へ出力する
  3. `area_basic.csv` の推計流出/流入患者割合が原典で `'XXX'`(未算出)に
     なっている区域集合が、境界のない区域(area_only)の集合と完全に一致する
     ことを検証する(突合結果とは独立した経路で得られる裏付け)
  4. `area_beds.csv`(構想区域別)を都道府県コードで集計し、`prefecture_beds.csv`
     (都道府県別、M1の成果物)と突合して集計整合を検証する
  5. 上記すべての実測値を埋め込んだ検証レポート `doc/JOIN_VERIFICATION.md` を
     生成する(生成日時は埋め込まない。埋め込むと再生成のたびに差分が出て
     バイト一致の再現性テストが翌日に壊れるため)

⚠ 三重県の対応表(`MIE_OLD_TO_NEW`)について: A38(令和2年度)の二次医療圏
4圏域(2401北勢・2402中勢伊賀・2403南勢志摩・2404東紀州)と、R7の構想区域
8区域(2405桑員〜2412東紀州)は、集合としては突合結果(area_only 8件/
geo_only 4件)から特定できる。「どの新区域がどの旧圏域に含まれるか」という
個々の対応関係は、入力データ(area_basic.csv・iryoken2_A38-20.geojson)
だけからは導出できないため、三重県公式資料(三重県医療政策課「資料４ 第８次
三重県医療計画における二次医療圏の設定について」`mie/001092203.pdf` 9ページ
「現行の二次医療圏・構想区域」)を一次資料として確認した(M2 チャンクC前工程)。
対応表(29市町の内訳を含む)は `data/reference/mie_area_municipalities.csv`
に機械可読な形で保持し、`tools/build_mie_area_municipalities.py` が
網羅性・一意性・入れ子の整合・名称の一致・医療機関所在地との突合という
5つの検証をすべて実施したうえで出力している(詳細は同スクリプトのdocstring、
検証結果は同CSVの `.meta.json` の `verification` を参照)。
`MIE_OLD_TO_NEW` はこのCSVから `load_mie_old_to_new()` で**導出**する
(ハードコードしない)。このスクリプトでは実行のたびに、導出した
`MIE_OLD_TO_NEW` が突合結果(geo_only/area_only の実際のコード集合)と
完全一致することも検証し、ずれていたら例外で中断する(将来データが変わって
対応表が古いまま誤った注記を静かに出力することを防ぐための、独立したドリフト
検知)。境界そのものの合成(ポリゴンのディゾルブ)は `tools/build_area_boundaries.py`
(M2 チャンクC2)が行い、339構想区域すべての境界を持つ
`data/processed/area_boundaries_R7.geojson` を生成済み。このスクリプトは
その成果物の `metadata`(検証済みの実測値)を読んでレポートに反映するのみで、
1.13GBの元zipやNode.jsには依存しない。

必要環境: Python 3.11+

使い方:
    python tools/verify_area_join.py
"""
import csv
import datetime
import json
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.build_area_boundaries import BOUNDARY_SOURCE_DEFAULT, BOUNDARY_SOURCE_MIE
from tools.lib.codes import normalize_area_code
from tools.lib.provenance import REPO_ROOT, write_csv_with_meta

PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DOC_DIR = REPO_ROOT / "doc"

AREA_BASIC_CSV = PROCESSED_DIR / "area_basic.csv"
AREA_BEDS_CSV = PROCESSED_DIR / "area_beds.csv"
PREFECTURE_BEDS_CSV = PROCESSED_DIR / "prefecture_beds.csv"
GEOJSON_PATH = PROCESSED_DIR / "iryoken2_A38-20.geojson"
AREA_BOUNDARIES_GEOJSON = PROCESSED_DIR / "area_boundaries_R7.geojson"
MIE_AREA_MUNI_CSV = REPO_ROOT / "data" / "reference" / "mie_area_municipalities.csv"
MIE_AREA_MUNI_META = Path(str(MIE_AREA_MUNI_CSV) + ".meta.json")

# デフォルトの出力先(`main()` が使う。テストはコミット済み成果物の参照や
# `build_and_write()` への一時ディレクトリ渡しに使う)
OUT_CSV = PROCESSED_DIR / "area_geo_join.csv"
OUT_DOC = DOC_DIR / "JOIN_VERIFICATION.md"

JOIN_STATUS_ORDER = ["matched", "area_only", "geo_only"]


def load_mie_old_to_new(csv_path: Path = MIE_AREA_MUNI_CSV) -> dict:
    """三重県: A38(令和2年度)の旧4圏域 -> R7構想区域(新8区域)コードの対応を
    `data/reference/mie_area_municipalities.csv`(三重県公式資料からの手転記+
    A38・医療機関所在地との整合を検証済み、`tools/build_mie_area_municipalities.py`
    参照)から導出する。

    同じ `area_code` を持つ行がすべて同じ `parent_iryoken2_code` を持つことを
    確認しながら集計する(CSV内部の矛盾を検知するための最低限のガード)。
    戻り値は旧圏域コード昇順、各値は新区域コード昇順の `{旧圏域コード: [新区域コード, ...]}`。
    """
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    area_to_parent = {}
    for row in rows:
        area_code = row["area_code"]
        parent = row["parent_iryoken2_code"]
        if area_code in area_to_parent and area_to_parent[area_code] != parent:
            raise ValueError(
                f"{csv_path}: 構想区域{area_code}が複数の二次医療圏コードに対応しています"
                f"({area_to_parent[area_code]} と {parent})"
            )
        area_to_parent[area_code] = parent

    grouped = defaultdict(list)
    for area_code, parent in area_to_parent.items():
        grouped[parent].append(area_code)
    return {parent: sorted(areas) for parent, areas in sorted(grouped.items())}


# 三重県: A38(令和2年度)の旧4圏域 -> R7構想区域(新8区域)コードの対応。
# `data/reference/mie_area_municipalities.csv`(三重県公式資料に基づく検証済みの
# 対応表)から導出する(ハードコードしない)。`main()` 内で実行時に、この対応表が
# 突合結果(geo_only/area_only)の実際のコード集合と一致することも検証する
# (ドリフト検知、詳細はモジュールdocstring参照)。
MIE_OLD_TO_NEW = load_mie_old_to_new()

FIELDS_JOIN = {
    "join_status": (
        "突合結果。matched=構想区域コードと二次医療圏コードが一致 / "
        "area_only=構想区域(area_basic.csv)側にのみ存在(対応する境界がない) / "
        "geo_only=二次医療圏境界(iryoken2_A38-20.geojson)側にのみ存在"
        "(対応する構想区域コードがない)"
    ),
    "area_code": "構想区域コード(ゼロ埋め4桁の文字列)。geo_only行では空",
    "area_name": "構想区域名(area_basic.csvより)。geo_only行では空",
    "pref_code": (
        "都道府県コード(ゼロ埋め2桁の文字列)。geo_only行はarea_basic.csvに"
        "対応行がないため、二次医療圏コードの先頭2桁から補っている"
    ),
    "pref_name": "都道府県名。geo_only行では空(pref_codeから機械的に補うと出典外の情報になるため空のまま)",
    "geo_code": "二次医療圏コード(ゼロ埋め4桁の文字列、A38b_003)。area_only行では空",
    "geo_name": "二次医療圏名(A38b_004)。area_only行では空",
    "note": (
        "matched行は空。area_only/geo_only行には、区割りが変わった経緯"
        "(三重県の細分化)に関する日本語の説明を入れる。旧圏域↔新区域の"
        "個々の対応は三重県公式資料(mie/001092203.pdf)に基づき検証済み"
        "(詳細はdoc/JOIN_VERIFICATION.md参照)"
    ),
}


def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _r7_source(meta: dict, label: str) -> dict:
    """`<csv>.meta.json` の `source` から published_fy=='R7' の要素を返す。

    `area_basic.csv`・`area_beds.csv`・`prefecture_beds.csv` はR6/R7が
    published_fy で並存するようになった(M9)ため、`source` が単一のdictでは
    なくリストになっている。このスクリプトはR7限定の検証・レポートなので、
    R7の出典情報だけを取り出す。
    """
    source = meta["source"]
    for entry in source:
        if entry.get("published_fy") == "R7":
            return entry
    raise ValueError(f"{label}: sourceにpublished_fy=='R7'の要素が見つかりません")


def load_area_basic():
    """`area_basic.csv` を読み、正規化済み構想区域コードをキーにした辞書を返す。

    戻り値: (area_by_code, rows, meta)
      area_by_code: {area_code(正規化済み): 行dict}
      rows: R7行のみ(dictのリスト、CSV原文順)
      meta: `area_basic.csv.meta.json` の内容
    """
    with open(AREA_BASIC_CSV, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    # area_basic.csv はR6/R7が published_fy で並存するようになった(M9)。
    # このスクリプトはR7の構想区域とA38二次医療圏の突合を検証するものなので、
    # 対象とするR7行のみを読む(R6行を含めるとarea_codeが重複してしまう)。
    rows = [r for r in rows if r["published_fy"] == "R7"]
    area_by_code = {}
    for row in rows:
        code = normalize_area_code(row["area_code"])
        if code in area_by_code:
            raise ValueError(f"area_basic.csv: 構想区域コード{code}が重複しています")
        area_by_code[code] = row
    meta = _read_json(Path(str(AREA_BASIC_CSV) + ".meta.json"))
    return area_by_code, rows, meta


def load_geojson():
    """`iryoken2_A38-20.geojson` を読み、正規化済み二次医療圏コードをキーに
    した辞書を返す(ジオメトリは使わないため保持しない)。

    戻り値: (geo_by_code, metadata)
      geo_by_code: {geo_code(正規化済み): properties dict}
      metadata: geojsonファイル冒頭の `metadata` メンバー
    """
    data = _read_json(GEOJSON_PATH)
    geo_by_code = {}
    for feature in data["features"]:
        props = feature["properties"]
        code = normalize_area_code(props["A38b_003"])
        if code in geo_by_code:
            raise ValueError(f"iryoken2_A38-20.geojson: 二次医療圏コード{code}が重複しています")
        geo_by_code[code] = props
    return geo_by_code, data["metadata"]


def load_area_boundaries_metadata(path: Path = AREA_BOUNDARIES_GEOJSON) -> dict:
    """`area_boundaries_R7.geojson`(339構想区域境界、`tools/build_area_boundaries.py`
    の成果物、M2 チャンクC2)の `metadata` を読む。

    ファイルは4.5MBあるため、面積等の再計算はせず、生成時に計算・検証済みの値
    (フィーチャ数・三重県の新旧面積整合等)を `metadata` からそのまま使う。

    `build_area_boundaries.py` は1.13GBの元zip(Git管理外)とNode.jsを要するため
    CIでは実行できない。生成済みファイルは通常コミットされているはずだが、万一
    存在しない場合でもこのスクリプト全体が原因不明なトレースバックだけで落ちる
    ことのないよう、再生成手順を示す分かりやすいメッセージを添えて例外を送出する
    (このスクリプトはCIでも動くため)。
    """
    if not path.exists():
        raise FileNotFoundError(
            f"{path} が見つかりません。先に "
            "`PYTHONIOENCODING=utf-8 python tools/build_area_boundaries.py`"
            "(要 Node.js・要 ksj/A38-20/A38-20_GML.zip[Git管理外])を実行するか、"
            "コミット済みの data/processed/area_boundaries_R7.geojson を取得してください。"
        )
    return _read_json(path)["metadata"]


def load_beds_csv(path: Path):
    """病床数CSV(`area_beds.csv` / `prefecture_beds.csv`)を読み、dictのリストで返す。

    両CSVともR6/R7が published_fy で並存するようになった(M9)。このスクリプトは
    R7の構想区域と都道府県の集計整合のみを検証するものなので、対象とするR7行の
    みを返す(R6行が混ざると集計値もキー数も変わってしまう)。
    """
    with open(path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r["published_fy"] == "R7"]


def compute_join(area_by_code: dict, geo_by_code: dict):
    """構想区域コードと二次医療圏コードの完全外部結合を行う。

    戻り値: (matched, area_only, geo_only) はいずれもコードの `sorted` list。
    """
    area_codes = set(area_by_code)
    geo_codes = set(geo_by_code)
    matched = sorted(area_codes & geo_codes)
    area_only = sorted(area_codes - geo_codes)
    geo_only = sorted(geo_codes - area_codes)
    return matched, area_only, geo_only


def _verify_mie_mapping_matches_join(area_only: list, geo_only: list):
    """`MIE_OLD_TO_NEW` が実際の突合結果(area_only/geo_only)と完全一致することを検証する。

    ずれていたら(想定外の区域が増減していたら)`ValueError` で中断する。
    これにより、対応表が古いまま誤った注記を静かに出力することを防ぐ。
    """
    mapped_old = set(MIE_OLD_TO_NEW)
    mapped_new = {code for codes in MIE_OLD_TO_NEW.values() for code in codes}
    if mapped_old != set(geo_only):
        raise ValueError(
            "MIE_OLD_TO_NEWの旧圏域コードが実際のgeo_only集合と一致しません: "
            f"対応表={sorted(mapped_old)} 実際={geo_only}"
        )
    if mapped_new != set(area_only):
        raise ValueError(
            "MIE_OLD_TO_NEWの新区域コードが実際のarea_only集合と一致しません: "
            f"対応表={sorted(mapped_new)} 実際={area_only}"
        )


def build_join_rows(area_by_code, geo_by_code, matched, area_only, geo_only):
    """`area_geo_join.csv` の行(dictのリスト、ヘッダー順の値を持つ)を組み立てる。

    並び順は決定的: join_status を matched/area_only/geo_only の順に固定し、
    各グループ内はコード昇順(`matched`/`area_only`/`geo_only` はいずれも
    `compute_join` が返す時点で既にソート済み)。
    """
    new_to_old = {new: old for old, news in MIE_OLD_TO_NEW.items() for new in news}

    rows = []
    for code in matched:
        area_row = area_by_code[code]
        geo_props = geo_by_code[code]
        rows.append(
            {
                "join_status": "matched",
                "area_code": code,
                "area_name": area_row["area_name"],
                "pref_code": area_row["pref_code"],
                "pref_name": area_row["pref_name"],
                "geo_code": code,
                "geo_name": geo_props["A38b_004"],
                "note": "",
            }
        )

    for code in area_only:
        area_row = area_by_code[code]
        old_code = new_to_old[code]
        old_name = geo_by_code[old_code]["A38b_004"]
        is_split = len(MIE_OLD_TO_NEW[old_code]) > 1
        if is_split:
            relation = "R7で細分化されたため境界なし"
        else:
            relation = "R7でコードが変わったため境界なし(細分化ではなく1対1)"
        note = (
            f"二次医療圏(令和2年度)では{old_code}{old_name}に含まれる区域"
            "(三重県公式資料により検証済み。doc/JOIN_VERIFICATION.md 参照)。"
            f"{relation}"
        )
        rows.append(
            {
                "join_status": "area_only",
                "area_code": code,
                "area_name": area_row["area_name"],
                "pref_code": area_row["pref_code"],
                "pref_name": area_row["pref_name"],
                "geo_code": "",
                "geo_name": "",
                "note": note,
            }
        )

    for code in geo_only:
        geo_props = geo_by_code[code]
        new_codes = MIE_OLD_TO_NEW[code]
        new_labels = "・".join(f"{c}{area_by_code[c]['area_name']}" for c in new_codes)
        if len(new_codes) > 1:
            action = f"{new_labels}の{len(new_codes)}構想区域に細分化された"
        else:
            action = f"{new_labels}へコードが変わった(細分化ではなく1対1)"
        note = (
            f"R7では{action}"
            "(三重県公式資料により検証済み。doc/JOIN_VERIFICATION.md 参照。"
            "境界(令和2年度時点)は残るが、対応する構想区域コードはない)"
        )
        rows.append(
            {
                "join_status": "geo_only",
                "area_code": "",
                "area_name": "",
                "pref_code": code[:2],
                "pref_name": "",
                "geo_code": code,
                "geo_name": geo_props["A38b_004"],
                "note": note,
            }
        )

    return rows


def compute_xxx_area_codes(area_rows):
    """`area_basic.csv` で推計流出/流入患者割合が原典'XXX'(未算出)の区域コード集合を返す。"""
    codes = set()
    for row in area_rows:
        if row["outflow_rate_source_value"] == "XXX" or row["inflow_rate_source_value"] == "XXX":
            codes.add(normalize_area_code(row["area_code"]))
    return codes


def aggregate_area_beds_by_pref(area_beds_rows):
    """構想区域別病床数を都道府県コードで集計する。

    キー: (pref_code, bed_function, series, year) -> beds合計
    """
    agg = defaultdict(int)
    for row in area_beds_rows:
        key = (row["pref_code"], row["bed_function"], row["series"], int(row["year"]))
        agg[key] += int(row["beds"])
    return dict(agg)


def prefecture_beds_lookup(prefecture_beds_rows):
    """都道府県別病床数を辞書化する(全国'00'は除外、構想区域側に存在しないため)。

    キー: (pref_code, bed_function, series, year) -> beds
    """
    lookup = {}
    for row in prefecture_beds_rows:
        if row["pref_code"] == "00":
            continue
        key = (row["pref_code"], row["bed_function"], row["series"], int(row["year"]))
        lookup[key] = int(row["beds"])
    return lookup


def compare_aggregates(area_agg: dict, pref_lookup: dict):
    """構想区域集計と都道府県公表値を突合する。

    戻り値: dict with:
      common_keys: 両方に存在するキーの集合
      mismatches: [(key, area_value, pref_value), ...](不一致のみ)
      only_in_area / only_in_pref: 片方にしか存在しないキーの集合(想定は空)
      by_series_year: {(series, year): {"key_count": int, "mismatch_count": int}}
    """
    area_keys = set(area_agg)
    pref_keys = set(pref_lookup)
    common_keys = area_keys & pref_keys
    only_in_area = area_keys - pref_keys
    only_in_pref = pref_keys - area_keys

    mismatches = []
    by_series_year = defaultdict(lambda: {"key_count": 0, "mismatch_count": 0})
    for key in common_keys:
        pref_code, bed_function, series, year = key
        by_series_year[(series, year)]["key_count"] += 1
        if area_agg[key] != pref_lookup[key]:
            mismatches.append((key, area_agg[key], pref_lookup[key]))
            by_series_year[(series, year)]["mismatch_count"] += 1

    return {
        "common_keys": common_keys,
        "mismatches": mismatches,
        "only_in_area": only_in_area,
        "only_in_pref": only_in_pref,
        "by_series_year": dict(by_series_year),
    }


def _fmt_pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "-"
    return f"{numerator / denominator * 100:.2f}%"


def build_report_markdown(
    *,
    area_meta: dict,
    area_beds_meta: dict,
    pref_beds_meta: dict,
    geo_metadata: dict,
    area_rows,
    area_beds_rows,
    pref_beds_rows,
    geo_by_code,
    area_by_code,
    matched,
    area_only,
    geo_only,
    join_rows,
    xxx_codes,
    agg_result,
    mie_meta: dict,
    boundaries_metadata: dict,
) -> str:
    """`doc/JOIN_VERIFICATION.md` の本文を組み立てる(生成日時は含めない)。

    `mie_meta` は `data/reference/mie_area_municipalities.csv.meta.json` の内容
    (三重県公式資料の出典情報と、検証1〜6の実測値を持つ `verification` を含む)。
    `boundaries_metadata` は `area_boundaries_R7.geojson` 内 `metadata`
    (`load_area_boundaries_metadata()` が返す値。フィーチャ数・三重県の
    新旧面積整合等の検証済み実測値を持つ)。
    """
    # area_basic.csv・area_beds.csv・prefecture_beds.csv はR6/R7が並存するように
    # なった(M9)ため source がリストになっている。このレポートはR7限定の検証
    # なので、R7の出典情報だけを取り出す。
    area_source = _r7_source(area_meta, "area_basic.csv")
    area_beds_source = _r7_source(area_beds_meta, "area_beds.csv")
    pref_beds_source = _r7_source(pref_beds_meta, "prefecture_beds.csv")

    lines = []
    a = lines.append

    a("# 構想区域 × 二次医療圏境界 突合検証レポート")
    a("")
    a("このファイルは `python tools/verify_area_join.py` が生成する。手で編集しないこと。")
    a("再生成コマンド: `PYTHONIOENCODING=utf-8 python tools/verify_area_join.py`")
    a("")

    # --- 1. 目的と対象データ ------------------------------------------------
    a("## 1. 目的と対象データ")
    a("")
    a(
        "厚生労働省「R7構想区域データ」(`data/processed/area_basic.csv`、339構想区域)と"
        "国土数値情報「二次医療圏境界(令和2年度、A38-20)」の簡略化GeoJSON"
        "(`data/processed/iryoken2_A38-20.geojson`、335二次医療圏)を、構想区域コード/"
        "二次医療圏コードで突合し、可視化に境界データをそのまま使えるかを検証する。"
        "あわせて構想区域別病床数の都道府県集計値が、都道府県別病床数(M1の成果物)と"
        "一致するかも検証する(パーサの正しさの裏付け)。"
    )
    a("")
    a(
        "本レポートが扱う範囲には、この突合結果をもとに339構想区域すべての境界を"
        "用意した `data/processed/area_boundaries_R7.geojson`"
        f"({boundaries_metadata['feature_count']}フィーチャ、M2 チャンクC2の成果物)も"
        "含む。生成方法・検証結果は「5. 可視化への影響と対応方針」で扱う。"
    )
    a("")
    a(
        "入力ファイル(`data/processed/` 配下の加工済みデータと、"
        "`data/reference/mie_area_municipalities.csv`(三重県公式資料に基づく検証済み"
        "対応表)。生Excel・元zipは参照しない):"
    )
    a("")
    a("| ファイル | 行数/フィーチャ数 | 元データ | 元データのSHA-256 |")
    a("|---|---|---|---|")
    a(
        f"| `area_basic.csv` | {len(area_rows)}行 | "
        f"{area_source['source_file']}("
        f"{area_source['fiscal_year']}) | `{area_source['source_sha256']}` |"
    )
    a(
        f"| `area_beds.csv` | {len(area_beds_rows)}行 | "
        f"{area_beds_source['source_file']}("
        f"{area_beds_source['fiscal_year']}) | `{area_beds_source['source_sha256']}` |"
    )
    a(
        f"| `prefecture_beds.csv` | {len(pref_beds_rows)}行 | "
        f"{pref_beds_source['source_file']}("
        f"{pref_beds_source['fiscal_year']}) | `{pref_beds_source['source_sha256']}` |"
    )
    a(
        f"| `iryoken2_A38-20.geojson` | {geo_metadata['feature_count']}フィーチャ | "
        f"{geo_metadata['source']['source_file']}({geo_metadata['source']['data_year']}) | "
        f"`{geo_metadata['source']['source_sha256']}` |"
    )
    mie_pdf_source = mie_meta["source"]["inputs"][0]
    a(
        f"| `mie_area_municipalities.csv`(`data/reference/`) | {mie_meta['row_count']}行 | "
        f"{mie_pdf_source['title']}({mie_pdf_source['publisher']}) | "
        f"`{mie_pdf_source['source_sha256']}` |"
    )
    a("")
    a(
        "GeoJSONの由来メタデータ(ファイル内 `metadata`)には、上記に加えて加工手順"
        f"(`{geo_metadata['processing']['tool']}` による簡略化等)も記録されている。"
        "詳細は `iryoken2_A38-20.geojson` の `metadata` を参照。"
        "`mie_area_municipalities.csv` の由来・検証結果は "
        "`data/reference/mie_area_municipalities.csv.meta.json` の "
        "`source`/`verification` を参照。"
    )
    a("")

    # --- 2. コード突合の結果 -------------------------------------------------
    a("## 2. コード突合の結果")
    a("")
    total = len(matched) + len(area_only) + len(geo_only)
    a(f"構想区域コード(339件)と二次医療圏コード(335件)を正規化のうえ完全外部結合した結果:")
    a("")
    a("| 区分 | 件数 | 内容 |")
    a("|---|---|---|")
    a(f"| matched | {len(matched)} | コード・名称ともに一致する構想区域 |")
    a(f"| area_only | {len(area_only)} | 構想区域側にのみ存在(対応する境界がない) |")
    a(f"| geo_only | {len(geo_only)} | 二次医療圏境界側にのみ存在(対応する構想区域コードがない) |")
    a(f"| 合計(`area_geo_join.csv` の行数) | {total} | |")
    a("")

    name_mismatches = [c for c in matched if area_by_code[c]["area_name"] != geo_by_code[c]["A38b_004"]]
    a(
        f"matched {len(matched)}件は**名称も完全一致**している(構想区域名 `area_name` と"
        f"二次医療圏名 `A38b_004` の名称不一致は{len(name_mismatches)}件)。"
    )
    a("")
    total_muni_count = sum(
        len(geo_by_code[c]["A38b_002"].split(",")) for c in sorted(MIE_OLD_TO_NEW)
    )
    a(
        f"不一致の{len(area_only)}区域・{len(geo_only)}圏域はすべて三重県。A38(令和2年度)の"
        f"二次医療圏4圏域(構成市区町村は合計{total_muni_count}市町)と、R7の構想区域8区域"
        "(2405桑員〜2412東紀州)が、この不一致に対応している。"
    )
    a("")
    verification = mie_meta["verification"]
    coverage = verification["coverage"]
    uniqueness = verification["uniqueness"]
    nesting = verification["nesting"]
    name_match = verification["name_match"]
    institution = verification["institution_corroboration"]
    residual = verification["residual_risk"]

    a(
        "**検証済みの事実(一次資料に基づく)**: 三重県は4つの二次医療圏(令和2年度、"
        "A38-20)と8つの構想区域(R7)を併存させており、構想区域は二次医療圏の細分"
        "(入れ子構造)である。「どの新区域がどの旧圏域に含まれるか」という個々の"
        f"対応関係(29市町の内訳を含む)は、三重県医療政策課「{mie_pdf_source['title']}」"
        f"(`mie/001092203.pdf`、{mie_pdf_source['reference_page']}、"
        f"取得日{mie_pdf_source['acquired_date']}、SHA-256 `{mie_pdf_source['source_sha256']}`)"
        "を一次資料として確認済みである。"
    )
    a("")
    a(
        "対応表は `data/reference/mie_area_municipalities.csv`"
        f"({mie_meta['row_count']}行、8構想区域×29市町)に機械可読な形で保持し、"
        "`tools/build_mie_area_municipalities.py` が以下の検証をすべて実施したうえで"
        "出力している(手転記である以上、転記ミスを機械的に検出できることが重要であり、"
        "1件でも不一致があれば例外で中断する設計)。"
    )
    a("")
    a("| # | 検証内容 | 結果(実測値) |")
    a("|---|---|---|")
    a(
        f"| 1 | 網羅性: CSVの市町コード集合とA38の三重県4圏域の構成市区町村の集合が完全一致 | "
        f"{coverage['csv_muni_count']}市町 == {coverage['a38_union_muni_count']}市町(完全一致) |"
    )
    a(f"| 2 | 一意性: 各市町コードがCSV全体でちょうど1回だけ出現 | {uniqueness['muni_count']}市町すべて重複なし |")
    a(
        f"| 3 | 入れ子の整合: 各行の`parent_iryoken2_code`がA38の実際の市町→二次医療圏の割当と一致 | "
        f"{nesting['checked']}行中、不一致{len(nesting['mismatches'])}件 |"
    )
    a(
        f"| 4 | 名称の一致: `muni_name`がA38の`A38b_002`表記と完全一致 | "
        f"{name_match['checked']}件中、不一致{len(name_match['mismatches'])}件 |"
    )
    a(
        "| 5 | 独立した裏付け: 医療機関所在地(`R7/001723127.xlsx`、三重県8シート)との突合 | "
        f"{institution['verified_muni_count']}市町を裏付け、不一致{len(institution['mismatches'])}件 |"
    )
    a("")
    a(
        "この対応表(`MIE_OLD_TO_NEW`)は本スクリプトが実行時に "
        "`data/reference/mie_area_municipalities.csv` から `load_mie_old_to_new()` で"
        "**導出**し(ハードコードしない)、突合結果(area_only 8件/geo_only 4件の"
        "実際のコード集合)と一致することも検証している(ずれていたら例外で中断する、"
        "検証3の1〜4/5とは独立したドリフト検知)。"
    )
    a("")
    a("| A38コード(令和2年度) | A38名称 | 構成市区町村 | → R7構想区域(検証済み) |")
    a("|---|---|---|---|")
    for old_code in sorted(MIE_OLD_TO_NEW):
        props = geo_by_code[old_code]
        muni_names = props["A38b_002"].split(",")
        new_codes = MIE_OLD_TO_NEW[old_code]
        new_labels = "、".join(f"{c} {area_by_code[c]['area_name']}" for c in new_codes)
        a(f"| {old_code} | {props['A38b_004']} | {'、'.join(muni_names)} | {new_labels} |")
    a("")
    a(
        "(2404東紀州と2412東紀州は名称が完全一致しており、細分化ではなく1対1で"
        "コードが変わった。他3圏域(2401北勢・2402中勢伊賀・2403南勢志摩)はそれぞれ"
        "2〜3区域に分かれる。)"
    )
    a("")

    # --- 残存リスク ---------------------------------------------------------
    a("### 残存リスク")
    a("")
    unverified_labels = "、".join(r["muni_name"] for r in residual["unverified"])
    a(
        f"上記の検証5(医療機関所在地との突合)は、病床機能報告の対象医療機関がある市町"
        "のみを独立に裏付けられる。対象医療機関がなく裏付けが取れない市町は"
        f"{residual['unverified_count']}件({unverified_labels})。"
    )
    a("")
    unambiguous = residual["unambiguous_unverified"]
    unambiguous_labels = "、".join(
        f"{r['muni_name']}({r['parent_iryoken2_code']}{r['parent_iryoken2_name']})" for r in unambiguous
    )
    a(
        f"このうち{residual['unambiguous_unverified_count']}件({unambiguous_labels})は、"
        "属する旧圏域が新区域に分割されない(1対1で対応する)ため、独立した裏付けが"
        "なくても割当が一意に定まる。"
    )
    a("")
    true_risk = residual["true_residual_risk"]
    true_risk_labels = "、".join(f"{r['muni_name']}({r['area_code']}{r['area_name']})" for r in true_risk)
    a(
        f"残る{residual['true_residual_risk_count']}件({true_risk_labels})が、**真の残存"
        "リスク**である: 属する旧圏域が複数の新区域に分割されるケースに属し、かつ"
        "医療機関所在地による独立した裏付けがない市町であり、三重県公式資料PDFからの"
        "手転記のみに依拠している。監査できるよう一次資料PDF(`mie/001092203.pdf`)を"
        "リポジトリに収載している。"
    )
    a("")

    # --- 3. 独立した裏付け -----------------------------------------------
    a("## 3. 独立した裏付け: 流出入率のXXX")
    a("")
    a(
        "`area_basic.csv` の推計流出患者割合・推計流入患者割合が原典で `'XXX'`(未算出)に"
        f"なっている構想区域は{len(xxx_codes)}件({', '.join(sorted(xxx_codes))})。"
        f"境界のない構想区域(area_only、{len(area_only)}件)の集合と比較すると:"
    )
    a("")
    xxx_equals_area_only = xxx_codes == set(area_only)
    a(f"- `XXX`の区域集合 == area_only の区域集合: **{xxx_equals_area_only}**")
    a(
        "\nこれは突合(コード同士の比較)とは完全に独立した経路で得られた裏付けである: "
        "厚生労働省自身が、この8区域について細分化後の区域単位での流出入率を算出できていない"
        "(=令和2年度の二次医療圏を前提にした計算がそのまま使えない)ことを示しており、"
        "上記のコード突合結果(この8区域だけ境界がない)と符合する。"
    )
    a("")

    # --- 4. 集計整合検証 -----------------------------------------------
    a("## 4. 集計整合検証(構想区域 → 都道府県)")
    a("")
    common_keys = agg_result["common_keys"]
    mismatches = agg_result["mismatches"]
    a(
        f"`area_beds.csv` を都道府県コード×病床機能×系列×年で集計し、`prefecture_beds.csv`"
        "(全国'00'を除く)と突合した。比較キーは47都道府県×5病床機能×11系列"
        "(実績9年+見込量1年+必要数1年)の組み合わせ。"
    )
    a("")
    a("| 項目 | 件数 |")
    a("|---|---|")
    a(f"| 比較キー数 | {len(common_keys)} |")
    a(f"| 一致 | {len(common_keys) - len(mismatches)} |")
    a(f"| 不一致 | {len(mismatches)} |")
    a(
        f"| 構想区域側にのみ存在するキー(想定: 0) | {len(agg_result['only_in_area'])} |"
    )
    a(
        f"| 都道府県側にのみ存在するキー(想定: 0) | {len(agg_result['only_in_pref'])} |"
    )
    a("")

    mismatch_years = sorted({key[3] for key, _, _ in mismatches})
    mismatch_years_label = "、".join(f"{y}年" for y in mismatch_years)
    a(f"不一致{len(mismatches)}件の対象年は{mismatch_years_label}のみであり、**2024年に完全に集中している**。")
    a("")
    a("系列・年別の内訳(不一致が発生していない行が大半であることを示す):")
    a("")
    a("| 系列 | 年 | 比較キー数 | 不一致数 | 一致率 |")
    a("|---|---|---|---|---|")
    by_series_year = agg_result["by_series_year"]
    for series, year in sorted(by_series_year, key=lambda k: (k[0] != "実績", k[0], k[1])):
        stats = by_series_year[(series, year)]
        key_count = stats["key_count"]
        mismatch_count = stats["mismatch_count"]
        match_count = key_count - mismatch_count
        a(
            f"| {series} | {year} | {key_count} | {mismatch_count} | "
            f"{_fmt_pct(match_count, key_count)} |"
        )
    a("")
    non_2024_keys = [k for k in common_keys if k[3] != 2024]
    non_2024_mismatches = [m for m in mismatches if m[0][3] != 2024]
    a(
        f"2024年以外の{len(non_2024_keys)}キーは不一致{len(non_2024_mismatches)}件、"
        "すなわち**完全に一致する**(パーサの正しさの強い裏づけでもある)。"
    )
    a("")
    a("### 原因")
    a("")
    known_issue = None
    for issue in area_beds_meta.get("known_issues", []):
        if issue.get("id") == "area_beds_2024_actual_duplicated_as_2025":
            known_issue = issue
            break
    if known_issue is not None:
        a(f"`area_beds.csv.meta.json` の既知の品質問題として記録済み: {known_issue['summary']}")
        a("")
        a("証拠:")
        a("")
        for ev in known_issue["evidence"]:
            a(f"- {ev}")
        a("")
        a(f"対応: {known_issue['action']}")
    else:
        a(
            "`area_beds.csv.meta.json` に既知の品質問題として記録されているはずの"
            "`area_beds_2024_actual_duplicated_as_2025` が見つからなかった"
            "(スキーマが変わった可能性があるため要確認)。"
        )
    a("")

    # --- 5. 可視化への影響と対応方針 -----------------------------------------
    a("## 5. 可視化への影響と対応方針")
    a("")
    mie_check = boundaries_metadata["verification"]["mie_area_check_km2"]
    boundaries_feature_count = boundaries_metadata["feature_count"]
    a(
        f"- (a) R7の339構想区域すべてに境界を用意できた。`data/processed/"
        f"area_boundaries_R7.geojson`({boundaries_feature_count}フィーチャ、"
        "`tools/build_area_boundaries.py` の成果物、M2 チャンクC2)がその境界データであり、"
        f"matchedの{len(matched)}区域・三重県の{len(area_only)}区域"
        f"({area_only[0]}〜{area_only[-1]})を含むR7の339構想区域すべてをカバーする。"
    )
    a(
        f"- (b) matchedの{len(matched)}区域についても、A38の二次医療圏ポリゴン"
        "(`A38-20_2`、国土数値情報が公表済みのディゾルブ済みポリゴン)をそのまま流用するのでは"
        "なく、339区域すべてを一次医療圏レイヤ(`A38-20_1`、市区町村ポリゴン)から同一の"
        "ディゾルブ・簡略化条件で生成し直している。二つの生成方式(331区域はA38-20_2をそのまま"
        "使い、8区域だけA38-20_1から合成)を混在させると簡略化(Visvalingam)の挙動が入力ポリゴン"
        "の粒度に依存するため、三重県の県境(331区域側と8区域側の接合線)に継ぎ目"
        "(隙間・重なり)が生じうる。これを避けるため、全339区域を同一ソース・同一条件で"
        "ディゾルブしている。"
    )
    a(
        f"- (c) 三重県の{len(area_only)}区域(2405〜2412)の境界は、国土数値情報が公表している"
        "ものではなく、市区町村ポリゴンを `data/reference/mie_area_municipalities.csv`"
        "(三重県公式資料に基づく検証済みの市町対応表)の構想区域単位でディゾルブして合成した"
        "派生物である。各フィーチャの `boundary_source` で区別できる(331区域は "
        f"`{BOUNDARY_SOURCE_DEFAULT}`、三重県8区域は `{BOUNDARY_SOURCE_MIE}`)。"
    )
    a(
        f"- (d) 面積の整合: 三重県の新8区域(2405〜2412)の面積合計"
        f"{mie_check['new_area_2405_2412_total']} km² と、旧4圏域(2401〜2404)の面積合計"
        f"{mie_check['old_iryoken2_2401_2404_total']} km² の差は{mie_check['diff_pct']}%であり"
        f"(許容差{mie_check['tolerance_pct']}%以内)、境界合成によって領域の過不足が"
        "生じていないことを裏づけている。"
    )
    a(
        "- (e) 構想区域レベルの2024年実績(`area_beds.csv` の `series='実績', year=2024`)は"
        "2025年実績の複製であり信頼できないため、可視化では使わない"
        "(2025年実績、または都道府県レベルの2024年実績(`prefecture_beds.csv`)を使う)。"
    )
    a(
        "- (f) 境界の元データは令和2年度時点の市区町村界であり、それ以降の市区町村合併等は"
        "反映されていない。339区域とR7の構想区域はコード・名称とも一致するが、この限界は"
        "331区域・三重県8区域のいずれにも共通する。"
    )
    a("")

    # --- 6. 再現手順 ---------------------------------------------------
    a("## 6. 再現手順")
    a("")
    a("```bash")
    a("PYTHONIOENCODING=utf-8 python tools/verify_area_join.py")
    a("PYTHONIOENCODING=utf-8 python tools/build_area_boundaries.py   # 要 Node.js・要 ksj/A38-20 zip(Git管理外)")
    a("```")
    a("")
    a(
        "`build_area_boundaries.py` は1.13GBのzip(Git管理外)とNode.jsを必要とするため、"
        "CIでは実行されない。生成済みの `area_boundaries_R7.geojson` に対する検証は "
        "`tools/tests/test_area_boundaries.py` がCIで常時実行する。"
    )
    a("")
    a(
        "上記の実測値(331/8/4の内訳、2585キー中230件の不一致等)は "
        "`tools/tests/test_verify_area_join.py` にpytestの期待値として固定してあり、"
        "`pytest` で継続的に検証される。"
    )
    a("")

    return "\n".join(lines) + "\n"


def build_and_write(out_dir: Path, doc_dir: Path) -> dict:
    """全処理(読み込み→突合→検証→出力)を実行する。

    `out_dir` に `area_geo_join.csv`(+`.meta.json`)を、`doc_dir` に
    `JOIN_VERIFICATION.md` を出力する。テスト(再現性の検証)から
    一時ディレクトリを渡して呼べるよう、出力先をパラメータ化してある
    (`tools/parse_area_beds.py` の `build_and_write(source_key, out_dir)` と
    同じ流儀)。

    戻り値: {"csv": ..., "meta": ..., "doc": ...} の Path 辞書。
    """
    out_dir = Path(out_dir)
    doc_dir = Path(doc_dir)

    print("[ok] 入力読み込み開始(生Excel・元zipには触れない)")
    area_by_code, area_rows, area_meta = load_area_basic()
    print(f"[ok] area_basic.csv 読み込み: {len(area_rows)}行")

    area_beds_rows = load_beds_csv(AREA_BEDS_CSV)
    area_beds_meta = _read_json(Path(str(AREA_BEDS_CSV) + ".meta.json"))
    print(f"[ok] area_beds.csv 読み込み: {len(area_beds_rows)}行")

    pref_beds_rows = load_beds_csv(PREFECTURE_BEDS_CSV)
    pref_beds_meta = _read_json(Path(str(PREFECTURE_BEDS_CSV) + ".meta.json"))
    print(f"[ok] prefecture_beds.csv 読み込み: {len(pref_beds_rows)}行")

    geo_by_code, geo_metadata = load_geojson()
    print(f"[ok] iryoken2_A38-20.geojson 読み込み: {len(geo_by_code)}フィーチャ")

    mie_meta = _read_json(MIE_AREA_MUNI_META)
    print(
        f"[ok] mie_area_municipalities.csv.meta.json 読み込み: "
        f"{mie_meta['row_count']}行(三重県公式資料に基づく検証済み対応表)"
    )

    boundaries_metadata = load_area_boundaries_metadata()
    print(
        f"[ok] area_boundaries_R7.geojson metadata 読み込み: "
        f"{boundaries_metadata['feature_count']}フィーチャ"
    )

    matched, area_only, geo_only = compute_join(area_by_code, geo_by_code)
    print(
        f"[ok] コード突合: matched={len(matched)} area_only={len(area_only)} "
        f"geo_only={len(geo_only)}"
    )
    assert len(matched) + len(area_only) == len(area_by_code)
    assert len(matched) + len(geo_only) == len(geo_by_code)

    _verify_mie_mapping_matches_join(area_only, geo_only)
    print("[ok] 三重県対応表(MIE_OLD_TO_NEW)が実際の突合結果と一致することを確認")

    xxx_codes = compute_xxx_area_codes(area_rows)
    xxx_equals_area_only = xxx_codes == set(area_only)
    print(
        f"[ok] 独立裏付け確認: 流出入率XXXの区域集合(={len(xxx_codes)}件) == "
        f"area_only 集合: {xxx_equals_area_only}"
    )

    area_agg = aggregate_area_beds_by_pref(area_beds_rows)
    pref_lookup = prefecture_beds_lookup(pref_beds_rows)
    agg_result = compare_aggregates(area_agg, pref_lookup)
    print(
        f"[ok] 集計整合検証: 比較キー={len(agg_result['common_keys'])} "
        f"不一致={len(agg_result['mismatches'])}"
    )

    join_rows = build_join_rows(area_by_code, geo_by_code, matched, area_only, geo_only)

    join_header = [
        "join_status",
        "area_code",
        "area_name",
        "pref_code",
        "pref_name",
        "geo_code",
        "geo_name",
        "note",
    ]
    join_tuples = [tuple(row[h] if row[h] != "" else None for h in join_header) for row in join_rows]

    today = datetime.date.today().isoformat()
    # area_basic.csv は source がリストになった(M9)ため、R7の出典情報だけを取り出す
    # (area_geo_join.csv自体はR7限定のデータセットであり、この出力形は従来どおり
    # 単一のdictを保つ)。
    area_source_r7 = _r7_source(area_meta, "area_basic.csv")
    source = {
        "name": "構想区域(area_basic.csv) × 二次医療圏境界(iryoken2_A38-20.geojson) の完全外部結合",
        "inputs": [
            {
                "file": "data/processed/area_basic.csv",
                "row_count": len(area_rows),
                "source_file": area_source_r7["source_file"],
                "source_sha256": area_source_r7["source_sha256"],
            },
            {
                "file": "data/processed/iryoken2_A38-20.geojson",
                "feature_count": geo_metadata["feature_count"],
                "source_file": geo_metadata["source"]["source_file"],
                "source_sha256": geo_metadata["source"]["source_sha256"],
            },
            {
                "file": "data/reference/mie_area_municipalities.csv",
                "row_count": mie_meta["row_count"],
                "source_file": "mie/001092203.pdf",
                "source_sha256": mie_meta["source"]["inputs"][0]["source_sha256"],
            },
        ],
        "license": (
            "厚生労働省ホームページ利用規約（政府標準利用規約準拠） "
            "https://www.mhlw.go.jp/chosakuken/index.html / "
            "国土数値情報ダウンロードサービス利用約款（オープンデータ） / "
            "三重県ウェブサイト利用規約"
        ),
    }
    processing = {
        "script": "tools/verify_area_join.py",
        "date": today,
        "steps": [
            "area_basic.csv の area_code と iryoken2_A38-20.geojson の A38b_003 を "
            "tools.lib.codes.normalize_area_code で正規化し、完全外部結合",
            "一致(matched)/構想区域側のみ(area_only)/境界側のみ(geo_only)に分類し、"
            "join_status→コード昇順で決定的に並べる",
            "area_only/geo_only には三重県の細分化前後の対応(MIE_OLD_TO_NEW、"
            "data/reference/mie_area_municipalities.csv から導出し、実行時に"
            "突合結果との一致を検証)から日本語の注記(note)を付与",
        ],
        "caveat": (
            "境界(GeoJSON)は令和2年度時点の二次医療圏であり、R7の構想区域と区割りが"
            "完全一致しない場合がある(三重県のみ、詳細は doc/JOIN_VERIFICATION.md 参照)。"
        ),
    }

    csv_path, meta_path = write_csv_with_meta(
        out_dir / "area_geo_join.csv",
        join_header,
        join_tuples,
        title="構想区域 × 二次医療圏境界 突合結果",
        source=source,
        processing=processing,
        fields=FIELDS_JOIN,
    )
    print(f"[ok] 出力: {csv_path} ({len(join_tuples)}行)")

    report_md = build_report_markdown(
        area_meta=area_meta,
        area_beds_meta=area_beds_meta,
        pref_beds_meta=pref_beds_meta,
        geo_metadata=geo_metadata,
        area_rows=area_rows,
        area_beds_rows=area_beds_rows,
        pref_beds_rows=pref_beds_rows,
        geo_by_code=geo_by_code,
        area_by_code=area_by_code,
        matched=matched,
        area_only=area_only,
        geo_only=geo_only,
        join_rows=join_rows,
        xxx_codes=xxx_codes,
        agg_result=agg_result,
        mie_meta=mie_meta,
        boundaries_metadata=boundaries_metadata,
    )
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / "JOIN_VERIFICATION.md"
    with open(doc_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(report_md)
    print(f"[ok] 出力: {doc_path}")

    return {"csv": csv_path, "meta": meta_path, "doc": doc_path}


def main():
    build_and_write(PROCESSED_DIR, DOC_DIR)


if __name__ == "__main__":
    main()
