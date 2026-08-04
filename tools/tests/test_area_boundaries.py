# -*- coding: utf-8 -*-
"""tools/build_area_boundaries.py の出力
(`data/processed/area_boundaries_R7.geojson`)を検証する。

`ksj/A38-20/A38-20_GML.zip`(1.13GB)はGit管理外でCI(Ubuntu)には存在しないため、
再生成そのものに依存するテストはここには置かない。一方コミット済みの
`area_boundaries_R7.geojson`(339フィーチャ)は常にGit管理下にあるため、これを
読んで検証するテスト、および zip を必要としない純粋関数(`feature_area_km2`・
`load_area_basic`・`load_mie_muni_map`)のテストは常に実行する。

GeoJSONのバイト一致テストは書かない(mapshaper/GEOSのバージョン差でディゾルブ
結果の座標順が変わりうるため環境依存で壊れる。`iryoken2_A38-20.geojson`にも
同様のテストはない)。
"""
import csv
import json

import pytest

from tools.build_area_boundaries import (
    AREA_BASIC_CSV,
    BOUNDARY_SOURCE_DEFAULT,
    BOUNDARY_SOURCE_MIE,
    IRYOKEN2_PATH,
    MIE_AREA_CODES,
    MIE_CSV,
    OUT_PATH,
    SRC_ZIP,
    TOLERANCE_PCT,
    feature_area_km2,
    load_area_basic,
    load_mie_muni_map,
)
from tools.lib.codes import normalize_area_code

MIE_OLD_IRYOKEN2_CODES = {"2401", "2402", "2403", "2404"}


@pytest.fixture(scope="module")
def area_basic_codes():
    with open(AREA_BASIC_CSV, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {normalize_area_code(r["area_code"]) for r in rows}


@pytest.fixture(scope="module")
def gj():
    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_area_boundaries.py` を実行してください)"
    )
    with open(OUT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def features(gj):
    return gj["features"]


@pytest.fixture(scope="module")
def by_code(features):
    return {f["properties"]["area_code"]: f for f in features}


# --- 検証1: フィーチャ数が339 ------------------------------------------------


def test_feature_count(features):
    assert len(features) == 339


# --- 検証2: area_codeの一意性 + area_basic.csvとの集合一致 --------------------


def test_area_code_unique_and_matches_area_basic(features, area_basic_codes):
    codes = [f["properties"]["area_code"] for f in features]
    assert len(codes) == len(set(codes)), "area_codeが重複しています"
    assert set(codes) == area_basic_codes
    assert len(area_basic_codes) == 339


# --- properties の必須キー ---------------------------------------------------


def test_properties_required_keys(features):
    required = {"area_code", "area_name", "pref_code", "pref_name", "boundary_source"}
    for f in features:
        props = f["properties"]
        assert required.issubset(props.keys()), props
        for key in required:
            assert props[key], (props.get("area_code"), key, "空です")
        assert len(props["area_code"]) == 4 and props["area_code"].isdigit(), props["area_code"]
        assert len(props["pref_code"]) == 2 and props["pref_code"].isdigit(), props["pref_code"]


# --- boundary_source の値 ----------------------------------------------------


def test_boundary_source_is_one_of_the_two_expected_values(features):
    allowed = {BOUNDARY_SOURCE_DEFAULT, BOUNDARY_SOURCE_MIE}
    for f in features:
        assert f["properties"]["boundary_source"] in allowed, f["properties"]


def test_boundary_source_does_not_overclaim_official_publication(features):
    """三重県8区域のboundary_sourceが、国土数値情報がR7区域を公表しているかの
    ような表現になっていないこと(合成物であることが読み取れる値であること)。
    """
    for f in features:
        if f["properties"]["area_code"] in MIE_AREA_CODES:
            source = f["properties"]["boundary_source"]
            assert "対応表" in source or "dissolve" in source
            assert source == BOUNDARY_SOURCE_MIE


# --- 検証3: 三重県8区域の存在とboundary_source --------------------------------


def test_mie_areas_present_with_mie_boundary_source(by_code):
    assert MIE_AREA_CODES == {"2405", "2406", "2407", "2408", "2409", "2410", "2411", "2412"}
    for code in MIE_AREA_CODES:
        assert code in by_code, f"三重県の区域{code}が出力に存在しません"
        assert by_code[code]["properties"]["boundary_source"] == BOUNDARY_SOURCE_MIE, code


def test_non_mie_areas_use_default_boundary_source(features):
    non_mie = [f for f in features if f["properties"]["area_code"] not in MIE_AREA_CODES]
    assert len(non_mie) == 331
    for f in non_mie:
        assert f["properties"]["boundary_source"] == BOUNDARY_SOURCE_DEFAULT, f["properties"]["area_code"]


# --- 検証5: ジオメトリ型と非空 ------------------------------------------------


def test_geometry_types_and_non_empty(features):
    for f in features:
        geom = f.get("geometry")
        code = f["properties"]["area_code"]
        assert geom is not None, code
        assert geom["type"] in ("Polygon", "MultiPolygon"), (code, geom["type"])
        assert geom["coordinates"], code


# --- metadata の必須項目 ------------------------------------------------------


def test_metadata_required_fields(gj):
    meta = gj["metadata"]
    assert meta["feature_count"] == 339
    for key in ("title", "source", "processing", "fields", "feature_count"):
        assert key in meta, key

    source = meta["source"]
    assert source["source_file"] == "ksj/A38-20/A38-20_GML.zip 内 A38-20_GML/A38-20_1.shp"
    assert len(source["source_sha256"]) == 64

    mie_ref = source["mie_correspondence"]
    assert mie_ref["file"] == "data/reference/mie_area_municipalities.csv"
    assert mie_ref["row_count"] == 29
    primary = mie_ref["primary_source"]
    assert primary["file"] == "mie/001092203.pdf"
    assert len(primary["source_sha256"]) == 64

    for field in ("area_code", "area_name", "pref_code", "pref_name", "boundary_source"):
        assert field in meta["fields"], field


def test_metadata_caveat_mentions_mie_is_a_derived_composite(gj):
    """三重県8区域が国土数値情報の公表物ではなく合成物であることが、
    metadataのcaveatからも読み取れること(properties以外にも明記する)。
    """
    caveat = gj["metadata"]["processing"]["caveat"]
    assert "三重県" in caveat
    assert "派生物" in caveat or "合成" in caveat
    assert "令和2年度" in caveat


# --- iryoken2_A38-20.geojson は変更されていないこと ---------------------------


def test_iryoken2_geojson_untouched_and_still_335_features():
    """このスクリプトは既存の iryoken2_A38-20.geojson を変更しないこと。
    335フィーチャであることは同ファイルの既知の値(build_iryoken2_geojson.py参照)。
    """
    with open(IRYOKEN2_PATH, "r", encoding="utf-8") as f:
        old_gj = json.load(f)
    assert len(old_gj["features"]) == 335
    codes = {normalize_area_code(f["properties"]["A38b_003"]) for f in old_gj["features"]}
    assert MIE_OLD_IRYOKEN2_CODES <= codes


# --- 検証6: 三重県新8区域と旧4圏域の面積合計が近いこと --------------------------


def test_mie_area_close_to_old_iryoken2_total(features):
    with open(IRYOKEN2_PATH, "r", encoding="utf-8") as f:
        old_gj = json.load(f)
    old_total = sum(
        feature_area_km2(feat["geometry"])
        for feat in old_gj["features"]
        if normalize_area_code(feat["properties"]["A38b_003"]) in MIE_OLD_IRYOKEN2_CODES
    )
    new_total = sum(
        feature_area_km2(f["geometry"]) for f in features if f["properties"]["area_code"] in MIE_AREA_CODES
    )
    assert old_total > 0 and new_total > 0
    diff_pct = abs(new_total - old_total) / old_total * 100
    assert diff_pct < TOLERANCE_PCT, (old_total, new_total, diff_pct)


def test_metadata_verification_area_check_matches_tolerance(gj):
    check = gj["metadata"]["verification"]["mie_area_check_km2"]
    assert check["tolerance_pct"] == TOLERANCE_PCT
    assert check["diff_pct"] < TOLERANCE_PCT


# --- feature_area_km2(球面近似の面積計算)の単体テスト --------------------------


def test_feature_area_km2_square_near_equator():
    # 経度1度×緯度1度の正方形(赤道付近)。1度 ≈ 111.32km なので面積 ≈ 12,392km2。
    square = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    area = feature_area_km2(square, ref_lat_deg=0.0)
    assert 12000 < area < 12800


def test_feature_area_km2_hole_is_subtracted():
    outer = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    hole = [[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75], [0.25, 0.25]]
    with_hole = {"type": "Polygon", "coordinates": [outer, hole]}
    without_hole = {"type": "Polygon", "coordinates": [outer]}
    area_with_hole = feature_area_km2(with_hole, ref_lat_deg=20.0)
    area_without_hole = feature_area_km2(without_hole, ref_lat_deg=20.0)
    assert area_with_hole < area_without_hole
    # 穴は0.5x0.5(外環1x1の1/4の面積)
    assert area_with_hole == pytest.approx(area_without_hole * 0.75, rel=0.01)


def test_feature_area_km2_multipolygon_is_sum_of_polygons():
    poly = {"type": "Polygon", "coordinates": [[[0, 0], [0.1, 0], [0.1, 0.1], [0, 0.1], [0, 0]]]}
    multi = {"type": "MultiPolygon", "coordinates": [poly["coordinates"], poly["coordinates"]]}
    single_area = feature_area_km2(poly, ref_lat_deg=30.0)
    multi_area = feature_area_km2(multi, ref_lat_deg=30.0)
    assert multi_area == pytest.approx(2 * single_area)


def test_feature_area_km2_rejects_point_geometry():
    with pytest.raises(ValueError):
        feature_area_km2({"type": "Point", "coordinates": [0, 0]})


# --- load_area_basic / load_mie_muni_map(zipを必要としない純粋な読み込み) ------


def test_load_area_basic_has_339_entries():
    area_by_code = load_area_basic()
    assert len(area_by_code) == 339
    for code, info in area_by_code.items():
        assert len(code) == 4
        assert info["area_name"] and info["pref_code"] and info["pref_name"]


def test_load_mie_muni_map_has_29_entries_covering_mie_area_codes():
    muni_to_area, rows = load_mie_muni_map()
    assert len(muni_to_area) == 29
    assert len(rows) == 29
    assert set(muni_to_area.values()) == MIE_AREA_CODES


def test_mie_csv_referenced_by_build_script_exists():
    assert MIE_CSV.exists()


# --- zipが無い環境(CI)ではスキップされる再生成関連の前提だけ確認 ------------------


@pytest.mark.skipif(
    not SRC_ZIP.exists(), reason="ksj/A38-20/A38-20_GML.zip はGit管理外でCIに存在しないため"
)
def test_src_zip_path_when_present():
    """ローカル(zipあり)環境でのみ、想定パスにzipがあることを確認する
    (再生成手順そのもののテストではない。数分かかるフルディゾルブは実行しない)。
    """
    assert SRC_ZIP.name == "A38-20_GML.zip"
    assert SRC_ZIP.stat().st_size > 0
