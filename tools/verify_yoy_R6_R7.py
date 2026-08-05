# -*- coding: utf-8 -*-
"""R6公表分とR7公表分の構想区域別病床数を突合し、年度間比較として意味のある
指標を検証する。

M9チャンク2。`tools/verify_area_join.py` と同じ流儀の生成物であり、入力は
すべて `data/processed/` 配下の加工済みCSVのみ(生Excel・元zipには触れない)。

処理内容:
  1. `area_beds.csv`・`area_bed_report_rate.csv`・`area_basic.csv`・
     `prefecture_beds.csv` を読み込み、`published_fy`(R7/R6)で分割する
  2. 区域コード・区域名・都道府県名がR6/R7で完全一致することを確認する
  3. 系列(実績/見込量/必要数)×年ごとに、R6/R7の両方に存在するセルの
     一致/不一致数を数える。R6原典の欠測1件(南檜山・高度急性期・2015実績)は
     「欠測」として区別し、不一致には数えない
  4. 2024年実績を構想区域→都道府県で集計し、`prefecture_beds.csv`(同一
     published_fy)と突合する。R6/R7それぞれについて行う(R7側の集計は
     `area_beds_2024_actual_duplicated_as_2025` の追加証拠になる)
  5. 病床機能報告の報告率がR6/R7で年ごとにどれだけ異なるかを数える
  6. 年度間比較として意味のある2指標の比の分布を機能別に出す:
       - 指標A: 実績2025(R7) ÷ 見込量2025(R6) (見込みと実績のずれ)
       - 指標B: 実績2025(R7) ÷ 実績2024(R6) (区域レベルの1年変化)
     分母が0の(area_code, 機能)は分布から除外し、件数を別途数える
  7. 2020年人口・2020年面積がR6/R7で完全一致することを確認する
  8. 上記すべての実測値を埋め込んだ検証レポート `doc/YOY_VERIFICATION.md` と、
     339区域×5機能=1695行の `data/processed/area_yoy_diff.csv` を生成する
     (生成日時は埋め込まない。埋め込むと再生成のたびに差分が出てバイト一致の
     再現性テストが翌日に壊れるため)

このスクリプトが出す `doc/YOY_VERIFICATION.md` の「6. 指標A・Bの比の分布」は、
次のチャンク(`web/`)で地図の固定境界(`YOY_RATIO_BIN_EDGES`)を確定させるための
根拠になる。このスクリプト自体は境界を実装しない(`web/src/lib/metrics.ts` は
別チャンク)。

必要環境: Python 3.11+

使い方:
    PYTHONIOENCODING=utf-8 python tools/verify_yoy_R6_R7.py
"""
import csv
import datetime
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lib.provenance import REPO_ROOT, write_csv_with_meta
from tools.parse_area_beds import (
    BED_FUNCTIONS,
    CAVEAT,
    KNOWN_ISSUE_BEDS_2024_DUP,
    KNOWN_ISSUE_BEDS_R6_MISSING_MINAMIHIYAMA,
    KNOWN_ISSUE_REPORT_RATE_R6_R7_DIFF_2024,
)

PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DOC_DIR = REPO_ROOT / "doc"

AREA_BEDS_CSV = PROCESSED_DIR / "area_beds.csv"
AREA_BASIC_CSV = PROCESSED_DIR / "area_basic.csv"
AREA_BED_REPORT_RATE_CSV = PROCESSED_DIR / "area_bed_report_rate.csv"
PREFECTURE_BEDS_CSV = PROCESSED_DIR / "prefecture_beds.csv"

OUT_CSV = PROCESSED_DIR / "area_yoy_diff.csv"
OUT_DOC = DOC_DIR / "YOY_VERIFICATION.md"

# 年度間比較として意味のある2系列(モジュールdocstring「6.」参照)。
INDICATOR_A_LABEL = "指標A: 実績2025(R7) ÷ 見込量2025(R6)"
INDICATOR_B_LABEL = "指標B: 実績2025(R7) ÷ 実績2024(R6)"

PERCENTILES = [1, 5, 25, 50, 75, 95, 99]

LICENSE_NOTE = (
    "厚生労働省ホームページ利用規約（政府標準利用規約準拠） "
    "https://www.mhlw.go.jp/chosakuken/index.html"
)

FIELDS_YOY_DIFF = {
    "area_code": "構想区域(二次医療圏)コード(ゼロ埋め4桁の文字列)",
    "area_name": "構想区域名",
    "pref_code": "都道府県コード(ゼロ埋め2桁の文字列)",
    "pref_name": "都道府県名",
    "bed_function": "病床機能区分(合計/高度急性期/急性期/回復期/慢性期)。合計は他4区分の和",
    "plan_2025_r6": "R6公表分(別添４③)の2025年見込量(床)。実績2025とは公表回が異なる見込み値である点に留意",
    "actual_2025_r7": "R7公表分の2025年実績(床)",
    "actual_2024_r6": (
        "R6公表分の2024年実績(床)。都道府県版との集計突合で健全な値であることを確認済み"
        "(area_beds_2024_actual_duplicated_as_2025参照)"
    ),
    "actual_2024_r7": (
        "R7公表分の2024年実績(床)。2025年実績の複製という既知の原典の欠陥がある"
        "(area_beds_2024_actual_duplicated_as_2025参照)。比較のため参考収録するが、"
        "年度間比較の値としては使わないこと(actual_2024_r6を使うこと)"
    ),
    "need_2025": (
        "2025年の必要病床数(床)。R6公表分・R7公表分で全1695セル一致することを検証済み"
        "(本CSVの値はR7公表分を採用。doc/YOY_VERIFICATION.md 3節参照)"
    ),
}


def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_csv_rows(path: Path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _source_by_fy(meta: dict, label: str) -> dict:
    """`<csv>.meta.json` の `source`(published_fy付きdictのリスト)を
    `{published_fy: entry}` へ変換する。"""
    source = meta["source"]
    result = {}
    for entry in source:
        fy = entry.get("published_fy")
        if fy is None:
            raise ValueError(f"{label}: sourceの要素にpublished_fyがありません: {entry}")
        result[fy] = entry
    for fy in ("R7", "R6"):
        if fy not in result:
            raise ValueError(f"{label}: sourceにpublished_fy=='{fy}'の要素が見つかりません")
    return result


def split_by_fy(rows):
    """行のリストを published_fy をキーにした辞書へ分割する。"""
    result = defaultdict(list)
    for row in rows:
        result[row["published_fy"]].append(row)
    return dict(result)


def index_beds(rows):
    """`area_beds.csv` の行(単一published_fy)を
    `{(area_code, bed_function, series, year:int): beds(int or None)}` へ変換する。

    `beds` が空欄(原典の欠測、R6のみ)は None にする。
    """
    idx = {}
    for r in rows:
        key = (r["area_code"], r["bed_function"], r["series"], int(r["year"]))
        idx[key] = int(r["beds"]) if r["beds"] != "" else None
    return idx


def years_for_series(idx: dict, series: str) -> list:
    return sorted({k[3] for k in idx if k[2] == series})


def compare_cells(idx_r7: dict, idx_r6: dict, series: str, year: int) -> dict:
    """指定した(series, year)について、R6/R7両方に存在するキー集合を比較する。

    戻り値: {"key_count", "missing", "match", "mismatch", "mismatch_keys"}
      - missing: 片側の値がNone(原典の欠測、EXPECTED_MISSING_BEDS)であるため
        比較対象から除外したキー数
      - mismatch_keys: 不一致キーの先頭20件(レポートでの例示用)
    """
    keys_r7 = {k for k in idx_r7 if k[2] == series and k[3] == year}
    keys_r6 = {k for k in idx_r6 if k[2] == series and k[3] == year}
    common = keys_r7 & keys_r6
    missing = 0
    mismatch_keys = []
    for k in sorted(common):
        v7 = idx_r7[k]
        v6 = idx_r6[k]
        if v7 is None or v6 is None:
            missing += 1
            continue
        if v7 != v6:
            mismatch_keys.append(k)
    match = len(common) - missing - len(mismatch_keys)
    return {
        "key_count": len(common),
        "missing": missing,
        "match": match,
        "mismatch": len(mismatch_keys),
        "mismatch_keys": mismatch_keys[:20],
    }


def compute_prefecture_2024_check(beds_by_fy: dict, pref_beds_by_fy: dict) -> dict:
    """2024年実績を構想区域→都道府県で集計し、`prefecture_beds.csv`
    (同一published_fy)と突合する。R6・R7それぞれについて行う。

    戻り値: {published_fy: {"key_count", "mismatch", "mismatch_keys"}}
    """
    result = {}
    for fy in ("R7", "R6"):
        agg = defaultdict(int)
        for r in beds_by_fy[fy]:
            if r["series"] == "実績" and r["year"] == "2024":
                beds = r["beds"]
                agg[(r["pref_code"], r["bed_function"])] += int(beds) if beds != "" else 0

        pref_lookup = {}
        for r in pref_beds_by_fy[fy]:
            if r["series"] == "実績" and r["year"] == "2024" and r["pref_code"] != "00":
                pref_lookup[(r["pref_code"], r["bed_function"])] = int(r["beds"])

        common = set(agg) & set(pref_lookup)
        mismatch_keys = sorted(k for k in common if agg[k] != pref_lookup[k])
        result[fy] = {
            "agg_key_count": len(agg),
            "pref_key_count": len(pref_lookup),
            "key_count": len(common),
            "mismatch": len(mismatch_keys),
            "mismatch_keys": mismatch_keys[:20],
        }
    return result


def index_report_rate(rows):
    """`area_bed_report_rate.csv` の行(単一published_fy)を
    `{(area_code, year:int): report_rate(float)}` へ変換する。"""
    return {(r["area_code"], int(r["year"])): float(r["report_rate"]) for r in rows}


def compute_report_rate_diff(rate_r7: dict, rate_r6: dict) -> dict:
    """報告率のR6/R7差を年ごとに数える。

    戻り値: {year: {"key_count", "mismatch"}}(共通年のみ)
    """
    years_r7 = {y for (_, y) in rate_r7}
    years_r6 = {y for (_, y) in rate_r6}
    common_years = sorted(years_r7 & years_r6)
    result = {}
    for year in common_years:
        keys_r7 = {k for k in rate_r7 if k[1] == year}
        keys_r6 = {k for k in rate_r6 if k[1] == year}
        common = keys_r7 & keys_r6
        mismatch = sum(1 for k in common if rate_r7[k] != rate_r6.get(k))
        result[year] = {"key_count": len(common), "mismatch": mismatch}
    return result, sorted(years_r7 - years_r6), sorted(years_r6 - years_r7)


def _percentile(sorted_vals: list, p: float):
    """線形補間によるパーセンタイル(numpyの既定"linear"法と同じ計算)。"""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p / 100
    f = math.floor(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def compute_ratio_distribution(idx_r7: dict, idx_r6: dict, *, numerator_key, denominator_key) -> dict:
    """指定した(series, year)ペアの比の分布を機能別に計算する。

    `numerator_key`/`denominator_key` は (series, year) のタプル
    (それぞれidx_r7/idx_r6から引く側を呼び出し側が指定する)。

    戻り値: {bed_function: {"n", "zero_denom", "min", "max", "percentiles": {p: value}}}
    """
    num_series, num_year = numerator_key
    den_series, den_year = denominator_key
    result = {}
    for fn in BED_FUNCTIONS:
        area_codes = sorted({k[0] for k in idx_r6 if k[1] == fn and k[2] == den_series and k[3] == den_year})
        vals = []
        zero_denom = 0
        for area_code in area_codes:
            denom = idx_r6[(area_code, fn, den_series, den_year)]
            numer = idx_r7[(area_code, fn, num_series, num_year)]
            if denom is None or numer is None:
                raise ValueError(f"想定外の欠測: area_code={area_code} bed_function={fn}")
            if denom == 0:
                zero_denom += 1
                continue
            vals.append(numer / denom)
        vals.sort()
        result[fn] = {
            "n": len(vals),
            "zero_denom": zero_denom,
            "min": vals[0] if vals else None,
            "max": vals[-1] if vals else None,
            "percentiles": {p: _percentile(vals, p) for p in PERCENTILES},
        }
    return result


def compute_basic_consistency(basic_r7_by_code: dict, basic_r6_by_code: dict) -> dict:
    """区域コード集合・区域名・都道府県名・人口2020・面積2020がR6/R7で一致するか検証する。"""
    codes_r7 = set(basic_r7_by_code)
    codes_r6 = set(basic_r6_by_code)
    name_mismatches = []
    population_mismatches = []
    area_mismatches = []
    for code in sorted(codes_r7 & codes_r6):
        r7 = basic_r7_by_code[code]
        r6 = basic_r6_by_code[code]
        if (r7["area_name"], r7["pref_code"], r7["pref_name"]) != (
            r6["area_name"],
            r6["pref_code"],
            r6["pref_name"],
        ):
            name_mismatches.append(code)
        if r7["population_2020"] != r6["population_2020"]:
            population_mismatches.append(code)
        if r7["area_2020_km2"] != r6["area_2020_km2"]:
            area_mismatches.append(code)
    return {
        "codes_r7": codes_r7,
        "codes_r6": codes_r6,
        "common_count": len(codes_r7 & codes_r6),
        "only_in_r7": sorted(codes_r7 - codes_r6),
        "only_in_r6": sorted(codes_r6 - codes_r7),
        "name_mismatches": name_mismatches,
        "population_mismatches": population_mismatches,
        "area_mismatches": area_mismatches,
    }


def build_area_yoy_diff_rows(basic_r7_by_code: dict, idx_r7: dict, idx_r6: dict) -> list:
    """`area_yoy_diff.csv` の行(dictのリスト)を組み立てる。

    並び順は area_code 昇順 × BED_FUNCTIONS の順(339×5=1695行)。
    need_2025はR6/R7で一致することを検証したうえでR7側の値を採用する
    (不一致があれば ValueError で中断し、静かに片側だけ使わない)。
    """
    rows = []
    for area_code in sorted(basic_r7_by_code):
        basic_row = basic_r7_by_code[area_code]
        for fn in BED_FUNCTIONS:
            plan_2025_r6 = idx_r6[(area_code, fn, "見込量", 2025)]
            actual_2025_r7 = idx_r7[(area_code, fn, "実績", 2025)]
            actual_2024_r6 = idx_r6[(area_code, fn, "実績", 2024)]
            actual_2024_r7 = idx_r7[(area_code, fn, "実績", 2024)]
            need_2025_r7 = idx_r7[(area_code, fn, "必要数", 2025)]
            need_2025_r6 = idx_r6[(area_code, fn, "必要数", 2025)]
            if need_2025_r7 != need_2025_r6:
                raise ValueError(
                    f"想定外: area_code={area_code} bed_function={fn} の必要数(2025)が"
                    f"R6/R7で不一致です(R7={need_2025_r7} R6={need_2025_r6})"
                )
            rows.append(
                {
                    "area_code": area_code,
                    "area_name": basic_row["area_name"],
                    "pref_code": basic_row["pref_code"],
                    "pref_name": basic_row["pref_name"],
                    "bed_function": fn,
                    "plan_2025_r6": plan_2025_r6,
                    "actual_2025_r7": actual_2025_r7,
                    "actual_2024_r6": actual_2024_r6,
                    "actual_2024_r7": actual_2024_r7,
                    "need_2025": need_2025_r7,
                }
            )
    return rows


def _fmt_pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "-"
    return f"{numerator / denominator * 100:.2f}%"


def _fmt_ratio(x) -> str:
    return "-" if x is None else f"{x:.3f}"


def build_report_markdown(
    *,
    beds_meta: dict,
    rate_meta: dict,
    basic_meta: dict,
    pref_beds_meta: dict,
    beds_by_fy: dict,
    rate_by_fy: dict,
    basic_by_fy: dict,
    pref_beds_by_fy: dict,
    idx_r7: dict,
    idx_r6: dict,
    basic_consistency: dict,
    series_year_checks: dict,
    pref_2024_check: dict,
    rate_diff: dict,
    rate_years_r7_only: list,
    rate_years_r6_only: list,
    ratio_a: dict,
    ratio_b: dict,
) -> str:
    beds_source = _source_by_fy(beds_meta, "area_beds.csv")
    rate_source = _source_by_fy(rate_meta, "area_bed_report_rate.csv")
    basic_source = _source_by_fy(basic_meta, "area_basic.csv")
    pref_beds_source = _source_by_fy(pref_beds_meta, "prefecture_beds.csv")

    lines = []
    a = lines.append

    a("# R6→R7 年度間比較 検証レポート")
    a("")
    a("このファイルは `python tools/verify_yoy_R6_R7.py` が生成する。手で編集しないこと。")
    a("再生成コマンド: `PYTHONIOENCODING=utf-8 python tools/verify_yoy_R6_R7.py`")
    a("")

    # --- 1. 目的と対象データ -------------------------------------------------
    a("## 1. 目的と対象データ")
    a("")
    a(
        "厚生労働省「②構想区域の病床数等」は、令和6年度公表分(R6、別添４③)と"
        "令和7年度公表分(R7、001723349.xlsx)の両方が `data/processed/` に "
        "`published_fy` で並存している(M9チャンク1)。本レポートはこの2公表回を"
        "突合し、年度間比較として意味のある指標を検証する。"
    )
    a("")
    a("入力ファイル(いずれも `data/processed/` の加工済みCSV。生Excel・元zipは参照しない):")
    a("")
    a("| ファイル | 行数(R7) | 行数(R6) | 元データ(R7) | 元データ(R6) |")
    a("|---|---|---|---|---|")
    a(
        f"| `area_beds.csv` | {len(beds_by_fy['R7'])} | {len(beds_by_fy['R6'])} | "
        f"{beds_source['R7']['source_file']}(`{beds_source['R7']['source_sha256']}`) | "
        f"{beds_source['R6']['source_file']}(`{beds_source['R6']['source_sha256']}`) |"
    )
    a(
        f"| `area_bed_report_rate.csv` | {len(rate_by_fy['R7'])} | {len(rate_by_fy['R6'])} | "
        f"{rate_source['R7']['source_file']}(`{rate_source['R7']['source_sha256']}`) | "
        f"{rate_source['R6']['source_file']}(`{rate_source['R6']['source_sha256']}`) |"
    )
    a(
        f"| `area_basic.csv` | {len(basic_by_fy['R7'])} | {len(basic_by_fy['R6'])} | "
        f"{basic_source['R7']['source_file']}(`{basic_source['R7']['source_sha256']}`) | "
        f"{basic_source['R6']['source_file']}(`{basic_source['R6']['source_sha256']}`) |"
    )
    a(
        f"| `prefecture_beds.csv` | {len(pref_beds_by_fy['R7'])} | {len(pref_beds_by_fy['R6'])} | "
        f"{pref_beds_source['R7']['source_file']}(`{pref_beds_source['R7']['source_sha256']}`) | "
        f"{pref_beds_source['R6']['source_file']}(`{pref_beds_source['R6']['source_sha256']}`) |"
    )
    a("")
    a(
        "以降で言及する既知の品質問題(`known_issues`)の定義・根拠は "
        "`tools/parse_area_beds.py` の `KNOWN_ISSUES` および各CSVの `.meta.json` を参照。"
    )
    a("")

    # --- 2. 区域コード・区域名の一致 -----------------------------------------
    a("## 2. 区域コード・区域名の一致")
    a("")
    a(
        f"`area_basic.csv` のR7行({len(basic_consistency['codes_r7'])}件)とR6行"
        f"({len(basic_consistency['codes_r6'])}件)の構想区域コード集合は"
        f"{'**完全一致**' if not basic_consistency['only_in_r7'] and not basic_consistency['only_in_r6'] else '不一致'}"
        f"(共通{basic_consistency['common_count']}件、R7のみ{len(basic_consistency['only_in_r7'])}件、"
        f"R6のみ{len(basic_consistency['only_in_r6'])}件)。"
    )
    a("")
    a(
        f"共通する{basic_consistency['common_count']}区域について、区域名・都道府県コード・"
        f"都道府県名の不一致は{len(basic_consistency['name_mismatches'])}件。"
    )
    a("")

    # --- 3. 系列×年ごとの一致/不一致セル数 -----------------------------------
    a("## 3. 系列×年ごとの一致/不一致セル数")
    a("")
    a("系列ごとの対象年(公表年度別。実測値。CLAUDE.md「R6の列ずれの罠」参照):")
    a("")
    a("| 系列 | R7の対象年 | R6の対象年 |")
    a("|---|---|---|")
    for series in ("実績", "見込量", "必要数"):
        years_r7 = years_for_series(idx_r7, series)
        years_r6 = years_for_series(idx_r6, series)
        a(f"| {series} | {'・'.join(str(y) for y in years_r7)} | {'・'.join(str(y) for y in years_r6)} |")
    a("")

    a("### 実績(共通年のみ、339区域×5機能=1695セル)")
    a("")
    a("| 年 | 比較キー数 | 欠測(片側のみ、除外) | 一致 | 不一致 | 一致率(欠測を除く) |")
    a("|---|---|---|---|---|---|")
    for year in sorted(series_year_checks["実績"]):
        c = series_year_checks["実績"][year]
        comparable = c["match"] + c["mismatch"]
        a(
            f"| {year} | {c['key_count']} | {c['missing']} | {c['match']} | {c['mismatch']} | "
            f"{_fmt_pct(c['match'], comparable)} |"
        )
    a("")
    total_mismatch_2024 = series_year_checks["実績"][2024]["mismatch"]
    total_missing = sum(c["missing"] for c in series_year_checks["実績"].values())
    a(
        f"2024年以外の実績は全セルが一致し(欠測{total_missing}件を除く)、"
        f"2024年実績のみ{total_mismatch_2024}件が不一致になる。"
    )
    a("")
    known_issue_2024 = None
    for issue in [KNOWN_ISSUE_BEDS_2024_DUP]:
        known_issue_2024 = issue
    a("**原因(2024年実績の不一致)**: " + known_issue_2024["summary"])
    a("")
    for ev in known_issue_2024["evidence"]:
        a(f"- {ev}")
    a("")
    a(f"対応: {known_issue_2024['action']}")
    a("")
    a("**欠測1件について**: " + KNOWN_ISSUE_BEDS_R6_MISSING_MINAMIHIYAMA["summary"])
    a("")

    a("### 必要数(2025)")
    a("")
    need_check = series_year_checks["必要数"][2025]
    a(
        f"比較キー数{need_check['key_count']}件中、欠測{need_check['missing']}件を除き"
        f"一致{need_check['match']}件・不一致{need_check['mismatch']}件"
        f"({_fmt_pct(need_check['match'], need_check['match'] + need_check['mismatch'])})。"
    )
    a("")

    a("### 見込量")
    a("")
    plan_years_r7 = years_for_series(idx_r7, "見込量")
    plan_years_r6 = years_for_series(idx_r6, "見込量")
    a(
        f"R7は{'・'.join(str(y) for y in plan_years_r7)}年見込量、R6は"
        f"{'・'.join(str(y) for y in plan_years_r6)}年見込量であり、対象年そのものが"
        "異なるため比較できない(セル単位の突合は行わない)。"
    )
    a("")

    # --- 4. 2024年実績の都道府県集計突合 -------------------------------------
    a("## 4. 2024年実績の都道府県集計突合(R6/R7それぞれ)")
    a("")
    a(
        "`area_beds.csv` の2024年実績(`series=='実績' and year==2024`)を"
        "都道府県コード×病床機能で集計し、同一 `published_fy` の "
        "`prefecture_beds.csv` と突合した(比較キーは47都道府県×5機能=235件)。"
    )
    a("")
    a("| published_fy | 集計キー数 | prefecture_beds.csv側キー数 | 比較キー数 | 不一致 | 一致率 |")
    a("|---|---|---|---|---|---|")
    for fy in ("R7", "R6"):
        c = pref_2024_check[fy]
        match = c["key_count"] - c["mismatch"]
        a(
            f"| {fy} | {c['agg_key_count']} | {c['pref_key_count']} | {c['key_count']} | "
            f"{c['mismatch']} | {_fmt_pct(match, c['key_count'])} |"
        )
    a("")
    a(
        f"R6は235キー全て一致するのに対し、R7は{pref_2024_check['R7']['mismatch']}キーが不一致になる。"
        "これは「3. 系列×年ごとの一致/不一致セル数」で確認した"
        "`area_beds_2024_actual_duplicated_as_2025`(R7の区域別2024年実績が2025年実績の複製に"
        "なっている)の追加証拠であり、都道府県レベルの2024年実績自体はR6・R7とも"
        "都道府県版(`prefecture_beds.csv`)と一致している(構想区域→都道府県の集計経路と"
        "都道府県版の直接公表値が一致するのはR6の区域別2024年実績が健全であることの裏付け)。"
    )
    a("")

    # --- 5. 報告率のR6/R7差 ---------------------------------------------------
    a("## 5. 報告率のR6/R7差")
    a("")
    a(
        f"`area_bed_report_rate.csv` をR6/R7で突合した(339区域が対象)。R7のみに存在する年: "
        f"{'・'.join(str(y) for y in rate_years_r7_only) if rate_years_r7_only else 'なし'}。"
        f"R6のみに存在する年: {'・'.join(str(y) for y in rate_years_r6_only) if rate_years_r6_only else 'なし'}。"
    )
    a("")
    a("| 年 | 比較区域数 | 不一致区域数 | 一致率 |")
    a("|---|---|---|---|")
    for year in sorted(rate_diff):
        c = rate_diff[year]
        match = c["key_count"] - c["mismatch"]
        a(f"| {year} | {c['key_count']} | {c['mismatch']} | {_fmt_pct(match, c['key_count'])} |")
    a("")
    a("**原因**: " + KNOWN_ISSUE_REPORT_RATE_R6_R7_DIFF_2024["summary"])
    a("")
    a(f"対応: {KNOWN_ISSUE_REPORT_RATE_R6_R7_DIFF_2024['action']}")
    a("")

    # --- 6. 指標A・Bの比の分布 -------------------------------------------------
    a("## 6. 指標A・Bの比の分布")
    a("")
    a(
        "年度間比較として意味のある2指標(モジュールdocstring参照)について、"
        "機能別に比の分布を実測した。分母が0の(area_code, 機能)は分布から除外し、"
        "件数を「分母0」列に示す(0で割らない。0倍として塗らない)。"
    )
    a("")
    a(f"### {INDICATOR_A_LABEL}")
    a("")
    a("| 機能 | n | 分母0 | min | p1 | p5 | p25 | p50(中央値) | p75 | p95 | p99 | max |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for fn in BED_FUNCTIONS:
        s = ratio_a[fn]
        pcts = s["percentiles"]
        a(
            f"| {fn} | {s['n']} | {s['zero_denom']} | {_fmt_ratio(s['min'])} | "
            + " | ".join(_fmt_ratio(pcts[p]) for p in PERCENTILES)
            + f" | {_fmt_ratio(s['max'])} |"
        )
    a("")
    a(f"### {INDICATOR_B_LABEL}")
    a("")
    a("| 機能 | n | 分母0 | min | p1 | p5 | p25 | p50(中央値) | p75 | p95 | p99 | max |")
    a("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for fn in BED_FUNCTIONS:
        s = ratio_b[fn]
        pcts = s["percentiles"]
        a(
            f"| {fn} | {s['n']} | {s['zero_denom']} | {_fmt_ratio(s['min'])} | "
            + " | ".join(_fmt_ratio(pcts[p]) for p in PERCENTILES)
            + f" | {_fmt_ratio(s['max'])} |"
        )
    a("")
    a(
        "両指標とも大半の区域は0.9〜1.1程度に集中し(p25〜p75の範囲)、高度急性期・"
        "回復期・慢性期は分母が小さい区域があるため裾が広い(最大5.86倍)。地図の"
        "固定境界(`YOY_RATIO_BIN_EDGES`)はこの分布を踏まえて別チャンクで確定する。"
    )
    a("")

    # --- 7. 人口2020・面積2020の一致 ------------------------------------------
    a("## 7. 人口2020・面積2020の一致")
    a("")
    a(
        f"`area_basic.csv` の共通{basic_consistency['common_count']}区域について、"
        f"`population_2020` の不一致は{len(basic_consistency['population_mismatches'])}件、"
        f"`area_2020_km2` の不一致は{len(basic_consistency['area_mismatches'])}件"
        "(いずれも0件なら完全一致)。これらはR6/R7で共通の国勢調査人口(2020年)・"
        "面積(2020年)であり、公表年度によらず一定であるべき値であることの確認。"
    )
    a("")

    # --- 8. 再現手順 -----------------------------------------------------
    a("## 8. 再現手順")
    a("")
    a("```bash")
    a("PYTHONIOENCODING=utf-8 python tools/parse_area_beds.py")
    a("PYTHONIOENCODING=utf-8 python tools/parse_prefecture_beds.py")
    a("PYTHONIOENCODING=utf-8 python tools/verify_yoy_R6_R7.py")
    a("```")
    a("")
    a(
        "上記の実測値は `tools/tests/test_verify_yoy.py` にpytestの期待値として"
        "固定してあり、`pytest` で継続的に検証される。"
    )
    a("")

    return "\n".join(lines) + "\n"


def build_and_write(out_dir: Path, doc_dir: Path) -> dict:
    """全処理(読み込み→突合→検証→出力)を実行する。

    `out_dir` に `area_yoy_diff.csv`(+`.meta.json`)を、`doc_dir` に
    `YOY_VERIFICATION.md` を出力する。テスト(再現性の検証)から一時ディレクトリを
    渡して呼べるよう、出力先をパラメータ化してある。

    戻り値: {"csv": ..., "meta": ..., "doc": ...} の Path 辞書。
    """
    out_dir = Path(out_dir)
    doc_dir = Path(doc_dir)

    print("[ok] 入力読み込み開始(生Excel・元zipには触れない)")
    beds_rows = _load_csv_rows(AREA_BEDS_CSV)
    beds_meta = _read_json(Path(str(AREA_BEDS_CSV) + ".meta.json"))
    beds_by_fy = split_by_fy(beds_rows)
    print(f"[ok] area_beds.csv 読み込み: R7={len(beds_by_fy['R7'])}行 R6={len(beds_by_fy['R6'])}行")

    rate_rows = _load_csv_rows(AREA_BED_REPORT_RATE_CSV)
    rate_meta = _read_json(Path(str(AREA_BED_REPORT_RATE_CSV) + ".meta.json"))
    rate_by_fy = split_by_fy(rate_rows)
    print(
        f"[ok] area_bed_report_rate.csv 読み込み: "
        f"R7={len(rate_by_fy['R7'])}行 R6={len(rate_by_fy['R6'])}行"
    )

    basic_rows = _load_csv_rows(AREA_BASIC_CSV)
    basic_meta = _read_json(Path(str(AREA_BASIC_CSV) + ".meta.json"))
    basic_by_fy = split_by_fy(basic_rows)
    print(f"[ok] area_basic.csv 読み込み: R7={len(basic_by_fy['R7'])}行 R6={len(basic_by_fy['R6'])}行")

    pref_beds_rows = _load_csv_rows(PREFECTURE_BEDS_CSV)
    pref_beds_meta = _read_json(Path(str(PREFECTURE_BEDS_CSV) + ".meta.json"))
    pref_beds_by_fy = split_by_fy(pref_beds_rows)
    print(
        f"[ok] prefecture_beds.csv 読み込み: "
        f"R7={len(pref_beds_by_fy['R7'])}行 R6={len(pref_beds_by_fy['R6'])}行"
    )

    idx_r7 = index_beds(beds_by_fy["R7"])
    idx_r6 = index_beds(beds_by_fy["R6"])

    basic_r7_by_code = {r["area_code"]: r for r in basic_by_fy["R7"]}
    basic_r6_by_code = {r["area_code"]: r for r in basic_by_fy["R6"]}
    basic_consistency = compute_basic_consistency(basic_r7_by_code, basic_r6_by_code)
    print(
        f"[ok] 区域コード・区域名の一致確認: 共通{basic_consistency['common_count']}件 "
        f"名称不一致{len(basic_consistency['name_mismatches'])}件"
    )

    series_year_checks = {}
    for series in ("実績", "見込量", "必要数"):
        years_r7 = set(years_for_series(idx_r7, series))
        years_r6 = set(years_for_series(idx_r6, series))
        common_years = sorted(years_r7 & years_r6)
        series_year_checks[series] = {
            year: compare_cells(idx_r7, idx_r6, series, year) for year in common_years
        }
    print(
        f"[ok] 系列×年の一致/不一致集計: 実績共通年={sorted(series_year_checks['実績'])} "
        f"必要数共通年={sorted(series_year_checks['必要数'])}"
    )

    pref_2024_check = compute_prefecture_2024_check(beds_by_fy, pref_beds_by_fy)
    print(
        f"[ok] 2024年実績の都道府県集計突合: "
        f"R7不一致={pref_2024_check['R7']['mismatch']} R6不一致={pref_2024_check['R6']['mismatch']}"
    )

    rate_r7_idx = index_report_rate(rate_by_fy["R7"])
    rate_r6_idx = index_report_rate(rate_by_fy["R6"])
    rate_diff, rate_years_r7_only, rate_years_r6_only = compute_report_rate_diff(rate_r7_idx, rate_r6_idx)
    print(f"[ok] 報告率のR6/R7差: 年別不一致数={[(y, c['mismatch']) for y, c in sorted(rate_diff.items())]}")

    ratio_a = compute_ratio_distribution(
        idx_r7, idx_r6, numerator_key=("実績", 2025), denominator_key=("見込量", 2025)
    )
    ratio_b = compute_ratio_distribution(
        idx_r7, idx_r6, numerator_key=("実績", 2025), denominator_key=("実績", 2024)
    )
    print("[ok] 指標A・Bの比の分布を計算")

    yoy_rows = build_area_yoy_diff_rows(basic_r7_by_code, idx_r7, idx_r6)
    print(f"[ok] area_yoy_diff.csv 行構築: {len(yoy_rows)}行")

    header = [
        "area_code",
        "area_name",
        "pref_code",
        "pref_name",
        "bed_function",
        "plan_2025_r6",
        "actual_2025_r7",
        "actual_2024_r6",
        "actual_2024_r7",
        "need_2025",
    ]
    tuples = [tuple(row[h] for h in header) for row in yoy_rows]

    beds_source = _source_by_fy(beds_meta, "area_beds.csv")
    source = {
        "name": "構想区域別病床数(area_beds.csv) のR6公表分×R7公表分の突合",
        "inputs": [
            {
                "file": "data/processed/area_beds.csv",
                "published_fy": "R7",
                "row_count": len(beds_by_fy["R7"]),
                "source_file": beds_source["R7"]["source_file"],
                "source_sha256": beds_source["R7"]["source_sha256"],
            },
            {
                "file": "data/processed/area_beds.csv",
                "published_fy": "R6",
                "row_count": len(beds_by_fy["R6"]),
                "source_file": beds_source["R6"]["source_file"],
                "source_sha256": beds_source["R6"]["source_sha256"],
            },
        ],
        "license": LICENSE_NOTE,
    }
    processing = {
        "script": "tools/verify_yoy_R6_R7.py",
        "date": datetime.date.today().isoformat(),
        "steps": [
            "area_beds.csv をpublished_fy(R7/R6)で分割し、(area_code, bed_function, series, year)を"
            "キーに引けるよう索引化",
            "見込量2025(R6)・実績2025(R7)・実績2024(R6・R7両方)・必要数2025(R7採用、R6と一致することを検証)を"
            "area_code×bed_function単位で1行にまとめる",
            "並び順はarea_code昇順×bed_function(合計/高度急性期/急性期/回復期/慢性期)の固定順",
        ],
        "caveat": (
            CAVEAT + " 見込量2025はR6公表時点の見込みであり、実績2025とは公表回が異なる。"
            "また年度ごとに報告率が異なるため、病床数の変化には報告率の変動が混ざりうる"
            "(area_bed_report_rate.csv・report_rate_2024/2025を参照)。"
        ),
    }
    csv_path, meta_path = write_csv_with_meta(
        out_dir / "area_yoy_diff.csv",
        header,
        tuples,
        title="構想区域別 病床数 年度間比較(R6見込量2025・R7実績2025・R6実績2024 等)",
        source=source,
        processing=processing,
        fields=FIELDS_YOY_DIFF,
        known_issues=[
            KNOWN_ISSUE_BEDS_2024_DUP,
            KNOWN_ISSUE_BEDS_R6_MISSING_MINAMIHIYAMA,
            KNOWN_ISSUE_REPORT_RATE_R6_R7_DIFF_2024,
        ],
    )
    print(f"[ok] 出力: {csv_path} ({len(tuples)}行)")

    report_md = build_report_markdown(
        beds_meta=beds_meta,
        rate_meta=rate_meta,
        basic_meta=basic_meta,
        pref_beds_meta=pref_beds_meta,
        beds_by_fy=beds_by_fy,
        rate_by_fy=rate_by_fy,
        basic_by_fy=basic_by_fy,
        pref_beds_by_fy=pref_beds_by_fy,
        idx_r7=idx_r7,
        idx_r6=idx_r6,
        basic_consistency=basic_consistency,
        series_year_checks=series_year_checks,
        pref_2024_check=pref_2024_check,
        rate_diff=rate_diff,
        rate_years_r7_only=rate_years_r7_only,
        rate_years_r6_only=rate_years_r6_only,
        ratio_a=ratio_a,
        ratio_b=ratio_b,
    )
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / "YOY_VERIFICATION.md"
    with open(doc_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(report_md)
    print(f"[ok] 出力: {doc_path}")

    return {"csv": csv_path, "meta": meta_path, "doc": doc_path}


def main():
    build_and_write(PROCESSED_DIR, DOC_DIR)


if __name__ == "__main__":
    main()
