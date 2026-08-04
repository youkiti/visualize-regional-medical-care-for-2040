# -*- coding: utf-8 -*-
"""tools/parse_area_beds.py のテスト。

R7(001723349.xlsx)のパース結果を中心に、集計の整合性・スポット値・
派生比率列との検算・既知の品質問題(2024実績の複製・三重県のXXX)の回帰・
R6との列ずれ回帰・再現性(バイト一致)を検証する。
"""
import json
import math
from collections import defaultdict

import pytest

from tools.lib.block_report import classify_bed_column, resolve_columns
from tools.lib.codes import normalize_area_code
from tools.lib.layout import read_header_row
from tools.lib.provenance import REPO_ROOT, recorded_hash, verify_source
from tools.parse_area_beds import (
    BED_FUNCTIONS,
    BLOCK_SIZE,
    BLOCK_TOP0,
    LayoutMismatchError,
    NUM_BLOCKS,
    build_and_write,
    load_sheet,
    parse_sheet,
)

PROCESSED_DIR = REPO_ROOT / "data" / "processed"

MIE_XXX_AREA_CODES = {"2405", "2406", "2407", "2408", "2409", "2410", "2411", "2412"}


@pytest.fixture(scope="module")
def r7():
    ws, cfg, source_sha256 = load_sheet("R7")
    result = parse_sheet(ws, published_fy="R7")
    return {"ws": ws, "cfg": cfg, "source_sha256": source_sha256, "result": result}


@pytest.fixture(scope="module")
def r7_beds_lookup(r7):
    return {
        (row["area_code"], row["bed_function"], row["series"], row["year"]): row["beds"]
        for row in r7["result"].beds_rows
    }


# --- ブロック数・区域コード一意性・都道府県コードとの整合 ------------------


def test_block_count_and_area_code_uniqueness(r7):
    codes = [row["area_code"] for row in r7["result"].basic_rows]
    assert NUM_BLOCKS == 339
    assert len(codes) == 339
    assert len(set(codes)) == 339


def test_area_code_prefix_matches_pref_code(r7):
    for row in r7["result"].basic_rows:
        assert row["area_code"][:2] == row["pref_code"], row


def test_pref_name_unique_per_pref_code(r7):
    names_by_code = defaultdict(set)
    for row in r7["result"].basic_rows:
        names_by_code[row["pref_code"]].add(row["pref_name"])
    assert len(names_by_code) == 47
    for pref_code, names in names_by_code.items():
        assert len(names) == 1, (pref_code, names)


def test_area_name_spotcheck(r7):
    names = {row["area_code"]: row["area_name"] for row in r7["result"].basic_rows}
    assert names["0101"] == "南渡島"
    assert names["4705"] == "八重山"


# --- 正確な行数 ----------------------------------------------------------


def test_row_counts(r7):
    result = r7["result"]
    assert len(result.beds_rows) == 18645  # 339区域 × 5機能 × 11系列
    assert len(result.report_rate_rows) == 3051  # 339区域 × 9実績年
    assert len(result.basic_rows) == 339


# --- 「合計」=4機能の和 ----------------------------------------------------


def test_total_equals_sum_of_four_functions(r7):
    grouped = defaultdict(dict)
    for row in r7["result"].beds_rows:
        key = (row["area_code"], row["series"], row["year"])
        grouped[key][row["bed_function"]] = row["beds"]

    assert len(grouped) == 339 * 11  # 339区域 × (実績9年+見込量1年+必要数1年)
    violations = []
    for key, funcs in grouped.items():
        assert set(funcs) == set(BED_FUNCTIONS), key
        parts = sum(funcs[f] for f in ("高度急性期", "急性期", "回復期", "慢性期"))
        if funcs["合計"] != parts:
            violations.append((key, funcs["合計"], parts))
    assert violations == []


# --- 原典の派生比率列との検算(列マッピングの正しさの証明) --------------


def _find_header_col(ws, header_row, max_col, text):
    for col in range(1, max_col + 1):
        v = ws.cell(row=header_row, column=col).value
        if v is not None and str(v).replace("\n", "") == text:
            return col
    raise AssertionError(f"サブヘッダーに見出し {text!r} が見つかりません")


def test_derived_ratio_columns_match_recalculation(r7, r7_beds_lookup):
    """原典の派生比率列を実績・見込量・必要数から再計算し、列マッピングの
    正しさを検算する。

    構想区域レベルは都道府県レベルよりずっと粒度が細かく、高度急性期等で
    分母(必要数2025・実績2015)が0の区域が実在する(例: 0102 高度急性期の
    必要数2025=0)。原典はこの場合、比率セルを数値ではなく文字列 `'-'` に
    している。ゼロ除算を避けるため、分母が0の行は「原典が'-'であること」
    のみ確認し、数値比較の対象からは除く。
    """
    ws = r7["ws"]
    header_row = BLOCK_TOP0 + 8
    max_col = ws.max_column

    col_ratio_to_required = _find_header_col(ws, header_row, max_col, "2025年必要数に対する比")
    col_ratio_to_2015 = _find_header_col(ws, header_row, max_col, "2015年に対する比")
    col_diff_to_2015 = _find_header_col(ws, header_row, max_col, "2015年との差")
    col_plan_over_required = _find_header_col(ws, header_row, max_col, "見込み／必要数")

    checked = 0
    zero_denominator_skipped = 0
    for block in range(NUM_BLOCKS):
        top = BLOCK_TOP0 + BLOCK_SIZE * block
        area_code = normalize_area_code(ws.cell(row=top + 3, column=6).value)
        for i, bed_function in enumerate(BED_FUNCTIONS):
            row = top + 9 + i
            actual_2015 = r7_beds_lookup[(area_code, bed_function, "実績", 2015)]
            actual_2025 = r7_beds_lookup[(area_code, bed_function, "実績", 2025)]
            plan_2026 = r7_beds_lookup[(area_code, bed_function, "見込量", 2026)]
            required_2025 = r7_beds_lookup[(area_code, bed_function, "必要数", 2025)]

            ratio_to_required = ws.cell(row=row, column=col_ratio_to_required).value
            ratio_to_2015 = ws.cell(row=row, column=col_ratio_to_2015).value
            diff_to_2015 = ws.cell(row=row, column=col_diff_to_2015).value
            plan_over_required = ws.cell(row=row, column=col_plan_over_required).value

            if required_2025 == 0:
                assert ratio_to_required == "-", (area_code, bed_function, ratio_to_required)
                assert plan_over_required == "-", (area_code, bed_function, plan_over_required)
                zero_denominator_skipped += 1
            else:
                assert math.isclose(ratio_to_required, actual_2015 / required_2025, rel_tol=1e-9)
                assert math.isclose(plan_over_required, plan_2026 / required_2025, rel_tol=1e-9)

            if actual_2015 == 0:
                assert ratio_to_2015 == "-", (area_code, bed_function, ratio_to_2015)
                zero_denominator_skipped += 1
            else:
                assert math.isclose(ratio_to_2015, actual_2025 / actual_2015, rel_tol=1e-9)

            assert diff_to_2015 == actual_2025 - actual_2015
            checked += 1

    assert checked == NUM_BLOCKS * len(BED_FUNCTIONS)
    assert zero_denominator_skipped > 0  # 分母0のケースが実在することの前提を保証する


# --- スポット値 ------------------------------------------------------------


def test_spot_values(r7_beds_lookup):
    assert r7_beds_lookup[("0101", "合計", "実績", 2015)] == 5595
    assert r7_beds_lookup[("0101", "高度急性期", "実績", 2015)] == 382
    assert r7_beds_lookup[("0101", "合計", "見込量", 2026)] == 5075
    assert r7_beds_lookup[("0101", "合計", "必要数", 2025)] == 4857
    assert r7_beds_lookup[("4705", "合計", "実績", 2015)] == 411


def test_basic_info_spotcheck(r7):
    rows = {row["area_code"]: row for row in r7["result"].basic_rows}
    minamiwatashima = rows["0101"]
    assert minamiwatashima["population_2020"] == 359223
    assert minamiwatashima["population_2020_source_value"] == 35.9223
    assert minamiwatashima["area_2020_km2"] == 2670.6
    assert minamiwatashima["outflow_rate"] == 0.035
    assert minamiwatashima["inflow_rate"] == 0.085


# --- 既知の品質問題1: 2024実績が2025実績と全区域・全機能で同一 -------------


def test_known_issue_2024_actual_duplicates_2025(r7_beds_lookup, r7):
    checked = 0
    for row in r7["result"].basic_rows:
        area_code = row["area_code"]
        for bed_function in BED_FUNCTIONS:
            v2024 = r7_beds_lookup[(area_code, bed_function, "実績", 2024)]
            v2025 = r7_beds_lookup[(area_code, bed_function, "実績", 2025)]
            assert v2024 == v2025, (area_code, bed_function, v2024, v2025)
            checked += 1
    assert checked == 339 * len(BED_FUNCTIONS)


# --- 既知の品質問題2: 三重県8区域のみ流出入率がXXX ---------------------------


def test_known_issue_mie_outflow_inflow_rate_is_xxx(r7):
    rows = {row["area_code"]: row for row in r7["result"].basic_rows}

    for area_code in MIE_XXX_AREA_CODES:
        row = rows[area_code]
        assert row["pref_name"] == "三重県", row
        assert row["outflow_rate"] is None
        assert row["outflow_rate_source_value"] == "XXX"
        assert row["inflow_rate"] is None
        assert row["inflow_rate_source_value"] == "XXX"

    other_area_codes = set(rows) - MIE_XXX_AREA_CODES
    assert len(other_area_codes) == 331
    for area_code in other_area_codes:
        row = rows[area_code]
        assert isinstance(row["outflow_rate"], (int, float))
        assert 0 <= row["outflow_rate"] <= 1
        assert row["outflow_rate_source_value"] == row["outflow_rate"]
        assert isinstance(row["inflow_rate"], (int, float))
        assert 0 <= row["inflow_rate"] <= 1
        assert row["inflow_rate_source_value"] == row["inflow_rate"]


# --- R6互換性(年度間の列ずれ回帰テスト) --------------------------------

# R6原典には一部ブロックで実績セルが空欄になっている既知の欠測が1件ある
# (ブロック2「南檜山」の高度急性期 2015実績。派生比率列も原典側で'-'表記
# されており、レイアウト崩れではなく原典データそのものの欠測)。R6を
# `parse_sheet` でフル走査すると `expect_int` の整数検証がこの欠測セルで
# 中断してしまう(R6のCSV出力自体はこのパーサのスコープ外でもある)ため、
# ここでは値の走査を伴わないヘッダー解決のみで列ずれへの追随を検証する。


def test_r6_r7_year_layout_regression():
    ws_r6, _, _ = load_sheet("R6")
    header_r6 = read_header_row(ws_r6, BLOCK_TOP0 + 8, 2, ws_r6.max_column - 1)
    col_map_r6 = resolve_columns(header_r6, col_start=2, classify=classify_bed_column)
    actual_years_r6 = sorted({year for series, year in col_map_r6.values() if series == "実績"})
    plan_years_r6 = sorted({year for series, year in col_map_r6.values() if series == "見込量"})
    assert actual_years_r6 == [2015, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
    assert plan_years_r6 == [2025]

    ws_r7, _, _ = load_sheet("R7")
    header_r7 = read_header_row(ws_r7, BLOCK_TOP0 + 8, 2, ws_r7.max_column - 1)
    col_map_r7 = resolve_columns(header_r7, col_start=2, classify=classify_bed_column)
    actual_years_r7 = sorted({year for series, year in col_map_r7.values() if series == "実績"})
    plan_years_r7 = sorted({year for series, year in col_map_r7.values() if series == "見込量"})
    assert actual_years_r7 == [2015, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
    assert plan_years_r7 == [2026]


# --- レイアウト崩れ検知(LayoutMismatchError) -----------------------------


def test_layout_mismatch_is_detected_without_touching_raw_file():
    """あるブロックのサブヘッダーが先頭ブロックと異なる場合に検知できるか。

    module スコープの `r7` フィクスチャは他のテストと共有しているため使わず、
    ここでは新規にワークブックを開いてメモリ上でのみセルを書き換える。
    `wb.save()` は一切呼ばない(R7/ 配下は編集禁止のため)。テストの最後に
    `verify_source()` で生データが改変されていないことを確認する。
    """
    ws, _, _ = load_sheet("R7")

    block = 5
    header_row = BLOCK_TOP0 + BLOCK_SIZE * block + 8
    original = ws.cell(row=header_row, column=6).value
    assert original is not None  # 前提: このセルは通常 "2015\n実績"

    ws.cell(row=header_row, column=6).value = "改変されたヘッダー"

    with pytest.raises(LayoutMismatchError):
        parse_sheet(ws, published_fy="R7")

    # ワークブックはメモリ上でのみ改変しており保存していない。生データ
    # ファイル自体は無傷であることをハッシュで確認する。
    assert verify_source("R7/001723349.xlsx") == recorded_hash("R7/001723349.xlsx")


def test_outflow_inflow_label_drift_is_detected():
    """R列(18)の推計流出/流入患者割合ラベルが動いた場合に検知できるか。

    R列は位置でハードコードしているため、ラベルセル自体を書き換えて
    レイアウト崩れとして検知されることを確認する。こちらもメモリ上の
    改変のみで `wb.save()` は呼ばない。
    """
    ws, _, _ = load_sheet("R7")

    block = 0
    label_row = BLOCK_TOP0 + BLOCK_SIZE * block + 2
    original = ws.cell(row=label_row, column=18).value
    assert original == "（推計流出患者割合）"

    ws.cell(row=label_row, column=18).value = "（別のラベル）"

    with pytest.raises(LayoutMismatchError):
        parse_sheet(ws, published_fy="R7")

    assert verify_source("R7/001723349.xlsx") == recorded_hash("R7/001723349.xlsx")


# --- 再現性(バイト一致) -----------------------------------------------------

CSV_NAMES = [
    "area_beds.csv",
    "area_bed_report_rate.csv",
    "area_basic.csv",
]


def test_reproducibility_byte_identical(tmp_path):
    paths = build_and_write("R7", tmp_path)
    assert paths.keys() == {"beds", "report_rate", "basic"}
    expected_sha256 = recorded_hash("R7/001723349.xlsx")

    for name in CSV_NAMES:
        committed_path = PROCESSED_DIR / name
        assert committed_path.exists(), (
            f"{committed_path} が存在しません"
            "(先に `python tools/parse_area_beds.py` を実行してください)"
        )
        new_bytes = (tmp_path / name).read_bytes()
        old_bytes = committed_path.read_bytes()
        assert new_bytes == old_bytes, f"{name} がコミット済みデータとバイト一致しません"

        new_meta = json.loads((tmp_path / f"{name}.meta.json").read_text(encoding="utf-8"))
        old_meta = json.loads((PROCESSED_DIR / f"{name}.meta.json").read_text(encoding="utf-8"))

        assert new_meta["source"]["source_sha256"] == expected_sha256
        assert old_meta["source"]["source_sha256"] == expected_sha256

        # processing.date は実行日ごとに変わるため、比較対象から除外する
        new_meta["processing"]["date"] = None
        old_meta["processing"]["date"] = None
        assert new_meta == old_meta, f"{name}.meta.json の内容(processing.dateを除く)が一致しません"
