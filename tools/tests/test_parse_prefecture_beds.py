# -*- coding: utf-8 -*-
"""tools/parse_prefecture_beds.py のテスト。

R7(001722915.xlsx)のパース結果を中心に、集計の整合性・スポット値・
派生比率列との検算・R6との列ずれ回帰・再現性(バイト一致)を検証する。
"""
import json
import math
from collections import defaultdict

import pytest

from tools.lib.codes import normalize_pref_code
from tools.lib.provenance import REPO_ROOT, recorded_hash, verify_source
from tools.parse_prefecture_beds import (
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


@pytest.fixture(scope="module")
def r7():
    ws, cfg, source_sha256 = load_sheet("R7")
    result = parse_sheet(ws, published_fy="R7")
    return {"ws": ws, "cfg": cfg, "source_sha256": source_sha256, "result": result}


@pytest.fixture(scope="module")
def r7_beds_lookup(r7):
    return {
        (row["pref_code"], row["bed_function"], row["series"], row["year"]): row["beds"]
        for row in r7["result"].beds_rows
    }


# --- 3. ブロック数・pref_code・都道府県名スポット確認・行数 --------------


def test_block_count_and_pref_code_uniqueness(r7):
    codes = [row["pref_code"] for row in r7["result"].basic_rows]
    assert NUM_BLOCKS == 48
    assert len(codes) == 48
    assert len(set(codes)) == 48
    assert set(codes) == {f"{i:02d}" for i in range(48)}


def test_pref_name_spotcheck(r7):
    names = {row["pref_code"]: row["pref_name"] for row in r7["result"].basic_rows}
    assert names["00"] == "全国"
    assert names["01"] == "北海道"
    assert names["47"] == "沖縄県"


def test_row_counts(r7):
    result = r7["result"]
    assert len(result.beds_rows) == 2640
    assert len(result.report_rate_rows) == 432
    assert len(result.basic_rows) == 48


# --- 4/5. 「合計」=4機能の和、「全国」=47都道府県の和 ----------------------


def test_total_equals_sum_of_four_functions(r7):
    grouped = defaultdict(dict)
    for row in r7["result"].beds_rows:
        key = (row["pref_code"], row["series"], row["year"])
        grouped[key][row["bed_function"]] = row["beds"]

    assert len(grouped) == 48 * 11  # 48ブロック × (実績9年+見込量1年+必要数1年)
    violations = []
    for key, funcs in grouped.items():
        assert set(funcs) == set(BED_FUNCTIONS), key
        parts = sum(funcs[f] for f in ("高度急性期", "急性期", "回復期", "慢性期"))
        if funcs["合計"] != parts:
            violations.append((key, funcs["合計"], parts))
    assert violations == []


def test_national_equals_sum_of_prefectures(r7):
    national = {}
    pref_sum = defaultdict(int)
    for row in r7["result"].beds_rows:
        key = (row["bed_function"], row["series"], row["year"])
        if row["pref_code"] == "00":
            national[key] = row["beds"]
        else:
            pref_sum[key] += row["beds"]

    assert set(national) == set(pref_sum)
    violations = [
        (key, value, pref_sum[key]) for key, value in national.items() if value != pref_sum[key]
    ]
    assert violations == []


# --- 6. 原典の派生比率列との検算(列マッピングの正しさの証明) --------------


def _find_header_col(ws, header_row, max_col, text):
    for col in range(1, max_col + 1):
        v = ws.cell(row=header_row, column=col).value
        if v is not None and str(v).replace("\n", "") == text:
            return col
    raise AssertionError(f"サブヘッダーに見出し {text!r} が見つかりません")


def test_derived_ratio_columns_match_recalculation(r7, r7_beds_lookup):
    ws = r7["ws"]
    header_row = BLOCK_TOP0 + 8
    max_col = ws.max_column

    col_ratio_to_required = _find_header_col(ws, header_row, max_col, "2025年必要数に対する比")
    col_ratio_to_2015 = _find_header_col(ws, header_row, max_col, "2015年に対する比")
    col_diff_to_2015 = _find_header_col(ws, header_row, max_col, "2015年との差")
    col_plan_over_required = _find_header_col(ws, header_row, max_col, "見込み／必要数")

    checked = 0
    for block in range(NUM_BLOCKS):
        top = BLOCK_TOP0 + BLOCK_SIZE * block
        pref_code = normalize_pref_code(ws.cell(row=top + 2, column=6).value)
        for i, bed_function in enumerate(BED_FUNCTIONS):
            row = top + 9 + i
            actual_2015 = r7_beds_lookup[(pref_code, bed_function, "実績", 2015)]
            actual_2025 = r7_beds_lookup[(pref_code, bed_function, "実績", 2025)]
            plan_2026 = r7_beds_lookup[(pref_code, bed_function, "見込量", 2026)]
            required_2025 = r7_beds_lookup[(pref_code, bed_function, "必要数", 2025)]

            ratio_to_required = ws.cell(row=row, column=col_ratio_to_required).value
            ratio_to_2015 = ws.cell(row=row, column=col_ratio_to_2015).value
            diff_to_2015 = ws.cell(row=row, column=col_diff_to_2015).value
            plan_over_required = ws.cell(row=row, column=col_plan_over_required).value

            assert math.isclose(ratio_to_required, actual_2015 / required_2025, rel_tol=1e-9)
            assert math.isclose(ratio_to_2015, actual_2025 / actual_2015, rel_tol=1e-9)
            assert diff_to_2015 == actual_2025 - actual_2015
            assert math.isclose(plan_over_required, plan_2026 / required_2025, rel_tol=1e-9)
            checked += 1

    assert checked == NUM_BLOCKS * len(BED_FUNCTIONS)


# --- 7. スポット値 ----------------------------------------------------


def test_spot_values(r7_beds_lookup):
    assert r7_beds_lookup[("00", "高度急性期", "必要数", 2025)] == 130455
    assert r7_beds_lookup[("01", "急性期", "実績", 2015)] == 36851
    assert r7_beds_lookup[("00", "合計", "見込量", 2026)] == 1153234


# --- 8. 基礎情報(人口・単位変換) -----------------------------------------


def test_basic_info_national(r7):
    row = next(r for r in r7["result"].basic_rows if r["pref_code"] == "00")
    assert row["population_2020"] == 126146099
    assert row["population_2020_source_value"] == 12614.6099
    assert row["population_2020_source_unit"] == "万人"


# --- 9. R6互換性(年度間の列ずれ回帰テスト) --------------------------------


def test_r6_r7_year_layout_regression():
    ws_r6, _, _ = load_sheet("R6")
    result_r6 = parse_sheet(ws_r6, published_fy="R6")
    actual_years_r6 = sorted({r["year"] for r in result_r6.beds_rows if r["series"] == "実績"})
    plan_years_r6 = sorted({r["year"] for r in result_r6.beds_rows if r["series"] == "見込量"})
    assert actual_years_r6 == [2015, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
    assert plan_years_r6 == [2025]

    ws_r7, _, _ = load_sheet("R7")
    result_r7 = parse_sheet(ws_r7, published_fy="R7")
    actual_years_r7 = sorted({r["year"] for r in result_r7.beds_rows if r["series"] == "実績"})
    plan_years_r7 = sorted({r["year"] for r in result_r7.beds_rows if r["series"] == "見込量"})
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
    assert verify_source("R7/001722915.xlsx") == recorded_hash("R7/001722915.xlsx")


# --- 10. 再現性(バイト一致) -----------------------------------------------

CSV_NAMES = [
    "prefecture_beds.csv",
    "prefecture_bed_report_rate.csv",
    "prefecture_basic.csv",
]


def test_reproducibility_byte_identical(tmp_path):
    paths = build_and_write("R7", tmp_path)
    assert paths.keys() == {"beds", "report_rate", "basic"}
    expected_sha256 = recorded_hash("R7/001722915.xlsx")

    for name in CSV_NAMES:
        committed_path = PROCESSED_DIR / name
        assert committed_path.exists(), (
            f"{committed_path} が存在しません"
            "(先に `python tools/parse_prefecture_beds.py` を実行してください)"
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
