# -*- coding: utf-8 -*-
"""可視化サイトの概観レイヤ(都道府県)が直接読み込む表示用データセット
`data/processed/prefecture_indicators_R7.json` を、既にコミット済みの加工CSV
(`prefecture_beds.csv`・`prefecture_basic.csv`・`demand_forecast.csv`・
`demand_population.csv`・`area_beds.csv`・`area_basic.csv`)と都道府県境界GeoJSON
(`prefecture_boundaries_R7.geojson`、pref_codeの一致検証にのみ使用しジオメトリは
読まない)から生成する。

構想区域側の正本(`build_web_data.py`/`build_web_demand.py`)とは別データセット
であり、それらの出力には一切触れない。

## 病床と需要で「派生の度合い」が違う

  - **病床(2025実績・2025必要数)は厚労省が都道府県単位で公表している**
    (R7/001722915.xlsx = `prefecture_beds.csv`)。本スクリプトは公表値を
    そのまま出す。構想区域の合計とも完全に一致することを検証8・9で確認する。
  - **医療需要推計(在宅（訪問診療）・外来)は構想区域単位でしか公表されていない**
    (R7/001728462.xlsx)。都道府県値は本リポジトリが構想区域の値を合計した
    **派生値**である(レセプト件数/月は加算可能な量)。この事実は
    `known_issues` の `prefecture_demand_aggregated_by_this_repository` として
    機械可読に記録し、画面の出典欄まで自動で流れるようにしてある
    (CLAUDE.md「原典側の欠陥の記録先」の例外扱い= 表示用データセットを作る
    過程で下した判断。`build_web_data.py` の
    `area_indicators_2024_actual_excluded` と同じ位置づけ)。

## 全国(00)

`prefecture_boundaries_R7.geojson` は47都道府県のみでフィーチャを持たないため、
全国は `prefectures` 配列ではなくトップレベルの `national` に分ける
(配列の要素数と境界のフィーチャ数を常に一致させ、突合を単純に保つ)。
全国の病床は原典の公表値(pref_code='00'の行)を使い、47都道府県の合計と一致
することを検証9で確認する。全国の需要は47都道府県の合計(=339区域の合計)。

## 浮動小数点の決定性

需要の合計は**必ずソート済みの順序で**足す(区域コード昇順→都道府県コード
昇順)。集合やdictのイテレーション順に依存して足すと、再生成のたびに末尾ビット
が変わって「バイト一致の再現性テスト」が壊れうるため。全国値も
「47都道府県の値の合計」として定義し、339区域を直接足した値との一致は相対
許容差付きで検証する(検証11。和の結合順序の違いで最終ビットがずれうる)。

処理内容:
  1. 上記6CSVと`prefecture_boundaries_R7.geojson`を読み込む
  2. 検証1〜13(下記)を行い、違反があれば SystemExit で中断する
  3. 47都道府県 × 5機能の実績2025/必要数2025、× 2区分 × 6年度の需要(合計値)、
     基礎情報(人口・面積・構想区域数)を組み立てる
  4. 各入力CSVの `.meta.json` から `source`・`caveat`・`known_issues` を実行時に
     読み込んで引き継ぐ(出典情報のハードコードによる二重管理を避ける)
  5. UTF-8・LF・`ensure_ascii=False`・indent=2・末尾改行1つで出力する

検証1〜13:
   1. 6CSVの全行が published_fy == 'R7'
   2. prefecture_beds.csv の (pref_code, bed_function, series, year) に重複がない
   3. pref_code集合の整合: prefecture_beds.csv / prefecture_basic.csv が48件
      (全国00を含む)、prefecture_boundaries_R7.geojson が47件、
      area_basic.csv から導いた都道府県が47件で、全国を除いて4つとも完全一致
   4. 各pref_code(48) × 5機能について実績2025・必要数2025がちょうど1行ずつ存在
   5. beds は全て非負の整数
   6. pref_code が2桁の数字文字列
   7. pref_name が prefecture_beds.csv / prefecture_basic.csv / area_basic.csv /
      境界GeoJSON の4者で一致する
   8. **47都道府県 × 5機能の実績2025・必要数2025が、構想区域(area_beds.csv)を
      都道府県で合計した値と完全に一致する**(厚労省の別々の公表ファイル
      001722915.xlsx と 001723349.xlsx の内部整合の確認でもある)
   9. **全国(00)の病床が47都道府県の合計と完全に一致する**
  10. 需要: demand_forecast.csv の全区域が既知の都道府県に属し、集計後の
      47都道府県 × 2区分 × 6年度が全て有限かつ正、基準年(2024)が0でない
  11. 全国の需要(47都道府県の合計)が、339区域を直接合計した値と一致する
      (相対許容差 `SUM_RELATIVE_TOLERANCE`。和の結合順序による最終ビットの
      ずれのみを許容する)
  12. 人口・面積が正、かつ全国(00)の人口・面積が47都道府県の合計と一致する
  13. 必要数(2025)が0の(pref_code,機能)の件数をログ出力(実データは0件だが、
      構想区域側には10件あるためエラーにはしない)

生成日時は埋め込まない(CLAUDE.md参照。再現性テストが翌日に壊れるため)。

必要環境: Python 3.11+

使い方:
    PYTHONIOENCODING=utf-8 python tools/build_web_prefecture.py
"""
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lib.provenance import REPO_ROOT, sha256

PROCESSED = REPO_ROOT / "data" / "processed"
PREFECTURE_BEDS_CSV = PROCESSED / "prefecture_beds.csv"
PREFECTURE_BASIC_CSV = PROCESSED / "prefecture_basic.csv"
DEMAND_FORECAST_CSV = PROCESSED / "demand_forecast.csv"
DEMAND_POPULATION_CSV = PROCESSED / "demand_population.csv"
AREA_BEDS_CSV = PROCESSED / "area_beds.csv"
AREA_BASIC_CSV = PROCESSED / "area_basic.csv"
PREFECTURE_BOUNDARIES_GEOJSON = PROCESSED / "prefecture_boundaries_R7.geojson"
OUT_PATH = PROCESSED / "prefecture_indicators_R7.json"

INPUT_CSVS = (
    PREFECTURE_BEDS_CSV,
    PREFECTURE_BASIC_CSV,
    DEMAND_FORECAST_CSV,
    DEMAND_POPULATION_CSV,
    AREA_BEDS_CSV,
    AREA_BASIC_CSV,
)

NATIONAL_CODE = "00"
NATIONAL_NAME = "全国"
EXPECTED_PREFECTURE_COUNT = 47
EXPECTED_AREA_COUNT = 339

FUNCTIONS = ["total", "high_acute", "acute", "recovery", "chronic"]
FUNCTION_LABELS = {
    "total": "合計",
    "high_acute": "高度急性期",
    "acute": "急性期",
    "recovery": "回復期",
    "chronic": "慢性期",
}
BED_FUNCTION_KEY_BY_JA = {ja: key for key, ja in FUNCTION_LABELS.items()}

CATEGORIES = ["home_care", "outpatient"]
CATEGORY_LABELS = {
    "home_care": "在宅（訪問診療）",
    "outpatient": "外来",
}
DEMAND_CATEGORY_KEY_BY_JA = {ja: key for key, ja in CATEGORY_LABELS.items()}

YEARS = [2024, 2030, 2035, 2040, 2045, 2050]
BASELINE_YEAR = 2024

# 検証11の許容差。全国値を「47都道府県の合計」として定義する一方、339区域を
# 直接足した値とは和の結合順序が違うため、最終ビットがずれうる。実データでの
# 実測相対差は0(完全一致)だが、将来データが変わっても結合順序の違いだけは
# 許容し、桁の異なる取りこぼし(区域の欠落など)は検出できる水準にする。
SUM_RELATIVE_TOLERANCE = 1e-9

# 引き継ぐ meta.json の source ブロックのキー。病床側4CSV・需要側2CSVは
# それぞれ同一の原典xlsxから派生しているため、グループ内では値が一致するはず
# (build_metadata() で照合する)。
SOURCE_KEYS = (
    "name",
    "publisher",
    "url",
    "page_url",
    "fiscal_year",
    "source_file",
    "source_sha256",
    "source_sheet",
    "acquired_date",
    "license",
    "original_title",
    "original_notes",
)

# 需要を都道府県で合計したことの記録。原典(厚労省)の欠陥ではなく本リポジトリが
# 下した判断だが、`build_web_data.py` の area_indicators_2024_actual_excluded と
# 同じく known_issues として機械可読に持たせ、画面の出典欄まで自動で流す。
DEMAND_AGGREGATION_ISSUE = {
    "id": "prefecture_demand_aggregated_by_this_repository",
    "scope": {
        "json": "data/processed/prefecture_indicators_R7.json",
        "fields": ["prefectures[].demand", "national.demand", "prefectures[].population_2024", "prefectures[].population_2040"],
    },
    "summary": (
        "医療需要推計(在宅（訪問診療）・外来)と、その基準人口は、厚生労働省が"
        "構想区域単位でのみ公表しており、都道府県単位の公表値は存在しない。"
        "本データセットの都道府県別・全国の需要と人口は、構想区域の値を"
        "本リポジトリが合計した派生値である"
    ),
    "evidence": [
        "R7/001728462.xlsx の2シート(在宅（訪問診療）・外来)はいずれも339構想区域の"
        "行のみを持ち、都道府県の集計行を持たない",
        "レセプト件数/月・人口はいずれも加算可能な量であり、構想区域は都道府県を"
        "重複なく分割している(area_basic.csvの339区域のpref_codeが47都道府県を覆う)",
        "病床(prefecture_beds.csv)は厚労省がR7/001722915.xlsxで都道府県単位を"
        "公表しているため合計ではなく公表値をそのまま使っており、需要とは"
        "派生の度合いが異なる",
    ],
    "action": (
        "合計値を出力し、都道府県の需要が派生値であることを本項目として記録する。"
        "合計はソート済みの順序(区域コード昇順→都道府県コード昇順)で行い、"
        "全国値が339区域の直接合計と一致することをビルド時に検証している(検証11)"
    ),
}

FIELD_DESCRIPTIONS = {
    "functions": "病床機能区分の英字キー一覧(表示順)。total=合計、他4区分の和",
    "function_labels": "機能キー -> 日本語ラベルの対応(表示用)",
    "categories": "需要区分の英字キー一覧(表示順)。home_care=在宅（訪問診療）、outpatient=外来",
    "category_labels": "区分キー -> 日本語ラベルの対応(表示用)",
    "years": (
        "需要推計の対象年(西暦4桁の整数)の配列。demand.<category>とyear_labelsの"
        "キーは年の**文字列**である点に注意(JSONのオブジェクトキーは文字列のため)"
    ),
    "year_labels": (
        "年の文字列 -> 年度ラベル原文の対応(demand_forecast.csvのyear_labelをそのまま"
        "引き継ぐ)。2024年度のみ「現状投影」が付かない(原典の区別)"
    ),
    "baseline_year": "需要の変化率算出の基準年(2024)。全都道府県×区分で0でないことを検証済み(検証10)",
    "national": (
        "全国(pref_code='00')。境界GeoJSONは47都道府県のみでフィーチャを持たないため、"
        "prefectures配列とは分けている。bedsは原典の公表値(47都道府県の合計と一致する"
        "ことを検証9で確認)、demandは47都道府県の合計(=339区域の合計、検証11)"
    ),
    "prefectures": "47都道府県(pref_codeの昇順)。全国は含まない(national参照)",
    "pref_code": "都道府県コード(ゼロ埋め2桁の文字列)。全国は'00'",
    "pref_name": "都道府県名",
    "area_count": "その都道府県に属する構想区域の数(area_basic.csvより。全国は339)",
    "population_2020": "2020年国勢調査人口(人単位の整数、prefecture_basic.csvのpopulation_2020をそのまま)",
    "area_km2": "2020年面積(km2、prefecture_basic.csvのarea_2020_km2をそのまま)",
    "population_2024": (
        "医療需要推計の基準人口(人単位の整数)。**構想区域の値を合計した派生値**"
        "(known_issues の prefecture_demand_aggregated_by_this_repository 参照)。"
        "原典Excelの見出しは「人口(2024年度)」だが公式説明書は「人口(2025年)」として"
        "おり、基準年が公表物どうしで食い違っている(known_issues参照)"
    ),
    "population_2040": (
        "2040年人口(人単位の整数)。**構想区域の値を合計した派生値**"
        "(known_issues の prefecture_demand_aggregated_by_this_repository 参照)"
    ),
    "beds": "5機能(total/high_acute/acute/recovery/chronic)ごとの2025年実績・必要数",
    "beds.actual_2025": (
        "病床機能報告による2025年実績病床数(床)。prefecture_beds.csvの"
        "series=='実績' and year=='2025'(厚労省の都道府県別公表値そのもの)"
    ),
    "beds.need_2025": (
        "2025年の必要病床数(床、地域医療構想における将来の病床数の必要量)。"
        "prefecture_beds.csvのseries=='必要数' and year=='2025'(厚労省の都道府県別公表値そのもの)"
    ),
    "demand": (
        "区分キー(home_care/outpatient) -> {年の文字列(years参照): レセプト件数/月}の対応。"
        "**構想区域の値を合計した派生値**(known_issues参照)。患者数・人数そのものではない。"
        "変化率(2024年度比)はこのファイルには含まれず、表示側で算出する"
    ),
}


def _load_csv_rows(path: Path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_meta(csv_path: Path) -> dict:
    with open(Path(str(csv_path) + ".meta.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def _select(d: dict, keys) -> dict:
    return {k: d[k] for k in keys}


def _load_geojson_pref(path: Path):
    """境界GeoJSONから {pref_code: pref_name} を読む(ジオメトリは読まない)。"""
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)
    return {feat["properties"]["pref_code"]: feat["properties"]["pref_name"] for feat in gj["features"]}


def validate_published_fy(rows_by_name: dict) -> None:
    """検証1: 全CSVの全行が published_fy == 'R7'。"""
    for name, rows in rows_by_name.items():
        bad = sorted({r["published_fy"] for r in rows} - {"R7"})
        if bad:
            raise SystemExit(f"検証1失敗: {name}にR7以外のpublished_fyがあります: {bad}")


def validate_and_index_beds(pref_beds_rows, pref_basic_rows, geo_pref, area_basic_rows, area_beds_rows):
    """検証2〜9を行い、違反があれば SystemExit で中断する。

    戻り値: (actual_by_key, need_by_key, basic_by_code, area_count_by_pref)
      actual_by_key / need_by_key: {(pref_code, bed_function_ja): beds(int)}
                                   全国('00')を含む48都道府県ぶん
      basic_by_code: {pref_code: row(dict)}(全国を含む)
      area_count_by_pref: {pref_code: 構想区域数}(全国は含まない)
    """
    # 検証2: (pref_code, bed_function, series, year) の重複なし
    key_counts = Counter(
        (r["pref_code"], r["bed_function"], r["series"], r["year"]) for r in pref_beds_rows
    )
    dup = sorted(k for k, n in key_counts.items() if n > 1)
    if dup:
        raise SystemExit(f"検証2失敗: (pref_code,bed_function,series,year)が重複しています: {dup[:20]}")

    # 検証3: pref_code集合の整合
    beds_codes = {r["pref_code"] for r in pref_beds_rows}
    basic_codes = {r["pref_code"] for r in pref_basic_rows}
    geo_codes = set(geo_pref)
    area_pref_codes = {r["pref_code"] for r in area_basic_rows}
    if beds_codes != basic_codes:
        raise SystemExit(
            "検証3失敗: pref_codeの集合がprefecture_beds.csvとprefecture_basic.csvで一致しません。"
            f"beds側のみ={sorted(beds_codes - basic_codes)} basic側のみ={sorted(basic_codes - beds_codes)}"
        )
    if NATIONAL_CODE not in beds_codes:
        raise SystemExit(f"検証3失敗: prefecture_beds.csvに全国(pref_code='{NATIONAL_CODE}')の行がありません")
    prefecture_codes = beds_codes - {NATIONAL_CODE}
    if len(prefecture_codes) != EXPECTED_PREFECTURE_COUNT:
        raise SystemExit(
            f"検証3失敗: 全国を除いた都道府県が{EXPECTED_PREFECTURE_COUNT}件ではありません"
            f"({len(prefecture_codes)}件)"
        )
    for name, codes in (
        ("prefecture_boundaries_R7.geojson", geo_codes),
        ("area_basic.csv", area_pref_codes),
    ):
        if codes != prefecture_codes:
            raise SystemExit(
                f"検証3失敗: pref_codeの集合が{name}とprefecture_beds.csv(全国を除く)で"
                f"一致しません。{name}のみ={sorted(codes - prefecture_codes)} "
                f"prefecture_beds.csvのみ={sorted(prefecture_codes - codes)}"
            )

    # 検証4: 各pref_code(48) × 5機能について実績2025・必要数2025がちょうど1行ずつ
    actual_rows = [r for r in pref_beds_rows if r["series"] == "実績" and r["year"] == "2025"]
    need_rows = [r for r in pref_beds_rows if r["series"] == "必要数" and r["year"] == "2025"]
    expected_pairs = {(code, ja) for code in beds_codes for ja in BED_FUNCTION_KEY_BY_JA}
    for label, rows in (("実績", actual_rows), ("必要数", need_rows)):
        pairs = {(r["pref_code"], r["bed_function"]) for r in rows}
        if len(rows) != len(expected_pairs) or pairs != expected_pairs:
            raise SystemExit(
                f"検証4失敗: {label}2025が48都道府県(全国含む)×5機能={len(expected_pairs)}件"
                f"ちょうどではありません(実際{len(rows)}件)。"
                f"不足={sorted(expected_pairs - pairs)[:10]} 余剰={sorted(pairs - expected_pairs)[:10]}"
            )

    # 検証5: beds は全て非負の整数
    for r in pref_beds_rows:
        try:
            beds = int(r["beds"])
        except (TypeError, ValueError):
            raise SystemExit(f"検証5失敗: bedsが整数として解釈できません: {r}")
        if beds != float(r["beds"]) or beds < 0:
            raise SystemExit(f"検証5失敗: bedsが非負の整数ではありません: {r}")

    # 検証6: pref_code が2桁の数字文字列
    basic_by_code = {}
    for r in pref_basic_rows:
        code = r["pref_code"]
        if not (len(code) == 2 and code.isdigit()):
            raise SystemExit(f"検証6失敗: pref_codeが2桁の数字文字列ではありません: {code!r}")
        basic_by_code[code] = r

    # 検証7: pref_name が4者で一致
    names_by_source = {"prefecture_beds.csv": {}, "prefecture_basic.csv": {}, "area_basic.csv": {}}
    for name, rows in (
        ("prefecture_beds.csv", pref_beds_rows),
        ("prefecture_basic.csv", pref_basic_rows),
        ("area_basic.csv", area_basic_rows),
    ):
        for r in rows:
            code = r["pref_code"]
            existing = names_by_source[name].get(code)
            if existing is not None and existing != r["pref_name"]:
                raise SystemExit(
                    f"検証7失敗: {name}内でpref_code={code}のpref_nameが行によって揺れています: "
                    f"{existing!r} != {r['pref_name']!r}"
                )
            names_by_source[name][code] = r["pref_name"]
    for code in sorted(prefecture_codes):
        candidates = {
            "prefecture_beds.csv": names_by_source["prefecture_beds.csv"][code],
            "prefecture_basic.csv": names_by_source["prefecture_basic.csv"][code],
            "area_basic.csv": names_by_source["area_basic.csv"][code],
            "prefecture_boundaries_R7.geojson": geo_pref[code],
        }
        if len(set(candidates.values())) != 1:
            raise SystemExit(f"検証7失敗: pref_code={code}のpref_nameが一致しません: {candidates}")
    if names_by_source["prefecture_beds.csv"][NATIONAL_CODE] != NATIONAL_NAME:
        raise SystemExit(
            f"検証7失敗: pref_code='{NATIONAL_CODE}'のpref_nameが'{NATIONAL_NAME}'ではありません: "
            f"{names_by_source['prefecture_beds.csv'][NATIONAL_CODE]!r}"
        )

    actual_by_key = {(r["pref_code"], r["bed_function"]): int(r["beds"]) for r in actual_rows}
    need_by_key = {(r["pref_code"], r["bed_function"]): int(r["beds"]) for r in need_rows}

    # 検証8: 都道府県の値が構想区域(area_beds.csv)の合計と完全一致
    validate_beds_match_area_sum(actual_by_key, need_by_key, area_beds_rows, area_basic_rows, prefecture_codes)

    # 検証9: 全国が47都道府県の合計と完全一致
    for label, by_key in (("実績", actual_by_key), ("必要数", need_by_key)):
        for ja in sorted(BED_FUNCTION_KEY_BY_JA):
            total = sum(by_key[(code, ja)] for code in sorted(prefecture_codes))
            national = by_key[(NATIONAL_CODE, ja)]
            if total != national:
                raise SystemExit(
                    f"検証9失敗: 全国の{label}2025({ja})が47都道府県の合計と一致しません"
                    f"(全国={national} 合計={total})"
                )

    area_count_by_pref = Counter(r["pref_code"] for r in area_basic_rows)
    if sum(area_count_by_pref.values()) != EXPECTED_AREA_COUNT:
        raise SystemExit(
            f"検証3失敗: area_basic.csvの構想区域数が{EXPECTED_AREA_COUNT}ではありません"
            f"({sum(area_count_by_pref.values())})"
        )

    return actual_by_key, need_by_key, basic_by_code, dict(area_count_by_pref)


def validate_beds_match_area_sum(actual_by_key, need_by_key, area_beds_rows, area_basic_rows, prefecture_codes):
    """検証8: 47都道府県 × 5機能の実績2025・必要数2025が、構想区域を都道府県で
    合計した値と完全に一致することを確認する。

    厚労省の別々の公表ファイル(001722915.xlsx=都道府県、001723349.xlsx=構想区域)
    どうしの内部整合の確認でもある。ここが崩れると「概観層と主表示層で数字が
    食い違う」という最も分かりにくい事故になるため、警告ではなく中断にする。
    """
    pref_by_area = {r["area_code"]: r["pref_code"] for r in area_basic_rows}

    sums = defaultdict(int)
    for r in area_beds_rows:
        if r["year"] != "2025" or r["series"] not in ("実績", "必要数"):
            continue
        pref_code = pref_by_area.get(r["area_code"])
        if pref_code is None:
            raise SystemExit(
                f"検証8失敗: area_beds.csvのarea_code={r['area_code']}がarea_basic.csvにありません"
            )
        sums[(pref_code, r["bed_function"], r["series"])] += int(r["beds"])

    mismatches = []
    for code in sorted(prefecture_codes):
        for ja in sorted(BED_FUNCTION_KEY_BY_JA):
            for series, by_key in (("実績", actual_by_key), ("必要数", need_by_key)):
                expected = sums.get((code, ja, series))
                actual = by_key[(code, ja)]
                if expected != actual:
                    mismatches.append((code, ja, series, actual, expected))
    if mismatches:
        raise SystemExit(
            "検証8失敗: 都道府県の2025年病床数が構想区域の合計と一致しません"
            f"({len(mismatches)}件)。(pref_code, 機能, series, 都道府県値, 区域合計)="
            f"{mismatches[:10]}"
        )


def aggregate_demand(forecast_rows, population_rows, area_basic_rows, prefecture_codes):
    """検証10・11を行い、需要と基準人口を都道府県で合計する。

    合計は必ずソート済みの順序(区域コード昇順)で行う(浮動小数点の決定性。
    モジュールdocstring「浮動小数点の決定性」参照)。

    戻り値: (demand_by_pref, national_demand, population_by_pref, national_population,
             year_label_by_year)
      demand_by_pref: {(pref_code, category_key, year): value(float)}
      national_demand: {(category_key, year): value(float)}
      population_by_pref: {pref_code: {"population_2024": int, "population_2040": int}}
      national_population: {"population_2024": int, "population_2040": int}
    """
    pref_by_area = {r["area_code"]: r["pref_code"] for r in area_basic_rows}

    # 区域コード昇順で走査するため、先に (area_code, category, year) -> value を作る
    values = {}
    year_label_by_year = {}
    for r in forecast_rows:
        area_code = r["area_code"]
        if area_code not in pref_by_area:
            raise SystemExit(
                f"検証10失敗: demand_forecast.csvのarea_code={area_code}がarea_basic.csvにありません"
            )
        category_ja = r["demand_category"]
        if category_ja not in DEMAND_CATEGORY_KEY_BY_JA:
            raise SystemExit(f"検証10失敗: 未知のdemand_categoryがあります: {category_ja!r}")
        year = int(r["year"])
        if year not in YEARS:
            raise SystemExit(f"検証10失敗: 未知のyearがあります: {year}")
        label = r["year_label"]
        if year in year_label_by_year and year_label_by_year[year] != label:
            raise SystemExit(
                f"検証10失敗: year={year}のyear_labelが行によって揺れています: "
                f"{year_label_by_year[year]!r} != {label!r}"
            )
        year_label_by_year[year] = label
        try:
            value = float(r["receipts_per_month"])
        except (TypeError, ValueError):
            raise SystemExit(f"検証10失敗: receipts_per_monthが数値として解釈できません: {r}")
        if not math.isfinite(value) or not (value > 0):
            raise SystemExit(f"検証10失敗: receipts_per_monthが有限の正の数値ではありません: {r}")
        values[(area_code, DEMAND_CATEGORY_KEY_BY_JA[category_ja], year)] = value

    expected_cells = len(pref_by_area) * len(CATEGORIES) * len(YEARS)
    if len(values) != expected_cells:
        raise SystemExit(
            f"検証10失敗: demand_forecast.csvの(area,区分,年度)が{expected_cells}件"
            f"ちょうどではありません(実際{len(values)}件)"
        )
    missing_years = sorted(set(YEARS) - set(year_label_by_year))
    if missing_years:
        raise SystemExit(f"検証10失敗: year_labelが1件も無いyearがあります: {missing_years}")

    sorted_area_codes = sorted(pref_by_area)

    demand_by_pref = {}
    for category in CATEGORIES:
        for year in YEARS:
            per_pref = defaultdict(float)
            for area_code in sorted_area_codes:  # 決定的な加算順序
                per_pref[pref_by_area[area_code]] += values[(area_code, category, year)]
            for code in sorted(prefecture_codes):
                total = per_pref.get(code)
                if total is None or not math.isfinite(total) or not (total > 0):
                    raise SystemExit(
                        f"検証10失敗: 集計後のpref_code={code} {category} {year}が"
                        f"有限の正の数値ではありません: {total}"
                    )
                demand_by_pref[(code, category, year)] = total

    # 基準年(2024)が0でない(表示側の2024年度比の分母)
    for code in sorted(prefecture_codes):
        for category in CATEGORIES:
            if demand_by_pref[(code, category, BASELINE_YEAR)] == 0:
                raise SystemExit(
                    f"検証10失敗: pref_code={code} {category} の基準年({BASELINE_YEAR})の値が0です"
                )

    # 検証11: 全国(47都道府県の合計)が339区域の直接合計と一致する
    national_demand = {}
    for category in CATEGORIES:
        for year in YEARS:
            from_prefectures = sum(
                demand_by_pref[(code, category, year)] for code in sorted(prefecture_codes)
            )
            from_areas = sum(values[(area_code, category, year)] for area_code in sorted_area_codes)
            if abs(from_prefectures - from_areas) > abs(from_areas) * SUM_RELATIVE_TOLERANCE:
                raise SystemExit(
                    f"検証11失敗: 全国の{category} {year}が、47都道府県の合計"
                    f"({from_prefectures!r})と339区域の直接合計({from_areas!r})で一致しません"
                )
            national_demand[(category, year)] = from_prefectures

    # 基準人口(構想区域の合計)。こちらも同じ規律で合計する
    population_rows_by_area = {r["area_code"]: r for r in population_rows}
    missing = sorted(set(pref_by_area) - set(population_rows_by_area))
    if missing:
        raise SystemExit(f"検証10失敗: demand_population.csvに無いarea_codeがあります: {missing[:10]}")

    population_by_pref = defaultdict(lambda: {"population_2024": 0, "population_2040": 0})
    national_population = {"population_2024": 0, "population_2040": 0}
    for area_code in sorted_area_codes:  # 決定的な加算順序(整数なので順序非依存だが規律を揃える)
        row = population_rows_by_area[area_code]
        pref_code = pref_by_area[area_code]
        for field_name in ("population_2024", "population_2040"):
            raw = row[field_name]
            try:
                value = int(raw)
            except (TypeError, ValueError):
                raise SystemExit(f"検証10失敗: {field_name}が整数として解釈できません: {row}")
            if value != float(raw) or value <= 0:
                raise SystemExit(f"検証10失敗: {field_name}が正の整数ではありません: {row}")
            population_by_pref[pref_code][field_name] += value
            national_population[field_name] += value

    return (
        demand_by_pref,
        national_demand,
        dict(population_by_pref),
        national_population,
        year_label_by_year,
    )


def validate_basic(basic_by_code, prefecture_codes) -> None:
    """検証12: 人口・面積が正、かつ全国が47都道府県の合計と一致する。"""
    for code, row in sorted(basic_by_code.items()):
        population = int(row["population_2020"])
        area_km2 = float(row["area_2020_km2"])
        if population <= 0:
            raise SystemExit(f"検証12失敗: pref_code={code}のpopulation_2020が正ではありません: {population}")
        if not math.isfinite(area_km2) or area_km2 <= 0:
            raise SystemExit(f"検証12失敗: pref_code={code}のarea_2020_km2が正ではありません: {area_km2}")

    population_total = sum(int(basic_by_code[code]["population_2020"]) for code in sorted(prefecture_codes))
    national_population = int(basic_by_code[NATIONAL_CODE]["population_2020"])
    if population_total != national_population:
        raise SystemExit(
            f"検証12失敗: 全国のpopulation_2020({national_population})が47都道府県の合計"
            f"({population_total})と一致しません"
        )
    # 面積は原典が小数第2位までのため、合計と全国行が最終桁でずれうる。丸めて比較する。
    area_total = round(sum(float(basic_by_code[code]["area_2020_km2"]) for code in sorted(prefecture_codes)), 2)
    national_area = round(float(basic_by_code[NATIONAL_CODE]["area_2020_km2"]), 2)
    if area_total != national_area:
        raise SystemExit(
            f"検証12失敗: 全国のarea_2020_km2({national_area})が47都道府県の合計({area_total})と一致しません"
        )


def log_zero_need_count(need_by_key) -> None:
    """検証13: 必要数が0の(pref_code,機能)の件数をログ出力する(エラーにはしない)。"""
    zero = sorted(k for k, v in need_by_key.items() if v == 0)
    print(f"[info] 検証13: 必要数(2025)が0の(pref_code,機能)は{len(zero)}件あります(異常ではない): {zero}")


def build_entry(pref_code, pref_name, basic_row, area_count, actual_by_key, need_by_key,
                demand_lookup, population):
    """1都道府県(または全国)ぶんの出力オブジェクトを組み立てる。

    `demand_lookup(category, year) -> float` で需要を引く(都道府県と全国で
    キーの形が違うため、呼び出し側でクロージャを渡す)。
    """
    beds = {}
    for func_key in FUNCTIONS:
        ja = FUNCTION_LABELS[func_key]
        beds[func_key] = {
            "actual_2025": actual_by_key[(pref_code, ja)],
            "need_2025": need_by_key[(pref_code, ja)],
        }

    demand = {
        category: {str(year): demand_lookup(category, year) for year in YEARS}
        for category in CATEGORIES
    }

    return {
        "pref_code": pref_code,
        "pref_name": pref_name,
        "area_count": area_count,
        "population_2020": int(basic_row["population_2020"]),
        "area_km2": float(basic_row["area_2020_km2"]),
        "population_2024": population["population_2024"],
        "population_2040": population["population_2040"],
        "beds": beds,
        "demand": demand,
    }


def build_metadata(metas: dict, inputs: list) -> dict:
    """入力CSVの meta.json から出典・注記・known_issues を引き継いでメタデータを
    組み立てる。

    病床側(prefecture_beds/prefecture_basic、001722915.xlsx由来)と
    需要側(demand_forecast/demand_population、001728462.xlsx由来)で原典が違う
    ため、`source`は1つではなく`source_beds`/`source_demand`の2ブロックに分ける
    (CLAUDE.md「可視化実装で判明した罠」11 — 表示用JSONを増やすとmetadataの形は
    揃わない。ここでも既存3データセットのどれとも違う形になる)。
    """
    beds_source = _select(metas["prefecture_beds"]["source"], SOURCE_KEYS)
    basic_source = _select(metas["prefecture_basic"]["source"], SOURCE_KEYS)
    if beds_source != basic_source:
        raise SystemExit(
            "prefecture_beds.csv.meta.json と prefecture_basic.csv.meta.json の source が"
            "一致しません(両方とも同一のR7/001722915.xlsxから派生しているはずです)。"
            f"beds={beds_source} basic={basic_source}"
        )
    forecast_source = _select(metas["demand_forecast"]["source"], SOURCE_KEYS)
    population_source = _select(metas["demand_population"]["source"], SOURCE_KEYS)
    if forecast_source != population_source:
        raise SystemExit(
            "demand_forecast.csv.meta.json と demand_population.csv.meta.json の source が"
            "一致しません(両方とも同一のR7/001728462.xlsxから派生しているはずです)。"
            f"forecast={forecast_source} population={population_source}"
        )

    beds_caveat = metas["prefecture_beds"]["processing"]["caveat"]
    basic_caveat = metas["prefecture_basic"]["processing"]["caveat"]
    if beds_caveat != basic_caveat:
        raise SystemExit(
            "prefecture_beds.csv.meta.json と prefecture_basic.csv.meta.json の "
            f"processing.caveat が一致しません。beds={beds_caveat!r} basic={basic_caveat!r}"
        )

    source_beds = dict(beds_source)
    source_beds["derived_via"] = [
        {"csv": "data/processed/prefecture_beds.csv", "meta": "data/processed/prefecture_beds.csv.meta.json"},
        {"csv": "data/processed/prefecture_basic.csv", "meta": "data/processed/prefecture_basic.csv.meta.json"},
    ]
    source_demand = dict(forecast_source)
    source_demand["derived_via"] = [
        {"csv": "data/processed/demand_forecast.csv", "meta": "data/processed/demand_forecast.csv.meta.json"},
        {"csv": "data/processed/demand_population.csv", "meta": "data/processed/demand_population.csv.meta.json"},
    ]

    # 原典側の既知の欠陥は入力CSVのmeta.jsonから拾って集約する(この場で新規に
    # 書き足さない)。唯一の例外が DEMAND_AGGREGATION_ISSUE で、これは
    # 「表示用データセットを作る過程で下した判断」(build_web_data.py の
    # area_indicators_2024_actual_excluded と同じ位置づけ)。
    known_issues = []
    for name in ("prefecture_beds", "prefecture_basic", "demand_forecast", "demand_population"):
        known_issues.extend(metas[name].get("known_issues", []))
    known_issues.append(DEMAND_AGGREGATION_ISSUE)

    return {
        "title": (
            "都道府県別 2025年病床数（実績・必要数）と医療需要推計"
            "（在宅（訪問診療）・外来、構想区域からの集計、可視化サイト表示用）"
        ),
        "source_beds": source_beds,
        "source_demand": source_demand,
        "processing": {
            "script": "tools/build_web_prefecture.py",
            "inputs": inputs,
            "steps": [
                "prefecture_beds.csv・prefecture_basic.csv・demand_forecast.csv・"
                "demand_population.csv・area_beds.csv・area_basic.csv・"
                "prefecture_boundaries_R7.geojsonを読み込み",
                "全CSVの全行がpublished_fy=='R7'であることを確認(検証1)",
                "(pref_code, bed_function, series, year)の重複がないことを確認(検証2)",
                "pref_code集合が4者(prefecture_beds/prefecture_basic/境界GeoJSON/"
                "area_basic)で整合し、全国を除いて47件であることを確認(検証3)",
                "各pref_code(48、全国含む)×5機能について実績2025・必要数2025が"
                "ちょうど1行ずつ存在することを確認(検証4)",
                "beds列が全て非負の整数であることを確認(検証5)",
                "pref_codeが2桁の数字文字列であることを確認(検証6)",
                "pref_nameが4者(prefecture_beds/prefecture_basic/area_basic/境界GeoJSON)で"
                "一致することを確認(検証7)",
                "47都道府県×5機能の実績2025・必要数2025が、構想区域(area_beds.csv)を"
                "都道府県で合計した値と完全に一致することを確認(検証8。厚労省の別々の"
                "公表ファイル001722915.xlsxと001723349.xlsxの内部整合の確認でもある)",
                "全国(00)の病床が47都道府県の合計と完全に一致することを確認(検証9)",
                "需要を都道府県で合計(区域コード昇順の決定的な順序)。全区域が既知の"
                "都道府県に属し、集計後が全て有限かつ正で、基準年(2024)が0でないことを"
                "確認(検証10)",
                "全国の需要(47都道府県の合計)が339区域の直接合計と一致することを確認"
                "(検証11、相対許容差1e-9)",
                "人口・面積が正であり、全国が47都道府県の合計と一致することを確認(検証12)",
                "必要数(2025)が0の(pref_code,機能)の件数をログ出力(検証13。エラーにはしない)",
                "pref_codeの昇順(文字列ソート)でprefecturesを整列し、全国はnationalへ分離",
            ],
            # 入力CSV4本ぶんの注記。病床側2本は内容が同一のため1キーにまとめ、
            # 需要側は2本それぞれ別内容なので個別に持つ(area_demand_R7.jsonと同じ理由)。
            "caveat": {
                "beds": beds_caveat,
                "demand_forecast": metas["demand_forecast"]["processing"]["caveat"],
                "demand_population": metas["demand_population"]["processing"]["caveat"],
            },
        },
        "fields": FIELD_DESCRIPTIONS,
        "known_issues": known_issues,
    }


def build_and_write(out_path: Path) -> Path:
    """入力を読み込み・検証・変換し、`out_path`へ表示用データセットのJSONを
    書き出す(再現性テストでの再利用のため、出力先を引数化している)。

    戻り値: 書き出したファイルのPath。
    """
    rows = {
        "prefecture_beds": _load_csv_rows(PREFECTURE_BEDS_CSV),
        "prefecture_basic": _load_csv_rows(PREFECTURE_BASIC_CSV),
        "demand_forecast": _load_csv_rows(DEMAND_FORECAST_CSV),
        "demand_population": _load_csv_rows(DEMAND_POPULATION_CSV),
        "area_beds": _load_csv_rows(AREA_BEDS_CSV),
        "area_basic": _load_csv_rows(AREA_BASIC_CSV),
    }
    geo_pref = _load_geojson_pref(PREFECTURE_BOUNDARIES_GEOJSON)
    print(
        "[ok] 入力読み込み: "
        + " ".join(f"{name}.csv={len(r)}行" for name, r in rows.items())
        + f" prefecture_boundaries_R7.geojson={len(geo_pref)}都道府県"
    )

    validate_published_fy(rows)

    actual_by_key, need_by_key, basic_by_code, area_count_by_pref = validate_and_index_beds(
        rows["prefecture_beds"], rows["prefecture_basic"], geo_pref, rows["area_basic"], rows["area_beds"]
    )
    prefecture_codes = set(geo_pref)
    print(
        "[ok] 検証1〜9: published_fy・重複なし・pref_code集合一致(47+全国)・"
        "実績/必要数の存在・非負整数・コード形式・名称整合(4者)・"
        "構想区域合計との完全一致(470キー)・全国=47都道府県の合計 を確認"
    )

    (
        demand_by_pref,
        national_demand,
        population_by_pref,
        national_population,
        year_label_by_year,
    ) = aggregate_demand(rows["demand_forecast"], rows["demand_population"], rows["area_basic"], prefecture_codes)
    print("[ok] 検証10・11: 需要の都道府県集計(2区分×6年度)・基準年非ゼロ・全国=339区域の直接合計 を確認")

    validate_basic(basic_by_code, prefecture_codes)
    print("[ok] 検証12: 人口・面積が正、全国=47都道府県の合計 を確認")

    log_zero_need_count(need_by_key)

    prefectures = [
        build_entry(
            code,
            basic_by_code[code]["pref_name"],
            basic_by_code[code],
            area_count_by_pref[code],
            actual_by_key,
            need_by_key,
            lambda category, year, c=code: demand_by_pref[(c, category, year)],
            population_by_pref[code],
        )
        for code in sorted(prefecture_codes)
    ]
    national = build_entry(
        NATIONAL_CODE,
        NATIONAL_NAME,
        basic_by_code[NATIONAL_CODE],
        EXPECTED_AREA_COUNT,
        actual_by_key,
        need_by_key,
        lambda category, year: national_demand[(category, year)],
        national_population,
    )
    print(f"[ok] prefectures構築: {len(prefectures)}都道府県 + national")

    metas = {name: _load_meta(path) for name, path in (
        ("prefecture_beds", PREFECTURE_BEDS_CSV),
        ("prefecture_basic", PREFECTURE_BASIC_CSV),
        ("demand_forecast", DEMAND_FORECAST_CSV),
        ("demand_population", DEMAND_POPULATION_CSV),
    )}
    inputs = [
        {"path": f"data/processed/{path.name}", "sha256": sha256(path)}
        for path in (*INPUT_CSVS, PREFECTURE_BOUNDARIES_GEOJSON)
    ]
    metadata = build_metadata(metas, inputs)

    output = {
        "metadata": metadata,
        "functions": FUNCTIONS,
        "function_labels": FUNCTION_LABELS,
        "categories": CATEGORIES,
        "category_labels": CATEGORY_LABELS,
        "years": YEARS,
        "year_labels": {str(year): year_label_by_year[year] for year in YEARS},
        "baseline_year": BASELINE_YEAR,
        "national": national,
        "prefectures": prefectures,
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[ok] 出力: {out_path}")
    print(f"     都道府県数: {len(prefectures)}")
    print(f"     サイズ: {out_path.stat().st_size:,} bytes")
    print(f"     sha256 = {sha256(out_path)}")

    return out_path


def main() -> None:
    build_and_write(OUT_PATH)


if __name__ == "__main__":
    main()
