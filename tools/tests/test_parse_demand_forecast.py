# -*- coding: utf-8 -*-
"""tools/parse_demand_forecast.py のテスト。

R7(001728462.xlsx)のパース結果を中心に、年度ラベルからの年抽出・
行数/列/area_codeの形式といった構造テスト・area_basic.csvとの整合・
再現性(バイト一致)を検証する。
"""
import csv
import json

import pytest

from tools.lib.provenance import REPO_ROOT, recorded_hash, verify_source
from tools.parse_demand_forecast import (
    DATA_END_ROW,
    DATA_START_ROW,
    EXPECTED_YEARS,
    KNOWN_ISSUES,
    LayoutMismatchError,
    NUM_AREAS,
    SHEET_HOME_CARE,
    SHEET_OUTPATIENT,
    _extract_year,
    _validate_against_area_basic,
    build_and_write,
    known_issues_for,
    load_workbook,
    parse_sheet,
)

PROCESSED_DIR = REPO_ROOT / "data" / "processed"


@pytest.fixture(scope="module")
def workbook():
    wb, source_sha256 = load_workbook()
    return {"wb": wb, "source_sha256": source_sha256}


@pytest.fixture(scope="module")
def home_care_result(workbook):
    ws = workbook["wb"][SHEET_HOME_CARE]
    return parse_sheet(ws, demand_category="在宅（訪問診療）")


@pytest.fixture(scope="module")
def outpatient_result(workbook):
    ws = workbook["wb"][SHEET_OUTPATIENT]
    return parse_sheet(ws, demand_category="外来")


# --- 年度ラベルからの年抽出(ユニットテスト) --------------------------------


def test_extract_year_plain():
    assert _extract_year("2024年度") == 2024


def test_extract_year_with_projection_suffix():
    assert _extract_year("2030年度（現状投影）") == 2030
    assert _extract_year("2050年度（現状投影）") == 2050


def test_extract_year_rejects_non_matching_text():
    with pytest.raises(LayoutMismatchError):
        _extract_year("現状投影")


def test_extract_year_rejects_non_string():
    with pytest.raises(LayoutMismatchError):
        _extract_year(2024)


# --- 行数・年度・区域コードの構造テスト -------------------------------------


def test_data_row_range_covers_339_areas():
    assert DATA_END_ROW - DATA_START_ROW + 1 == NUM_AREAS == 339


def test_forecast_row_count_per_sheet(home_care_result, outpatient_result):
    assert len(home_care_result.forecast_rows) == 339 * len(EXPECTED_YEARS) == 2034
    assert len(outpatient_result.forecast_rows) == 339 * len(EXPECTED_YEARS) == 2034


def test_population_count_per_sheet(home_care_result, outpatient_result):
    assert len(home_care_result.population_by_area) == 339
    assert len(outpatient_result.population_by_area) == 339


def test_years_extracted_match_expected(home_care_result, outpatient_result):
    years_home = [y for _, y, _ in home_care_result.years]
    years_out = [y for _, y, _ in outpatient_result.years]
    assert years_home == EXPECTED_YEARS
    assert years_out == EXPECTED_YEARS


def test_area_code_format_and_uniqueness(home_care_result):
    codes = list(home_care_result.population_by_area.keys())
    assert len(codes) == len(set(codes)) == 339
    for code in codes:
        assert isinstance(code, str)
        assert len(code) == 4
        assert code.isdigit()


def test_area_code_spotcheck(home_care_result):
    assert "0101" in home_care_result.population_by_area
    assert home_care_result.population_by_area["0101"]["area_name"] == "南渡島"


# --- スポット値(原典との整合) -----------------------------------------------


def test_forecast_spot_values(home_care_result, outpatient_result):
    home_0101 = [
        row
        for row in home_care_result.forecast_rows
        if row["area_code"] == "0101" and row["year"] == 2024
    ]
    assert len(home_0101) == 1
    assert home_0101[0]["receipts_per_month"] == 4382.75
    assert home_0101[0]["year_label"] == "2024年度"

    out_0101_2030 = [
        row
        for row in outpatient_result.forecast_rows
        if row["area_code"] == "0101" and row["year"] == 2030
    ]
    assert len(out_0101_2030) == 1
    assert out_0101_2030[0]["year_label"] == "2030年度（現状投影）"


def test_population_matches_between_sheets(home_care_result, outpatient_result):
    for area_code, home_info in home_care_result.population_by_area.items():
        out_info = outpatient_result.population_by_area[area_code]
        assert home_info["population_2024"] == out_info["population_2024"]
        assert home_info["population_2040"] == out_info["population_2040"]


def test_population_spot_values(home_care_result):
    info = home_care_result.population_by_area["0101"]
    assert info["population_2024"] == 340005
    assert info["population_2040"] == 259252


# --- area_basic.csv との整合(area_code / 名称) ------------------------------


def test_area_code_and_names_match_area_basic(home_care_result, outpatient_result):
    """area_basic.csvとの整合は在宅シートだけでなく外来シートも検証する。

    demand_forecast.csvの外来行は外来シートから読んだpref_name/area_nameを
    そのまま書き出すため、在宅シート側だけをarea_basic.csvと突合しても
    外来シート側の名称のずれを検知できない。
    """
    reference = {}
    with open(PROCESSED_DIR / "area_basic.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            reference[row["area_code"]] = (row["pref_name"], row["area_name"])

    for result in (home_care_result, outpatient_result):
        assert set(result.population_by_area.keys()) == set(reference.keys())
        for area_code, info in result.population_by_area.items():
            ref_pref_name, ref_area_name = reference[area_code]
            assert info["pref_name"] == ref_pref_name, (result.demand_category, area_code)
            assert info["area_name"] == ref_area_name, (result.demand_category, area_code)


# --- レイアウト崩れ検知(LayoutMismatchError) -----------------------------


def test_layout_mismatch_is_detected_without_touching_raw_file():
    """5行目(見出し行)の文字列が想定と異なる場合に検知できるか。

    `wb.save()` は一切呼ばない(R7/ 配下は編集禁止のため)メモリ上の改変のみ。
    テストの最後に `verify_source()` で生データが改変されていないことを確認する。
    """
    wb, _ = load_workbook()
    ws = wb[SHEET_HOME_CARE]

    original = ws.cell(row=5, column=1).value
    assert original == "都道府県"

    ws.cell(row=5, column=1).value = "改変された見出し"

    with pytest.raises(LayoutMismatchError):
        parse_sheet(ws, demand_category="在宅（訪問診療）")

    assert verify_source("R7/001728462.xlsx") == recorded_hash("R7/001728462.xlsx")


def test_year_label_drift_is_detected():
    """4行目(年度ラベル行)が想定外の文字列に変わった場合に検知できるか。"""
    wb, _ = load_workbook()
    ws = wb[SHEET_OUTPATIENT]

    original = ws.cell(row=4, column=6).value
    assert original == "2024年度"

    ws.cell(row=4, column=6).value = "西暦不明"

    with pytest.raises(LayoutMismatchError):
        parse_sheet(ws, demand_category="外来")

    assert verify_source("R7/001728462.xlsx") == recorded_hash("R7/001728462.xlsx")


def test_outpatient_area_name_drift_is_detected(home_care_result):
    """外来シートの構想区域名(C列)が想定外の値に変わった場合に、
    `_validate_against_area_basic()`(両シート間 + area_basic.csvとの突合)
    で検知できるか。

    `parse_sheet()` 単体はシート間の突合を行わない(area_basic.csvとの整合は
    `build_and_write()` から `_validate_against_area_basic()` を両シート分
    まとめて呼ぶことで担保している)ため、ここではその関数を直接呼ぶ。
    `wb.save()` は一切呼ばない(R7/ 配下は編集禁止のため)メモリ上の改変のみ。
    """
    wb, _ = load_workbook()
    ws = wb[SHEET_OUTPATIENT]

    original = ws.cell(row=DATA_START_ROW, column=3).value
    assert original == "南渡島"

    ws.cell(row=DATA_START_ROW, column=3).value = "改変された区域名"
    mutated_outpatient = parse_sheet(ws, demand_category="外来")

    with pytest.raises(LayoutMismatchError):
        _validate_against_area_basic([home_care_result, mutated_outpatient])

    assert verify_source("R7/001728462.xlsx") == recorded_hash("R7/001728462.xlsx")


# --- 原典側の既知の欠陥(known_issues) ---------------------------------------

# パーサが出力する2本のCSV。known_issuesのscope.csvの妥当性検査と、
# 下の再現性テストの両方で使う。
CSV_NAMES = [
    "demand_forecast.csv",
    "demand_population.csv",
]


def test_known_issues_have_the_required_shape():
    """KNOWN_ISSUESの各件がid/scope/summary/evidence/actionを持ち、scope.csvが
    実在の出力CSVを指すこと。今後ここへ足していくための形の固定。"""
    assert KNOWN_ISSUES, "KNOWN_ISSUESが空(この帳票には少なくとも基準人口の不一致がある)"
    ids = [issue["id"] for issue in KNOWN_ISSUES]
    assert len(ids) == len(set(ids)), f"idが重複している: {ids}"
    for issue in KNOWN_ISSUES:
        assert issue["scope"]["csv"] in CSV_NAMES, issue["id"]
        for key in ("id", "summary", "action"):
            assert isinstance(issue[key], str) and issue[key], (issue["id"], key)
        assert isinstance(issue["evidence"], list) and issue["evidence"], issue["id"]


def test_known_issues_for_routes_by_scope_csv():
    """known_issues_for()がscope.csvで振り分け、該当なしではNoneを返すこと
    (Noneのときmeta.jsonにknown_issuesキー自体を出さないため、空リストと
    区別されることが重要)。"""
    assert known_issues_for("存在しない.csv") is None
    routed = {name: known_issues_for(name) or [] for name in CSV_NAMES}
    assert sum(len(v) for v in routed.values()) == len(KNOWN_ISSUES)
    for name, issues in routed.items():
        for issue in issues:
            assert issue["scope"]["csv"] == name


def test_population_base_year_conflict_is_recorded():
    """基準人口の年が原典Excel(2024年度)と公式説明書(2025年)で食い違う件が
    記録されており、値を読み替えていないと明記されていること。"""
    issue = next(i for i in KNOWN_ISSUES if i["id"] == "demand_population_base_year_conflict")
    assert issue["scope"]["csv"] == "demand_population.csv"
    assert "population_2024" in issue["scope"]["columns"]
    evidence = " ".join(issue["evidence"])
    assert "001728462" in evidence and "001728467" in evidence
    assert "2024年度" in evidence and "2025" in evidence


# --- 再現性(バイト一致) -----------------------------------------------------


def test_reproducibility_byte_identical(tmp_path):
    paths = build_and_write(tmp_path)
    assert paths.keys() == {"forecast", "population"}
    expected_sha256 = recorded_hash("R7/001728462.xlsx")

    for name in CSV_NAMES:
        committed_path = PROCESSED_DIR / name
        assert committed_path.exists(), (
            f"{committed_path} が存在しません"
            "(先に `python tools/parse_demand_forecast.py` を実行してください)"
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
