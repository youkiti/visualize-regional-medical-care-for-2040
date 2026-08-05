# -*- coding: utf-8 -*-
"""tools/build_web_prefecture.py のテスト。

再現性(バイト一致)、スキーマの健全性(47都道府県+全国・5機能・2区分・6年度)、
prefecture_boundaries_R7.geojsonとのpref_code整合、変換の忠実性
(prefecture_beds.csvの公表値と出力JSONが一致すること、需要が構想区域の合計に
なっていること)、metadataの出典・生成日時不在・known_issuesの形を検証する。

**このファイルの中心は「都道府県の病床が構想区域の合計と一致する」テスト**
(test_beds_match_area_sum_for_every_prefecture)。ここが崩れると概観層と
主表示層で数字が食い違うため、ビルド側(検証8)とテスト側の二重で固定する。
"""
import csv
import json
from collections import defaultdict

import pytest

from tools.build_web_prefecture import (
    AREA_BEDS_CSV,
    AREA_BASIC_CSV,
    BASELINE_YEAR,
    CATEGORIES,
    CATEGORY_LABELS,
    DEMAND_FORECAST_CSV,
    EXPECTED_AREA_COUNT,
    EXPECTED_PREFECTURE_COUNT,
    FUNCTIONS,
    FUNCTION_LABELS,
    NATIONAL_CODE,
    OUT_PATH,
    PREFECTURE_BEDS_CSV,
    PREFECTURE_BOUNDARIES_GEOJSON,
    YEARS,
    build_and_write,
)

CATEGORY_KEY_BY_JA = {ja: key for key, ja in CATEGORY_LABELS.items()}


@pytest.fixture(scope="module")
def data():
    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_prefecture.py` を実行してください)"
    )
    with open(OUT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def prefectures(data):
    return data["prefectures"]


@pytest.fixture(scope="module")
def prefectures_by_code(prefectures):
    return {p["pref_code"]: p for p in prefectures}


# --- 再現性(バイト一致) -----------------------------------------------------


def test_reproducibility_byte_identical(tmp_path):
    for path in (PREFECTURE_BEDS_CSV, AREA_BEDS_CSV, DEMAND_FORECAST_CSV, PREFECTURE_BOUNDARIES_GEOJSON):
        assert path.exists(), path

    out = build_and_write(tmp_path / "prefecture_indicators_R7.json")

    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_prefecture.py` を実行してください)"
    )
    assert out.read_bytes() == OUT_PATH.read_bytes(), (
        "prefecture_indicators_R7.json がコミット済みデータとバイト一致しません"
        "(需要の合計順序が非決定的になっていないか確認すること)"
    )


def test_output_ends_with_single_trailing_newline():
    text = OUT_PATH.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_output_has_no_crlf():
    raw = OUT_PATH.read_bytes()
    assert b"\r" not in raw, "prefecture_indicators_R7.json にCRが含まれています(LF固定のはず)"


# --- スキーマの健全性 --------------------------------------------------------


def test_top_level_keys(data):
    assert set(data.keys()) == {
        "metadata",
        "functions",
        "function_labels",
        "categories",
        "category_labels",
        "years",
        "year_labels",
        "baseline_year",
        "national",
        "prefectures",
    }
    assert data["functions"] == FUNCTIONS
    assert data["categories"] == CATEGORIES
    assert data["years"] == YEARS
    assert data["baseline_year"] == BASELINE_YEAR


def test_prefectures_count_and_unique_and_sorted(prefectures):
    codes = [p["pref_code"] for p in prefectures]
    assert len(codes) == EXPECTED_PREFECTURE_COUNT
    assert len(set(codes)) == EXPECTED_PREFECTURE_COUNT
    assert codes == sorted(codes)
    assert NATIONAL_CODE not in codes, "全国はprefectures配列ではなくnationalへ入れる"


def test_national_is_separate_and_covers_every_area(data):
    national = data["national"]
    assert national["pref_code"] == NATIONAL_CODE
    assert national["pref_name"] == "全国"
    assert national["area_count"] == EXPECTED_AREA_COUNT


def test_pref_code_format(prefectures):
    for p in prefectures:
        assert len(p["pref_code"]) == 2 and p["pref_code"].isdigit(), p["pref_code"]
        assert p["pref_name"]


def test_area_count_sums_to_339(prefectures):
    assert sum(p["area_count"] for p in prefectures) == EXPECTED_AREA_COUNT


def test_each_prefecture_has_all_functions_and_categories(prefectures):
    for p in prefectures:
        assert set(p["beds"].keys()) == set(FUNCTIONS), p["pref_code"]
        for fn in FUNCTIONS:
            beds = p["beds"][fn]
            assert set(beds.keys()) == {"actual_2025", "need_2025"}
            for key in ("actual_2025", "need_2025"):
                assert isinstance(beds[key], int) and not isinstance(beds[key], bool)
                assert beds[key] >= 0
        assert set(p["demand"].keys()) == set(CATEGORIES), p["pref_code"]
        for category in CATEGORIES:
            entry = p["demand"][category]
            assert set(entry.keys()) == {str(y) for y in YEARS}, (p["pref_code"], category)
            for year in YEARS:
                value = entry[str(year)]
                assert isinstance(value, (int, float)) and not isinstance(value, bool)
                assert value > 0


def test_population_and_area_positive(data, prefectures):
    for p in [*prefectures, data["national"]]:
        for key in ("population_2020", "population_2024", "population_2040"):
            assert isinstance(p[key], int) and not isinstance(p[key], bool)
            assert p[key] > 0, (p["pref_code"], key)
        assert isinstance(p["area_km2"], float)
        assert p["area_km2"] > 0


def test_baseline_year_value_nonzero_for_all(prefectures):
    for p in prefectures:
        for category in CATEGORIES:
            assert p["demand"][category][str(BASELINE_YEAR)] != 0, (p["pref_code"], category)


def test_no_prefecture_has_zero_need(prefectures):
    """必要数0の都道府県は存在しない(=地図の「算出不可」区分は概観層では出ない)。
    構想区域側には10件あるので、層によって状況が違うことをテストで固定する。"""
    zero = [
        (p["pref_code"], fn) for p in prefectures for fn in FUNCTIONS if p["beds"][fn]["need_2025"] == 0
    ]
    assert zero == []


# --- 境界GeoJSONとのpref_code整合 ---------------------------------------------


def test_pref_codes_match_boundaries_geojson(prefectures):
    with open(PREFECTURE_BOUNDARIES_GEOJSON, "r", encoding="utf-8") as f:
        gj = json.load(f)
    geo_codes = {feat["properties"]["pref_code"] for feat in gj["features"]}
    assert {p["pref_code"] for p in prefectures} == geo_codes
    assert len(geo_codes) == EXPECTED_PREFECTURE_COUNT


# --- 変換の忠実性 -------------------------------------------------------------


def test_beds_are_the_published_prefecture_values(prefectures_by_code):
    """病床は「都道府県別の公表値そのもの」であること(構想区域の合計を書いて
    いるのではない)。prefecture_beds.csvの2025年行と1件ずつ突き合わせる。

    prefecture_beds.csvはR6/R7がpublished_fyで並存する(M9)ため、出力データセット
    (R7のみで構成)と突き合わせるにはR7行だけに絞り込む必要がある。絞り込まないと
    R6の該当行が二重にカウントされる。
    """
    with open(PREFECTURE_BEDS_CSV, "r", encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["published_fy"] == "R7"]
    checked = 0
    for row in rows:
        if row["year"] != "2025" or row["pref_code"] == NATIONAL_CODE:
            continue
        if row["series"] == "実績":
            key = "actual_2025"
        elif row["series"] == "必要数":
            key = "need_2025"
        else:
            continue
        fn = {ja: k for k, ja in FUNCTION_LABELS.items()}[row["bed_function"]]
        assert prefectures_by_code[row["pref_code"]]["beds"][fn][key] == int(row["beds"]), row
        checked += 1
    assert checked == EXPECTED_PREFECTURE_COUNT * len(FUNCTIONS) * 2


def test_beds_match_area_sum_for_every_prefecture(prefectures_by_code):
    """**このファイルの中心**: 都道府県の2025年病床数が、構想区域(area_beds.csv)を
    都道府県で合計した値と完全に一致すること。厚生労働省の別々の公表ファイル
    (001722915.xlsx と 001723349.xlsx)どうしの内部整合の確認でもあり、
    概観層と主表示層で数字が食い違わないことの担保でもある。

    area_basic.csv・area_beds.csvはR6/R7がpublished_fyで並存する(M9)ため、R7行
    だけに絞り込む。area_beds.csvを絞り込まないとR6分が二重に合算されてしまう。
    """
    with open(AREA_BASIC_CSV, "r", encoding="utf-8", newline="") as f:
        pref_by_area = {
            r["area_code"]: r["pref_code"] for r in csv.DictReader(f) if r["published_fy"] == "R7"
        }
    with open(AREA_BEDS_CSV, "r", encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["published_fy"] == "R7"]

    sums = defaultdict(int)
    for row in rows:
        if row["year"] != "2025" or row["series"] not in ("実績", "必要数"):
            continue
        sums[(pref_by_area[row["area_code"]], row["bed_function"], row["series"])] += int(row["beds"])

    assert len(sums) == EXPECTED_PREFECTURE_COUNT * len(FUNCTIONS) * 2
    for (pref_code, ja, series), total in sums.items():
        fn = {ja2: k for k, ja2 in FUNCTION_LABELS.items()}[ja]
        key = "actual_2025" if series == "実績" else "need_2025"
        assert prefectures_by_code[pref_code]["beds"][fn][key] == total, (pref_code, ja, series)


def test_national_beds_equal_sum_of_prefectures(data, prefectures):
    national = data["national"]
    for fn in FUNCTIONS:
        for key in ("actual_2025", "need_2025"):
            assert national["beds"][fn][key] == sum(p["beds"][fn][key] for p in prefectures), (fn, key)


def test_demand_is_the_sum_of_the_areas(prefectures_by_code):
    """需要は構想区域の合計であること(厚労省は都道府県単位を公表していない)。

    area_basic.csvはR6/R7がpublished_fyで並存する(M9)ため、R7行だけに絞り込む
    (pref_codeの値自体はR6/R7で同一だが、他のテストと同じ規律に揃える)。
    """
    with open(AREA_BASIC_CSV, "r", encoding="utf-8", newline="") as f:
        pref_by_area = {
            r["area_code"]: r["pref_code"] for r in csv.DictReader(f) if r["published_fy"] == "R7"
        }
    with open(DEMAND_FORECAST_CSV, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    sums = defaultdict(float)
    for row in rows:
        category = CATEGORY_KEY_BY_JA[row["demand_category"]]
        sums[(pref_by_area[row["area_code"]], category, row["year"])] += float(row["receipts_per_month"])

    assert len(sums) == EXPECTED_PREFECTURE_COUNT * len(CATEGORIES) * len(YEARS)
    for (pref_code, category, year), total in sums.items():
        assert prefectures_by_code[pref_code]["demand"][category][year] == pytest.approx(total)


def test_national_demand_equals_sum_of_prefectures(data, prefectures):
    national = data["national"]
    for category in CATEGORIES:
        for year in YEARS:
            total = sum(p["demand"][category][str(year)] for p in prefectures)
            assert national["demand"][category][str(year)] == pytest.approx(total)


def test_spotcheck_hokkaido(prefectures_by_code):
    p = prefectures_by_code["01"]
    assert p["pref_name"] == "北海道"
    assert p["area_count"] == 21
    assert p["population_2020"] == 5224614


# --- metadata ----------------------------------------------------------------


def test_metadata_has_two_source_blocks_and_no_generation_timestamp(data):
    meta = data["metadata"]
    # 病床と需要で原典が違うため source は1つではない(types.ts の
    # PrefectureIndicatorsMetadata と対応)
    assert "source" not in meta
    for key in ("source_beds", "source_demand"):
        assert len(meta[key]["source_sha256"]) == 64
        assert meta[key]["derived_via"]
    assert meta["source_beds"]["source_file"] != meta["source_demand"]["source_file"]

    assert len(meta["processing"]["inputs"]) == 7
    for entry in meta["processing"]["inputs"]:
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

    _walk(meta)


def test_metadata_caveat_has_three_keys(data):
    caveat = data["metadata"]["processing"]["caveat"]
    assert set(caveat.keys()) == {"beds", "demand_forecast", "demand_population"}
    for value in caveat.values():
        assert isinstance(value, str) and value


def test_metadata_known_issues_shape(data):
    issues = data["metadata"]["known_issues"]
    assert isinstance(issues, list)
    for issue in issues:
        for key in ("id", "summary", "action"):
            assert isinstance(issue.get(key), str) and issue[key], (issue.get("id"), key)
    ids = [issue["id"] for issue in issues]
    assert len(ids) == len(set(ids)), f"known_issuesのidが重複している: {ids}"


def test_metadata_records_that_demand_is_a_derived_aggregation(data):
    """需要が本リポジトリによる合計であることが、散文のcaveatではなく機械可読な
    known_issuesとして載っていること(画面の出典欄まで自動で流れる導線)。"""
    issues = {issue["id"]: issue for issue in data["metadata"]["known_issues"]}
    issue = issues["prefecture_demand_aggregated_by_this_repository"]
    assert "合計" in issue["summary"]
    assert issue["scope"]["json"].endswith("prefecture_indicators_R7.json")
    assert any("001728462" in e for e in issue["evidence"])
    # 病床は合計ではなく公表値であることが区別して書かれていること
    assert "001722915" in " ".join(issue["evidence"])


def test_known_issues_are_carried_over_from_the_input_csv_metadata(data):
    """入力CSVのknown_issuesが漏れなく引き継がれること(パーサのKNOWN_ISSUESへ
    1件足すだけで表示用データセットまで流れる導線を固定する)。末尾1件だけが
    このスクリプト固有の判断(需要の合計)。"""
    carried = []
    for csv_path in (
        PREFECTURE_BEDS_CSV,
        PREFECTURE_BEDS_CSV.with_name("prefecture_basic.csv"),
        DEMAND_FORECAST_CSV,
        DEMAND_FORECAST_CSV.with_name("demand_population.csv"),
    ):
        meta_path = csv_path.with_name(csv_path.name + ".meta.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        carried.extend(meta.get("known_issues", []))
    issues = data["metadata"]["known_issues"]
    assert issues[: len(carried)] == carried
    assert len(issues) == len(carried) + 1
    assert issues[-1]["id"] == "prefecture_demand_aggregated_by_this_repository"
