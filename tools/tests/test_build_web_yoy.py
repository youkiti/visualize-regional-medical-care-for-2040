# -*- coding: utf-8 -*-
"""tools/build_web_yoy.py のテスト。

再現性(バイト一致)、スキーマの健全性(339区域・5機能×3系列が揃っている)、
area_boundaries_R7.geojsonとのarea_code整合、area_yoy_diff.csv(検証用CSV、
tools/verify_yoy_R6_R7.py)との値の一致、known_issuesの形、検証ロジックが
実際に落ちることを検証する。
"""
import csv
import json

import pytest

from tools.build_web_yoy import (
    AREA_BEDS_CSV,
    AREA_BED_REPORT_RATE_CSV,
    AREA_BOUNDARIES_GEOJSON,
    FUNCTIONS,
    FUNCTION_LABELS,
    OUT_PATH,
    _load_csv_rows,
    _load_geojson_area_codes,
    build_and_write,
    validate_and_index,
)

FUNCTION_KEY_BY_JA = {ja: key for key, ja in FUNCTION_LABELS.items()}


@pytest.fixture(scope="module")
def data():
    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_yoy.py` を実行してください)"
    )
    with open(OUT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def areas(data):
    return data["areas"]


@pytest.fixture(scope="module")
def areas_by_code(areas):
    return {a["area_code"]: a for a in areas}


# --- 再現性(バイト一致) -----------------------------------------------------


def test_reproducibility_byte_identical(tmp_path):
    assert AREA_BEDS_CSV.exists()
    assert AREA_BED_REPORT_RATE_CSV.exists()
    assert AREA_BOUNDARIES_GEOJSON.exists()

    out = build_and_write(tmp_path / "area_yoy_R6_R7.json")

    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_yoy.py` を実行してください)"
    )
    assert out.read_bytes() == OUT_PATH.read_bytes(), "area_yoy_R6_R7.json がコミット済みデータとバイト一致しません"


def test_output_ends_with_single_trailing_newline():
    text = OUT_PATH.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_output_has_no_crlf():
    raw = OUT_PATH.read_bytes()
    assert b"\r" not in raw, "area_yoy_R6_R7.json にCRが含まれています(LF固定のはず)"


# --- スキーマの健全性 --------------------------------------------------------


def test_top_level_keys(data):
    assert set(data.keys()) == {"metadata", "functions", "function_labels", "areas"}
    assert data["functions"] == ["total", "high_acute", "acute", "recovery", "chronic"]
    assert data["function_labels"] == {
        "total": "合計",
        "high_acute": "高度急性期",
        "acute": "急性期",
        "recovery": "回復期",
        "chronic": "慢性期",
    }


def test_areas_count_and_unique_and_sorted(areas):
    codes = [a["area_code"] for a in areas]
    assert len(codes) == 339
    assert len(set(codes)) == 339
    assert codes == sorted(codes)


def test_area_code_format_and_pref_code_prefix(areas):
    for a in areas:
        code = a["area_code"]
        assert len(code) == 4 and code.isdigit(), code
        assert len(a["pref_code"]) == 2 and a["pref_code"].isdigit(), a["pref_code"]
        assert code[:2] == a["pref_code"], code


def test_each_area_has_all_functions_and_three_series(areas):
    for a in areas:
        assert set(a["beds"].keys()) == set(FUNCTIONS), a["area_code"]
        for fn in FUNCTIONS:
            entry = a["beds"][fn]
            assert set(entry.keys()) == {"plan_2025", "actual_2025", "actual_2024"}, (a["area_code"], fn)
            for series_key in ("plan_2025", "actual_2025", "actual_2024"):
                value = entry[series_key]
                assert isinstance(value, int) and not isinstance(value, bool), (a["area_code"], fn, series_key)
                assert value >= 0


def test_total_equals_sum_of_four_functions(areas):
    other_keys = ["high_acute", "acute", "recovery", "chronic"]
    for a in areas:
        for series_key in ("plan_2025", "actual_2025", "actual_2024"):
            total = a["beds"]["total"][series_key]
            parts_sum = sum(a["beds"][fn][series_key] for fn in other_keys)
            assert total == parts_sum, (a["area_code"], series_key, total, parts_sum)


def test_report_rate_present_and_in_range(areas):
    for a in areas:
        for key in ("report_rate_2024", "report_rate_2025"):
            value = a[key]
            assert isinstance(value, (int, float)) and not isinstance(value, bool)
            assert 0 <= value <= 1


def test_area_name_and_pref_name_non_empty(areas):
    for a in areas:
        assert a["area_name"]
        assert a["pref_name"]


def test_no_ratio_fields_in_output(areas):
    """比率(実績÷見込量等)は出力せず、フロント側で算出する方針(demand側と同じ流儀)。"""
    for a in areas:
        for fn in FUNCTIONS:
            entry = a["beds"][fn]
            assert "ratio" not in entry
            for key in entry:
                assert "ratio" not in key


def test_spotcheck_hokkaido_minamioshima(areas_by_code):
    a = areas_by_code["0101"]
    assert a["area_name"] == "南渡島"
    assert a["pref_name"] == "北海道"
    assert a["beds"]["total"] == {"plan_2025": 5216, "actual_2025": 4995, "actual_2024": 5243}
    assert a["beds"]["high_acute"] == {"plan_2025": 956, "actual_2025": 661, "actual_2024": 940}


# --- area_boundaries_R7.geojsonとのarea_code整合 -------------------------------


def test_area_codes_match_boundaries_geojson(areas):
    with open(AREA_BOUNDARIES_GEOJSON, "r", encoding="utf-8") as f:
        gj = json.load(f)
    geo_codes = {feat["properties"]["area_code"] for feat in gj["features"]}
    output_codes = {a["area_code"] for a in areas}
    assert output_codes == geo_codes
    assert len(geo_codes) == 339


# --- area_yoy_diff.csv(検証用CSV)との値の一致 --------------------------------


def test_matches_area_yoy_diff_csv(areas_by_code):
    """tools/verify_yoy_R6_R7.py が出す area_yoy_diff.csv と同じ値であること
    (2つの独立したスクリプトが同じ入力から同じ値を導出していることの相互検証)。
    """
    from tools.verify_yoy_R6_R7 import OUT_CSV

    with open(OUT_CSV, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1695
    for row in rows:
        area = areas_by_code[row["area_code"]]
        fn_key = FUNCTION_KEY_BY_JA[row["bed_function"]]
        entry = area["beds"][fn_key]
        assert entry["plan_2025"] == int(row["plan_2025_r6"]), row
        assert entry["actual_2025"] == int(row["actual_2025_r7"]), row
        assert entry["actual_2024"] == int(row["actual_2024_r6"]), row


# --- metadata: 出典・生成日時不在・known_issues -------------------------------


def test_metadata_source_is_list_of_two_with_sha256(data):
    source = data["metadata"]["source"]
    assert isinstance(source, list)
    by_fy = {s["published_fy"]: s for s in source}
    assert set(by_fy) == {"R7", "R6"}
    for entry in source:
        assert len(entry["source_sha256"]) == 64

    assert "inputs" in data["metadata"]["processing"]
    assert len(data["metadata"]["processing"]["inputs"]) == 3
    for entry in data["metadata"]["processing"]["inputs"]:
        assert set(entry.keys()) == {"path", "sha256"}
        assert len(entry["sha256"]) == 64

    def _walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                assert key not in ("date", "generated_at", "timestamp", "created_at"), key
                _walk(value)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data["metadata"])


def test_metadata_required_top_level_keys(data):
    meta = data["metadata"]
    for key in ("title", "source", "processing", "fields", "known_issues"):
        assert key in meta, key


def test_metadata_caveat_mentions_plan_and_report_rate(data):
    caveat = data["metadata"]["processing"]["caveat"]
    assert isinstance(caveat, str)
    assert "見込量2025" in caveat
    assert "公表回" in caveat
    assert "報告率" in caveat


def test_metadata_known_issues_shape(data):
    issues = data["metadata"]["known_issues"]
    assert isinstance(issues, list)
    ids = [issue["id"] for issue in issues]
    assert len(ids) == len(set(ids)), f"known_issuesのidが重複している: {ids}"
    for issue in issues:
        for key in ("id", "summary", "action"):
            assert isinstance(issue.get(key), str) and issue[key], (issue.get("id"), key)


def test_metadata_known_issues_includes_the_2024_actual_choice(data):
    issues = {issue["id"]: issue for issue in data["metadata"]["known_issues"]}
    issue = issues["area_yoy_2024_actual_from_r6"]
    assert "R6" in issue["action"]
    assert "actual_2024" in issue["action"]


def test_known_issues_are_carried_over_from_input_csv_metadata(data):
    carried = []
    for csv_path in (AREA_BEDS_CSV, AREA_BED_REPORT_RATE_CSV):
        meta_path = csv_path.with_name(csv_path.name + ".meta.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        carried.extend(meta.get("known_issues", []))
    output_issues = data["metadata"]["known_issues"]
    assert output_issues[: len(carried)] == carried
    assert output_issues[-1]["id"] == "area_yoy_2024_actual_from_r6"


# --- 検証ロジックが実際に落ちること ------------------------------------------
#
# 検証2(area_code集合が339件で一致)があるため、1区域だけの合成フィクスチャでは
# 他の検証に到達する前に必ず検証2で落ちてしまう。そこで実データ(339区域ぶん)を
# 読み込み、特定の1セルだけをメモリ上で改変してから渡す
# (tools/tests/test_parse_prefecture_beds.py の
# test_layout_mismatch_is_detected_without_touching_raw_file と同じ流儀)。


@pytest.fixture(scope="module")
def real_inputs():
    beds_rows = _load_csv_rows(AREA_BEDS_CSV)
    rate_rows = _load_csv_rows(AREA_BED_REPORT_RATE_CSV)
    geo_codes = _load_geojson_area_codes(AREA_BOUNDARIES_GEOJSON)
    return beds_rows, rate_rows, geo_codes


def test_validate_raises_when_r6_missing(real_inputs):
    beds_rows, rate_rows, geo_codes = real_inputs
    r7_only = [dict(r) for r in beds_rows if r["published_fy"] != "R6"]
    with pytest.raises(SystemExit, match="検証1失敗"):
        validate_and_index(r7_only, rate_rows, geo_codes)


def test_validate_raises_when_area_code_sets_disagree(real_inputs):
    beds_rows, rate_rows, geo_codes = real_inputs
    bad_geo_codes = set(geo_codes) - {"0101"}
    with pytest.raises(SystemExit, match="検証2失敗"):
        validate_and_index(beds_rows, rate_rows, bad_geo_codes)


def test_validate_raises_when_beds_value_is_negative(real_inputs):
    beds_rows, rate_rows, geo_codes = real_inputs
    mutated = [dict(r) for r in beds_rows]
    hit = False
    for r in mutated:
        if (
            r["published_fy"] == "R6"
            and r["series"] == "見込量"
            and r["year"] == "2025"
            and r["area_code"] == "0101"
            and r["bed_function"] == "急性期"
        ):
            r["beds"] = "-1"
            hit = True
    assert hit
    with pytest.raises(SystemExit, match="検証5失敗"):
        validate_and_index(mutated, rate_rows, geo_codes)


def test_validate_raises_when_total_does_not_equal_sum(real_inputs):
    beds_rows, rate_rows, geo_codes = real_inputs
    mutated = [dict(r) for r in beds_rows]
    hit = False
    for r in mutated:
        if (
            r["published_fy"] == "R7"
            and r["series"] == "実績"
            and r["year"] == "2025"
            and r["area_code"] == "0101"
            and r["bed_function"] == "合計"
        ):
            r["beds"] = "999999"
            hit = True
    assert hit
    with pytest.raises(SystemExit, match="検証7失敗"):
        validate_and_index(mutated, rate_rows, geo_codes)


def test_validate_raises_when_report_rate_out_of_range(real_inputs):
    beds_rows, rate_rows, geo_codes = real_inputs
    mutated_rate = [dict(r) for r in rate_rows]
    hit = False
    for r in mutated_rate:
        if r["published_fy"] == "R6" and r["year"] == "2024" and r["area_code"] == "0101":
            r["report_rate"] = "1.5"
            hit = True
    assert hit
    with pytest.raises(SystemExit, match="検証6失敗"):
        validate_and_index(beds_rows, mutated_rate, geo_codes)


def test_validate_passes_on_real_input(real_inputs):
    beds_rows, rate_rows, geo_codes = real_inputs
    indexed = validate_and_index(beds_rows, rate_rows, geo_codes)
    assert indexed["plan_2025"][("0101", "合計")] == 5216
    assert indexed["report_rate_2024"]["0101"] == pytest.approx(1.0)
