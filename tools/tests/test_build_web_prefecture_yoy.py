# -*- coding: utf-8 -*-
"""tools/build_web_prefecture_yoy.py のテスト。

再現性(バイト一致)、スキーマの健全性(47都道府県+全国・5機能×3系列が揃っている)、
prefecture_boundaries_R7.geojsonとのpref_code整合、prefecture_beds.csvとの値の一致、
構想区域側(area_yoy_R6_R7.json)との定義の対称性、検証ロジックが実際に落ちることを
検証する。
"""
import csv
import json

import pytest

from tools.build_web_prefecture_yoy import (
    FUNCTIONS,
    FUNCTION_LABELS,
    NATIONAL_CODE,
    OUT_PATH,
    PREFECTURE_BED_REPORT_RATE_CSV,
    PREFECTURE_BEDS_CSV,
    PREFECTURE_BOUNDARIES_GEOJSON,
    _load_csv_rows,
    _load_geojson_pref_codes,
    build_and_write,
    validate_and_index,
)

AREA_YOY_PATH = OUT_PATH.parent / "area_yoy_R6_R7.json"


@pytest.fixture(scope="module")
def data():
    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_prefecture_yoy.py` を実行してください)"
    )
    with open(OUT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def prefectures(data):
    return data["prefectures"]


@pytest.fixture(scope="module")
def by_code(data):
    entries = {p["pref_code"]: p for p in data["prefectures"]}
    entries[data["national"]["pref_code"]] = data["national"]
    return entries


# --- 再現性(バイト一致) -----------------------------------------------------


def test_reproducibility_byte_identical(tmp_path):
    assert PREFECTURE_BEDS_CSV.exists()
    assert PREFECTURE_BED_REPORT_RATE_CSV.exists()
    assert PREFECTURE_BOUNDARIES_GEOJSON.exists()

    out = build_and_write(tmp_path / "prefecture_yoy_R6_R7.json")

    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_prefecture_yoy.py` を実行してください)"
    )
    assert out.read_bytes() == OUT_PATH.read_bytes(), (
        "prefecture_yoy_R6_R7.json がコミット済みデータとバイト一致しません"
    )


def test_output_ends_with_single_trailing_newline():
    text = OUT_PATH.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_output_has_no_crlf():
    raw = OUT_PATH.read_bytes()
    assert b"\r" not in raw, "prefecture_yoy_R6_R7.json にCRが含まれています(LF固定のはず)"


# --- スキーマの健全性 --------------------------------------------------------


def test_top_level_keys(data):
    # 全国は prefectures 配列ではなく national キー(prefecture_indicators_R7.json と同じ形)
    assert set(data.keys()) == {"metadata", "functions", "function_labels", "national", "prefectures"}
    assert data["functions"] == ["total", "high_acute", "acute", "recovery", "chronic"]
    assert data["function_labels"] == FUNCTION_LABELS


def test_prefectures_count_unique_sorted_and_exclude_national(prefectures):
    codes = [p["pref_code"] for p in prefectures]
    assert len(codes) == 47
    assert len(set(codes)) == 47
    assert codes == sorted(codes)
    assert NATIONAL_CODE not in codes


def test_national_entry(data):
    national = data["national"]
    assert national["pref_code"] == "00"
    assert national["pref_name"] == "全国"


def test_pref_code_format(data, prefectures):
    for entry in [*prefectures, data["national"]]:
        assert len(entry["pref_code"]) == 2 and entry["pref_code"].isdigit()
        assert entry["pref_name"]


def test_each_entry_has_all_functions_and_three_series(data, prefectures):
    for entry in [*prefectures, data["national"]]:
        assert set(entry["beds"].keys()) == set(FUNCTIONS)
        for fn in FUNCTIONS:
            beds = entry["beds"][fn]
            assert set(beds.keys()) == {"plan_2025", "actual_2025", "actual_2024"}
            for key, value in beds.items():
                assert isinstance(value, int), f"{entry['pref_code']}.{fn}.{key} が整数ではありません"
                assert value >= 0


def test_total_equals_sum_of_four_functions(data, prefectures):
    for entry in [*prefectures, data["national"]]:
        for series in ("plan_2025", "actual_2025", "actual_2024"):
            total = entry["beds"]["total"][series]
            parts = sum(entry["beds"][fn][series] for fn in FUNCTIONS if fn != "total")
            assert total == parts, f"{entry['pref_code']}の{series}で合計!=4機能の和"


def test_national_equals_sum_of_47(data, prefectures):
    """全国は47都道府県の合計(検証8がビルド時に固定しているものを出力側でも押さえる)。"""
    for fn in FUNCTIONS:
        for series in ("plan_2025", "actual_2025", "actual_2024"):
            assert data["national"]["beds"][fn][series] == sum(
                p["beds"][fn][series] for p in prefectures
            ), f"全国の{fn}.{series}が47都道府県の合計と一致しません"


def test_report_rate_present_and_in_range(data, prefectures):
    for entry in [*prefectures, data["national"]]:
        for key in ("report_rate_2024", "report_rate_2025"):
            value = entry[key]
            assert isinstance(value, float)
            assert 0 <= value <= 1


def test_no_ratio_fields_in_output(prefectures):
    """比率はフロントエンド側で算出する(構想区域版と同じ規律)。"""
    for entry in prefectures:
        assert "ratio" not in entry
        for fn in FUNCTIONS:
            assert not any(k.startswith("ratio") for k in entry["beds"][fn])


def test_no_denominator_is_zero(data, prefectures):
    """都道府県層では見込量2025・実績2024に0が無い(=「算出不可」が発生しない)。

    構想区域層には分母0が81件あるが、都道府県層には無いという実測を固定する。
    将来0が現れたらこのテストが落ちるので、そのときは画面の「算出不可」表示が
    都道府県層でも出ることを確認すること(機構自体は共通なのでそのまま効く)。
    """
    for entry in [*prefectures, data["national"]]:
        for fn in FUNCTIONS:
            assert entry["beds"][fn]["plan_2025"] > 0
            assert entry["beds"][fn]["actual_2024"] > 0


# --- 入力CSV・境界GeoJSONとの整合 --------------------------------------------


def test_pref_codes_match_boundaries_geojson(prefectures):
    geo = _load_geojson_pref_codes(PREFECTURE_BOUNDARIES_GEOJSON)
    assert {p["pref_code"] for p in prefectures} == set(geo)
    for p in prefectures:
        assert p["pref_name"] == geo[p["pref_code"]]


def test_values_match_prefecture_beds_csv(by_code):
    """出力の3系列が prefecture_beds.csv の該当行と一致する(published_fyの取り違え検出)。"""
    rows = _load_csv_rows(PREFECTURE_BEDS_CSV)
    expected = {
        "plan_2025": {},
        "actual_2025": {},
        "actual_2024": {},
    }
    for r in rows:
        key = (r["pref_code"], r["bed_function"])
        if r["published_fy"] == "R6" and r["series"] == "見込量" and r["year"] == "2025":
            expected["plan_2025"][key] = int(r["beds"])
        elif r["published_fy"] == "R7" and r["series"] == "実績" and r["year"] == "2025":
            expected["actual_2025"][key] = int(r["beds"])
        elif r["published_fy"] == "R6" and r["series"] == "実績" and r["year"] == "2024":
            expected["actual_2024"][key] = int(r["beds"])

    for series, table in expected.items():
        assert len(table) == 240, f"{series} の期待値が240件ではありません({len(table)}件)"
        for (pref_code, ja), value in table.items():
            fn = {ja_: key for key, ja_ in FUNCTION_LABELS.items()}[ja]
            assert by_code[pref_code]["beds"][fn][series] == value, (
                f"{pref_code}.{fn}.{series} が prefecture_beds.csv と一致しません"
            )


def test_2024_actual_is_identical_in_r6_and_r7(by_code):
    """都道府県層では2024年実績がR6/R7で一致する(構想区域層の欠陥が無いことの担保)。

    ビルド時の検証9と同じ主張を、コミット済みCSVに対して独立に確認する。
    """
    rows = _load_csv_rows(PREFECTURE_BEDS_CSV)
    r6 = {}
    r7 = {}
    for r in rows:
        if r["series"] != "実績" or r["year"] != "2024":
            continue
        (r6 if r["published_fy"] == "R6" else r7)[(r["pref_code"], r["bed_function"])] = int(r["beds"])
    assert len(r6) == 240 and len(r7) == 240
    assert r6 == r7, "都道府県の2024年実績がR6公表分とR7公表分で一致しません"


def test_symmetric_with_area_yoy_dataset():
    """構想区域版(area_yoy_R6_R7.json)と指標の定義・キー名が対称であること。

    片方だけキー名が変わると、フロントの共通コード(metrics.ts の
    yoyPlanRatioKey 等)がどちらかの層で静かに無色になる。
    """
    assert AREA_YOY_PATH.exists()
    with open(AREA_YOY_PATH, "r", encoding="utf-8") as f:
        area = json.load(f)
    with open(OUT_PATH, "r", encoding="utf-8") as f:
        pref = json.load(f)

    assert pref["functions"] == area["functions"]
    assert pref["function_labels"] == area["function_labels"]
    assert set(pref["prefectures"][0]["beds"]["total"].keys()) == set(
        area["areas"][0]["beds"]["total"].keys()
    )
    for key in ("report_rate_2024", "report_rate_2025"):
        assert key in pref["prefectures"][0] and key in area["areas"][0]


# --- メタデータ --------------------------------------------------------------


def test_metadata_required_top_level_keys(data):
    meta = data["metadata"]
    assert set(meta.keys()) == {"title", "source", "processing", "fields", "known_issues"}
    assert meta["processing"]["script"] == "tools/build_web_prefecture_yoy.py"


def test_metadata_source_is_list_of_two_with_sha256(data):
    """出典はR7/R6の2要素配列(区域側と同じ形。CLAUDE.md 罠31)。"""
    source = data["metadata"]["source"]
    assert isinstance(source, list) and len(source) == 2
    assert [s["published_fy"] for s in source] == ["R7", "R6"]
    for s in source:
        assert s["source_sha256"] and len(s["source_sha256"]) == 64
        assert s["source_file"]
        assert s["page_url"].startswith("https://")


def test_metadata_inputs_have_sha256(data):
    inputs = data["metadata"]["processing"]["inputs"]
    assert [i["path"] for i in inputs] == [
        "data/processed/prefecture_beds.csv",
        "data/processed/prefecture_bed_report_rate.csv",
        "data/processed/prefecture_boundaries_R7.geojson",
    ]
    for i in inputs:
        assert len(i["sha256"]) == 64


def test_metadata_caveat_mentions_plan_report_rate_and_2024_identity(data):
    caveat = data["metadata"]["processing"]["caveat"]
    assert "見込量2025" in caveat
    assert "報告率" in caveat
    # 「2024年実績はR6/R7で一致するので採用の判断が要らない」ことを明示している
    assert "2024年実績" in caveat


def test_metadata_known_issues_shape_and_no_invented_entries(data):
    """known_issues は入力CSVから引き継ぐのみ。

    構想区域版が足す area_yoy_2024_actual_from_r6 に相当するものは、都道府県層では
    判断自体が発生しない(検証9)ため足さない。非欠陥を「データの既知の問題」欄へ
    出さないための規律。
    """
    issues = data["metadata"]["known_issues"]
    assert isinstance(issues, list)
    ids = [i["id"] for i in issues]
    assert len(ids) == len(set(ids))
    for issue in issues:
        assert {"id", "summary", "action"} <= set(issue.keys())
    assert "area_yoy_2024_actual_from_r6" not in ids

    carried = []
    for path in (PREFECTURE_BEDS_CSV, PREFECTURE_BED_REPORT_RATE_CSV):
        with open(str(path) + ".meta.json", "r", encoding="utf-8") as f:
            carried.extend(json.load(f).get("known_issues", []))
    assert ids == [i["id"] for i in carried]


def test_fields_document_the_2024_actual_and_report_rate_nuances(data):
    fields = data["metadata"]["fields"]
    assert "beds.actual_2024" in fields and "一致" in fields["beds.actual_2024"]
    assert "report_rate_2024" in fields and "全国" in fields["report_rate_2024"]


# --- 検証ロジックが実際に落ちること ------------------------------------------
#
# 検証2(pref_code集合が48件で一致)があるため、1都道府県だけの合成フィクスチャでは
# 他の検証に到達する前に検証2で落ちる。実データを読み込んで特定の1セルだけを
# メモリ上で改変してから渡す(test_build_web_yoy.py と同じ流儀。生データには触れない)。


@pytest.fixture(scope="module")
def real_inputs():
    beds_rows = _load_csv_rows(PREFECTURE_BEDS_CSV)
    rate_rows = _load_csv_rows(PREFECTURE_BED_REPORT_RATE_CSV)
    geo = _load_geojson_pref_codes(PREFECTURE_BOUNDARIES_GEOJSON)
    return beds_rows, rate_rows, geo


def _mutate(rows, match: dict, column: str, value: str):
    mutated = [dict(r) for r in rows]
    hit = False
    for r in mutated:
        if all(r[k] == v for k, v in match.items()):
            r[column] = value
            hit = True
    assert hit, f"改変対象の行が見つかりません: {match}"
    return mutated


def test_validate_raises_when_r6_missing(real_inputs):
    beds_rows, rate_rows, geo = real_inputs
    r7_only = [dict(r) for r in beds_rows if r["published_fy"] != "R6"]
    with pytest.raises(SystemExit, match="検証1失敗"):
        validate_and_index(r7_only, rate_rows, geo)


def test_validate_raises_when_boundaries_disagree(real_inputs):
    beds_rows, rate_rows, geo = real_inputs
    bad_geo = {k: v for k, v in geo.items() if k != "01"}
    with pytest.raises(SystemExit, match="検証2失敗"):
        validate_and_index(beds_rows, rate_rows, bad_geo)


def test_validate_raises_when_pref_name_disagrees_with_boundaries(real_inputs):
    beds_rows, rate_rows, geo = real_inputs
    bad_geo = dict(geo)
    bad_geo["01"] = "北海道(改変)"
    with pytest.raises(SystemExit, match="検証3失敗"):
        validate_and_index(beds_rows, rate_rows, bad_geo)


def test_validate_raises_when_beds_value_is_negative(real_inputs):
    beds_rows, rate_rows, geo = real_inputs
    mutated = _mutate(
        beds_rows,
        {"published_fy": "R6", "series": "見込量", "year": "2025", "pref_code": "01", "bed_function": "急性期"},
        "beds",
        "-1",
    )
    with pytest.raises(SystemExit, match="検証5失敗"):
        validate_and_index(mutated, rate_rows, geo)


def test_validate_raises_when_total_does_not_equal_sum(real_inputs):
    beds_rows, rate_rows, geo = real_inputs
    mutated = _mutate(
        beds_rows,
        {"published_fy": "R7", "series": "実績", "year": "2025", "pref_code": "01", "bed_function": "合計"},
        "beds",
        "999999",
    )
    with pytest.raises(SystemExit, match="検証7失敗"):
        validate_and_index(mutated, rate_rows, geo)


def test_validate_raises_when_national_is_not_sum_of_47(real_inputs):
    """全国の1セルだけを、4機能の和は保ったまま増やすと検証8で落ちる。

    「合計」ではなく「急性期」を変え、同じだけ「合計」も増やすことで検証7を通過させ、
    検証8(全国==47都道府県の合計)だけが落ちることを確かめる。
    """
    beds_rows, rate_rows, geo = real_inputs
    base = {r["bed_function"]: r for r in beds_rows
            if r["published_fy"] == "R7" and r["series"] == "実績" and r["year"] == "2025"
            and r["pref_code"] == "00"}
    mutated = _mutate(
        beds_rows,
        {"published_fy": "R7", "series": "実績", "year": "2025", "pref_code": "00", "bed_function": "急性期"},
        "beds",
        str(int(base["急性期"]["beds"]) + 10),
    )
    mutated = _mutate(
        mutated,
        {"published_fy": "R7", "series": "実績", "year": "2025", "pref_code": "00", "bed_function": "合計"},
        "beds",
        str(int(base["合計"]["beds"]) + 10),
    )
    with pytest.raises(SystemExit, match="検証8失敗"):
        validate_and_index(mutated, rate_rows, geo)


def test_validate_raises_when_2024_actual_differs_between_r6_and_r7(real_inputs):
    """R7の2024年実績を1セルだけずらすと検証9で落ちる。

    構想区域側で起きている原典の欠陥が都道府県側にも現れたときに、黙って
    通り過ぎないことの確認。
    """
    beds_rows, rate_rows, geo = real_inputs
    row = next(
        r for r in beds_rows
        if r["published_fy"] == "R7" and r["series"] == "実績" and r["year"] == "2024"
        and r["pref_code"] == "13" and r["bed_function"] == "急性期"
    )
    mutated = _mutate(
        beds_rows,
        {"published_fy": "R7", "series": "実績", "year": "2024", "pref_code": "13", "bed_function": "急性期"},
        "beds",
        str(int(row["beds"]) + 1),
    )
    # 検証7(合計==4機能の和)より先に検証9へ到達させるため、合計も同じだけ動かす
    total_row = next(
        r for r in beds_rows
        if r["published_fy"] == "R7" and r["series"] == "実績" and r["year"] == "2024"
        and r["pref_code"] == "13" and r["bed_function"] == "合計"
    )
    mutated = _mutate(
        mutated,
        {"published_fy": "R7", "series": "実績", "year": "2024", "pref_code": "13", "bed_function": "合計"},
        "beds",
        str(int(total_row["beds"]) + 1),
    )
    with pytest.raises(SystemExit, match="検証9失敗"):
        validate_and_index(mutated, rate_rows, geo)


def test_validate_raises_when_report_rate_out_of_range(real_inputs):
    beds_rows, rate_rows, geo = real_inputs
    mutated_rate = _mutate(
        rate_rows,
        {"published_fy": "R6", "year": "2024", "pref_code": "01"},
        "report_rate",
        "1.5",
    )
    with pytest.raises(SystemExit, match="検証6失敗"):
        validate_and_index(beds_rows, mutated_rate, geo)


def test_validate_passes_on_real_input(real_inputs):
    beds_rows, rate_rows, geo = real_inputs
    indexed = validate_and_index(beds_rows, rate_rows, geo)
    assert len(indexed["prefecture_codes"]) == 47
    assert indexed["plan_2025"][("00", "合計")] > 0
    assert 0 < indexed["report_rate_2025"]["01"] <= 1
