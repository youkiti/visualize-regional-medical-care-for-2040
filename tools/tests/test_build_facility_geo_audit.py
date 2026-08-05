# -*- coding: utf-8 -*-
"""tools/build_facility_geo_audit.py のテスト。

再現性(バイト一致)、参照データの読み込み(座標センチネル0.0/0.0の除外)、
距離計算、監査結果の分類、known_issuesの形、レポートの生成日時不在を検証する。
"""
import csv
import json

import pytest

from tools.build_facility_geo_audit import (
    AUDIT_AGREE,
    AUDIT_CONFLICT,
    AUDIT_LABELS,
    AUDIT_MINOR_GAP,
    AGREE_MAX_M,
    CONFLICT_MIN_M,
    DOC_DIR,
    OUTPUT_HEADER,
    PROCESSED_DIR,
    REF_LABELS,
    _usable_coordinate,
    build_and_write,
    haversine_m,
    known_issues_for,
)

OUT_CSV = PROCESSED_DIR / "facility_geo_audit.csv"
OUT_META = PROCESSED_DIR / "facility_geo_audit.csv.meta.json"
OUT_DOC = DOC_DIR / "FACILITY_GEO_AUDIT.md"


@pytest.fixture(scope="module")
def rows():
    assert OUT_CSV.exists(), (
        f"{OUT_CSV} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_facility_geo_audit.py` を実行してください)"
    )
    with open(OUT_CSV, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def meta():
    with open(OUT_META, "r", encoding="utf-8") as f:
        return json.load(f)


# --- 座標センチネル ----------------------------------------------------------


def test_usable_coordinate_rejects_zero_sentinel():
    """医療情報ネットの座標欠測は空欄ではなく 0.0/0.0。空欄判定では検出できない。"""
    assert _usable_coordinate({"所在地座標（緯度）": "43.0", "所在地座標（経度）": "141.3"}) == (141.3, 43.0)
    assert _usable_coordinate({"所在地座標（緯度）": "0.0", "所在地座標（経度）": "0.0"}) is None
    assert _usable_coordinate({"所在地座標（緯度）": "", "所在地座標（経度）": ""}) is None
    assert _usable_coordinate({"所在地座標（緯度）": "-", "所在地座標（経度）": "-"}) is None
    # 日本の範囲外(緯度経度を取り違えた値など)も弾く
    assert _usable_coordinate({"所在地座標（緯度）": "141.3", "所在地座標（経度）": "43.0"}) is None


# --- 距離 --------------------------------------------------------------------


def test_haversine_known_distances():
    assert haversine_m(139.0, 35.0, 139.0, 35.0) == 0.0
    # 緯度1分(1/60度)はおよそ1,852m(1海里)
    assert haversine_m(139.0, 35.0, 139.0, 35.0 + 1 / 60) == pytest.approx(1852, rel=0.01)
    # 経度方向は cos(緯度) 倍に縮む
    east = haversine_m(139.0, 35.0, 139.0 + 1 / 60, 35.0)
    assert east == pytest.approx(1852 * 0.8192, rel=0.01)


# --- 出力CSVの形 -------------------------------------------------------------


def test_header_and_row_count(rows):
    with open(OUT_CSV, "r", encoding="utf-8", newline="") as f:
        header = next(csv.reader(f))
    assert header == OUTPUT_HEADER
    assert len(rows) == 11760


def test_audit_and_reference_status_values_are_known(rows):
    assert {r["audit_status"] for r in rows} <= set(AUDIT_LABELS)
    assert {r["reference_status"] for r in rows} <= set(REF_LABELS)


def test_distance_bands_are_consistent_with_audit_status(rows):
    """audit_status と distance_m の関係が閾値どおりであること。

    CSVのdistance_mは小数1桁に丸めてあるので、境界ちょうど付近では丸めた値が
    閾値と一致しうる(実測: 99.96m→'100.0'がagree)。分類は丸める前の値で
    行っているため、比較には丸め幅の半分(0.05m)の許容を持たせる。
    """
    eps = 0.05
    for r in rows:
        if r["audit_status"] == AUDIT_AGREE:
            assert float(r["distance_m"]) < AGREE_MAX_M + eps, r["record_id"]
        elif r["audit_status"] == AUDIT_MINOR_GAP:
            assert AGREE_MAX_M - eps <= float(r["distance_m"]) < CONFLICT_MIN_M + eps, r["record_id"]
        elif r["audit_status"] == AUDIT_CONFLICT:
            assert float(r["distance_m"]) >= CONFLICT_MIN_M - eps, r["record_id"]
        else:
            assert r["distance_m"] == "", r["record_id"]


def test_reference_columns_present_exactly_when_reference_resolved(rows):
    for r in rows:
        resolved = r["reference_id"] != ""
        assert (r["reference_latitude"] != "") == resolved, r["record_id"]
        assert (r["reference_longitude"] != "") == resolved, r["record_id"]
        if resolved:
            lat = float(r["reference_latitude"])
            lon = float(r["reference_longitude"])
            assert 20 < lat < 46, r["record_id"]
            assert 122 < lon < 154, r["record_id"]


def test_conflicts_exist_and_are_the_documented_count(rows):
    conflicts = [r for r in rows if r["audit_status"] == AUDIT_CONFLICT]
    assert len(conflicts) == 76


# --- meta.json ---------------------------------------------------------------


def test_meta_known_issues_shape(meta):
    issues = meta["known_issues"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue["id"] == "facility_coordinate_conflicts_with_published_reference"
    for key in ("id", "scope", "summary", "evidence", "action"):
        assert key in issue
    assert issue["scope"]["csv"] == "facility_geo_audit.csv"
    assert isinstance(issue["evidence"], list) and len(issue["evidence"]) >= 2


def test_known_issues_for_returns_empty_without_conflicts():
    """conflictが0件になったら known_issues も空にする(存在しない欠陥を書かない)。"""
    assert known_issues_for([]) == []


def test_meta_inputs_include_reference_zips(meta):
    files = {i["file"] for i in meta["source"]["inputs"]}
    assert "iryojoho/01-1_hospital_facility_info_20250601.zip" in files
    assert "iryojoho/02-1_clinic_facility_info_20250601.zip" in files
    assert "data/processed/facility_geo_linkage.csv" in files


# --- 再現性(バイト一致) -----------------------------------------------------


def test_reproducibility_byte_identical(tmp_path):
    out_dir = tmp_path / "processed"
    doc_dir = tmp_path / "doc"
    out_dir.mkdir()
    doc_dir.mkdir()
    result = build_and_write(out_dir, doc_dir)

    assert result["csv"].read_bytes() == OUT_CSV.read_bytes()
    assert result["doc"].read_bytes() == OUT_DOC.read_bytes()

    # meta.jsonは processing.date(生成日)だけが揺れうるので、その項目を除いて比較する
    # (他の生成物の再現性テストと同じ規律)。
    regenerated = json.loads(result["meta"].read_text(encoding="utf-8"))
    committed = json.loads(OUT_META.read_text(encoding="utf-8"))
    regenerated["processing"].pop("date", None)
    committed["processing"].pop("date", None)
    assert regenerated == committed


def test_report_has_no_generation_timestamp():
    """生成日時を埋め込まない(埋め込むと翌日にバイト一致テストが壊れる)。"""
    text = OUT_DOC.read_text(encoding="utf-8")
    assert "生成日時" not in text
    assert "生成日:" not in text
