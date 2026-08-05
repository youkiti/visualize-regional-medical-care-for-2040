# -*- coding: utf-8 -*-
"""可視化サイトが直接読み込む表示用データセット
`data/processed/area_indicators_R7.json` を、既にコミット済みの加工CSV
(`area_beds.csv`・`area_basic.csv`)と境界GeoJSON(`area_boundaries_R7.geojson`、
area_codeの一致検証にのみ使用しジオメトリは読まない)から生成する。

M3「最小の公開サイト」の Chunk A（データ層のみ）。フロントエンド
(Vite/React/MapLibre)は別チャンクで扱うため、本スクリプトは`web/`配下や
package.json等には一切触れない。

処理内容:
  1. `area_beds.csv`・`area_basic.csv`・`area_boundaries_R7.geojson`
     (area_codeの一致検証にのみ使用)を読み込む
  2. 検証1〜8(下記)を行い、違反があれば SystemExit で中断する(静かに
     握りつぶさない)
  3. 339区域 × 5機能について、`series=='実績' and year=='2025'` を
     `actual_2025`、`series=='必要数' and year=='2025'` を `need_2025` として
     抽出する(2024年実績は既知欠陥[2025年実績の複製]のため出力しない。
     見込量2026・比率も出力対象外)
  4. `area_beds.csv.meta.json` / `area_basic.csv.meta.json` の `source` を
     実行時に読み込んで引き継ぎ、`metadata.source` を構築する(出典情報の
     ハードコードによる二重管理を避ける)
  5. UTF-8・LF・`ensure_ascii=False`・indent=2・末尾改行1つで出力する

検証1〜8:
  1. area_beds.csv / area_basic.csv は published_fy == 'R7' の行だけに絞り込んでから
     以降の検証・抽出を行う(両CSVともR6/R7が published_fy で並存するようになった
     [M7]ため)。絞り込み後に0行ならSystemExitで中断する
  2. (area_code, bed_function, series, year) に重複がない
  3. area_beds.csv / area_basic.csv / area_boundaries_R7.geojson の area_code
     集合が3つとも完全一致し、要素数がちょうど339
  4. 各area_code×5機能について実績2025・必要数2025がちょうど1行ずつ存在する
     (計 339×5×2 = 3390セル)
  5. beds は全て非負の整数
  6. area_code の上2桁 == pref_code、area_code は4桁の数字文字列
  7. area_name / pref_name が area_beds.csv と area_basic.csv の間で一致する
  8. 必要数が0の(area_code, 機能)の件数をログとして標準出力へ出す
     (実データに10件あり、それ自体は正常なのでエラーにしない)

三重県8区域(2405〜2412)は推計流出/流入患者割合の原典が文字列'XXX'(未算出)
で area_basic.csv の数値列が空のため、出力では outflow_rate/inflow_rate に
null を入れ、`flow_rate_unavailable` キーに原典値('XXX')を追加する
(値が入る区域にはこのキー自体を出さない)。'XXX' を 0 として扱うことは
絶対にしない。

生成日時は埋め込まない(CLAUDE.md参照。再現性テストが翌日に壊れるため)。

必要環境: Python 3.11+

使い方:
    PYTHONIOENCODING=utf-8 python tools/build_web_data.py
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
AREA_BASIC_CSV = REPO_ROOT / "data" / "processed" / "area_basic.csv"
AREA_BOUNDARIES_GEOJSON = REPO_ROOT / "data" / "processed" / "area_boundaries_R7.geojson"
OUT_PATH = REPO_ROOT / "data" / "processed" / "area_indicators_R7.json"

AREA_BEDS_META_PATH = Path(str(AREA_BEDS_CSV) + ".meta.json")
AREA_BASIC_META_PATH = Path(str(AREA_BASIC_CSV) + ".meta.json")

FUNCTIONS = ["total", "high_acute", "acute", "recovery", "chronic"]
FUNCTION_LABELS = {
    "total": "合計",
    "high_acute": "高度急性期",
    "acute": "急性期",
    "recovery": "回復期",
    "chronic": "慢性期",
}
# area_beds.csv の bed_function は日本語ラベルで格納されている(tools/parse_area_beds.py
# の BED_FUNCTIONS 参照)。出力スキーマの英字キーへ変換するための逆引き。
BED_FUNCTION_KEY_BY_JA = {ja: key for key, ja in FUNCTION_LABELS.items()}

# メタデータへ引き継ぐ area_beds.csv.meta.json / area_basic.csv.meta.json の
# source ブロックのキー。両ファイルとも同一のR7/001723349.xlsxから派生して
# いるため値は一致するはず(main()で照合する)。
SOURCE_KEYS = (
    "name",
    "publisher",
    "url",
    "page_url",
    "fiscal_year",
    "source_file",
    "source_sha256",
    "acquired_date",
    "license",
    "original_notes",
)

FIELD_DESCRIPTIONS = {
    "functions": "病床機能区分の英字キー一覧(表示順)。total=合計、他4区分の和",
    "function_labels": "機能キー -> 日本語ラベルの対応(表示用)",
    "area_code": "構想区域コード(ゼロ埋め4桁の文字列)",
    "area_name": "構想区域名",
    "pref_code": "都道府県コード(ゼロ埋め2桁の文字列)",
    "pref_name": "都道府県名",
    "population_2020": "2020年国勢調査人口(人単位の整数、area_basic.csvのpopulation_2020をそのまま)",
    "area_km2": "2020年面積(km2、area_basic.csvのarea_2020_km2をそのまま)",
    "outflow_rate": (
        "推計流出患者割合(0〜1)。原典が数値の場合のみ値を持つ。三重県8区域"
        "(2405〜2412)は原典が'XXX'(未算出)のためnull(flow_rate_unavailable参照)。"
        "'XXX'を0として扱ってはならない"
    ),
    "inflow_rate": (
        "推計流入患者割合(0〜1)。原典が数値の場合のみ値を持つ。三重県8区域"
        "(2405〜2412)は原典が'XXX'(未算出)のためnull(flow_rate_unavailable参照)。"
        "'XXX'を0として扱ってはならない"
    ),
    "flow_rate_unavailable": (
        "outflow_rate/inflow_rateがnullの区域にのみ存在するキー。原典の非数値"
        "センチネル値('XXX')をそのまま保持する。値が入る区域にはこのキー自体が存在しない"
    ),
    "beds": "5機能(total/high_acute/acute/recovery/chronic)ごとの2025年実績・必要数",
    "beds.actual_2025": (
        "病床機能報告による2025年実績病床数(床)。"
        "area_beds.csvのseries=='実績' and year=='2025'"
    ),
    "beds.need_2025": (
        "2025年の必要病床数(床、地域医療構想における将来の病床数の必要量)。"
        "area_beds.csvのseries=='必要数' and year=='2025'"
    ),
}


def _load_csv_rows(path: Path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_geojson_area_codes(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)
    return {feat["properties"]["area_code"] for feat in gj["features"]}


def _select(d: dict, keys) -> dict:
    return {k: d[k] for k in keys}


def _r7_source(meta: dict, label: str) -> dict:
    """`<csv>.meta.json` の `source` から published_fy=='R7' の要素を返す。

    area_beds.csv・area_basic.csvはR6/R7が published_fy で並存するように
    なった(M7)ため `source` がリストになっている。本データセット
    (area_indicators_R7.json)はR7のみで構成されるため、R7の出典情報だけを
    取り出す。
    """
    for entry in meta["source"]:
        if entry.get("published_fy") == "R7":
            return entry
    raise SystemExit(f"{label}: sourceにpublished_fy=='R7'の要素が見つかりません")


def _filter_known_issues_for_r7(issues: list) -> list:
    """`known_issues` から、scope.published_fy が明示的に'R7'以外(=R6行についての
    既知の欠陥)になっている項目を除外する。published_fyキーが無い項目は両年度に
    当てはまるため残す。

    area_beds.csv.meta.json・area_basic.csv.meta.json はR6/R7が並存するように
    なった(M7)ため、R7行のみで構成される本データセットには当てはまらない
    R6限定の既知欠陥(area_beds_r6_2015_actual_missing_minamihiyama・
    area_basic_r6_net_flow_rate_different_concept)が混ざっている。画面の
    出典欄に出すと利用者を誤誘導するため、ここで絞り込む。
    """
    return [issue for issue in issues if issue.get("scope", {}).get("published_fy", "R7") == "R7"]


def validate_and_index(beds_rows, basic_rows, geo_codes):
    """検証1〜7を行い、違反があれば SystemExit で中断する。

    戻り値: (actual_by_key, need_by_key, basic_by_code)
      actual_by_key / need_by_key: {(area_code, bed_function_ja): beds(int)}
      basic_by_code: {area_code: row(dict)}
    """
    # 検証1: published_fy == 'R7' の行だけに絞り込む(area_beds.csv・area_basic.csv
    # ともにR6/R7が published_fy で並存するようになった[M7]ため、まずこの
    # データセットが対象とするR7行だけに絞ってから以降の検証・抽出を行う)。
    beds_rows = [r for r in beds_rows if r["published_fy"] == "R7"]
    if not beds_rows:
        raise SystemExit("検証1失敗: area_beds.csvにpublished_fy=='R7'の行がありません")
    basic_rows = [r for r in basic_rows if r["published_fy"] == "R7"]
    if not basic_rows:
        raise SystemExit("検証1失敗: area_basic.csvにpublished_fy=='R7'の行がありません")

    # 検証2: (area_code, bed_function, series, year) の重複なし
    key_counts = Counter((r["area_code"], r["bed_function"], r["series"], r["year"]) for r in beds_rows)
    dup = sorted(k for k, n in key_counts.items() if n > 1)
    if dup:
        raise SystemExit(f"検証2失敗: (area_code,bed_function,series,year)が重複しています: {dup[:20]}")

    # 検証3: 3ファイルのarea_code集合が完全一致し339件
    beds_codes = {r["area_code"] for r in beds_rows}
    basic_codes = {r["area_code"] for r in basic_rows}
    sets = {
        "area_beds.csv": beds_codes,
        "area_basic.csv": basic_codes,
        "area_boundaries_R7.geojson": geo_codes,
    }
    all_codes = set().union(*sets.values())
    if not (beds_codes == basic_codes == geo_codes) or len(beds_codes) != 339:
        missing = {name: sorted(all_codes - codes) for name, codes in sets.items()}
        raise SystemExit(
            "検証3失敗: area_codeの集合が3ファイルで一致しないか339件ではありません。"
            f"件数: area_beds.csv={len(beds_codes)} area_basic.csv={len(basic_codes)} "
            f"area_boundaries_R7.geojson={len(geo_codes)}。各ファイルに無いコード: {missing}"
        )

    # 検証4: 各area_code×5機能について実績2025・必要数2025がちょうど1行ずつ存在
    actual_rows = [r for r in beds_rows if r["series"] == "実績" and r["year"] == "2025"]
    need_rows = [r for r in beds_rows if r["series"] == "必要数" and r["year"] == "2025"]
    expected_pairs = {(code, ja) for code in beds_codes for ja in BED_FUNCTION_KEY_BY_JA}
    actual_pairs = {(r["area_code"], r["bed_function"]) for r in actual_rows}
    need_pairs = {(r["area_code"], r["bed_function"]) for r in need_rows}
    if len(actual_rows) != len(expected_pairs) or actual_pairs != expected_pairs:
        raise SystemExit(
            "検証4失敗: 実績2025(series=='実績' and year=='2025')が"
            f"339区域×5機能={len(expected_pairs)}件ちょうどではありません"
            f"(実際{len(actual_rows)}件)。不足={sorted(expected_pairs - actual_pairs)[:10]} "
            f"余剰={sorted(actual_pairs - expected_pairs)[:10]}"
        )
    if len(need_rows) != len(expected_pairs) or need_pairs != expected_pairs:
        raise SystemExit(
            "検証4失敗: 必要数2025(series=='必要数' and year=='2025')が"
            f"339区域×5機能={len(expected_pairs)}件ちょうどではありません"
            f"(実際{len(need_rows)}件)。不足={sorted(expected_pairs - need_pairs)[:10]} "
            f"余剰={sorted(need_pairs - expected_pairs)[:10]}"
        )

    # 検証5: beds は全て非負の整数
    for r in beds_rows:
        try:
            beds = int(r["beds"])
        except (TypeError, ValueError):
            raise SystemExit(f"検証5失敗: bedsが整数として解釈できません: {r}")
        if beds != float(r["beds"]) or beds < 0:
            raise SystemExit(f"検証5失敗: bedsが非負の整数ではありません: {r}")

    # 検証6: area_code の上2桁 == pref_code、area_codeは4桁の数字文字列
    basic_by_code = {}
    for r in basic_rows:
        code = r["area_code"]
        if not (len(code) == 4 and code.isdigit()):
            raise SystemExit(f"検証6失敗: area_codeが4桁の数字文字列ではありません: {code!r}")
        if code[:2] != r["pref_code"]:
            raise SystemExit(
                f"検証6失敗: area_code={code}の上2桁がpref_code={r['pref_code']!r}と一致しません"
            )
        basic_by_code[code] = r

    # 検証7: area_name / pref_name が area_beds.csv と area_basic.csv の間で一致
    beds_names = {}
    for r in beds_rows:
        key = r["area_code"]
        val = (r["area_name"], r["pref_code"], r["pref_name"])
        if key in beds_names and beds_names[key] != val:
            raise SystemExit(
                f"検証7失敗: area_beds.csv内でarea_code={key}のarea_name/pref_nameが"
                f"行によって揺れています: {beds_names[key]} != {val}"
            )
        beds_names[key] = val
    for code, val in beds_names.items():
        basic_row = basic_by_code[code]
        basic_val = (basic_row["area_name"], basic_row["pref_code"], basic_row["pref_name"])
        if val != basic_val:
            raise SystemExit(
                f"検証7失敗: area_code={code}のarea_name/pref_nameがarea_beds.csv{val}と"
                f"area_basic.csv{basic_val}で不一致です"
            )

    actual_by_key = {(r["area_code"], r["bed_function"]): int(r["beds"]) for r in actual_rows}
    need_by_key = {(r["area_code"], r["bed_function"]): int(r["beds"]) for r in need_rows}
    return actual_by_key, need_by_key, basic_by_code


def log_zero_need_count(need_by_key) -> None:
    """検証8: 必要数が0の(area_code,機能)の件数をログ出力する(エラーにはしない)。"""
    zero = sorted(k for k, v in need_by_key.items() if v == 0)
    print(f"[info] 検証8: 必要数(2025)が0の(area_code,機能)は{len(zero)}件あります(異常ではない): {zero}")


def build_flow_rate(basic_row: dict, area_code: str):
    """area_basic.csvの1行から (outflow_rate, inflow_rate, flow_rate_unavailable)
    を組み立てる。原典が'XXX'等の非数値の場合はレート側をNoneにし、
    flow_rate_unavailableへ原典値をそのまま保持する。
    """
    outflow_str = basic_row["outflow_rate"]
    inflow_str = basic_row["inflow_rate"]
    outflow_source = basic_row["outflow_rate_source_value"]
    inflow_source = basic_row["inflow_rate_source_value"]

    if outflow_str == "" or inflow_str == "":
        if outflow_str != "" or inflow_str != "":
            raise SystemExit(
                f"想定外: area_code={area_code}のoutflow_rate/inflow_rateの欠測状態が"
                f"非対称です(outflow={outflow_str!r} inflow={inflow_str!r})"
            )
        if outflow_source != inflow_source:
            raise SystemExit(
                f"想定外: area_code={area_code}のoutflow/inflowの原典センチネル値が"
                f"異なります(outflow={outflow_source!r} inflow={inflow_source!r})"
            )
        return None, None, outflow_source

    return float(outflow_str), float(inflow_str), None


def build_areas(actual_by_key, need_by_key, basic_by_code):
    areas = []
    for area_code in sorted(basic_by_code):
        basic_row = basic_by_code[area_code]
        outflow_rate, inflow_rate, flow_rate_unavailable = build_flow_rate(basic_row, area_code)

        beds = {}
        for func_key in FUNCTIONS:
            ja = FUNCTION_LABELS[func_key]
            beds[func_key] = {
                "actual_2025": actual_by_key[(area_code, ja)],
                "need_2025": need_by_key[(area_code, ja)],
            }

        area = {
            "area_code": area_code,
            "area_name": basic_row["area_name"],
            "pref_code": basic_row["pref_code"],
            "pref_name": basic_row["pref_name"],
            "population_2020": int(basic_row["population_2020"]),
            "area_km2": float(basic_row["area_2020_km2"]),
            "outflow_rate": outflow_rate,
            "inflow_rate": inflow_rate,
            "beds": beds,
        }
        if flow_rate_unavailable is not None:
            area["flow_rate_unavailable"] = flow_rate_unavailable
        areas.append(area)
    return areas


def build_metadata(beds_meta: dict, basic_meta: dict, inputs: list) -> dict:
    beds_source = _select(_r7_source(beds_meta, "area_beds.csv.meta.json"), SOURCE_KEYS)
    basic_source = _select(_r7_source(basic_meta, "area_basic.csv.meta.json"), SOURCE_KEYS)
    if beds_source != basic_source:
        raise SystemExit(
            "area_beds.csv.meta.json と area_basic.csv.meta.json の source が一致しません"
            "(両方とも同一のR7/001723349.xlsxから派生しているはずです)。"
            f"beds={beds_source} basic={basic_source}"
        )

    beds_caveat = beds_meta["processing"]["caveat"]
    basic_caveat = basic_meta["processing"]["caveat"]
    if beds_caveat != basic_caveat:
        raise SystemExit(
            "area_beds.csv.meta.json と area_basic.csv.meta.json の processing.caveat が"
            f"一致しません。beds={beds_caveat!r} basic={basic_caveat!r}"
        )

    metadata_source = dict(beds_source)
    metadata_source["derived_via"] = [
        {"csv": "data/processed/area_beds.csv", "meta": "data/processed/area_beds.csv.meta.json"},
        {"csv": "data/processed/area_basic.csv", "meta": "data/processed/area_basic.csv.meta.json"},
    ]

    known_issues = _filter_known_issues_for_r7(
        list(beds_meta.get("known_issues", [])) + list(basic_meta.get("known_issues", []))
    )
    known_issues.append(
        {
            "id": "area_indicators_2024_actual_excluded",
            "summary": (
                "area_beds_2024_actual_duplicated_as_2025(2024実績が2025実績の複製に"
                "なっている既知の原典の問題)の影響を避けるため、本データセット"
                "(area_indicators_R7.json)では2024年実績を出力対象から除外した"
                "(2025年実績のみ採用)"
            ),
            "action": (
                "beds.*.actual_2025(2025年実績)のみを出力する。2024年実績・見込量2026・"
                "実績の時系列・比率(実績÷必要数)はいずれも出力対象外(フロントエンド側で"
                "必要に応じて算出する)"
            ),
        }
    )

    return {
        "title": "構想区域別 2025年病床数(実績)と必要数（可視化サイト表示用）",
        "source": metadata_source,
        "processing": {
            "script": "tools/build_web_data.py",
            "inputs": inputs,
            "steps": [
                "area_beds.csv・area_basic.csv・area_boundaries_R7.geojsonを読み込み",
                "area_beds.csv・area_basic.csvをpublished_fy=='R7'の行だけに絞り込み"
                "(絞り込み後に0行ならSystemExitで中断。検証1)",
                "(area_code, bed_function, series, year)の重複がないことを確認(検証2)",
                "3ファイルのarea_code集合が完全一致し339件であることを確認(検証3)",
                "各area_code×5機能について実績2025・必要数2025がちょうど1行ずつ"
                "存在することを確認(検証4、339×5×2=3390セル)",
                "beds列が全て非負の整数であることを確認(検証5)",
                "area_codeの上2桁がpref_codeと一致し、area_codeが4桁の数字文字列で"
                "あることを確認(検証6)",
                "area_name/pref_nameがarea_beds.csvとarea_basic.csvの間で一致する"
                "ことを確認(検証7)",
                "必要数(2025)が0の(area_code,機能)の件数をログ出力(検証8。エラーには"
                "しない。実データに10件あり、これ自体は正常)",
                "series=='実績' and year=='2025'をbeds.*.actual_2025、"
                "series=='必要数' and year=='2025'をbeds.*.need_2025として抽出",
                "area_basic.csvの推計流出/流入患者割合が原典'XXX'(未算出、三重県8区域)"
                "の場合はoutflow_rate/inflow_rateをnullにし、flow_rate_unavailableへ"
                "原典値をそのまま保持('XXX'を0として扱うことはしない)",
                "area_codeの昇順(文字列ソート)でareasを整列",
                "known_issues(area_beds.csv.meta.json・area_basic.csv.meta.json)のうち、"
                "scope.published_fyが'R7'以外(R6行についての既知欠陥)を除外した"
                "(本データセットはR7行のみで構成されるため)",
            ],
            "caveat": beds_caveat,
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
    basic_rows = _load_csv_rows(AREA_BASIC_CSV)
    geo_codes = _load_geojson_area_codes(AREA_BOUNDARIES_GEOJSON)
    print(
        f"[ok] 入力読み込み: area_beds.csv={len(beds_rows)}行 "
        f"area_basic.csv={len(basic_rows)}行 area_boundaries_R7.geojson={len(geo_codes)}区域"
    )

    actual_by_key, need_by_key, basic_by_code = validate_and_index(beds_rows, basic_rows, geo_codes)
    print("[ok] 検証1〜7: published_fy・重複なし・area_code集合一致(339)・実績/必要数の存在・非負整数・コード整合・名称整合を確認")

    log_zero_need_count(need_by_key)

    areas = build_areas(actual_by_key, need_by_key, basic_by_code)
    print(f"[ok] areas構築: {len(areas)}区域")

    with open(AREA_BEDS_META_PATH, "r", encoding="utf-8") as f:
        beds_meta = json.load(f)
    with open(AREA_BASIC_META_PATH, "r", encoding="utf-8") as f:
        basic_meta = json.load(f)

    inputs = [
        {"path": "data/processed/area_beds.csv", "sha256": sha256(AREA_BEDS_CSV)},
        {"path": "data/processed/area_basic.csv", "sha256": sha256(AREA_BASIC_CSV)},
        {"path": "data/processed/area_boundaries_R7.geojson", "sha256": sha256(AREA_BOUNDARIES_GEOJSON)},
    ]
    metadata = build_metadata(beds_meta, basic_meta, inputs)

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
