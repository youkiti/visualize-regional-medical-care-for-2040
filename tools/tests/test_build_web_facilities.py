# -*- coding: utf-8 -*-
"""tools/build_web_facilities.py のテスト。

再現性(バイト一致)、出力フォーマット(areasは1区域1行の決定的フォーマット、
metadataは可読)、スキーマの健全性(339区域・11,760施設・全施設で
len(values)==len(value_status)==21)、変換の忠実性(facility_observations.csvの
246,960行全件と出力の値が一致すること。サンプリングではなく全件)、座標
(名寄せの10,244件のうち、検算で否定された76件を除いた10,168件が出力され、
match_statusとの関係が「matchedでも座標を持つとは限らない」形になっていること)、
metadataの出典・生成日時不在・known_issuesの入力CSV由来を検証する。
"""
import csv
import json

import pytest

from tools.build_web_facilities import (
    EXPECTED_COORDINATE_WITHDRAWN_COUNT,
    EXPECTED_DISPLAYED_COORDINATE_COUNT,
    EXPECTED_GEOCODED_COUNT,
    FACILITY_BASIC_CSV,
    FACILITY_GEO_AUDIT_CSV,
    FACILITY_FUNCTIONS_CSV,
    FACILITY_GEO_LINKAGE_CSV,
    FACILITY_OBSERVATIONS_CSV,
    METRIC_KEY_BY_PAIR,
    METRICS,
    NUM_AREAS,
    NUM_FACILITIES,
    OUT_PATH,
    VALUE_STATUS_LABELS,
    build_and_write,
)

METRIC_INDEX_BY_KEY = {m["key"]: i for i, m in enumerate(METRICS)}


@pytest.fixture(scope="module")
def data():
    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_facilities.py` を実行してください)"
    )
    with open(OUT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def areas(data):
    return data["areas"]


@pytest.fixture(scope="module")
def facilities_by_id(areas):
    return {f["record_id"]: f for a in areas for f in a["facilities"]}


# --- 再現性(バイト一致) -----------------------------------------------------


def test_reproducibility_byte_identical(tmp_path):
    assert FACILITY_BASIC_CSV.exists()
    assert FACILITY_OBSERVATIONS_CSV.exists()
    assert FACILITY_FUNCTIONS_CSV.exists()
    assert FACILITY_GEO_LINKAGE_CSV.exists()

    out = build_and_write(tmp_path / "area_facilities_R7.json")

    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_facilities.py` を実行してください)"
    )
    new_bytes = out.read_bytes()
    old_bytes = OUT_PATH.read_bytes()
    assert new_bytes == old_bytes, "area_facilities_R7.json がコミット済みデータとバイト一致しません"


def test_output_ends_with_single_trailing_newline():
    text = OUT_PATH.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_output_has_no_crlf():
    raw = OUT_PATH.read_bytes()
    assert b"\r" not in raw, "area_facilities_R7.json にCRが含まれています(LF固定のはず)"


def test_output_has_no_generation_timestamp(data):
    """metadata全体を再帰的に確認し、生成日時らしきキーが無いこと
    (CLAUDE.md「生成物には生成日時を埋め込まない」)。"""

    def _walk(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                assert key not in ("date", "generated_at", "timestamp", "created_at"), key
                _walk(value)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(data["metadata"])


# --- 出力フォーマット: areasは1区域1行の決定的フォーマット ---------------------


def test_output_is_valid_json():
    text = OUT_PATH.read_text(encoding="utf-8")
    parsed = json.loads(text)
    assert isinstance(parsed, dict)
    assert set(parsed.keys()) == {"metadata", "metrics", "value_status_labels", "areas"}


def test_areas_are_serialized_one_per_line():
    """`"areas": [` の次の行から `]` の直前までがちょうど339行で、各行
    (末尾のカンマを除く)が単独でjson.loadsでき、area_codeを持つこと。
    metadata/metricsは`indent=2`で可読なので、途中に単独の`]`行が現れうる
    (metricsの閉じ括弧)。`"areas": [`より後で最初に現れる単独`]`行を
    areasの終端として扱う(build_web_facilities.pyのdump_json()参照)。
    """
    text = OUT_PATH.read_text(encoding="utf-8")
    lines = text.split("\n")
    start = lines.index('"areas": [')
    end = lines.index("]", start + 1)
    area_lines = lines[start + 1 : end]

    assert len(area_lines) == NUM_AREAS

    seen_codes = []
    for line in area_lines:
        stripped = line[:-1] if line.endswith(",") else line
        area = json.loads(stripped)
        assert "area_code" in area
        seen_codes.append(area["area_code"])
    assert len(set(seen_codes)) == NUM_AREAS
    assert seen_codes == sorted(seen_codes)


# --- スキーマの健全性 --------------------------------------------------------


def test_metrics_list(data):
    assert len(data["metrics"]) == 21
    keys = [m["key"] for m in data["metrics"]]
    assert len(set(keys)) == 21
    for m in data["metrics"]:
        assert set(m.keys()) == {"key", "metric", "bed_function", "label"}


def test_value_status_labels(data):
    assert set(data["value_status_labels"].keys()) == {
        "observed",
        "source_dash",
        "not_disclosed",
        "not_reported",
        "blank",
    }
    assert data["value_status_labels"] == VALUE_STATUS_LABELS


def test_areas_count_and_unique_and_sorted(areas):
    codes = [a["area_code"] for a in areas]
    assert len(codes) == NUM_AREAS
    assert len(set(codes)) == NUM_AREAS
    assert codes == sorted(codes)


def test_area_code_format_and_pref_code_prefix(areas):
    for a in areas:
        code = a["area_code"]
        assert len(code) == 4 and code.isdigit(), code
        assert len(a["pref_code"]) == 2 and a["pref_code"].isdigit(), a["pref_code"]
        assert code[:2] == a["pref_code"], code


def test_total_facility_count_is_11760(areas):
    total = sum(a["facility_count"] for a in areas)
    assert total == NUM_FACILITIES
    total_from_list = sum(len(a["facilities"]) for a in areas)
    assert total_from_list == NUM_FACILITIES


def test_facility_count_matches_facilities_list_length(areas):
    for a in areas:
        assert a["facility_count"] == len(a["facilities"]), a["area_code"]


def test_record_ids_are_unique_across_areas_and_match_facility_basic(facilities_by_id):
    """検証13相当: record_idが区域をまたいで重複せず、facility_basic.csvの
    record_id集合と完全一致すること。"""
    with open(FACILITY_BASIC_CSV, "r", encoding="utf-8", newline="") as f:
        basic_ids = {row["record_id"] for row in csv.DictReader(f)}
    assert len(facilities_by_id) == NUM_FACILITIES
    assert set(facilities_by_id.keys()) == basic_ids


def test_all_facilities_have_21_values_and_value_status(areas):
    for a in areas:
        for f in a["facilities"]:
            assert len(f["values"]) == 21, f["record_id"]
            assert len(f["value_status"]) == 21, f["record_id"]
            for status in f["value_status"]:
                assert status in VALUE_STATUS_LABELS, (f["record_id"], status)


def test_values_are_null_iff_not_observed(areas):
    for a in areas:
        for f in a["facilities"]:
            for value, status in zip(f["values"], f["value_status"]):
                if status == "observed":
                    assert value is not None, (f["record_id"], status)
                    assert isinstance(value, (int, float))
                    assert not isinstance(value, bool)
                else:
                    assert value is None, (f["record_id"], status)


def test_facilities_within_area_are_sorted_by_source_row(areas):
    """facilitiesは原典の並び順(facility_basic.csvのsource_row昇順)を保つ。
    record_idが`R7-<area_code>-<source_row>`形式であることを利用して検証する。
    """
    for a in areas:
        rows = [int(f["record_id"].rsplit("-", 1)[1]) for f in a["facilities"]]
        assert rows == sorted(rows), a["area_code"]


def test_functions_key_omitted_when_empty(areas):
    """該当する医療機関機能が無い施設ではfunctionsキー自体を省略する
    (0件を意味する空配列にはしない)。"""
    for a in areas:
        for f in a["facilities"]:
            if "functions" in f:
                assert isinstance(f["functions"], list) and len(f["functions"]) > 0, f["record_id"]


def test_coordinates_key_omitted_when_unmatched_or_withdrawn(areas):
    """座標を持つのは「名寄せでmatched」かつ「検算で取り下げていない」施設だけ。

    **match_status だけでは判定できない**(取り下げた施設はmatchedのまま座標を
    持たない)。この非対称が入ったのがM10の変更点なので、ここで固定しておく。
    """
    for a in areas:
        for f in a["facilities"]:
            has_coordinates = "coordinates" in f
            withdrawn = f.get("coordinate_withdrawn", False)
            assert has_coordinates == (f["match_status"] == "matched" and not withdrawn), f["record_id"]
            if withdrawn:
                assert withdrawn is True, f["record_id"]
                assert f["match_status"] == "matched", f["record_id"]
            if has_coordinates:
                lon, lat = f["coordinates"]
                assert 122 <= lon <= 154, f["record_id"]
                assert 20 <= lat <= 46, f["record_id"]


# --- 座標: 名寄せ10,244件 − 検算で取り下げ76件 = 出力10,168件 ------------------


def test_geocoded_count_excludes_withdrawn(areas, facilities_by_id):
    total_geocoded = sum(a["geocoded_count"] for a in areas)
    total_withdrawn = sum(a["coordinate_withdrawn_count"] for a in areas)
    assert total_geocoded == EXPECTED_DISPLAYED_COORDINATE_COUNT
    assert total_withdrawn == EXPECTED_COORDINATE_WITHDRAWN_COUNT
    assert total_geocoded + total_withdrawn == EXPECTED_GEOCODED_COUNT

    with_coordinates = [rid for rid, f in facilities_by_id.items() if "coordinates" in f]
    assert len(with_coordinates) == EXPECTED_DISPLAYED_COORDINATE_COUNT

    withdrawn_ids = {rid for rid, f in facilities_by_id.items() if f.get("coordinate_withdrawn")}
    assert len(withdrawn_ids) == EXPECTED_COORDINATE_WITHDRAWN_COUNT

    with open(FACILITY_GEO_LINKAGE_CSV, "r", encoding="utf-8", newline="") as f:
        geo_rows = list(csv.DictReader(f))
    matched_ids = {r["record_id"] for r in geo_rows if r["match_status"] == "matched"}
    assert set(with_coordinates) | withdrawn_ids == matched_ids
    assert not (set(with_coordinates) & withdrawn_ids)


def test_withdrawn_ids_are_exactly_the_audit_conflicts(facilities_by_id):
    """取り下げる施設は facility_geo_audit.csv の audit_status=='conflict' と完全一致する。"""
    with open(FACILITY_GEO_AUDIT_CSV, "r", encoding="utf-8", newline="") as f:
        conflict_ids = {r["record_id"] for r in csv.DictReader(f) if r["audit_status"] == "conflict"}
    withdrawn_ids = {rid for rid, fac in facilities_by_id.items() if fac.get("coordinate_withdrawn")}
    assert withdrawn_ids == conflict_ids
    assert len(conflict_ids) == EXPECTED_COORDINATE_WITHDRAWN_COUNT


def test_coordinates_match_geo_linkage_csv_exactly(facilities_by_id):
    with open(FACILITY_GEO_LINKAGE_CSV, "r", encoding="utf-8", newline="") as f:
        geo_rows = list(csv.DictReader(f))
    for r in geo_rows:
        facility = facilities_by_id[r["record_id"]]
        # match_status は名寄せの結果そのまま(取り下げても書き換えない)。
        assert facility["match_status"] == r["match_status"], r["record_id"]
        if r["match_status"] == "matched" and not facility.get("coordinate_withdrawn"):
            assert facility["coordinates"] == pytest.approx([float(r["longitude"]), float(r["latitude"])])
        else:
            assert "coordinates" not in facility


def test_withdrawn_facilities_keep_all_21_metrics(facilities_by_id):
    """座標を取り下げても一覧からは消さない(21指標はそのまま出す)。"""
    withdrawn = [f for f in facilities_by_id.values() if f.get("coordinate_withdrawn")]
    assert len(withdrawn) == EXPECTED_COORDINATE_WITHDRAWN_COUNT
    for f in withdrawn:
        assert len(f["values"]) == len(METRICS), f["record_id"]
        assert len(f["value_status"]) == len(METRICS), f["record_id"]


# --- 変換の忠実性: facility_observations.csvの全246,960行と出力の値が一致 -----


def test_all_observation_rows_match_output_exactly(facilities_by_id):
    with open(FACILITY_OBSERVATIONS_CSV, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == NUM_FACILITIES * len(METRICS)

    for row in rows:
        key = METRIC_KEY_BY_PAIR[(row["metric"], row["bed_function"])]
        idx = METRIC_INDEX_BY_KEY[key]
        facility = facilities_by_id[row["record_id"]]

        assert facility["value_status"][idx] == row["value_status"], row

        if row["value_status"] == "observed":
            assert facility["values"][idx] == pytest.approx(float(row["value"])), row
        else:
            assert row["value"] == "", row
            assert facility["values"][idx] is None, row


def test_all_function_rows_are_reflected_in_output(facilities_by_id):
    with open(FACILITY_FUNCTIONS_CSV, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    expected_by_id = {}
    for row in rows:
        expected_by_id.setdefault(row["record_id"], []).append(row["function_name"])

    for record_id, expected_functions in expected_by_id.items():
        assert facilities_by_id[record_id]["functions"] == expected_functions, record_id

    # facility_functions.csvに現れないrecord_idはfunctionsキー自体を持たない
    for record_id, facility in facilities_by_id.items():
        if record_id not in expected_by_id:
            assert "functions" not in facility, record_id


# --- metadata: 出典・known_issues --------------------------------------------


def test_metadata_required_top_level_keys(data):
    meta = data["metadata"]
    for key in ("title", "source", "geo_linkage_source", "processing", "fields", "known_issues"):
        assert key in meta, key


def test_metadata_source_has_sha256(data):
    meta = data["metadata"]
    assert "source_sha256" in meta["source"]
    assert len(meta["source"]["source_sha256"]) == 64
    assert "inputs" in meta["processing"]
    assert len(meta["processing"]["inputs"]) == 6
    for entry in meta["processing"]["inputs"]:
        assert set(entry.keys()) == {"path", "sha256"}
        assert len(entry["sha256"]) == 64


def test_metadata_geo_linkage_source_has_different_shape(data):
    """facility_geo_linkage.csv.meta.jsonのsourceは本体(001723127.xlsx)とは
    別の形(source_file/source_sha256を持たない)なので、metadata.sourceとは
    別キー(geo_linkage_source)に格納されていること。"""
    geo_source = data["metadata"]["geo_linkage_source"]
    assert "source_file" not in geo_source
    assert "source_sha256" not in geo_source
    assert "inputs" in geo_source


def test_derived_via_is_a_list_in_both_source_blocks(data):
    """metadata.source.derived_via / metadata.geo_linkage_source.derived_via は
    どちらもlistであること(area_indicators_R7.json・area_demand_R7.jsonと同じ形。
    CLAUDE.md「可視化実装で判明した罠」11番: 表示用JSONごとにmetadataの形が
    揃わないとReact側が落ちる。片方だけ辞書になって再び分岐しないよう固定する)。"""
    meta = data["metadata"]
    assert isinstance(meta["source"]["derived_via"], list)
    assert len(meta["source"]["derived_via"]) > 0
    assert isinstance(meta["geo_linkage_source"]["derived_via"], list)
    assert len(meta["geo_linkage_source"]["derived_via"]) > 0


def test_metadata_caveat_has_all_five_inputs(data):
    caveat = data["metadata"]["processing"]["caveat"]
    assert set(caveat.keys()) == {
        "facility_basic",
        "facility_observations",
        "facility_functions",
        "facility_geo_linkage",
        "facility_geo_audit",
    }
    for value in caveat.values():
        assert isinstance(value, str) and value


def test_metadata_known_issues_is_a_list_with_the_required_shape(data):
    issues = data["metadata"]["known_issues"]
    assert isinstance(issues, list)
    for issue in issues:
        for key in ("id", "summary", "action"):
            assert isinstance(issue.get(key), str) and issue[key], (issue.get("id"), key)
    ids = [issue["id"] for issue in issues]
    assert len(ids) == len(set(ids)), f"known_issuesのidが重複している: {ids}"


def test_known_issues_are_carried_over_from_the_input_csv_metadata(data):
    """known_issuesはbuild_web_facilities.pyがその場で書くのではなく、入力CSVの
    meta.jsonから集約されること(パーサのKNOWN_ISSUESへ1件足すだけで表示用
    データセットまで流れる導線を固定する)。"""
    carried = []
    for csv_path in (
        FACILITY_BASIC_CSV,
        FACILITY_OBSERVATIONS_CSV,
        FACILITY_FUNCTIONS_CSV,
        FACILITY_GEO_LINKAGE_CSV,
        FACILITY_GEO_AUDIT_CSV,
    ):
        meta_path = csv_path.with_name(csv_path.name + ".meta.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        carried.extend(meta.get("known_issues", []))
    assert data["metadata"]["known_issues"] == carried


def test_metadata_known_issues_records_the_hospital_count_mismatch(data):
    issues = {issue["id"]: issue for issue in data["metadata"]["known_issues"]}
    assert "facility_basic_summary_hospital_count_mismatch" in issues
