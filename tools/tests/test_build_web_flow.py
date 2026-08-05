# -*- coding: utf-8 -*-
"""tools/build_web_flow.py のテスト。

`tools/tests/test_build_web_demand.py` に倣い、実CSVを読む重いテスト(再現性・
スキーマの健全性・変換の忠実性・metadata)と、検証関数を直接叩く軽いテスト
(インラインのフィクスチャでSystemExitになることを確認)を分ける。

`web/src/generated/*` はGit管理外のため、ここではimportしない
(CLAUDE.md「可視化実装で判明した罠」8番)。
"""
import json

import pytest

from tools.build_web_flow import (
    AREA_BOUNDARIES_GEOJSON,
    DIRECTION_LABELS,
    DIRECTIONS,
    EXPECTED_NO_SELF_ROW_GROUPS,
    NUM_AREAS,
    PATIENT_FLOW_CSV,
    PATIENT_FLOW_TOTAL_CSV,
    PHASE_LABELS,
    PHASES,
    OUT_PATH,
    build_and_write,
    validate_area_code_sets,
    validate_no_self_row_groups,
    validate_overall_rate_matches_acute_complement,
    validate_partner_membership,
    validate_published_fy,
    validate_rank_contiguous,
    validate_rate_non_increasing,
    validate_self_rate_bound,
    validate_value_status_and_parse,
)

DIRECTION_KEY_BY_JA = {ja: key for key, ja in DIRECTION_LABELS.items()}
PHASE_KEY_BY_JA = {ja: key for key, ja in PHASE_LABELS.items()}


@pytest.fixture(scope="module")
def data():
    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_flow.py` を実行してください)"
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
    assert PATIENT_FLOW_CSV.exists()
    assert PATIENT_FLOW_TOTAL_CSV.exists()
    assert AREA_BOUNDARIES_GEOJSON.exists()

    out = build_and_write(tmp_path / "area_flow_R7.json")

    assert OUT_PATH.exists(), (
        f"{OUT_PATH} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_web_flow.py` を実行してください)"
    )
    new_bytes = out.read_bytes()
    old_bytes = OUT_PATH.read_bytes()
    assert new_bytes == old_bytes, "area_flow_R7.json がコミット済みデータとバイト一致しません"


def test_output_ends_with_single_trailing_newline():
    text = OUT_PATH.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_output_has_no_crlf():
    raw = OUT_PATH.read_bytes()
    assert b"\r" not in raw, "area_flow_R7.json にCRが含まれています(LF固定のはず)"


def test_output_has_no_generation_timestamp(data):
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
    assert set(parsed.keys()) == {
        "metadata",
        "directions",
        "direction_labels",
        "phases",
        "phase_labels",
        "areas",
    }


def test_areas_are_serialized_one_per_line():
    """`"areas": [` の次の行から `]` の直前までがちょうど339行で、各行
    (末尾のカンマを除く)が単独でjson.loadsでき、area_codeを持つこと。
    metadata/direction_labels等は`indent=2`で可読なので、途中に単独の`]`行が
    現れうる。`"areas": [`より後で最初に現れる単独`]`行をareasの終端として
    扱う(build_web_flow.pyのdump_json()参照)。
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


def test_top_level_direction_and_phase_keys(data):
    assert data["directions"] == ["inflow", "outflow"]
    assert data["direction_labels"] == {"inflow": "流入率", "outflow": "流出率"}
    assert data["phases"] == ["acute", "comprehensive", "chronic"]
    assert data["phase_labels"] == {
        "acute": "高度急性期+急性期",
        "comprehensive": "包括期",
        "chronic": "慢性期",
    }


def test_areas_count_and_unique_and_sorted(areas):
    codes = [a["area_code"] for a in areas]
    assert len(codes) == NUM_AREAS
    assert len(set(codes)) == NUM_AREAS
    assert codes == sorted(codes)


def test_area_object_has_only_area_code_and_flows(areas):
    for a in areas:
        assert set(a.keys()) == {"area_code", "flows"}, a["area_code"]


def test_area_code_format_and_pref_code_prefix_via_source_csv(areas):
    import csv

    with open(PATIENT_FLOW_TOTAL_CSV, "r", encoding="utf-8", newline="") as f:
        pref_code_by_area = {row["area_code"]: row["pref_code"] for row in csv.DictReader(f)}

    for a in areas:
        code = a["area_code"]
        assert len(code) == 4 and code.isdigit(), code
        assert code[:2] == pref_code_by_area[code], code


def test_all_2034_groups_are_present(areas):
    total_groups = 0
    for a in areas:
        assert set(a["flows"].keys()) == set(DIRECTIONS), a["area_code"]
        for direction_key in DIRECTIONS:
            flow = a["flows"][direction_key]
            assert set(flow.keys()) == {"overall_rate", "phases"}, a["area_code"]
            assert isinstance(flow["overall_rate"], float)
            assert 0 <= flow["overall_rate"] <= 1
            assert set(flow["phases"].keys()) == set(PHASES), a["area_code"]
            for phase_key in PHASES:
                phase = flow["phases"][phase_key]
                assert set(phase.keys()) == {"self_rate", "self_rank", "partners", "value_error_count"}
                total_groups += 1
    assert total_groups == NUM_AREAS * len(DIRECTIONS) * len(PHASES) == 2034


def test_self_rate_and_self_rank_are_both_null_or_both_present(areas):
    for a in areas:
        for direction_key in DIRECTIONS:
            for phase_key in PHASES:
                phase = a["flows"][direction_key]["phases"][phase_key]
                assert (phase["self_rate"] is None) == (phase["self_rank"] is None), (
                    a["area_code"],
                    direction_key,
                    phase_key,
                )
                if phase["self_rate"] is not None:
                    assert 0 <= phase["self_rate"] <= 1
                    assert isinstance(phase["self_rank"], int) and phase["self_rank"] >= 1


def test_partners_are_two_element_arrays_with_no_self_reference(areas):
    for a in areas:
        for direction_key in DIRECTIONS:
            for phase_key in PHASES:
                phase = a["flows"][direction_key]["phases"][phase_key]
                for partner in phase["partners"]:
                    assert len(partner) == 2
                    partner_code, rate = partner
                    assert partner_code != a["area_code"], (a["area_code"], direction_key, phase_key)
                    assert isinstance(partner_code, str) and len(partner_code) == 4 and partner_code.isdigit()
                    assert isinstance(rate, float)
                    assert 0 <= rate <= 1


def test_value_error_count_is_zero_or_one(areas):
    for a in areas:
        for direction_key in DIRECTIONS:
            for phase_key in PHASES:
                phase = a["flows"][direction_key]["phases"][phase_key]
                assert phase["value_error_count"] in (0, 1), (a["area_code"], direction_key, phase_key)


def test_no_self_row_groups_match_the_known_12(areas):
    no_self = set()
    for a in areas:
        for direction_key in DIRECTIONS:
            for phase_key in PHASES:
                phase = a["flows"][direction_key]["phases"][phase_key]
                if phase["self_rate"] is None:
                    no_self.add((DIRECTION_LABELS[direction_key], PHASE_LABELS[phase_key], a["area_code"]))
    assert no_self == EXPECTED_NO_SELF_ROW_GROUPS
    assert len(no_self) == 12


# --- 実データからのスポットチェック -------------------------------------------


def test_spotcheck_hokkaido_minamioshima_inflow_acute(areas_by_code):
    a = areas_by_code["0101"]
    acute = a["flows"]["inflow"]["phases"]["acute"]
    assert acute["self_rate"] == pytest.approx(0.9062844376965826)
    assert acute["self_rank"] == 1
    assert acute["partners"] == [
        ["0102", pytest.approx(0.04220060329093418)],
        ["0103", pytest.approx(0.03450749414206655)],
        ["0104", pytest.approx(0.0045019022300602195)],
    ]
    assert a["flows"]["inflow"]["overall_rate"] == pytest.approx(0.09371556230341738)


def test_spotcheck_value_error_count_1313_4207_outflow_chronic(areas_by_code):
    for code in ("1313", "4207"):
        phase = areas_by_code[code]["flows"]["outflow"]["phases"]["chronic"]
        assert phase["value_error_count"] == 1
        assert phase["self_rate"] is None
        assert phase["self_rank"] is None
        assert phase["partners"] == []


def test_spotcheck_0502_inflow_chronic_is_empty_group(areas_by_code):
    phase = areas_by_code["0502"]["flows"]["inflow"]["phases"]["chronic"]
    assert phase == {
        "self_rate": None,
        "self_rank": None,
        "partners": [],
        "value_error_count": 0,
    }


# --- area_boundaries_R7.geojsonとのarea_code整合 -------------------------------


def test_area_codes_match_boundaries_geojson(areas):
    with open(AREA_BOUNDARIES_GEOJSON, "r", encoding="utf-8") as f:
        gj = json.load(f)
    geo_codes = {feat["properties"]["area_code"] for feat in gj["features"]}
    output_codes = {a["area_code"] for a in areas}
    assert output_codes == geo_codes
    assert len(geo_codes) == NUM_AREAS


# --- metadata: 出典・known_issues --------------------------------------------


def test_metadata_required_top_level_keys(data):
    meta = data["metadata"]
    for key in ("title", "source", "processing", "fields", "known_issues"):
        assert key in meta, key


def test_metadata_source_has_sha256_and_inputs(data):
    meta = data["metadata"]
    assert "source_sha256" in meta["source"]
    assert len(meta["source"]["source_sha256"]) == 64
    assert "inputs" in meta["processing"]
    assert len(meta["processing"]["inputs"]) == 3
    for entry in meta["processing"]["inputs"]:
        assert set(entry.keys()) == {"path", "sha256"}
        assert len(entry["sha256"]) == 64


def test_derived_via_is_a_list(data):
    assert isinstance(data["metadata"]["source"]["derived_via"], list)
    assert len(data["metadata"]["source"]["derived_via"]) == 2


def test_metadata_caveat_has_both_inputs(data):
    caveat = data["metadata"]["processing"]["caveat"]
    assert set(caveat.keys()) == {"patient_flow", "patient_flow_total"}
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


def test_metadata_known_issues_contains_the_two_expected_ids(data):
    ids = {issue["id"] for issue in data["metadata"]["known_issues"]}
    assert ids == {
        "flow_outflow_chronic_value_error_cells",
        "flow_overall_rate_equals_acute_phase_complement",
    }


def test_known_issues_are_carried_over_from_the_input_csv_metadata(data):
    carried = []
    for csv_path in (PATIENT_FLOW_CSV, PATIENT_FLOW_TOTAL_CSV):
        meta_path = csv_path.with_name(csv_path.name + ".meta.json")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        carried.extend(meta.get("known_issues", []))
    assert data["metadata"]["known_issues"] == carried


# ============================================================================
# 検証関数の単体テスト: 壊れたフィクスチャでSystemExitになることを確認する
# (実データ全体(339区域)を用意しなくても検証ロジックだけを狙い撃ちできるよう、
# build_web_flow.pyのvalidate_and_index()は小さな検証関数へ分割してある)。
# ============================================================================


def test_validate_published_fy_rejects_non_r7():
    with pytest.raises(SystemExit, match="検証1失敗"):
        validate_published_fy([{"published_fy": "R6"}], "dummy.csv")


def test_validate_area_code_sets_rejects_mismatched_sets():
    with pytest.raises(SystemExit, match="検証3失敗"):
        validate_area_code_sets({"0101"}, {"0101", "0102"}, {"0101"})


def test_validate_rank_contiguous_detects_duplicate_rank():
    """検証2: 同一グループ内でrankが重複しているフィクスチャはSystemExitになる。"""
    rows = [
        {"area_code": "0101", "direction": "流入率", "phase": "高度急性期+急性期", "rank": "1"},
        {"area_code": "0101", "direction": "流入率", "phase": "高度急性期+急性期", "rank": "1"},
    ]
    with pytest.raises(SystemExit, match="検証2失敗"):
        validate_rank_contiguous(rows)


def test_validate_rank_contiguous_detects_gap():
    rows = [
        {"area_code": "0101", "direction": "流入率", "phase": "高度急性期+急性期", "rank": "1"},
        {"area_code": "0101", "direction": "流入率", "phase": "高度急性期+急性期", "rank": "3"},
    ]
    with pytest.raises(SystemExit, match="検証2失敗"):
        validate_rank_contiguous(rows)


def test_validate_value_status_and_parse_detects_out_of_range_rate():
    """検証6: rateが0〜1の範囲外のフィクスチャはSystemExitになる。"""
    rows = [{"value_status": "observed", "rate": "1.5", "partner_area_code": "0102"}]
    with pytest.raises(SystemExit, match="検証6失敗"):
        validate_value_status_and_parse(rows)


def test_validate_value_status_and_parse_detects_negative_rate():
    rows = [{"value_status": "observed", "rate": "-0.1", "partner_area_code": "0102"}]
    with pytest.raises(SystemExit, match="検証6失敗"):
        validate_value_status_and_parse(rows)


def test_validate_value_status_and_parse_accepts_valid_rows():
    rows = [
        {"value_status": "observed", "rate": "0.5", "partner_area_code": "0102"},
        {"value_status": "error", "rate": "", "partner_area_code": ""},
    ]
    parsed = validate_value_status_and_parse(rows)
    assert parsed[0]["rate_value"] == pytest.approx(0.5)
    assert parsed[1]["rate_value"] is None


def test_validate_partner_membership_rejects_unknown_partner():
    rows = [{"value_status": "observed", "partner_area_code": "9999"}]
    with pytest.raises(SystemExit, match="検証7失敗"):
        validate_partner_membership(rows, {"0101", "0102"})


def test_validate_rate_non_increasing_detects_ascending_rate():
    """検証8: rank昇順で率が増加しているフィクスチャはSystemExitになる。"""
    all_groups = {
        ("0101", "流入率", "高度急性期+急性期"): [
            {"rank": "1", "value_status": "observed", "rate_value": 0.3, "partner_area_code": "0101"},
            {"rank": "2", "value_status": "observed", "rate_value": 0.5, "partner_area_code": "0102"},
        ]
    }
    with pytest.raises(SystemExit, match="検証8失敗"):
        validate_rate_non_increasing(all_groups)


def test_validate_no_self_row_groups_detects_wrong_set():
    """検証9: 自区域行が無いグループの集合が実測の12件と異なるフィクスチャは
    SystemExitになる(ここでは12件のうち1件を欠いた11件を渡す)。"""
    partial = list(EXPECTED_NO_SELF_ROW_GROUPS)[:-1]
    all_groups = {(area_code, direction_ja, phase_ja): [] for (direction_ja, phase_ja, area_code) in partial}
    with pytest.raises(SystemExit, match="検証9失敗"):
        validate_no_self_row_groups(all_groups)


def test_validate_self_rate_bound_detects_sum_over_one():
    all_groups = {
        ("0101", "流入率", "高度急性期+急性期"): [
            {"rank": "1", "value_status": "observed", "rate_value": 0.7, "partner_area_code": "0101"},
            {"rank": "2", "value_status": "observed", "rate_value": 0.5, "partner_area_code": "0102"},
        ]
    }
    with pytest.raises(SystemExit, match="検証10失敗"):
        validate_self_rate_bound(all_groups)


def test_validate_overall_rate_matches_acute_complement_detects_mismatch():
    """検証11: overall_rateが1-acute.self_rateと一致しないフィクスチャは
    SystemExitになる。"""
    acute_ja = PHASE_LABELS["acute"]
    all_groups = {
        ("0101", "流入率", acute_ja): [
            {"rank": "1", "value_status": "observed", "rate_value": 0.9, "partner_area_code": "0101"},
        ]
    }
    total_by_key = {("0101", "流入率"): 0.5}  # 期待値は1-0.9=0.1
    with pytest.raises(SystemExit, match="検証11失敗"):
        validate_overall_rate_matches_acute_complement(total_by_key, all_groups)


def test_validate_overall_rate_matches_acute_complement_accepts_matching_value():
    acute_ja = PHASE_LABELS["acute"]
    all_groups = {
        ("0101", "流入率", acute_ja): [
            {"rank": "1", "value_status": "observed", "rate_value": 0.9, "partner_area_code": "0101"},
        ]
    }
    total_by_key = {("0101", "流入率"): 1 - 0.9}  # 検証は厳密一致なので同じ計算式で期待値を作る
    # 例外が発生しないこと
    validate_overall_rate_matches_acute_complement(total_by_key, all_groups)
