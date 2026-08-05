# -*- coding: utf-8 -*-
"""可視化サイトが直接読み込む表示用データセット
`data/processed/area_yoy_R6_R7.json` を、既にコミット済みの加工CSV
(`area_beds.csv`・`area_bed_report_rate.csv`)と境界GeoJSON
(`area_boundaries_R7.geojson`、area_codeの一致検証にのみ使用しジオメトリは
読まない)から生成する。

M7チャンク3。フロントエンド(`web/`配下)は別チャンクで扱うため、本スクリプトは
`web/`配下には一切触れない。病床指標の正本(`tools/build_web_data.py` /
`data/processed/area_indicators_R7.json`)・需要推計の正本
(`tools/build_web_demand.py` / `data/processed/area_demand_R7.json`)も
別データセットのため一切変更しない。

処理内容:
  1. `area_beds.csv`・`area_bed_report_rate.csv`・`area_boundaries_R7.geojson`
     (area_codeの一致検証にのみ使用)を読み込む
  2. 検証1〜8(下記)を行い、違反があれば SystemExit で中断する(静かに
     握りつぶさない)
  3. 339区域 × 5機能について、見込量2025(R6公表)・実績2025(R7公表)・
     実績2024(R6公表)を抽出する(比率は出さない。フロント側で算出する)
  4. 区域ごとに報告率2024(R6公表)・報告率2025(R7公表)を併記する(報告率の差が
     病床数の変化を説明しうるため)
  5. `area_beds.csv.meta.json` / `area_bed_report_rate.csv.meta.json` の
     `source`(published_fy付きdictのリスト)を実行時に読み込んで引き継ぎ、
     `metadata.source` を構築する(出典情報のハードコードによる二重管理を避ける)
  6. UTF-8・LF・`ensure_ascii=False`・indent=2・末尾改行1つで出力する

検証1〜8:
  1. area_beds.csv に published_fy=='R6' と 'R7' の両方の行が存在する
     (片方しかなければ中断)
  2. 区域コード集合が area_beds.csv(R6)・area_beds.csv(R7)・
     area_boundaries_R7.geojson の3つで完全一致し339件
  3. 区域名・都道府県名がR6とR7で一致する(area_beds.csvの行から)
  4. 各(area_code, 5機能)について plan_2025(R6見込量2025)・
     actual_2025(R7実績2025)・actual_2024(R6実績2024)がちょうど1件ずつ存在する
     (計339×5×3=5085セル)
  5. 値は非負の整数であり、この3系列に欠測は無い(欠測があれば中断)
  6. 報告率(report_rate_2024・report_rate_2025)は0〜1
  7. 「合計」が他4機能の和と一致する(plan_2025・actual_2025・actual_2024の
     3系列それぞれについて)
  8. plan_2025が0の(area_code, 機能)の件数をログ出力する(エラーにはしない。
     フロントで「算出不可」表示にするため)。actual_2024が0の件数も同様に出す

三重県8区域(2405〜2412)を含め、上記5系列はいずれも欠測が無い前提で検証する
(推計流出/流入患者割合とは異なり、病床数・報告率は三重県8区域でも算出されている)。

生成日時は埋め込まない(CLAUDE.md参照。再現性テストが翌日に壊れるため)。

必要環境: Python 3.11+

使い方:
    PYTHONIOENCODING=utf-8 python tools/build_web_yoy.py
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lib.provenance import REPO_ROOT, sha256

AREA_BEDS_CSV = REPO_ROOT / "data" / "processed" / "area_beds.csv"
AREA_BED_REPORT_RATE_CSV = REPO_ROOT / "data" / "processed" / "area_bed_report_rate.csv"
AREA_BOUNDARIES_GEOJSON = REPO_ROOT / "data" / "processed" / "area_boundaries_R7.geojson"
OUT_PATH = REPO_ROOT / "data" / "processed" / "area_yoy_R6_R7.json"

AREA_BEDS_META_PATH = Path(str(AREA_BEDS_CSV) + ".meta.json")
AREA_BED_REPORT_RATE_META_PATH = Path(str(AREA_BED_REPORT_RATE_CSV) + ".meta.json")

FUNCTIONS = ["total", "high_acute", "acute", "recovery", "chronic"]
FUNCTION_LABELS = {
    "total": "合計",
    "high_acute": "高度急性期",
    "acute": "急性期",
    "recovery": "回復期",
    "chronic": "慢性期",
}
# area_beds.csv の bed_function は日本語ラベルで格納されている
# (tools/parse_area_beds.py の BED_FUNCTIONS 参照)。出力スキーマの英字キーへ
# 変換するための逆引き。
BED_FUNCTION_KEY_BY_JA = {ja: key for key, ja in FUNCTION_LABELS.items()}

# メタデータへ引き継ぐ area_beds.csv.meta.json / area_bed_report_rate.csv.meta.json の
# source配列(要素ごと)から選ぶキー。両ファイルとも同一の入力(R7/001723349.xlsx・
# R6/別添４③)から派生しているためsource自体は一致するはず(main()で照合する)。
# R6のみ持つ"source_note"は_select_present()でキーが無ければ黙って除外する。
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
    "area_code": "構想区域コード(ゼロ埋め4桁の文字列)",
    "area_name": "構想区域名",
    "pref_code": "都道府県コード(ゼロ埋め2桁の文字列)",
    "pref_name": "都道府県名",
    "report_rate_2024": (
        "R6公表分(別添４③)の2024年病床機能報告の報告率(0〜1)。R7公表分の同年報告率"
        "(report_rate_2025とは別年)とは105/339区域で異なる値になっている"
        "(area_bed_report_rate_2024_differs_between_r6_r7参照)。年度間の病床数の"
        "変化を見るときは、報告率自体も年度により異なることに留意すること"
    ),
    "report_rate_2025": "R7公表分の2025年病床機能報告の報告率(0〜1)",
    "beds": "5機能(total/high_acute/acute/recovery/chronic)ごとのplan_2025/actual_2025/actual_2024",
    "beds.plan_2025": (
        "R6公表分(別添４③)の2025年見込量(床)。実績2025(R7公表分)とは公表回が異なる"
        "見込み値である点に留意(見込みと実績のずれを見る指標)"
    ),
    "beds.actual_2025": "R7公表分の2025年実績病床数(床)",
    "beds.actual_2024": (
        "R6公表分の2024年実績病床数(床)。R7公表分の同列は2025年実績の複製という"
        "既知の原典の欠陥があるため採用していない"
        "(area_yoy_2024_actual_from_r6・area_beds_2024_actual_duplicated_as_2025参照)"
    ),
}


def _load_csv_rows(path: Path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_geojson_area_codes(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)
    return {feat["properties"]["area_code"] for feat in gj["features"]}


def _select_present(d: dict, keys) -> dict:
    """`keys` のうち `d` に存在するものだけを順序を保って取り出す。

    R6/R7で持つキーの集合が異なる場合(例: source_noteはR6のみ)があるため、
    `_select`(build_web_data.py・build_web_demand.py が使う、存在必須の厳格版)
    ではなく、存在するものだけを拾う版を使う。
    """
    return {k: d[k] for k in keys if k in d}


def split_by_fy(rows):
    result = {}
    for r in rows:
        result.setdefault(r["published_fy"], []).append(r)
    return result


def validate_and_index(beds_rows, rate_rows, geo_codes):
    """検証1〜8のうち1〜7を行い、違反があれば SystemExit で中断する。

    戻り値: (beds_by_fy, rate_by_fy, area_rows_by_code)
      beds_by_fy: {"R7": [...], "R6": [...]}(area_beds.csvのpublished_fy分割)
      rate_by_fy: {"R7": [...], "R6": [...]}(area_bed_report_rate.csvのpublished_fy分割)
      area_rows_by_code: {area_code: {"area_name":..., "pref_code":..., "pref_name":...}}
    """
    # 検証1: published_fy=='R6'/'R7' の両方が存在する
    beds_by_fy = split_by_fy(beds_rows)
    missing_fy = sorted({"R7", "R6"} - set(beds_by_fy))
    if missing_fy:
        raise SystemExit(f"検証1失敗: area_beds.csvにpublished_fy={missing_fy}の行がありません")

    beds_r7 = beds_by_fy["R7"]
    beds_r6 = beds_by_fy["R6"]

    # 検証2: 3ファイルのarea_code集合が完全一致し339件
    codes_r7 = {r["area_code"] for r in beds_r7}
    codes_r6 = {r["area_code"] for r in beds_r6}
    sets = {
        "area_beds.csv(R7)": codes_r7,
        "area_beds.csv(R6)": codes_r6,
        "area_boundaries_R7.geojson": geo_codes,
    }
    all_codes = set().union(*sets.values())
    if not (codes_r7 == codes_r6 == geo_codes) or len(codes_r7) != 339:
        missing = {name: sorted(all_codes - codes) for name, codes in sets.items()}
        raise SystemExit(
            "検証2失敗: area_codeの集合が3ファイルで一致しないか339件ではありません。"
            f"件数: R7={len(codes_r7)} R6={len(codes_r6)} geojson={len(geo_codes)}。"
            f"各ファイルに無いコード: {missing}"
        )

    # 検証3: 区域名・都道府県名がR6とR7で一致する
    names_r7 = {}
    for r in beds_r7:
        key = r["area_code"]
        val = (r["area_name"], r["pref_code"], r["pref_name"])
        if key in names_r7 and names_r7[key] != val:
            raise SystemExit(
                f"検証3失敗: area_beds.csv(R7)内でarea_code={key}のarea_name/pref_nameが"
                f"行によって揺れています: {names_r7[key]} != {val}"
            )
        names_r7[key] = val
    names_r6 = {}
    for r in beds_r6:
        key = r["area_code"]
        val = (r["area_name"], r["pref_code"], r["pref_name"])
        if key in names_r6 and names_r6[key] != val:
            raise SystemExit(
                f"検証3失敗: area_beds.csv(R6)内でarea_code={key}のarea_name/pref_nameが"
                f"行によって揺れています: {names_r6[key]} != {val}"
            )
        names_r6[key] = val
    name_mismatches = [code for code in names_r7 if names_r7[code] != names_r6.get(code)]
    if name_mismatches:
        raise SystemExit(
            f"検証3失敗: area_name/pref_nameがR6/R7で一致しない区域があります: "
            f"{name_mismatches[:10]}"
        )

    area_rows_by_code = {
        code: {"area_name": val[0], "pref_code": val[1], "pref_name": val[2]}
        for code, val in names_r7.items()
    }

    # 検証4・5: 各area_code×5機能についてplan_2025(R6見込量2025)・
    # actual_2025(R7実績2025)・actual_2024(R6実績2024)がちょうど1件ずつ存在し、
    # 非負の整数(欠測なし)であることを確認する。
    def _extract(rows, series, year, label):
        by_key = {}
        for r in rows:
            if r["series"] != series or r["year"] != str(year):
                continue
            key = (r["area_code"], r["bed_function"])
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
                f"検証4失敗: {label}が339区域×5機能={len(expected_keys)}件ちょうどではありません"
                f"(実際{len(by_key)}件)。不足={missing[:10]} 余剰={extra[:10]}"
            )
        return by_key

    plan_2025 = _extract(beds_r6, "見込量", 2025, "plan_2025(R6見込量2025)")
    actual_2025 = _extract(beds_r7, "実績", 2025, "actual_2025(R7実績2025)")
    actual_2024 = _extract(beds_r6, "実績", 2024, "actual_2024(R6実績2024)")
    print("[ok] 検証4・5: plan_2025/actual_2025/actual_2024が339区域×5機能=1695件ずつ、非負整数で欠測なし")

    # 検証7: 「合計」が他4機能の和と一致する(3系列それぞれについて)
    for label, by_key in (("plan_2025", plan_2025), ("actual_2025", actual_2025), ("actual_2024", actual_2024)):
        for code in codes_r7:
            total = by_key[(code, "合計")]
            parts_sum = sum(by_key[(code, ja)] for ja in ("高度急性期", "急性期", "回復期", "慢性期"))
            if total != parts_sum:
                raise SystemExit(
                    f"検証7失敗: {label}のarea_code={code}で「合計」が4機能の和と不一致です"
                    f"(合計={total} 4機能の和={parts_sum})"
                )
    print("[ok] 検証7: plan_2025/actual_2025/actual_2024いずれも「合計」==4機能の和")

    # 検証6: 報告率(0〜1)。report_rate_2024はR6公表分・2024年、
    # report_rate_2025はR7公表分・2025年。
    rate_by_fy = split_by_fy(rate_rows)
    missing_rate_fy = sorted({"R7", "R6"} - set(rate_by_fy))
    if missing_rate_fy:
        raise SystemExit(
            f"検証6失敗: area_bed_report_rate.csvにpublished_fy={missing_rate_fy}の行がありません"
        )

    def _extract_rate(rows, year, label):
        by_code = {}
        for r in rows:
            if r["year"] != str(year):
                continue
            code = r["area_code"]
            if code in by_code:
                raise SystemExit(f"検証6失敗: {label}が重複しています: {code}")
            value = float(r["report_rate"])
            if not (0 <= value <= 1):
                raise SystemExit(f"検証6失敗: {label}が0〜1の範囲外です: {code}={value}")
            by_code[code] = value
        if set(by_code) != codes_r7:
            missing = sorted(codes_r7 - set(by_code))
            raise SystemExit(f"検証6失敗: {label}が339区域ぶん揃っていません。不足={missing[:10]}")
        return by_code

    report_rate_2024 = _extract_rate(rate_by_fy["R6"], 2024, "report_rate_2024(R6)")
    report_rate_2025 = _extract_rate(rate_by_fy["R7"], 2025, "report_rate_2025(R7)")
    print("[ok] 検証6: report_rate_2024(R6)/report_rate_2025(R7)が339区域ぶん揃い0〜1の範囲")

    return {
        "area_rows_by_code": area_rows_by_code,
        "plan_2025": plan_2025,
        "actual_2025": actual_2025,
        "actual_2024": actual_2024,
        "report_rate_2024": report_rate_2024,
        "report_rate_2025": report_rate_2025,
    }


def log_zero_counts(plan_2025: dict, actual_2024: dict) -> None:
    """検証8: plan_2025/actual_2024が0の(area_code,機能)の件数をログ出力する(エラーにしない)。"""
    zero_plan = sorted(k for k, v in plan_2025.items() if v == 0)
    zero_actual_2024 = sorted(k for k, v in actual_2024.items() if v == 0)
    plan_by_fn = Counter(k[1] for k in zero_plan)
    actual_by_fn = Counter(k[1] for k in zero_actual_2024)
    print(
        f"[info] 検証8: plan_2025(R6見込量2025)が0の(area_code,機能)は{len(zero_plan)}件"
        f"(機能別: {dict(plan_by_fn)})"
    )
    print(
        f"[info] 検証8: actual_2024(R6実績2024)が0の(area_code,機能)は{len(zero_actual_2024)}件"
        f"(機能別: {dict(actual_by_fn)})"
    )


def build_areas(indexed: dict) -> list:
    area_rows_by_code = indexed["area_rows_by_code"]
    plan_2025 = indexed["plan_2025"]
    actual_2025 = indexed["actual_2025"]
    actual_2024 = indexed["actual_2024"]
    report_rate_2024 = indexed["report_rate_2024"]
    report_rate_2025 = indexed["report_rate_2025"]

    areas = []
    for area_code in sorted(area_rows_by_code):
        row = area_rows_by_code[area_code]
        beds = {}
        for func_key in FUNCTIONS:
            ja = FUNCTION_LABELS[func_key]
            beds[func_key] = {
                "plan_2025": plan_2025[(area_code, ja)],
                "actual_2025": actual_2025[(area_code, ja)],
                "actual_2024": actual_2024[(area_code, ja)],
            }
        areas.append(
            {
                "area_code": area_code,
                "area_name": row["area_name"],
                "pref_code": row["pref_code"],
                "pref_name": row["pref_name"],
                "report_rate_2024": report_rate_2024[area_code],
                "report_rate_2025": report_rate_2025[area_code],
                "beds": beds,
            }
        )
    return areas


def build_metadata(beds_meta: dict, rate_meta: dict, inputs: list) -> dict:
    beds_source = [_select_present(entry, SOURCE_KEYS) for entry in beds_meta["source"]]
    rate_source = [_select_present(entry, SOURCE_KEYS) for entry in rate_meta["source"]]
    if beds_source != rate_source:
        raise SystemExit(
            "area_beds.csv.meta.json と area_bed_report_rate.csv.meta.json の source が"
            "一致しません(両方とも同一のR7/001723349.xlsx・R6/別添４③から派生しているはずです)。"
            f"beds={beds_source} rate={rate_source}"
        )

    beds_caveat = beds_meta["processing"]["caveat"]
    rate_caveat = rate_meta["processing"]["caveat"]
    if beds_caveat != rate_caveat:
        raise SystemExit(
            "area_beds.csv.meta.json と area_bed_report_rate.csv.meta.json の"
            f"processing.caveatが一致しません。beds={beds_caveat!r} rate={rate_caveat!r}"
        )

    caveat = (
        beds_caveat
        + " 見込量2025はR6公表時点の見込みであり、実績2025(R7公表分)とは公表回が異なる。"
        "また報告率が年度により異なるため(report_rate_2024/report_rate_2025)、"
        "病床数の年度間の変化には報告率の変動が混ざりうる。"
    )

    known_issues = list(beds_meta.get("known_issues", [])) + list(rate_meta.get("known_issues", []))
    known_issues.append(
        {
            "id": "area_yoy_2024_actual_from_r6",
            "summary": (
                "2024年実績はR6公表分を採用した。R7公表分の同列は "
                "area_beds_2024_actual_duplicated_as_2025(2025年実績の複製になっている"
                "既知の原典の欠陥)により使えないため"
            ),
            "action": "本データセットの beds.*.actual_2024 は published_fy=='R6' の値である",
        }
    )

    return {
        "title": "構想区域別 病床数 年度間比較（R6公表分の見込量2025・実績2024とR7公表分の実績2025、可視化サイト表示用）",
        "source": [_select_present(entry, SOURCE_KEYS) for entry in beds_meta["source"]],
        "processing": {
            "script": "tools/build_web_yoy.py",
            "inputs": inputs,
            "steps": [
                "area_beds.csv・area_bed_report_rate.csv・area_boundaries_R7.geojsonを読み込み",
                "area_beds.csvにpublished_fy=='R6'/'R7'の両方が存在することを確認(検証1)",
                "3ファイルのarea_code集合が完全一致し339件であることを確認(検証2)",
                "area_name/pref_nameがR6とR7のarea_beds.csvの間で一致することを確認(検証3)",
                "各area_code×5機能についてplan_2025(R6見込量2025)・actual_2025(R7実績2025)・"
                "actual_2024(R6実績2024)がちょうど1件ずつ存在することを確認(検証4、339×5×3=5085セル)",
                "上記3系列の値が非負の整数で欠測が無いことを確認(検証5)",
                "report_rate_2024(R6・2024年)・report_rate_2025(R7・2025年)が339区域ぶん揃い"
                "0〜1の範囲であることを確認(検証6)",
                "plan_2025/actual_2025/actual_2024いずれも「合計」が他4機能の和と一致することを"
                "確認(検証7)",
                "plan_2025/actual_2024が0の(area_code,機能)の件数をログ出力(検証8。エラーには"
                "しない。フロントで「算出不可」表示にするため)",
                "比率(実績2025÷見込量2025・実績2025÷実績2024)は出力せず、フロントエンド側で算出する",
                "area_codeの昇順(文字列ソート)でareasを整列",
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
    beds_rows = _load_csv_rows(AREA_BEDS_CSV)
    rate_rows = _load_csv_rows(AREA_BED_REPORT_RATE_CSV)
    geo_codes = _load_geojson_area_codes(AREA_BOUNDARIES_GEOJSON)
    print(
        f"[ok] 入力読み込み: area_beds.csv={len(beds_rows)}行 "
        f"area_bed_report_rate.csv={len(rate_rows)}行 "
        f"area_boundaries_R7.geojson={len(geo_codes)}区域"
    )

    indexed = validate_and_index(beds_rows, rate_rows, geo_codes)
    print("[ok] 検証1〜7完了")

    log_zero_counts(indexed["plan_2025"], indexed["actual_2024"])

    areas = build_areas(indexed)
    print(f"[ok] areas構築: {len(areas)}区域")

    with open(AREA_BEDS_META_PATH, "r", encoding="utf-8") as f:
        beds_meta = json.load(f)
    with open(AREA_BED_REPORT_RATE_META_PATH, "r", encoding="utf-8") as f:
        rate_meta = json.load(f)

    inputs = [
        {"path": "data/processed/area_beds.csv", "sha256": sha256(AREA_BEDS_CSV)},
        {"path": "data/processed/area_bed_report_rate.csv", "sha256": sha256(AREA_BED_REPORT_RATE_CSV)},
        {"path": "data/processed/area_boundaries_R7.geojson", "sha256": sha256(AREA_BOUNDARIES_GEOJSON)},
    ]
    metadata = build_metadata(beds_meta, rate_meta, inputs)

    output = {
        "metadata": metadata,
        "functions": FUNCTIONS,
        "function_labels": FUNCTION_LABELS,
        "areas": areas,
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[ok] 出力: {out_path}")
    print(f"     区域数: {len(areas)}")
    print(f"     サイズ: {out_path.stat().st_size:,} bytes")
    print(f"     sha256 = {sha256(out_path)}")

    return out_path


def main() -> None:
    build_and_write(OUT_PATH)


if __name__ == "__main__":
    main()
