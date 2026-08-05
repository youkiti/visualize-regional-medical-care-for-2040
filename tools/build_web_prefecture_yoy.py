# -*- coding: utf-8 -*-
"""可視化サイトの概観レイヤ(都道府県)が読み込む年度間比較の表示用データセット
`data/processed/prefecture_yoy_R6_R7.json` を、既にコミット済みの加工CSV
(`prefecture_beds.csv`・`prefecture_bed_report_rate.csv`)と都道府県境界GeoJSON
(`prefecture_boundaries_R7.geojson`、pref_codeの一致検証にのみ使用しジオメトリは
読まない)から生成する。

構想区域側の `tools/build_web_yoy.py`(→ `area_yoy_R6_R7.json`)の都道府県版であり、
指標の定義(見込量比・実績の1年変化)は同一にしてある。新しい生データは使わない。

## 構想区域版との違い(いずれも都道府県層の方が素直)

  - **2024年実績の採用に判断が要らない**: 構想区域では R7公表分の2024年実績が
    2025年実績の複製になっている原典の欠陥(`area_beds_2024_actual_duplicated_as_2025`)
    があり、R6公表分を採る判断(`area_yoy_2024_actual_from_r6`)が必要だった。
    **都道府県では R6公表分と R7公表分の2024年実績が48エンティティ×5機能=240キーの
    全てで一致する**(検証9で機械的に固定している)。したがって本データセットの
    actual_2024 はどちらから採っても同じ値であり、区域側のような known_issue は
    生じない。将来どちらかの公表物が変わって一致しなくなれば検証9で落ちる。
  - **分母0が無い**: 構想区域では plan_2025 が0の区域が81件(高度急性期70ほか)あり
    画面で「算出不可」表示になるが、都道府県では plan_2025・actual_2024 とも0が
    1件も無い(検証10でログ出力する。エラーにはしない ―― 将来0が現れても
    フロントの「算出不可」機構がそのまま効くため)。

## 全国(00)

`prefecture_boundaries_R7.geojson` は47都道府県のみでフィーチャを持たないため、
`prefecture_indicators_R7.json` と同じく全国は `prefectures` 配列ではなく
トップレベルの `national` に分ける(配列の要素数と境界のフィーチャ数を常に一致
させ、突合を単純に保つ)。全国の値は原典の公表値(pref_code='00'の行)を使い、
47都道府県の合計と一致することを検証8で確認する。

処理内容:
  1. 上記2CSVと`prefecture_boundaries_R7.geojson`を読み込む
  2. 検証1〜10(下記)を行い、違反があれば SystemExit で中断する
  3. 48エンティティ(47都道府県+全国) × 5機能について、見込量2025(R6公表)・
     実績2025(R7公表)・実績2024(R6公表)を抽出する(比率は出さない。構想区域版と
     同じくフロントエンド側で算出する)
  4. エンティティごとに報告率2024(R6公表)・報告率2025(R7公表)を併記する
     (報告率の差が病床数の変化を説明しうるため)
  5. `prefecture_beds.csv.meta.json` / `prefecture_bed_report_rate.csv.meta.json` の
     `source`(published_fy付きdictのリスト)を実行時に読み込んで引き継ぐ
     (出典情報のハードコードによる二重管理を避ける)
  6. UTF-8・LF・`ensure_ascii=False`・indent=2・末尾改行1つで出力する

検証1〜10:
   1. prefecture_beds.csv・prefecture_bed_report_rate.csv に published_fy=='R6' と
      'R7' の両方の行が存在する
   2. pref_code集合の整合: 2CSVのR6/R7がいずれも48件(全国00を含む)で一致し、
      境界GeoJSONの47件が「48件から全国を除いたもの」と完全一致する
   3. pref_name が prefecture_beds.csv の R6/R7 と境界GeoJSON の3者で一致する
   4. 各pref_code(48) × 5機能について plan_2025(R6見込量2025)・
      actual_2025(R7実績2025)・actual_2024(R6実績2024)がちょうど1件ずつ存在する
      (計48×5×3=720セル)
   5. 上記3系列の値が非負の整数で欠測が無い
   6. report_rate_2024(R6・2024年)・report_rate_2025(R7・2025年)が48件ぶん揃い
      0〜1の範囲
   7. 3系列それぞれについて「合計」が他4機能の和と一致する
   8. **3系列それぞれについて全国(00)が47都道府県の合計と完全に一致する**
   9. **R6公表分とR7公表分の2024年実績が240キー全てで一致する**(構想区域側の
      既知の欠陥が都道府県層には無いことの機械的な担保。上記「構想区域版との違い」参照)
  10. plan_2025/actual_2024 が0の(pref_code,機能)の件数をログ出力(検証というより
      観測値の記録。エラーにはしない)

生成日時は埋め込まない(CLAUDE.md参照。再現性テストが翌日に壊れるため)。

必要環境: Python 3.11+

使い方:
    PYTHONIOENCODING=utf-8 python tools/build_web_prefecture_yoy.py
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lib.provenance import REPO_ROOT, sha256

PROCESSED = REPO_ROOT / "data" / "processed"
PREFECTURE_BEDS_CSV = PROCESSED / "prefecture_beds.csv"
PREFECTURE_BED_REPORT_RATE_CSV = PROCESSED / "prefecture_bed_report_rate.csv"
PREFECTURE_BOUNDARIES_GEOJSON = PROCESSED / "prefecture_boundaries_R7.geojson"
OUT_PATH = PROCESSED / "prefecture_yoy_R6_R7.json"

PREFECTURE_BEDS_META_PATH = Path(str(PREFECTURE_BEDS_CSV) + ".meta.json")
PREFECTURE_BED_REPORT_RATE_META_PATH = Path(str(PREFECTURE_BED_REPORT_RATE_CSV) + ".meta.json")

NATIONAL_CODE = "00"
NATIONAL_NAME = "全国"
EXPECTED_PREFECTURE_COUNT = 47
EXPECTED_ENTITY_COUNT = 48  # 47都道府県 + 全国

FUNCTIONS = ["total", "high_acute", "acute", "recovery", "chronic"]
FUNCTION_LABELS = {
    "total": "合計",
    "high_acute": "高度急性期",
    "acute": "急性期",
    "recovery": "回復期",
    "chronic": "慢性期",
}
# prefecture_beds.csv の bed_function は日本語ラベルで格納されている
# (tools/parse_prefecture_beds.py 参照)。出力スキーマの英字キーへの逆引き。
BED_FUNCTION_KEY_BY_JA = {ja: key for key, ja in FUNCTION_LABELS.items()}
PART_FUNCTION_LABELS = ("高度急性期", "急性期", "回復期", "慢性期")

# メタデータへ引き継ぐ meta.json の source配列(要素ごと)から選ぶキー。
# build_web_yoy.py と同じ扱い(R6のみ持つ"source_note"は存在すれば拾う)。
SOURCE_KEYS = (
    "published_fy",
    "name",
    "publisher",
    "url",
    "source_note",
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

FIELD_DESCRIPTIONS = {
    "functions": "病床機能区分の英字キー一覧(表示順)。total=合計、他4区分の和",
    "function_labels": "機能キー -> 日本語ラベルの対応(表示用)",
    "national": (
        "全国(pref_code='00')。境界GeoJSONにフィーチャが無いため prefectures 配列とは"
        "分けている。値は原典の公表値であり、47都道府県の合計と一致する(検証8)"
    ),
    "prefectures": "47都道府県(pref_codeの昇順)。全国は含まない",
    "pref_code": "都道府県コード(ゼロ埋め2桁の文字列)。全国は'00'",
    "pref_name": "都道府県名",
    "report_rate_2024": (
        "R6公表分(別添４②)の2024年病床機能報告の報告率(0〜1)。**47都道府県では"
        "R7公表分の同年報告率と全て一致し、全国(00)のみ相違する**"
        "(構想区域では339区域中105区域で相違しており、"
        "area_bed_report_rate_2024_differs_between_r6_r7 として記録されている)。"
        "年度間の病床数の変化を見るときは、報告率自体も年度により異なることに留意すること"
    ),
    "report_rate_2025": "R7公表分の2025年病床機能報告の報告率(0〜1)",
    "beds": "5機能(total/high_acute/acute/recovery/chronic)ごとのplan_2025/actual_2025/actual_2024",
    "beds.plan_2025": (
        "R6公表分(別添４②)の2025年見込量(床)。実績2025(R7公表分)とは公表回が異なる"
        "見込み値である点に留意(見込みと実績のずれを見る指標)。R7公表分の見込量は"
        "2026年が対象のため使えない(CLAUDE.md「R6の列ずれの罠」参照)"
    ),
    "beds.actual_2025": "R7公表分の2025年実績病床数(床)",
    "beds.actual_2024": (
        "R6公表分の2024年実績病床数(床)。**都道府県層ではR7公表分の同列と240キー全てで"
        "一致する**ため(検証9)、どちらの公表回から採っても同じ値である。構想区域側の"
        "area_yoy_2024_actual_from_r6(R7の2024年実績が2025年実績の複製という原典の"
        "欠陥を避けるための判断)に相当するものは、都道府県層では生じない"
    ),
}


def _load_csv_rows(path: Path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_geojson_pref_codes(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)
    return {feat["properties"]["pref_code"]: feat["properties"]["pref_name"] for feat in gj["features"]}


def _select_present(d: dict, keys) -> dict:
    """`keys` のうち `d` に存在するものだけを順序を保って取り出す(build_web_yoy.py と同じ)。"""
    return {k: d[k] for k in keys if k in d}


def split_by_fy(rows):
    result = {}
    for r in rows:
        result.setdefault(r["published_fy"], []).append(r)
    return result


def validate_and_index(beds_rows, rate_rows, geo_pref_names):
    """検証1〜9を行い、違反があれば SystemExit で中断する。

    戻り値: 抽出済みのdict(pref_rows_by_code / plan_2025 / actual_2025 /
    actual_2024 / report_rate_2024 / report_rate_2025)。
    """
    # 検証1: published_fy=='R6'/'R7' の両方が存在する(2CSVとも)
    beds_by_fy = split_by_fy(beds_rows)
    missing_fy = sorted({"R7", "R6"} - set(beds_by_fy))
    if missing_fy:
        raise SystemExit(f"検証1失敗: prefecture_beds.csvにpublished_fy={missing_fy}の行がありません")
    rate_by_fy = split_by_fy(rate_rows)
    missing_rate_fy = sorted({"R7", "R6"} - set(rate_by_fy))
    if missing_rate_fy:
        raise SystemExit(
            f"検証1失敗: prefecture_bed_report_rate.csvにpublished_fy={missing_rate_fy}の行がありません"
        )

    beds_r7 = beds_by_fy["R7"]
    beds_r6 = beds_by_fy["R6"]

    # 検証2: pref_code集合の整合(48件 == 48件、境界47件 == 48件-全国)
    codes_r7 = {r["pref_code"] for r in beds_r7}
    codes_r6 = {r["pref_code"] for r in beds_r6}
    geo_codes = set(geo_pref_names)
    if codes_r7 != codes_r6 or len(codes_r7) != EXPECTED_ENTITY_COUNT:
        raise SystemExit(
            "検証2失敗: prefecture_beds.csvのpref_code集合がR6/R7で一致しないか"
            f"{EXPECTED_ENTITY_COUNT}件ではありません(R7={len(codes_r7)}件 R6={len(codes_r6)}件、"
            f"差分={sorted(codes_r7 ^ codes_r6)})"
        )
    if NATIONAL_CODE not in codes_r7:
        raise SystemExit(f"検証2失敗: prefecture_beds.csvに全国(pref_code='{NATIONAL_CODE}')の行がありません")
    prefecture_codes = codes_r7 - {NATIONAL_CODE}
    if geo_codes != prefecture_codes or len(geo_codes) != EXPECTED_PREFECTURE_COUNT:
        raise SystemExit(
            "検証2失敗: prefecture_boundaries_R7.geojsonのpref_code集合が"
            f"「prefecture_beds.csvから全国を除いた{EXPECTED_PREFECTURE_COUNT}件」と一致しません"
            f"(境界={len(geo_codes)}件、境界のみ={sorted(geo_codes - prefecture_codes)}、"
            f"CSVのみ={sorted(prefecture_codes - geo_codes)})"
        )

    # 検証3: pref_name が R6 / R7 / 境界GeoJSON の3者で一致する
    def _names(rows, label):
        names = {}
        for r in rows:
            code = r["pref_code"]
            if code in names and names[code] != r["pref_name"]:
                raise SystemExit(
                    f"検証3失敗: {label}内でpref_code={code}のpref_nameが行によって揺れています: "
                    f"{names[code]!r} != {r['pref_name']!r}"
                )
            names[code] = r["pref_name"]
        return names

    names_r7 = _names(beds_r7, "prefecture_beds.csv(R7)")
    names_r6 = _names(beds_r6, "prefecture_beds.csv(R6)")
    mismatches = [code for code in sorted(names_r7) if names_r7[code] != names_r6.get(code)]
    if mismatches:
        raise SystemExit(f"検証3失敗: pref_nameがR6/R7で一致しません: {mismatches[:10]}")
    geo_mismatches = [
        code for code in sorted(geo_pref_names) if geo_pref_names[code] != names_r7.get(code)
    ]
    if geo_mismatches:
        raise SystemExit(
            f"検証3失敗: pref_nameが境界GeoJSONとprefecture_beds.csvで一致しません: {geo_mismatches[:10]}"
        )
    if names_r7[NATIONAL_CODE] != NATIONAL_NAME:
        raise SystemExit(
            f"検証3失敗: pref_code='{NATIONAL_CODE}'のpref_nameが'{NATIONAL_NAME}'ではありません"
            f"({names_r7[NATIONAL_CODE]!r})"
        )
    print(f"[ok] 検証2・3: pref_code {EXPECTED_ENTITY_COUNT}件(全国含む)・境界{len(geo_codes)}件、pref_nameは3者一致")

    # 検証4・5: 各pref_code×5機能について3系列がちょうど1件ずつ、非負整数で欠測なし
    def _extract(rows, series, year, label):
        by_key = {}
        for r in rows:
            if r["series"] != series or r["year"] != str(year):
                continue
            key = (r["pref_code"], r["bed_function"])
            if key in by_key:
                raise SystemExit(f"検証4失敗: {label}が重複しています: {key}")
            raw = r["beds"]
            if raw == "":
                raise SystemExit(f"検証5失敗: {label}に欠測があります(想定外): {key}")
            try:
                beds = int(raw)
            except (TypeError, ValueError):
                raise SystemExit(f"検証5失敗: {label}が整数として解釈できません: {key}={raw!r}")
            if beds != float(raw) or beds < 0:
                raise SystemExit(f"検証5失敗: {label}が非負の整数ではありません: {key}={raw!r}")
            by_key[key] = beds
        expected_keys = {(code, ja) for code in codes_r7 for ja in BED_FUNCTION_KEY_BY_JA}
        if set(by_key) != expected_keys:
            missing = sorted(expected_keys - set(by_key))
            extra = sorted(set(by_key) - expected_keys)
            raise SystemExit(
                f"検証4失敗: {label}が{EXPECTED_ENTITY_COUNT}エンティティ×5機能="
                f"{len(expected_keys)}件ちょうどではありません(実際{len(by_key)}件)。"
                f"不足={missing[:10]} 余剰={extra[:10]}"
            )
        return by_key

    plan_2025 = _extract(beds_r6, "見込量", 2025, "plan_2025(R6見込量2025)")
    actual_2025 = _extract(beds_r7, "実績", 2025, "actual_2025(R7実績2025)")
    actual_2024 = _extract(beds_r6, "実績", 2024, "actual_2024(R6実績2024)")
    print(
        f"[ok] 検証4・5: plan_2025/actual_2025/actual_2024が{EXPECTED_ENTITY_COUNT}エンティティ×5機能="
        f"{EXPECTED_ENTITY_COUNT * 5}件ずつ、非負整数で欠測なし"
    )

    # 検証6: 報告率(0〜1)。report_rate_2024はR6公表分・2024年、report_rate_2025はR7公表分・2025年。
    def _extract_rate(rows, year, label):
        by_code = {}
        for r in rows:
            if r["year"] != str(year):
                continue
            code = r["pref_code"]
            if code in by_code:
                raise SystemExit(f"検証6失敗: {label}が重複しています: {code}")
            value = float(r["report_rate"])
            if not (0 <= value <= 1):
                raise SystemExit(f"検証6失敗: {label}が0〜1の範囲外です: {code}={value}")
            by_code[code] = value
        if set(by_code) != codes_r7:
            missing = sorted(codes_r7 - set(by_code))
            raise SystemExit(
                f"検証6失敗: {label}が{EXPECTED_ENTITY_COUNT}エンティティぶん揃っていません。不足={missing[:10]}"
            )
        return by_code

    report_rate_2024 = _extract_rate(rate_by_fy["R6"], 2024, "report_rate_2024(R6)")
    report_rate_2025 = _extract_rate(rate_by_fy["R7"], 2025, "report_rate_2025(R7)")
    print(f"[ok] 検証6: report_rate_2024(R6)/report_rate_2025(R7)が{EXPECTED_ENTITY_COUNT}件ぶん揃い0〜1の範囲")

    # 検証7: 「合計」が他4機能の和と一致する(3系列それぞれ)
    for label, by_key in (("plan_2025", plan_2025), ("actual_2025", actual_2025), ("actual_2024", actual_2024)):
        for code in sorted(codes_r7):
            total = by_key[(code, "合計")]
            parts_sum = sum(by_key[(code, ja)] for ja in PART_FUNCTION_LABELS)
            if total != parts_sum:
                raise SystemExit(
                    f"検証7失敗: {label}のpref_code={code}で「合計」が4機能の和と不一致です"
                    f"(合計={total} 4機能の和={parts_sum})"
                )
    print("[ok] 検証7: plan_2025/actual_2025/actual_2024いずれも「合計」==4機能の和")

    # 検証8: 全国(00)が47都道府県の合計と完全一致する(3系列それぞれ)
    for label, by_key in (("plan_2025", plan_2025), ("actual_2025", actual_2025), ("actual_2024", actual_2024)):
        for ja in FUNCTION_LABELS.values():
            national = by_key[(NATIONAL_CODE, ja)]
            # 整数の和なので順序に依存しないが、決定性の規律としてソート順で足す
            total = sum(by_key[(code, ja)] for code in sorted(prefecture_codes))
            if national != total:
                raise SystemExit(
                    f"検証8失敗: {label}の全国値が47都道府県の合計と一致しません"
                    f"(機能={ja} 全国={national} 47都道府県の合計={total})"
                )
    print("[ok] 検証8: plan_2025/actual_2025/actual_2024いずれも全国==47都道府県の合計")

    # 検証9: R6とR7の2024年実績が全キーで一致する(構想区域側の
    # area_beds_2024_actual_duplicated_as_2025 が都道府県層には無いことの担保)。
    actual_2024_r7 = _extract(beds_r7, "実績", 2024, "actual_2024(R7実績2024・検証用)")
    diff_keys = sorted(k for k in actual_2024 if actual_2024[k] != actual_2024_r7.get(k))
    if diff_keys:
        raise SystemExit(
            "検証9失敗: 2024年実績がR6公表分とR7公表分で一致しません"
            f"({len(diff_keys)}件。例: "
            + ", ".join(f"{k}: R6={actual_2024[k]} R7={actual_2024_r7[k]}" for k in diff_keys[:5])
            + ")。構想区域側と同様の原典の欠陥が都道府県層にも現れた可能性があります。"
            "どちらを採用するかを判断し、known_issuesへ記録してから本スクリプトを更新してください"
        )
    print(
        f"[ok] 検証9: 2024年実績がR6公表分とR7公表分で{len(actual_2024)}キー全て一致"
        "(構想区域側の既知の欠陥は都道府県層には無い)"
    )

    pref_rows_by_code = {code: {"pref_name": names_r7[code]} for code in sorted(codes_r7)}
    return {
        "pref_rows_by_code": pref_rows_by_code,
        "prefecture_codes": sorted(prefecture_codes),
        "plan_2025": plan_2025,
        "actual_2025": actual_2025,
        "actual_2024": actual_2024,
        "report_rate_2024": report_rate_2024,
        "report_rate_2025": report_rate_2025,
    }


def log_zero_counts(plan_2025: dict, actual_2024: dict) -> None:
    """検証10: plan_2025/actual_2024が0の(pref_code,機能)の件数をログ出力する(エラーにしない)。"""
    zero_plan = sorted(k for k, v in plan_2025.items() if v == 0)
    zero_actual_2024 = sorted(k for k, v in actual_2024.items() if v == 0)
    print(
        f"[info] 検証10: plan_2025(R6見込量2025)が0の(pref_code,機能)は{len(zero_plan)}件"
        f"(機能別: {dict(Counter(k[1] for k in zero_plan))})"
    )
    print(
        f"[info] 検証10: actual_2024(R6実績2024)が0の(pref_code,機能)は{len(zero_actual_2024)}件"
        f"(機能別: {dict(Counter(k[1] for k in zero_actual_2024))})"
    )


def build_entry(code: str, indexed: dict) -> dict:
    beds = {}
    for func_key in FUNCTIONS:
        ja = FUNCTION_LABELS[func_key]
        beds[func_key] = {
            "plan_2025": indexed["plan_2025"][(code, ja)],
            "actual_2025": indexed["actual_2025"][(code, ja)],
            "actual_2024": indexed["actual_2024"][(code, ja)],
        }
    return {
        "pref_code": code,
        "pref_name": indexed["pref_rows_by_code"][code]["pref_name"],
        "report_rate_2024": indexed["report_rate_2024"][code],
        "report_rate_2025": indexed["report_rate_2025"][code],
        "beds": beds,
    }


def build_metadata(beds_meta: dict, rate_meta: dict, inputs: list) -> dict:
    beds_source = [_select_present(entry, SOURCE_KEYS) for entry in beds_meta["source"]]
    rate_source = [_select_present(entry, SOURCE_KEYS) for entry in rate_meta["source"]]
    if beds_source != rate_source:
        raise SystemExit(
            "prefecture_beds.csv.meta.json と prefecture_bed_report_rate.csv.meta.json の source が"
            "一致しません(両方とも同一のR7/001722915.xlsx・R6/別添４②から派生しているはずです)。"
            f"beds={beds_source} rate={rate_source}"
        )

    beds_caveat = beds_meta["processing"]["caveat"]
    rate_caveat = rate_meta["processing"]["caveat"]
    if beds_caveat != rate_caveat:
        raise SystemExit(
            "prefecture_beds.csv.meta.json と prefecture_bed_report_rate.csv.meta.json の"
            f"processing.caveatが一致しません。beds={beds_caveat!r} rate={rate_caveat!r}"
        )

    caveat = (
        beds_caveat
        + " 見込量2025はR6公表時点の見込みであり、実績2025(R7公表分)とは公表回が異なる。"
        "また報告率が年度により異なるため(report_rate_2024/report_rate_2025)、"
        "病床数の年度間の変化には報告率の変動が混ざりうる。"
        "なお2024年実績はR6公表分から採っているが、都道府県層ではR7公表分と全キーで"
        "一致する(検証9)ため、どちらから採っても同じ値である"
        "(構想区域層とは異なり、採用の判断を要しない)。"
    )

    # known_issues は入力CSVのmeta.jsonから引き継ぐのみで、本スクリプトでは足さない。
    # 構想区域版が足している area_yoy_2024_actual_from_r6 は「R7の2024年実績が使えない
    # ため R6 を採る」という判断の記録だが、都道府県層ではそもそも両者が一致するため
    # (検証9)判断が発生しない。非欠陥の事実を known_issues に入れると、画面の
    # 「データの既知の問題」欄に問題でないものが並ぶので、caveat と fields に書く。
    known_issues = list(beds_meta.get("known_issues", [])) + list(rate_meta.get("known_issues", []))

    return {
        "title": (
            "都道府県別 病床数 年度間比較（R6公表分の見込量2025・実績2024とR7公表分の実績2025、"
            "可視化サイト表示用）"
        ),
        "source": beds_source,
        "processing": {
            "script": "tools/build_web_prefecture_yoy.py",
            "inputs": inputs,
            "steps": [
                "prefecture_beds.csv・prefecture_bed_report_rate.csv・"
                "prefecture_boundaries_R7.geojsonを読み込み",
                "2CSVにpublished_fy=='R6'/'R7'の両方が存在することを確認(検証1)",
                f"pref_code集合が2CSVのR6/R7で一致し{EXPECTED_ENTITY_COUNT}件(全国含む)、"
                f"境界GeoJSONが全国を除く{EXPECTED_PREFECTURE_COUNT}件と一致することを確認(検証2)",
                "pref_nameがR6/R7/境界GeoJSONの3者で一致することを確認(検証3)",
                f"各pref_code×5機能についてplan_2025(R6見込量2025)・actual_2025(R7実績2025)・"
                f"actual_2024(R6実績2024)がちょうど1件ずつ存在することを確認"
                f"(検証4、{EXPECTED_ENTITY_COUNT}×5×3={EXPECTED_ENTITY_COUNT * 15}セル)",
                "上記3系列の値が非負の整数で欠測が無いことを確認(検証5)",
                "report_rate_2024(R6・2024年)・report_rate_2025(R7・2025年)が"
                f"{EXPECTED_ENTITY_COUNT}件ぶん揃い0〜1の範囲であることを確認(検証6)",
                "3系列いずれも「合計」が他4機能の和と一致することを確認(検証7)",
                "3系列いずれも全国(00)が47都道府県の合計と一致することを確認(検証8)",
                "2024年実績がR6公表分とR7公表分で全キー一致することを確認(検証9。"
                "構想区域側の既知の欠陥area_beds_2024_actual_duplicated_as_2025が"
                "都道府県層には無いことの担保)",
                "plan_2025/actual_2024が0の(pref_code,機能)の件数をログ出力(検証10。"
                "エラーにはしない。実測は0件だが、将来0が現れてもフロントの「算出不可」"
                "機構がそのまま効くため)",
                "比率(実績2025÷見込量2025・実績2025÷実績2024)は出力せず、フロントエンド側で算出する",
                "全国(00)はprefectures配列ではなくnationalキーに分け、"
                "prefecturesはpref_codeの昇順(文字列ソート)で整列",
            ],
            "caveat": caveat,
        },
        "fields": FIELD_DESCRIPTIONS,
        "known_issues": known_issues,
    }


def build_and_write(out_path: Path) -> Path:
    """入力3ファイルを読み込み・検証・変換し、`out_path`へ表示用データセットの
    JSONを書き出す(再現性テストでの再利用のため、出力先を引数化している)。

    戻り値: 書き出したファイルのPath。
    """
    beds_rows = _load_csv_rows(PREFECTURE_BEDS_CSV)
    rate_rows = _load_csv_rows(PREFECTURE_BED_REPORT_RATE_CSV)
    geo_pref_names = _load_geojson_pref_codes(PREFECTURE_BOUNDARIES_GEOJSON)
    print(
        f"[ok] 入力読み込み: prefecture_beds.csv={len(beds_rows)}行 "
        f"prefecture_bed_report_rate.csv={len(rate_rows)}行 "
        f"prefecture_boundaries_R7.geojson={len(geo_pref_names)}都道府県"
    )

    indexed = validate_and_index(beds_rows, rate_rows, geo_pref_names)
    print("[ok] 検証1〜9完了")

    log_zero_counts(indexed["plan_2025"], indexed["actual_2024"])

    national = build_entry(NATIONAL_CODE, indexed)
    prefectures = [build_entry(code, indexed) for code in indexed["prefecture_codes"]]
    print(f"[ok] 構築: {len(prefectures)}都道府県 + 全国")

    with open(PREFECTURE_BEDS_META_PATH, "r", encoding="utf-8") as f:
        beds_meta = json.load(f)
    with open(PREFECTURE_BED_REPORT_RATE_META_PATH, "r", encoding="utf-8") as f:
        rate_meta = json.load(f)

    inputs = [
        {"path": "data/processed/prefecture_beds.csv", "sha256": sha256(PREFECTURE_BEDS_CSV)},
        {
            "path": "data/processed/prefecture_bed_report_rate.csv",
            "sha256": sha256(PREFECTURE_BED_REPORT_RATE_CSV),
        },
        {
            "path": "data/processed/prefecture_boundaries_R7.geojson",
            "sha256": sha256(PREFECTURE_BOUNDARIES_GEOJSON),
        },
    ]
    metadata = build_metadata(beds_meta, rate_meta, inputs)

    output = {
        "metadata": metadata,
        "functions": FUNCTIONS,
        "function_labels": FUNCTION_LABELS,
        "national": national,
        "prefectures": prefectures,
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[ok] 出力: {out_path}")
    print(f"     都道府県数: {len(prefectures)}(+全国)")
    print(f"     サイズ: {out_path.stat().st_size:,} bytes")
    print(f"     sha256 = {sha256(out_path)}")

    return out_path


def main() -> None:
    build_and_write(OUT_PATH)


if __name__ == "__main__":
    main()
