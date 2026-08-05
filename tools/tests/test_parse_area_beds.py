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
    EXPECTED_MISSING_BEDS,
    KNOWN_ISSUES,
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


@pytest.fixture(scope="module")
def r6():
    ws, cfg, source_sha256 = load_sheet("R6")
    result = parse_sheet(ws, published_fy="R6")
    return {"ws": ws, "cfg": cfg, "source_sha256": source_sha256, "result": result}


@pytest.fixture(scope="module")
def r6_beds_lookup(r6):
    return {
        (row["area_code"], row["bed_function"], row["series"], row["year"]): row["beds"]
        for row in r6["result"].beds_rows
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


def test_row_counts_r6(r6):
    result = r6["result"]
    assert len(result.beds_rows) == 16950  # 339区域 × 5機能 × 10系列(実績8+見込量1+必要数1)
    assert len(result.report_rate_rows) == 2712  # 339区域 × 8実績年
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
    # R7行はnet_flow_rate関連2列を常に持たない(空)
    assert minamiwatashima["net_flow_rate"] is None
    assert minamiwatashima["net_flow_rate_source_value"] is None


# --- R6: 流出入(net_flow_rate)・実績セル欠測(南檜山) -----------------------


def test_r6_basic_info_spotcheck(r6):
    rows = {row["area_code"]: row for row in r6["result"].basic_rows}
    minamihiyama = rows["0102"]
    # R6行はoutflow_rate/inflow_rate関連4列を常に持たない(空)
    assert minamihiyama["outflow_rate"] is None
    assert minamihiyama["outflow_rate_source_value"] is None
    assert minamihiyama["inflow_rate"] is None
    assert minamihiyama["inflow_rate_source_value"] is None
    assert math.isclose(minamihiyama["net_flow_rate"], -0.572, rel_tol=1e-9)
    assert math.isclose(minamihiyama["net_flow_rate_source_value"], -0.572, rel_tol=1e-9)


def test_r6_net_flow_rate_can_be_negative(r6):
    """R6の一般病床患者流出入はR7の推計流出/流入患者割合(0〜1)と異なり
    負値を取りうる(実測 -0.893〜0.434)。value_range=(-1, 1)が機能して
    いることの確認。
    """
    values = [
        row["net_flow_rate"]
        for row in r6["result"].basic_rows
        if row["net_flow_rate"] is not None
    ]
    assert values, "R6のnet_flow_rateが1件も無い(想定外)"
    assert any(v < 0 for v in values)
    assert min(values) >= -1
    assert max(values) <= 1


def test_r6_missing_bed_cell_is_blank_and_other_functions_intact(r6_beds_lookup):
    """南檜山(0102)の高度急性期・2015実績は原典で空欄(EXPECTED_MISSING_BEDS参照)。
    beds は None(CSV上は空欄)のまま出力し、合計から逆算して埋めない。
    同ブロックの他4値(合計・急性期・回復期・慢性期)は原典どおりの整数。
    """
    assert r6_beds_lookup[("0102", "高度急性期", "実績", 2015)] is None
    assert r6_beds_lookup[("0102", "合計", "実績", 2015)] == 399
    assert r6_beds_lookup[("0102", "急性期", "実績", 2015)] == 202
    assert r6_beds_lookup[("0102", "回復期", "実績", 2015)] == 0
    assert r6_beds_lookup[("0102", "慢性期", "実績", 2015)] == 197


def test_r6_missing_bed_cell_matches_expected_missing_beds_exactly():
    assert EXPECTED_MISSING_BEDS == {("R6", "0102", "高度急性期", "実績", 2015)}


def test_unknown_missing_bed_cell_is_detected():
    """EXPECTED_MISSING_BEDSに無い空セルが見つかった場合に検知できるか。

    R7の任意のセル(区域コード0101・合計・2015実績)をメモリ上でNoneに
    書き換える。`wb.save()` は呼ばない(R7/ 配下は編集禁止のため)。
    """
    ws, _, _ = load_sheet("R7")
    header = read_header_row(ws, BLOCK_TOP0 + 8, 2, ws.max_column - 1)
    col_map = resolve_columns(header, col_start=2, classify=classify_bed_column)
    col_2015 = next(c for c, (series, year) in col_map.items() if series == "実績" and year == 2015)

    block = 0  # 区域コード0101
    row = BLOCK_TOP0 + BLOCK_SIZE * block + 9  # 「合計」行(BED_FUNCTIONSの先頭)
    original = ws.cell(row=row, column=col_2015).value
    assert original is not None

    ws.cell(row=row, column=col_2015).value = None

    with pytest.raises(LayoutMismatchError):
        parse_sheet(ws, published_fy="R7")

    assert verify_source("R7/001723349.xlsx") == recorded_hash("R7/001723349.xlsx")


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


def test_known_issue_mie_net_flow_rate_is_xxx_in_r6_too(r6):
    """R6でも同じ三重県8区域でnet_flow_rateが'XXX'になっている
    (area_basic_outflow_inflow_rate_xxx_mieが両年度に当てはまることの根拠)。
    """
    rows = {row["area_code"]: row for row in r6["result"].basic_rows}

    for area_code in MIE_XXX_AREA_CODES:
        row = rows[area_code]
        assert row["pref_name"] == "三重県", row
        assert row["net_flow_rate"] is None
        assert row["net_flow_rate_source_value"] == "XXX"

    other_area_codes = set(rows) - MIE_XXX_AREA_CODES
    for area_code in other_area_codes:
        row = rows[area_code]
        assert isinstance(row["net_flow_rate"], (int, float))
        assert -1 <= row["net_flow_rate"] <= 1


# --- 既知の品質問題3: 2024実績のR6/R7差異(area_beds_2024_actual_duplicated_as_2025の追加根拠) ---


def test_known_issue_r6_2024_actual_mostly_differs_from_r7(r7_beds_lookup, r6_beds_lookup, r7):
    """R7の「2024実績」列は「2025実績」列の複製(既知の問題)だが、R6の
    2024実績はR7のそれとほとんど一致しない(=R6は複製ではなく健全な値)
    ことを数値で確認する。KNOWN_ISSUE_BEDS_2024_DUPのevidenceの根拠。
    """
    area_codes = {row["area_code"] for row in r7["result"].basic_rows}
    total = 0
    mismatched = 0
    for area_code in area_codes:
        for bed_function in BED_FUNCTIONS:
            r7_2024 = r7_beds_lookup[(area_code, bed_function, "実績", 2024)]
            r6_2024 = r6_beds_lookup[(area_code, bed_function, "実績", 2024)]
            total += 1
            if r6_2024 != r7_2024:
                mismatched += 1
    assert total == 339 * len(BED_FUNCTIONS)
    assert mismatched == 1281


# --- 既知の品質問題4: 病床機能報告の報告率(2024年)がR6/R7で一部異なる ---------


def test_known_issue_report_rate_2024_differs_between_r6_r7(r7, r6):
    r7_rr = {(row["area_code"], row["year"]): row["report_rate"] for row in r7["result"].report_rate_rows}
    r6_rr = {(row["area_code"], row["year"]): row["report_rate"] for row in r6["result"].report_rate_rows}

    area_codes_2024 = {area_code for area_code, year in r7_rr if year == 2024}
    assert len(area_codes_2024) == 339
    mismatched_2024 = [
        area_code
        for area_code in area_codes_2024
        if r6_rr.get((area_code, 2024)) != r7_rr.get((area_code, 2024))
    ]
    assert len(mismatched_2024) == 105

    for year in (2015, 2018, 2019, 2020, 2021, 2022, 2023):
        area_codes_year = {ac for ac, y in r7_rr if y == year}
        mismatched = [
            area_code
            for area_code in area_codes_year
            if r6_rr.get((area_code, year)) != r7_rr.get((area_code, year))
        ]
        assert mismatched == [], (year, mismatched)


# --- KNOWN_ISSUESの形状 -----------------------------------------------------


def test_known_issues_have_the_required_shape():
    ids = [issue["id"] for issue in KNOWN_ISSUES]
    assert len(ids) == len(set(ids)), "KNOWN_ISSUESのidが重複しています"
    valid_csvs = {"area_beds.csv", "area_bed_report_rate.csv", "area_basic.csv"}
    for issue in KNOWN_ISSUES:
        assert set(issue) >= {"id", "scope", "summary", "evidence", "action"}, issue["id"]
        assert issue["scope"]["csv"] in valid_csvs, issue["id"]
        assert isinstance(issue["evidence"], list) and issue["evidence"], issue["id"]


# --- R6互換性(年度間の列ずれ回帰テスト) --------------------------------

# R6は本番の出力経路(build_and_write)にも乗っており、`parse_sheet()` で
# フル走査できる(実績セルの欠測1件はEXPECTED_MISSING_BEDSで許容している。
# 上記「R6: 流出入(net_flow_rate)・実績セル欠測(南檜山)」参照)。このテストは
# ヘッダー文字列の列ずれ追随(実績年数・見込量の対象年がR6/R7で異なること)を
# 固定する回帰テストとして残す。


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


def test_r6_net_flow_label_drift_is_detected():
    """Q列(17)の一般病床患者流出入ラベル(R6)が動いた場合に検知できるか。

    R7のR列(18)とは異なる列(17)・異なる行オフセット(top+4)を使うため、
    別途検証する。こちらもメモリ上の改変のみで `wb.save()` は呼ばない。
    """
    ws, _, _ = load_sheet("R6")

    block = 0
    label_row = BLOCK_TOP0 + BLOCK_SIZE * block + 4
    original = ws.cell(row=label_row, column=17).value
    assert original == "（一般病床患者流出入）"

    ws.cell(row=label_row, column=17).value = "（別のラベル）"

    with pytest.raises(LayoutMismatchError):
        parse_sheet(ws, published_fy="R6")

    assert verify_source("R6/別添４③（構想区域の病床数等の状況）.xlsx") == recorded_hash(
        "R6/別添４③（構想区域の病床数等の状況）.xlsx"
    )


# --- R6を含む複数ソースの出力(--source対応) -----------------------------


def test_build_and_write_combines_r7_then_r6_in_fixed_order(tmp_path):
    """build_and_write(["R6", "R7"], ...)のように渡しても、出力行は常に
    R7が先・R6が後になることを確認する(SOURCE_ORDER固定、呼び出し順に依らない)。
    """
    build_and_write(["R6", "R7"], tmp_path)
    beds_lines = (tmp_path / "area_beds.csv").read_text(encoding="utf-8").splitlines()
    fy_column = [line.split(",")[0] for line in beds_lines[1:]]
    assert fy_column[0] == "R7"
    assert fy_column[-1] == "R6"
    assert len([i for i in range(1, len(fy_column)) if fy_column[i] != fy_column[i - 1]]) == 1


def test_build_and_write_row_counts_for_r7_plus_r6(tmp_path):
    build_and_write(["R7", "R6"], tmp_path)
    beds_rows = (tmp_path / "area_beds.csv").read_text(encoding="utf-8").splitlines()
    rate_rows = (tmp_path / "area_bed_report_rate.csv").read_text(encoding="utf-8").splitlines()
    basic_rows = (tmp_path / "area_basic.csv").read_text(encoding="utf-8").splitlines()
    assert len(beds_rows) - 1 == 18645 + 16950
    assert len(rate_rows) - 1 == 3051 + 2712
    assert len(basic_rows) - 1 == 339 + 339


def test_build_and_write_single_source_r6_only(tmp_path):
    build_and_write(["R6"], tmp_path)
    beds_rows = (tmp_path / "area_beds.csv").read_text(encoding="utf-8").splitlines()
    assert len(beds_rows) - 1 == 16950
    assert all(line.startswith("R6,") for line in beds_rows[1:])

    meta = json.loads((tmp_path / "area_beds.csv.meta.json").read_text(encoding="utf-8"))
    assert isinstance(meta["source"], list)
    assert [s["published_fy"] for s in meta["source"]] == ["R6"]


# --- 再現性(バイト一致) -----------------------------------------------------

CSV_NAMES = [
    "area_beds.csv",
    "area_bed_report_rate.csv",
    "area_basic.csv",
]


def test_reproducibility_byte_identical(tmp_path):
    # data/processed/ にコミット済みのCSVは既定(--source all = R7+R6)で
    # 生成したものなので、再現性テストも同じソース集合で再生成して比較する。
    paths = build_and_write(["R7", "R6"], tmp_path)
    assert paths.keys() == {"beds", "report_rate", "basic"}
    expected_sha256_r7 = recorded_hash("R7/001723349.xlsx")
    expected_sha256_r6 = recorded_hash("R6/別添４③（構想区域の病床数等の状況）.xlsx")

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

        for meta in (new_meta, old_meta):
            assert isinstance(meta["source"], list)
            by_fy = {s["published_fy"]: s for s in meta["source"]}
            assert set(by_fy) == {"R7", "R6"}
            assert by_fy["R7"]["source_sha256"] == expected_sha256_r7
            assert by_fy["R6"]["source_sha256"] == expected_sha256_r6

        # processing.date は実行日ごとに変わるため、比較対象から除外する
        new_meta["processing"]["date"] = None
        old_meta["processing"]["date"] = None
        assert new_meta == old_meta, f"{name}.meta.json の内容(processing.dateを除く)が一致しません"
