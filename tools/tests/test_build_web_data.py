# -*- coding: utf-8 -*-
"""tools/build_web_data.py のテスト。

再現性(バイト一致)、スキーマの健全性(339区域・機能そろい・三重県8区域の
flow_rate_unavailable)、既知欠陥(2024年実績)の防波堤、metadataの出典・
生成日時不在を検証する。
"""
import json

import pytest

from tools.build_web_data import (
    AREA_BASIC_CSV,
    AREA_BEDS_CSV,
    AREA_BOUNDARIES_GEOJSON,
    FUNCTIONS,
    OUT_PATH,
    build_and_write,
)

MIE_XXX_AREA_CODES = {"2405", "2406", "2407", "2408", "2409", "2410", "2411", "2412"}


@pytest.fixture(scope="module")
def data():
    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_data.py` を実行してください)"
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
    assert AREA_BASIC_CSV.exists()
    assert AREA_BOUNDARIES_GEOJSON.exists()

    out = build_and_write(tmp_path / "area_indicators_R7.json")

    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_data.py` を実行してください)"
    )
    new_bytes = out.read_bytes()
    old_bytes = OUT_PATH.read_bytes()
    assert new_bytes == old_bytes, "area_indicators_R7.json がコミット済みデータとバイト一致しません"


def test_output_ends_with_single_trailing_newline():
    text = OUT_PATH.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_output_has_no_crlf():
    raw = OUT_PATH.read_bytes()
    assert b"\r" not in raw, "area_indicators_R7.json にCRが含まれています(LF固定のはず)"


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


def test_each_area_has_all_five_functions_with_actual_and_need(areas):
    for a in areas:
        assert set(a["beds"].keys()) == set(FUNCTIONS), a["area_code"]
        for func in FUNCTIONS:
            entry = a["beds"][func]
            assert set(entry.keys()) == {"actual_2025", "need_2025"}, (a["area_code"], func)
            assert isinstance(entry["actual_2025"], int) and entry["actual_2025"] >= 0
            assert isinstance(entry["need_2025"], int) and entry["need_2025"] >= 0
            # bool は int のサブクラスなので明示的に除外する
            assert not isinstance(entry["actual_2025"], bool)
            assert not isinstance(entry["need_2025"], bool)


def test_area_basic_fields_present_and_typed(areas):
    for a in areas:
        assert isinstance(a["population_2020"], int)
        assert a["population_2020"] > 0
        assert isinstance(a["area_km2"], float)
        assert a["area_km2"] > 0


def test_area_name_and_pref_name_non_empty(areas):
    for a in areas:
        assert a["area_name"]
        assert a["pref_name"]


# --- 三重県8区域のXXXセンチネル -----------------------------------------------


def test_mie_areas_have_null_rates_and_unavailable_marker(areas_by_code):
    for code in MIE_XXX_AREA_CODES:
        a = areas_by_code[code]
        assert a["outflow_rate"] is None, code
        assert a["inflow_rate"] is None, code
        assert a["flow_rate_unavailable"] == "XXX", code


def test_non_mie_areas_have_numeric_rates_and_no_unavailable_marker(areas):
    non_mie = [a for a in areas if a["area_code"] not in MIE_XXX_AREA_CODES]
    assert len(non_mie) == 331
    for a in non_mie:
        assert "flow_rate_unavailable" not in a, a["area_code"]
        assert isinstance(a["outflow_rate"], float), a["area_code"]
        assert isinstance(a["inflow_rate"], float), a["area_code"]
        assert 0 <= a["outflow_rate"] <= 1, a["area_code"]
        assert 0 <= a["inflow_rate"] <= 1, a["area_code"]


def test_spotcheck_hokkaido_minamioshima():
    with open(OUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    by_code = {a["area_code"]: a for a in data["areas"]}
    a = by_code["0101"]
    assert a["area_name"] == "南渡島"
    assert a["pref_name"] == "北海道"
    assert a["population_2020"] == 359223
    assert a["area_km2"] == 2670.6
    assert a["outflow_rate"] == pytest.approx(0.035)
    assert a["inflow_rate"] == pytest.approx(0.085)
    assert "flow_rate_unavailable" not in a


# --- 既知欠陥の防波堤: 2024年実績はどこにも出力しない --------------------------


def test_no_2024_actuals_anywhere_in_areas(areas):
    """beds配下の各機能はactual_2025/need_2025の2キーのみを持ち、2024年や
    2026年見込量、比率などは一切含まれないこと(metadata.known_issuesの説明文
    には'2024'という文字列そのものは出現しうるため、比較対象はareas配下の
    構造化データに限定する)。
    """
    for a in areas:
        assert set(a.keys()) >= {
            "area_code",
            "area_name",
            "pref_code",
            "pref_name",
            "population_2020",
            "area_km2",
            "outflow_rate",
            "inflow_rate",
            "beds",
        }
        allowed_extra = {"flow_rate_unavailable"}
        assert set(a.keys()) - allowed_extra <= {
            "area_code",
            "area_name",
            "pref_code",
            "pref_name",
            "population_2020",
            "area_km2",
            "outflow_rate",
            "inflow_rate",
            "beds",
        }
        for func in FUNCTIONS:
            assert set(a["beds"][func].keys()) == {"actual_2025", "need_2025"}


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
    for key in ("title", "source", "processing", "fields", "known_issues"):
        assert key in meta, key


def test_metadata_caveat_mentions_actual_vs_need_are_not_comparable(data):
    caveat = data["metadata"]["processing"]["caveat"]
    assert "実績" in caveat
    assert "必要" in caveat


def test_metadata_known_issues_mentions_2024_exclusion(data):
    ids = {issue["id"] for issue in data["metadata"]["known_issues"]}
    assert "area_indicators_2024_actual_excluded" in ids
    assert "area_beds_2024_actual_duplicated_as_2025" in ids
    assert "area_basic_outflow_inflow_rate_xxx_mie" in ids
