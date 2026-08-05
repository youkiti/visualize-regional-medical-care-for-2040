# -*- coding: utf-8 -*-
"""tools/verify_yoy_R6_R7.py のテスト。

R6公表分・R7公表分の構想区域別病床数の突合結果(2024年実績1281/1695セル不一致・
都道府県集計突合でR7のみ230/235キー不一致・報告率2024が105/339区域で不一致・
指標A/Bの分布)と、`area_yoy_diff.csv`・`doc/YOY_VERIFICATION.md` の再現性
(バイト一致)を検証する。
"""
import json

import pytest

from tools.lib.provenance import REPO_ROOT
from tools.verify_yoy_R6_R7 import (
    AREA_BASIC_CSV,
    AREA_BEDS_CSV,
    AREA_BED_REPORT_RATE_CSV,
    OUT_CSV,
    OUT_DOC,
    PREFECTURE_BEDS_CSV,
    _load_csv_rows,
    _percentile,
    _read_json,
    build_and_write,
    build_area_yoy_diff_rows,
    compare_cells,
    compute_basic_consistency,
    compute_prefecture_2024_check,
    compute_ratio_distribution,
    compute_report_rate_diff,
    index_beds,
    index_report_rate,
    split_by_fy,
)

PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DOC_DIR = REPO_ROOT / "doc"


@pytest.fixture(scope="module")
def loaded():
    beds_rows = _load_csv_rows(AREA_BEDS_CSV)
    rate_rows = _load_csv_rows(AREA_BED_REPORT_RATE_CSV)
    basic_rows = _load_csv_rows(AREA_BASIC_CSV)
    pref_beds_rows = _load_csv_rows(PREFECTURE_BEDS_CSV)
    beds_by_fy = split_by_fy(beds_rows)
    rate_by_fy = split_by_fy(rate_rows)
    basic_by_fy = split_by_fy(basic_rows)
    pref_beds_by_fy = split_by_fy(pref_beds_rows)
    return {
        "beds_by_fy": beds_by_fy,
        "rate_by_fy": rate_by_fy,
        "basic_by_fy": basic_by_fy,
        "pref_beds_by_fy": pref_beds_by_fy,
        "idx_r7": index_beds(beds_by_fy["R7"]),
        "idx_r6": index_beds(beds_by_fy["R6"]),
    }


# --- 入力の行数(前提の確認) ------------------------------------------------


def test_input_counts(loaded):
    assert len(loaded["beds_by_fy"]["R7"]) == 18645
    assert len(loaded["beds_by_fy"]["R6"]) == 16950
    assert len(loaded["rate_by_fy"]["R7"]) == 3051
    assert len(loaded["rate_by_fy"]["R6"]) == 2712
    assert len(loaded["basic_by_fy"]["R7"]) == 339
    assert len(loaded["basic_by_fy"]["R6"]) == 339
    assert len(loaded["pref_beds_by_fy"]["R7"]) == 2640
    assert len(loaded["pref_beds_by_fy"]["R6"]) == 2400


# --- 区域コード・区域名・人口・面積の一致 -----------------------------------


def test_basic_consistency_full_match(loaded):
    basic_r7_by_code = {r["area_code"]: r for r in loaded["basic_by_fy"]["R7"]}
    basic_r6_by_code = {r["area_code"]: r for r in loaded["basic_by_fy"]["R6"]}
    result = compute_basic_consistency(basic_r7_by_code, basic_r6_by_code)
    assert result["common_count"] == 339
    assert result["only_in_r7"] == []
    assert result["only_in_r6"] == []
    assert result["name_mismatches"] == []
    assert result["population_mismatches"] == []
    assert result["area_mismatches"] == []


# --- 系列×年の一致/不一致(実測値の固定) ------------------------------------


def test_compare_cells_2015_has_one_missing_and_no_mismatch(loaded):
    result = compare_cells(loaded["idx_r7"], loaded["idx_r6"], "実績", 2015)
    assert result["key_count"] == 1695
    assert result["missing"] == 1
    assert result["match"] == 1694
    assert result["mismatch"] == 0


def test_compare_cells_2024_has_1281_mismatches(loaded):
    result = compare_cells(loaded["idx_r7"], loaded["idx_r6"], "実績", 2024)
    assert result["key_count"] == 1695
    assert result["missing"] == 0
    assert result["mismatch"] == 1281
    assert result["match"] == 414


def test_compare_cells_2018_to_2023_all_match(loaded):
    for year in (2018, 2019, 2020, 2021, 2022, 2023):
        result = compare_cells(loaded["idx_r7"], loaded["idx_r6"], "実績", year)
        assert result["key_count"] == 1695
        assert result["missing"] == 0
        assert result["mismatch"] == 0
        assert result["match"] == 1695


def test_compare_cells_need_2025_all_match(loaded):
    result = compare_cells(loaded["idx_r7"], loaded["idx_r6"], "必要数", 2025)
    assert result["key_count"] == 1695
    assert result["missing"] == 0
    assert result["mismatch"] == 0
    assert result["match"] == 1695


def test_plan_years_do_not_overlap(loaded):
    """見込量はR7=2026年・R6=2025年で対象年が異なり、比較キー(共通年)がないこと。"""
    years_r7 = {k[3] for k in loaded["idx_r7"] if k[2] == "見込量"}
    years_r6 = {k[3] for k in loaded["idx_r6"] if k[2] == "見込量"}
    assert years_r7 == {2026}
    assert years_r6 == {2025}
    assert years_r7.isdisjoint(years_r6)


# --- 2024年実績の都道府県集計突合 -------------------------------------------


def test_prefecture_2024_check_r7_has_230_mismatches_r6_none(loaded):
    result = compute_prefecture_2024_check(loaded["beds_by_fy"], loaded["pref_beds_by_fy"])
    assert result["R7"]["key_count"] == 235
    assert result["R7"]["mismatch"] == 230
    assert result["R6"]["key_count"] == 235
    assert result["R6"]["mismatch"] == 0


# --- 報告率のR6/R7差 ---------------------------------------------------------


def test_report_rate_diff_2024_has_105_mismatches(loaded):
    rate_r7_idx = index_report_rate(loaded["rate_by_fy"]["R7"])
    rate_r6_idx = index_report_rate(loaded["rate_by_fy"]["R6"])
    diff, years_r7_only, years_r6_only = compute_report_rate_diff(rate_r7_idx, rate_r6_idx)
    assert years_r7_only == [2025]
    assert years_r6_only == []
    for year in (2015, 2018, 2019, 2020, 2021, 2022, 2023):
        assert diff[year]["mismatch"] == 0
        assert diff[year]["key_count"] == 339
    assert diff[2024]["mismatch"] == 105
    assert diff[2024]["key_count"] == 339


# --- 指標A・Bの分布(件数・分母0件数の実測値) --------------------------------


def test_ratio_a_distribution_shape(loaded):
    ratio_a = compute_ratio_distribution(
        loaded["idx_r7"], loaded["idx_r6"], numerator_key=("実績", 2025), denominator_key=("見込量", 2025)
    )
    assert ratio_a["合計"]["n"] == 339
    assert ratio_a["合計"]["zero_denom"] == 0
    assert ratio_a["高度急性期"]["n"] == 269
    assert ratio_a["高度急性期"]["zero_denom"] == 70
    assert ratio_a["回復期"]["zero_denom"] == 5
    assert ratio_a["慢性期"]["zero_denom"] == 6
    for fn, stats in ratio_a.items():
        assert stats["n"] + stats["zero_denom"] == 339, fn
        if stats["n"] > 0:
            assert stats["min"] <= stats["percentiles"][50] <= stats["max"]


def test_ratio_b_distribution_shape(loaded):
    ratio_b = compute_ratio_distribution(
        loaded["idx_r7"], loaded["idx_r6"], numerator_key=("実績", 2025), denominator_key=("実績", 2024)
    )
    assert ratio_b["合計"]["n"] == 339
    assert ratio_b["合計"]["zero_denom"] == 0
    assert ratio_b["高度急性期"]["zero_denom"] == 70
    for fn, stats in ratio_b.items():
        assert stats["n"] + stats["zero_denom"] == 339, fn


def test_percentile_matches_linear_interpolation():
    vals = [1.0, 2.0, 3.0, 4.0]
    assert _percentile(vals, 0) == 1.0
    assert _percentile(vals, 100) == 4.0
    assert _percentile(vals, 50) == pytest.approx(2.5)
    assert _percentile([], 50) is None
    assert _percentile([5.0], 50) == 5.0


# --- area_yoy_diff.csv の行構築 ---------------------------------------------


def test_build_area_yoy_diff_rows_count_and_order(loaded):
    basic_r7_by_code = {r["area_code"]: r for r in loaded["basic_by_fy"]["R7"]}
    rows = build_area_yoy_diff_rows(basic_r7_by_code, loaded["idx_r7"], loaded["idx_r6"])
    assert len(rows) == 1695
    codes = [r["area_code"] for r in rows]
    # area_code昇順(1つのarea_codeにつき5機能が連続)であること
    assert codes == sorted(codes)
    first_area_rows = rows[:5]
    assert [r["bed_function"] for r in first_area_rows] == ["合計", "高度急性期", "急性期", "回復期", "慢性期"]


def test_build_area_yoy_diff_rows_detects_need_2025_mismatch():
    """need_2025がR6/R7で食い違う場合にValueErrorで中断すること(静かに片側だけ採用しない)。"""
    basic_by_code = {"0101": {"area_name": "テスト区域", "pref_code": "01", "pref_name": "北海道"}}
    idx_r7 = {}
    idx_r6 = {}
    for fn in ("合計", "高度急性期", "急性期", "回復期", "慢性期"):
        idx_r7[("0101", fn, "実績", 2025)] = 100
        idx_r7[("0101", fn, "実績", 2024)] = 100
        idx_r7[("0101", fn, "必要数", 2025)] = 90
        idx_r6[("0101", fn, "見込量", 2025)] = 100
        idx_r6[("0101", fn, "実績", 2024)] = 100
        idx_r6[("0101", fn, "必要数", 2025)] = 91  # R7と不一致
    with pytest.raises(ValueError):
        build_area_yoy_diff_rows(basic_by_code, idx_r7, idx_r6)


# --- known_issuesの形(id重複なし・必須キー) ----------------------------------


def test_output_csv_known_issues_shape():
    meta = _read_json(OUT_CSV.with_name(OUT_CSV.name + ".meta.json"))
    issues = meta["known_issues"]
    assert isinstance(issues, list) and len(issues) == 3
    ids = [issue["id"] for issue in issues]
    assert len(ids) == len(set(ids))
    for issue in issues:
        for key in ("id", "scope", "summary", "evidence", "action"):
            assert key in issue, key
        assert issue["scope"]["csv"] in ("area_beds.csv", "area_bed_report_rate.csv")


# --- 再現性(バイト一致) -----------------------------------------------------


def test_reproducibility_byte_identical(tmp_path):
    paths = build_and_write(tmp_path, tmp_path)
    assert paths.keys() == {"csv", "meta", "doc"}

    committed_csv = PROCESSED_DIR / "area_yoy_diff.csv"
    committed_doc = DOC_DIR / "YOY_VERIFICATION.md"
    assert committed_csv.exists(), (
        f"{committed_csv} が存在しません(先に `python tools/verify_yoy_R6_R7.py` を実行してください)"
    )
    assert committed_doc.exists(), (
        f"{committed_doc} が存在しません(先に `python tools/verify_yoy_R6_R7.py` を実行してください)"
    )

    assert paths["csv"].read_bytes() == committed_csv.read_bytes(), (
        "area_yoy_diff.csv がコミット済みデータとバイト一致しません"
    )
    assert paths["doc"].read_bytes() == committed_doc.read_bytes(), (
        "doc/YOY_VERIFICATION.md がコミット済みデータとバイト一致しません"
    )

    new_meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
    old_meta = json.loads((PROCESSED_DIR / "area_yoy_diff.csv.meta.json").read_text(encoding="utf-8"))
    new_meta["processing"]["date"] = None
    old_meta["processing"]["date"] = None
    assert new_meta == old_meta, "area_yoy_diff.csv.meta.json の内容(processing.dateを除く)が一致しません"


def test_report_markdown_has_no_date_stamp():
    content = OUT_DOC.read_text(encoding="utf-8")
    assert "生成日時" not in content
    assert "実行日" not in content


def test_report_markdown_is_lf_only():
    data = OUT_DOC.read_bytes()
    assert b"\r\n" not in data
    assert not data.startswith(b"\xef\xbb\xbf")


def test_report_markdown_contains_ratio_distribution_tables():
    content = OUT_DOC.read_text(encoding="utf-8")
    assert "指標A" in content
    assert "指標B" in content
    assert "5.857" in content  # 高度急性期のmax(実測値)


def test_report_markdown_mentions_2024_actual_known_issue():
    content = OUT_DOC.read_text(encoding="utf-8")
    assert "2024年実績" in content
    assert "1281" in content
