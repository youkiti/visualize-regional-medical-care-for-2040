# -*- coding: utf-8 -*-
"""tools/build_web_demand.py のテスト。

再現性(バイト一致)、スキーマの健全性(339区域・区分2・年6・全area×category×year
が揃っている)、area_boundaries_R7.geojsonとのarea_code整合、変換の忠実性
(demand_forecast.csvの全4,068件と出力JSONの値が一致すること)、metadataの
出典・生成日時不在を検証する。
"""
import csv
import json

import pytest

from tools.build_web_demand import (
    AREA_BOUNDARIES_GEOJSON,
    BASELINE_YEAR,
    CATEGORIES,
    CATEGORY_LABELS,
    DEMAND_FORECAST_CSV,
    DEMAND_POPULATION_CSV,
    OUT_PATH,
    YEARS,
    build_and_write,
)

CATEGORY_KEY_BY_JA = {ja: key for key, ja in CATEGORY_LABELS.items()}


@pytest.fixture(scope="module")
def data():
    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_demand.py` を実行してください)"
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
    assert DEMAND_FORECAST_CSV.exists()
    assert DEMAND_POPULATION_CSV.exists()
    assert AREA_BOUNDARIES_GEOJSON.exists()

    out = build_and_write(tmp_path / "area_demand_R7.json")

    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_demand.py` を実行してください)"
    )
    new_bytes = out.read_bytes()
    old_bytes = OUT_PATH.read_bytes()
    assert new_bytes == old_bytes, "area_demand_R7.json がコミット済みデータとバイト一致しません"


def test_output_ends_with_single_trailing_newline():
    text = OUT_PATH.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_output_has_no_crlf():
    raw = OUT_PATH.read_bytes()
    assert b"\r" not in raw, "area_demand_R7.json にCRが含まれています(LF固定のはず)"


# --- スキーマの健全性 --------------------------------------------------------


def test_top_level_keys(data):
    assert set(data.keys()) == {
        "metadata",
        "categories",
        "category_labels",
        "years",
        "year_labels",
        "baseline_year",
        "areas",
    }
    assert data["categories"] == ["home_care", "outpatient"]
    assert data["category_labels"] == {
        "home_care": "在宅（訪問診療）",
        "outpatient": "外来",
    }
    assert data["years"] == [2024, 2030, 2035, 2040, 2045, 2050]
    assert data["baseline_year"] == 2024


def test_year_labels_keys_are_year_strings(data):
    assert set(data["year_labels"].keys()) == {str(y) for y in YEARS}
    assert data["year_labels"]["2024"] == "2024年度"
    for year in YEARS[1:]:
        assert "現状投影" in data["year_labels"][str(year)]


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


def test_each_area_has_all_categories_and_years(areas):
    for a in areas:
        assert set(a["demand"].keys()) == set(CATEGORIES), a["area_code"]
        for category in CATEGORIES:
            entry = a["demand"][category]
            assert set(entry.keys()) == {str(y) for y in YEARS}, (a["area_code"], category)
            for year in YEARS:
                value = entry[str(year)]
                assert isinstance(value, (int, float))
                assert not isinstance(value, bool)
                assert value > 0


def test_population_fields_present_and_typed(areas):
    for a in areas:
        assert isinstance(a["population_2024"], int)
        assert not isinstance(a["population_2024"], bool)
        assert a["population_2024"] > 0
        assert isinstance(a["population_2040"], int)
        assert not isinstance(a["population_2040"], bool)
        assert a["population_2040"] > 0


def test_area_name_and_pref_name_non_empty(areas):
    for a in areas:
        assert a["area_name"]
        assert a["pref_name"]


def test_baseline_year_value_nonzero_for_all(areas):
    for a in areas:
        for category in CATEGORIES:
            assert a["demand"][category][str(BASELINE_YEAR)] != 0, (a["area_code"], category)


def test_spotcheck_hokkaido_minamioshima(areas_by_code):
    a = areas_by_code["0101"]
    assert a["area_name"] == "南渡島"
    assert a["pref_name"] == "北海道"
    assert a["population_2024"] == 340005
    assert a["population_2040"] == 259252
    assert a["demand"]["home_care"]["2024"] == pytest.approx(4382.75)
    assert a["demand"]["outpatient"]["2024"] == pytest.approx(261882.16666666657)


# --- area_boundaries_R7.geojsonとのarea_code整合 -------------------------------
# ksj/A38-20 (Git管理外)には依存しない: area_boundaries_R7.geojson自体は
# コミット済みなのでskipifは不要。


def test_area_codes_match_boundaries_geojson(areas):
    with open(AREA_BOUNDARIES_GEOJSON, "r", encoding="utf-8") as f:
        gj = json.load(f)
    geo_codes = {feat["properties"]["area_code"] for feat in gj["features"]}
    output_codes = {a["area_code"] for a in areas}
    assert output_codes == geo_codes
    assert len(geo_codes) == 339


# --- 変換の忠実性: demand_forecast.csvの全4068件と出力JSONの値が一致 -----------


def test_all_forecast_rows_match_output_exactly(areas_by_code):
    with open(DEMAND_FORECAST_CSV, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4068
    for row in rows:
        category_key = CATEGORY_KEY_BY_JA[row["demand_category"]]
        area = areas_by_code[row["area_code"]]
        output_value = area["demand"][category_key][row["year"]]
        assert output_value == pytest.approx(float(row["receipts_per_month"])), row


# --- metadata: 出典・生成日時不在 ---------------------------------------------


def test_metadata_source_has_sha256_and_no_generation_timestamp(data):
    meta = data["metadata"]
    assert "source_sha256" in meta["source"]
    assert len(meta["source"]["source_sha256"]) == 64
    assert "inputs" in meta["processing"]
    assert len(meta["processing"]["inputs"]) == 3
    for entry in meta["processing"]["inputs"]:
        assert set(entry.keys()) == {"path", "sha256"}
        assert len(entry["sha256"]) == 64

    # 生成日時らしきキーが無いこと(metadata全体を再帰的に確認)
    def _walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                assert key not in ("date", "generated_at", "timestamp", "created_at"), key
                _walk(value)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(meta)


def test_metadata_required_top_level_keys(data):
    meta = data["metadata"]
    for key in ("title", "source", "processing", "fields"):
        assert key in meta, key


def test_metadata_caveat_has_both_inputs(data):
    caveat = data["metadata"]["processing"]["caveat"]
    assert set(caveat.keys()) == {"demand_forecast", "demand_population"}
    assert "レセプト" in caveat["demand_forecast"]
    assert "人口" in caveat["demand_population"]
