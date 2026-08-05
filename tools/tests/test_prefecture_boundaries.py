# -*- coding: utf-8 -*-
"""tools/build_prefecture_boundaries.py の出力
(`data/processed/prefecture_boundaries_R7.geojson`)を検証する。

入力が `data/processed/area_boundaries_R7.geojson`(コミット済み)だけなので、
`tools/build_area_boundaries.py` と違って `ksj/A38-20`(Git管理外)には依存
しない。ただし再生成には Node.js(mapshaper)が要るため、**再生成そのものを
伴うテストは置かない**(GeoJSONのバイト一致テストを書かない理由は
`test_area_boundaries.py` 冒頭と同じ: mapshaper/GEOSのバージョン差で座標順が
変わりうる)。

代わりに、コミット済みの出力が「入力である339区域の忠実なディゾルブか」を
面積の保存で検証する — これが崩れていれば県の取り違えやジオメトリ欠落を
検出できる。
"""
import json

import pytest

from tools.build_area_boundaries import feature_area_km2
from tools.build_prefecture_boundaries import (
    AREA_BOUNDARIES_GEOJSON,
    BOUNDARY_SOURCE,
    EXPECTED_PREFECTURE_COUNT,
    NATIONAL_CODE,
    OUT_PATH,
    PREFECTURE_BASIC_CSV,
    REF_LAT_DEG,
    TOLERANCE_PCT,
    area_km2_by_pref,
    load_prefecture_names,
)


@pytest.fixture(scope="module")
def gj():
    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_prefecture_boundaries.py` を実行してください)"
    )
    with open(OUT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def features(gj):
    return gj["features"]


@pytest.fixture(scope="module")
def area_features():
    with open(AREA_BOUNDARIES_GEOJSON, "r", encoding="utf-8") as f:
        return json.load(f)["features"]


def test_feature_count(features):
    assert len(features) == EXPECTED_PREFECTURE_COUNT


def test_pref_code_unique_sorted_and_matches_prefecture_basic(features):
    codes = [f["properties"]["pref_code"] for f in features]
    assert len(set(codes)) == len(codes)
    assert codes == sorted(codes), "決定的な出力順(pref_code昇順)であること"
    assert set(codes) == set(load_prefecture_names())
    assert NATIONAL_CODE not in codes, "全国のフィーチャは作らない"


def test_properties_required_keys(features):
    for f in features:
        props = f["properties"]
        assert set(props.keys()) == {"pref_code", "pref_name", "boundary_source"}
        assert len(props["pref_code"]) == 2 and props["pref_code"].isdigit()
        assert props["pref_name"]
        assert props["boundary_source"] == BOUNDARY_SOURCE


def test_boundary_source_says_it_is_a_dissolve_of_the_area_boundaries(features):
    """県境が「国土数値情報の都道府県界」ではなく「構想区域境界のディゾルブ」で
    あることが、フィーチャ側にも書かれていること(出所の言い過ぎを防ぐ)。"""
    source = features[0]["properties"]["boundary_source"]
    assert "area_boundaries_R7.geojson" in source
    assert "dissolve" in source


def test_geometry_types_and_non_empty(features):
    for f in features:
        geom = f["geometry"]
        assert geom["type"] in ("Polygon", "MultiPolygon"), f["properties"]["pref_code"]
        assert geom["coordinates"]


def test_area_is_conserved_per_prefecture(features, area_features):
    """各都道府県の面積が、その県に属する構想区域の面積合計と一致すること。
    純粋なディゾルブなので理論上は完全一致する(実測差は0.0000%)。"""
    expected = area_km2_by_pref(area_features)
    assert set(expected) == {f["properties"]["pref_code"] for f in features}
    for f in features:
        code = f["properties"]["pref_code"]
        actual = feature_area_km2(f["geometry"], REF_LAT_DEG)
        diff_pct = abs(actual - expected[code]) / expected[code] * 100
        assert diff_pct <= TOLERANCE_PCT, (code, actual, expected[code], diff_pct)


def test_total_area_is_conserved(features, area_features):
    expected = sum(area_km2_by_pref(area_features).values())
    actual = sum(feature_area_km2(f["geometry"], REF_LAT_DEG) for f in features)
    assert abs(actual - expected) / expected * 100 <= TOLERANCE_PCT


def test_metadata_required_fields(gj):
    meta = gj["metadata"]
    for key in ("title", "source", "processing", "fields", "feature_count", "verification"):
        assert key in meta, key
    assert meta["feature_count"] == EXPECTED_PREFECTURE_COUNT
    # 出典は入力GeoJSON(国土数値情報A38-20)から引き継がれていること
    assert "A38" in meta["source"]["name"] or "医療圏" in meta["source"]["name"]
    assert len(meta["source"]["source_sha256"]) == 64
    inputs = meta["processing"]["inputs"]
    assert [i["path"] for i in inputs] == [
        "data/processed/area_boundaries_R7.geojson",
        "data/processed/prefecture_basic.csv",
    ]
    for entry in inputs:
        assert len(entry["sha256"]) == 64


def test_metadata_has_no_generation_timestamp(gj):
    """生成日時を埋め込まない(CLAUDE.md: 再生成のたびに差分が出るため)。"""

    def _walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                assert key not in ("date", "generated_at", "timestamp", "created_at"), key
                _walk(value)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(gj["metadata"])


def test_metadata_caveat_explains_mie_does_not_affect_the_outline(gj):
    """三重県の合成境界が県の外形には影響しないこと(ディゾルブで消えるのは
    区域どうしの内部境界)を注記していること。逆に「国土数値情報が都道府県界を
    公表している」と読める書き方になっていないこと。"""
    caveat = gj["metadata"]["processing"]["caveat"]
    assert "三重県" in caveat
    assert "外形" in caveat
    assert "全国" in caveat, "「全国」のフィーチャを含まないことを明記していること"


def test_load_prefecture_names_excludes_national():
    names = load_prefecture_names()
    assert len(names) == EXPECTED_PREFECTURE_COUNT
    assert NATIONAL_CODE not in names
    assert names["01"] == "北海道"
    assert names["47"] == "沖縄県"


def test_prefecture_basic_csv_referenced_by_build_script_exists():
    assert PREFECTURE_BASIC_CSV.exists()
