# -*- coding: utf-8 -*-
"""tools/build_mie_area_municipalities.py のテスト。

三重県の構想区域(8区域)×二次医療圏(令和2年度、4圏域)×構成市町(29市町)の
対応表は一次資料PDFからの手転記であるため、転記ミスを機械的に検出できることが
重要である。以下の検証すべてが実測値(29市町・8区域・4親圏域・裏付け20市町・
不一致0件・真の残存リスク8件)どおりであることをここで固定する。

`ksj/A38-20/A38-20_GML.zip`(Git管理外)には依存しない。使うのは
`data/processed/iryoken2_A38-20.geojson`(コミット済みの加工データ)のみ。
検証5(医療機関所在地との突合)は `R7/001723127.xlsx`(コミット済み)を読むため、
他のテストよりやや重い(数秒程度)が、CIで確実に実行されるよう特別なマークは
付けない。
"""
import json

import pytest

from tools.lib.provenance import REPO_ROOT
from tools.build_mie_area_municipalities import (
    MAPPING,
    OUT_CSV,
    PARENT_CODES,
    build_and_write,
    build_global_lookup,
    build_rows,
    compute_residual_risk,
    load_a38_mie_groups,
    validate_coverage,
    validate_name_match,
    validate_nesting,
    validate_uniqueness,
    verify_against_institutions,
)

MIE_AREA_CODES = {"2405", "2406", "2407", "2408", "2409", "2410", "2411", "2412"}

EXPECTED_VERIFIED_MUNI_COUNT = 20
EXPECTED_TRUE_RESIDUAL_RISK = {
    ("2405", "木曽岬町"),
    ("2405", "東員町"),
    ("2406", "朝日町"),
    ("2406", "川越町"),
    ("2410", "多気町"),
    ("2410", "大紀町"),
    ("2411", "鳥羽市"),
    ("2411", "度会町"),
}
EXPECTED_UNAMBIGUOUS_UNVERIFIED = {("2412", "紀宝町")}


# --- MAPPING(手転記の対応表そのもの)の形の確認 -------------------------------


def test_mapping_has_8_areas_29_municipalities_4_parents():
    assert len(MAPPING) == 8
    assert {e["area_code"] for e in MAPPING} == MIE_AREA_CODES
    assert {e["parent_code"] for e in MAPPING} == {"2401", "2402", "2403", "2404"}
    total_muni = sum(len(e["muni_names"]) for e in MAPPING)
    assert total_muni == 29


# --- 市町コード解決(A38-20から市町名で引く) ----------------------------------


@pytest.fixture(scope="module")
def groups():
    g, _ = load_a38_mie_groups()
    return g


@pytest.fixture(scope="module")
def lookup(groups):
    return build_global_lookup(groups)


@pytest.fixture(scope="module")
def rows(lookup):
    name_to_code, _, _ = lookup
    return build_rows(MAPPING, name_to_code)


def test_a38_groups_have_29_municipalities_total(groups):
    assert set(groups) == set(PARENT_CODES)
    total = sum(len(munis) for munis in groups.values())
    assert total == 29
    assert {code: len(munis) for code, munis in groups.items()} == {
        "2401": 10,
        "2402": 3,
        "2403": 11,
        "2404": 5,
    }


def test_build_rows_resolves_all_29_names(rows):
    assert len(rows) == 29
    assert {r["muni_code"] for r in rows} != set()  # 全行がmuni_codeを持つ(空でない)
    for r in rows:
        assert r["muni_code"], r
        assert r["area_code"] in MIE_AREA_CODES


def test_build_rows_aborts_on_unresolvable_name(lookup):
    """名称でA38の構成市区町村リストから解決できない市町があれば中断すること。"""
    name_to_code, _, _ = lookup
    bad_mapping = [
        {
            "area_code": "9999",
            "area_name": "テスト",
            "muni_names": ["存在しない架空市"],
            "parent_code": "9998",
            "parent_name": "テスト圏域",
        }
    ]
    with pytest.raises(RuntimeError):
        build_rows(bad_mapping, name_to_code)


# --- 検証1: 網羅性 -----------------------------------------------------------


def test_validate_coverage_29_matches_a38_union(rows, groups):
    result = validate_coverage(rows, groups)
    assert result == {"csv_muni_count": 29, "a38_union_muni_count": 29}


def test_validate_coverage_detects_missing_municipality(rows, groups):
    """CSV側が1件欠けていたら網羅性検証が中断すること(過不足の検出)。"""
    with pytest.raises(ValueError):
        validate_coverage(rows[:-1], groups)


# --- 検証2: 一意性 -----------------------------------------------------------


def test_validate_uniqueness_29_no_duplicates(rows):
    result = validate_uniqueness(rows)
    assert result == {"muni_count": 29}


def test_validate_uniqueness_detects_duplicate_muni_code():
    dup_rows = [
        {"muni_code": "24202", "area_code": "2406", "muni_name": "四日市市"},
        {"muni_code": "24202", "area_code": "2406", "muni_name": "四日市市"},
    ]
    with pytest.raises(ValueError):
        validate_uniqueness(dup_rows)


# --- 検証3: 入れ子の整合 -----------------------------------------------------


def test_validate_nesting_29_rows_no_mismatch(rows, lookup):
    _, code_to_owner, _ = lookup
    result = validate_nesting(rows, code_to_owner)
    assert result == {"checked": 29, "mismatches": []}


def test_validate_nesting_detects_wrong_old_zone(rows, lookup):
    """旧圏域をまたぐ誤転記(parent_iryoken2_codeの取り違え)を検出できること。"""
    _, code_to_owner, _ = lookup
    tampered = list(rows)
    bad_row = dict(tampered[0])
    bad_row["parent_iryoken2_code"] = "9999"  # 実際には別の圏域に属する市町のはず
    tampered[0] = bad_row
    with pytest.raises(ValueError):
        validate_nesting(tampered, code_to_owner)


# --- 検証4: 名称の一致 -------------------------------------------------------


def test_validate_name_match_29_rows_no_mismatch(rows, lookup):
    _, _, code_to_name = lookup
    result = validate_name_match(rows, code_to_name)
    assert result == {"checked": 29, "mismatches": []}


def test_validate_name_match_detects_wrong_name(rows, lookup):
    _, _, code_to_name = lookup
    tampered = list(rows)
    bad_row = dict(tampered[0])
    bad_row["muni_name"] = "架空市"
    tampered[0] = bad_row
    with pytest.raises(ValueError):
        validate_name_match(tampered, code_to_name)


# --- 検証5: 医療機関所在地との突合(独立した裏付け、生Excelを読む) --------------


@pytest.fixture(scope="module")
def institution_result(rows):
    return verify_against_institutions(rows)


def test_institution_corroboration_verifies_20_municipalities_no_mismatch(institution_result):
    assert institution_result["verified_muni_count"] == EXPECTED_VERIFIED_MUNI_COUNT
    assert institution_result["mismatches"] == []


def test_institution_corroboration_pairs_are_exactly_expected(institution_result):
    verified = set(institution_result["verified_pairs"])
    expected = {
        ("2405", "いなべ市"),
        ("2405", "桑名市"),
        ("2406", "四日市市"),
        ("2406", "菰野町"),
        ("2407", "亀山市"),
        ("2407", "鈴鹿市"),
        ("2408", "津市"),
        ("2409", "伊賀市"),
        ("2409", "名張市"),
        ("2410", "大台町"),
        ("2410", "明和町"),
        ("2410", "松阪市"),
        ("2411", "伊勢市"),
        ("2411", "南伊勢町"),
        ("2411", "志摩市"),
        ("2411", "玉城町"),
        ("2412", "尾鷲市"),
        ("2412", "御浜町"),
        ("2412", "熊野市"),
        ("2412", "紀北町"),
    }
    assert verified == expected
    assert len(expected) == EXPECTED_VERIFIED_MUNI_COUNT


# --- 検証6: 残存リスク -------------------------------------------------------


@pytest.fixture(scope="module")
def residual_risk(rows, institution_result):
    return compute_residual_risk(rows, MAPPING, institution_result["verified_pairs"])


def test_residual_risk_counts(residual_risk):
    assert residual_risk["unverified_count"] == 9
    assert residual_risk["true_residual_risk_count"] == 8
    assert residual_risk["unambiguous_unverified_count"] == 1


def test_residual_risk_true_risk_is_exactly_expected(residual_risk):
    true_risk_pairs = {(r["area_code"], r["muni_name"]) for r in residual_risk["true_residual_risk"]}
    assert true_risk_pairs == EXPECTED_TRUE_RESIDUAL_RISK


def test_residual_risk_unambiguous_is_kihoucho_only(residual_risk):
    """紀宝町(2412東紀州)は旧圏域(2404東紀州)が分割されない1対1のため、
    医療機関裏付けが無くても割当が一意に定まり、真の残存リスクに含めない。
    """
    unambiguous_pairs = {(r["area_code"], r["muni_name"]) for r in residual_risk["unambiguous_unverified"]}
    assert unambiguous_pairs == EXPECTED_UNAMBIGUOUS_UNVERIFIED


def test_residual_risk_unverified_is_union_of_true_and_unambiguous(residual_risk):
    unverified_pairs = {(r["area_code"], r["muni_name"]) for r in residual_risk["unverified"]}
    assert unverified_pairs == EXPECTED_TRUE_RESIDUAL_RISK | EXPECTED_UNAMBIGUOUS_UNVERIFIED


# --- 出力(CSV+meta.json)の再現性(バイト一致) --------------------------------


def test_reproducibility_byte_identical(tmp_path):
    paths = build_and_write(tmp_path)
    assert paths.keys() == {"csv", "meta"}

    committed_csv = OUT_CSV
    assert committed_csv.exists(), (
        f"{committed_csv} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_mie_area_municipalities.py` を実行してください)"
    )
    assert paths["csv"].read_bytes() == committed_csv.read_bytes(), (
        "mie_area_municipalities.csv がコミット済みデータとバイト一致しません"
    )

    new_meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
    committed_meta_path = REPO_ROOT / "data" / "reference" / "mie_area_municipalities.csv.meta.json"
    old_meta = json.loads(committed_meta_path.read_text(encoding="utf-8"))
    # processing.date は実行日ごとに変わるため、比較対象から除外する
    new_meta["processing"]["date"] = None
    old_meta["processing"]["date"] = None
    assert new_meta == old_meta, "mie_area_municipalities.csv.meta.json の内容(processing.dateを除く)が一致しません"


def test_csv_row_count_and_header():
    with open(OUT_CSV, "r", encoding="utf-8", newline="") as f:
        lines = f.read().splitlines()
    assert lines[0] == "area_code,area_name,muni_code,muni_name,parent_iryoken2_code,parent_iryoken2_name"
    assert len(lines) == 1 + 29  # ヘッダー + 29市町


def test_csv_is_lf_only():
    data = OUT_CSV.read_bytes()
    assert b"\r\n" not in data
    assert not data.startswith(b"\xef\xbb\xbf")
