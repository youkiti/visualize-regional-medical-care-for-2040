# -*- coding: utf-8 -*-
"""tools/verify_area_join.py のテスト。

339構想区域と335二次医療圏境界の突合結果(matched=331/area_only=8/geo_only=4)、
流出入率XXXとの独立裏付け、構想区域→都道府県の集計整合(2585キー中230件が
2024年に集中)、および `area_geo_join.csv`・`doc/JOIN_VERIFICATION.md` の
再現性(バイト一致)を検証する。

`ksj/A38-20/A38-20_GML.zip` には一切依存しない(Git管理外でCIに存在しないため)。
"""
import json

import pytest

from tools.lib.provenance import REPO_ROOT
from tools.verify_area_join import (
    AREA_BEDS_CSV,
    AREA_BOUNDARIES_GEOJSON,
    MIE_AREA_MUNI_META,
    MIE_OLD_TO_NEW,
    OUT_CSV,
    OUT_DOC,
    PREFECTURE_BEDS_CSV,
    aggregate_area_beds_by_pref,
    build_and_write,
    build_join_rows,
    build_report_markdown,
    compare_aggregates,
    compute_join,
    compute_xxx_area_codes,
    load_area_basic,
    load_area_boundaries_metadata,
    load_beds_csv,
    load_geojson,
    load_mie_old_to_new,
    prefecture_beds_lookup,
)

PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DOC_DIR = REPO_ROOT / "doc"

MIE_AREA_ONLY_CODES = {"2405", "2406", "2407", "2408", "2409", "2410", "2411", "2412"}
MIE_GEO_ONLY_CODES = {"2401", "2402", "2403", "2404"}


@pytest.fixture(scope="module")
def loaded():
    area_by_code, area_rows, area_meta = load_area_basic()
    geo_by_code, geo_metadata = load_geojson()
    area_beds_rows = load_beds_csv(AREA_BEDS_CSV)
    pref_beds_rows = load_beds_csv(PREFECTURE_BEDS_CSV)
    boundaries_metadata = load_area_boundaries_metadata()
    return {
        "area_by_code": area_by_code,
        "area_rows": area_rows,
        "area_meta": area_meta,
        "geo_by_code": geo_by_code,
        "geo_metadata": geo_metadata,
        "area_beds_rows": area_beds_rows,
        "pref_beds_rows": pref_beds_rows,
        "boundaries_metadata": boundaries_metadata,
    }


@pytest.fixture(scope="module")
def join_result(loaded):
    matched, area_only, geo_only = compute_join(loaded["area_by_code"], loaded["geo_by_code"])
    return matched, area_only, geo_only


# --- 入力の行数/フィーチャ数(前提の確認) ------------------------------------


def test_input_counts(loaded):
    assert len(loaded["area_rows"]) == 339
    assert len(loaded["geo_by_code"]) == 335
    assert len(loaded["area_beds_rows"]) == 18645
    assert len(loaded["pref_beds_rows"]) == 2640


# --- コード突合: matched=331 / area_only=8 / geo_only=4 ---------------------


def test_join_counts_and_codes(join_result):
    matched, area_only, geo_only = join_result
    assert len(matched) == 331
    assert len(area_only) == 8
    assert len(geo_only) == 4
    assert set(area_only) == MIE_AREA_ONLY_CODES
    assert set(geo_only) == MIE_GEO_ONLY_CODES
    # area_geo_join.csv の総行数
    assert len(matched) + len(area_only) + len(geo_only) == 343


def test_area_only_is_all_mie(loaded, join_result):
    _, area_only, _ = join_result
    for code in area_only:
        assert loaded["area_by_code"][code]["pref_name"] == "三重県", code


def test_matched_names_are_all_identical(loaded, join_result):
    matched, _, _ = join_result
    area_by_code = loaded["area_by_code"]
    geo_by_code = loaded["geo_by_code"]
    mismatches = [
        code for code in matched if area_by_code[code]["area_name"] != geo_by_code[code]["A38b_004"]
    ]
    assert mismatches == []


def test_mie_old_to_new_matches_join_result(join_result):
    """`MIE_OLD_TO_NEW`(旧4圏域→新8区域の対応表)が実際の突合結果と一致すること。"""
    _, area_only, geo_only = join_result
    assert set(MIE_OLD_TO_NEW) == set(geo_only) == MIE_GEO_ONLY_CODES
    mapped_new = {code for codes in MIE_OLD_TO_NEW.values() for code in codes}
    assert mapped_new == set(area_only) == MIE_AREA_ONLY_CODES


def test_mie_old_to_new_is_derived_from_reference_csv():
    """`MIE_OLD_TO_NEW`(モジュール読み込み時に確定)が、`data/reference/`の
    検証済み対応表を都度読み直しても同じ値になること(ハードコードされていないことの確認)。
    """
    assert load_mie_old_to_new() == MIE_OLD_TO_NEW
    assert MIE_OLD_TO_NEW == {
        "2401": ["2405", "2406", "2407"],
        "2402": ["2408", "2409"],
        "2403": ["2410", "2411"],
        "2404": ["2412"],
    }


def test_load_mie_old_to_new_detects_inconsistent_csv(tmp_path):
    """同じarea_codeの行が異なるparent_iryoken2_codeを持つCSVを渡すと中断すること
    (`data/reference/mie_area_municipalities.csv` が壊れた場合の検知)。
    """
    bad_csv = tmp_path / "mie_area_municipalities.csv"
    bad_csv.write_text(
        "area_code,area_name,muni_code,muni_name,parent_iryoken2_code,parent_iryoken2_name\n"
        "2405,桑員,24205,桑名市,2401,北勢\n"
        "2405,桑員,24214,いなべ市,9999,別の圏域\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(ValueError):
        load_mie_old_to_new(bad_csv)


# --- 独立した裏付け: 流出入率XXXの区域集合 == area_only の区域集合 -----------


def test_xxx_area_codes_equal_area_only(loaded, join_result):
    _, area_only, _ = join_result
    xxx_codes = compute_xxx_area_codes(loaded["area_rows"])
    assert xxx_codes == set(area_only) == MIE_AREA_ONLY_CODES


# --- 集計整合検証: 2585キー中230件が2024年に集中 -----------------------------


@pytest.fixture(scope="module")
def agg_result(loaded):
    area_agg = aggregate_area_beds_by_pref(loaded["area_beds_rows"])
    pref_lookup = prefecture_beds_lookup(loaded["pref_beds_rows"])
    return compare_aggregates(area_agg, pref_lookup)


def test_aggregate_comparison_key_count(agg_result):
    assert len(agg_result["common_keys"]) == 2585
    assert agg_result["only_in_area"] == set()
    assert agg_result["only_in_pref"] == set()


def test_aggregate_mismatches_all_in_2024(agg_result):
    mismatches = agg_result["mismatches"]
    assert len(mismatches) == 230
    years = {key[3] for key, _, _ in mismatches}
    assert years == {2024}
    series_set = {key[2] for key, _, _ in mismatches}
    assert series_set == {"実績"}


def test_non_2024_keys_fully_match(agg_result):
    common_keys = agg_result["common_keys"]
    mismatched_keys = {key for key, _, _ in agg_result["mismatches"]}
    non_2024_keys = {k for k in common_keys if k[3] != 2024}
    assert len(non_2024_keys) == 2350
    assert non_2024_keys.isdisjoint(mismatched_keys)


# --- area_geo_join.csv の行内容(空欄フィールドの規則) -----------------------


def test_build_join_rows_field_emptiness(loaded, join_result):
    matched, area_only, geo_only = join_result
    rows = build_join_rows(loaded["area_by_code"], loaded["geo_by_code"], matched, area_only, geo_only)
    assert len(rows) == 343

    by_status = {"matched": [], "area_only": [], "geo_only": []}
    for row in rows:
        by_status[row["join_status"]].append(row)

    assert len(by_status["matched"]) == 331
    assert len(by_status["area_only"]) == 8
    assert len(by_status["geo_only"]) == 4

    for row in by_status["matched"]:
        assert row["area_code"] and row["area_name"] and row["pref_code"] and row["pref_name"]
        assert row["geo_code"] and row["geo_name"]
        assert row["note"] == ""

    for row in by_status["area_only"]:
        assert row["area_code"] and row["area_name"] and row["pref_code"] and row["pref_name"]
        assert row["geo_code"] == "" and row["geo_name"] == ""
        assert row["note"] != ""

    for row in by_status["geo_only"]:
        assert row["area_code"] == "" and row["area_name"] == "" and row["pref_name"] == ""
        assert row["pref_code"] == row["geo_code"][:2]
        assert row["geo_code"] and row["geo_name"]
        assert row["note"] != ""


# --- レイアウト崩れ検知: 対応表がずれた場合に例外になるか -----------------------


def test_mie_mapping_mismatch_is_detected(monkeypatch):
    import tools.verify_area_join as mod

    with monkeypatch.context() as m:
        m.setattr(mod, "MIE_OLD_TO_NEW", {"2401": ["2405", "2406", "2407", "9999"]})
        with pytest.raises(ValueError):
            mod._verify_mie_mapping_matches_join(
                ["2405", "2406", "2407", "2408", "2409", "2410", "2411", "2412"],
                ["2401", "2402", "2403", "2404"],
            )


# --- 再現性(バイト一致) -----------------------------------------------------


def test_reproducibility_byte_identical(tmp_path):
    paths = build_and_write(tmp_path, tmp_path)
    assert paths.keys() == {"csv", "meta", "doc"}

    committed_csv = PROCESSED_DIR / "area_geo_join.csv"
    committed_doc = DOC_DIR / "JOIN_VERIFICATION.md"
    assert committed_csv.exists(), (
        f"{committed_csv} が存在しません(先に `python tools/verify_area_join.py` を実行してください)"
    )
    assert committed_doc.exists(), (
        f"{committed_doc} が存在しません(先に `python tools/verify_area_join.py` を実行してください)"
    )

    assert paths["csv"].read_bytes() == committed_csv.read_bytes(), (
        "area_geo_join.csv がコミット済みデータとバイト一致しません"
    )
    assert paths["doc"].read_bytes() == committed_doc.read_bytes(), (
        "doc/JOIN_VERIFICATION.md がコミット済みデータとバイト一致しません"
    )

    new_meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
    old_meta = json.loads((PROCESSED_DIR / "area_geo_join.csv.meta.json").read_text(encoding="utf-8"))
    # processing.date は実行日ごとに変わるため、比較対象から除外する
    new_meta["processing"]["date"] = None
    old_meta["processing"]["date"] = None
    assert new_meta == old_meta, "area_geo_join.csv.meta.json の内容(processing.dateを除く)が一致しません"


def test_report_markdown_has_no_date_stamp():
    """再生成のたびに差分が出ないよう、生成日時を埋め込んでいないことを確認する。"""
    content = OUT_DOC.read_text(encoding="utf-8")
    assert "生成日時" not in content
    assert "実行日" not in content


def test_report_markdown_is_lf_only():
    data = OUT_DOC.read_bytes()
    assert b"\r\n" not in data
    assert not data.startswith(b"\xef\xbb\xbf")


def test_report_markdown_mie_section_is_verified_not_estimated():
    """三重県の旧4圏域→新8区域の対応は、三重県公式資料により検証済みの事実として
    記述されていること(かつては「未検証の推定」だった、M2チャンクCの前工程)。
    """
    content = OUT_DOC.read_text(encoding="utf-8")
    assert "未検証の推定" not in content
    assert "とみられる" not in content
    assert "mie/001092203.pdf" in content
    assert "真の残存リスク" in content
    assert "data/reference/mie_area_municipalities.csv" in content


def test_report_markdown_reflects_completed_boundary_synthesis():
    """境界合成(`data/processed/area_boundaries_R7.geojson`、M2チャンクC2)が
    完了した後の状態を正しく反映していること。かつては「## 5. 可視化への影響と
    対応方針」が未完了の予定(境界合成は次工程/三重県8区域は境界がない)として
    書かれていたが、実際には339区域すべての境界が生成済みである。
    """
    content = OUT_DOC.read_text(encoding="utf-8")
    assert "次工程" not in content
    assert "境界合成が必要" not in content
    assert "境界がないため" not in content
    assert "area_boundaries_R7.geojson" in content
    assert "boundary_source" in content
    assert "339区域" in content or "339構想区域" in content


def test_report_markdown_mentions_mie_boundary_is_derived_not_published():
    """三重県8区域の境界が国土数値情報の公表物そのものではなく、市区町村
    ポリゴンからの合成派生物であることが、境界合成完了後もレポートから
    読み取れること(国土数値情報が新区域を測量・公表したかのような誤読を防ぐ)。
    """
    content = OUT_DOC.read_text(encoding="utf-8")
    assert "合成した派生物" in content or "合成派生物" in content
    assert "公表しているものではなく" in content


def test_report_markdown_mentions_area_consistency_check():
    """三重県新8区域と旧4圏域の面積整合(0.002%)が、実測値としてレポートに
    埋め込まれていること(ハードコードではなく area_boundaries_R7.geojson の
    metadata から読んだ値であることの間接確認)。
    """
    content = OUT_DOC.read_text(encoding="utf-8")
    assert "5782.81" in content
    assert "5782.68" in content
    assert "0.002%" in content


def test_load_area_boundaries_metadata_has_expected_shape():
    meta = load_area_boundaries_metadata()
    assert meta["feature_count"] == 339
    assert meta["verification"]["mie_area_check_km2"]["diff_pct"] < 1.0


def test_load_area_boundaries_metadata_raises_clear_error_when_missing(tmp_path):
    """area_boundaries_R7.geojson が存在しない場合に、原因不明なトレースバックの
    代わりに再生成手順を示す分かりやすいメッセージ付きで例外になること。
    """
    missing_path = tmp_path / "area_boundaries_R7.geojson"
    with pytest.raises(FileNotFoundError) as exc_info:
        load_area_boundaries_metadata(missing_path)
    assert "build_area_boundaries.py" in str(exc_info.value)


def test_area_boundaries_geojson_exists():
    assert AREA_BOUNDARIES_GEOJSON.exists(), (
        f"{AREA_BOUNDARIES_GEOJSON} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_area_boundaries.py` を実行してください)"
    )


def test_build_report_markdown_is_deterministic(loaded, join_result):
    """`build_report_markdown` を2回呼んでも同じ文字列になること(内部で日時等を使っていないか)。"""
    matched, area_only, geo_only = join_result
    join_rows = build_join_rows(loaded["area_by_code"], loaded["geo_by_code"], matched, area_only, geo_only)
    xxx_codes = compute_xxx_area_codes(loaded["area_rows"])
    area_agg = aggregate_area_beds_by_pref(loaded["area_beds_rows"])
    pref_lookup = prefecture_beds_lookup(loaded["pref_beds_rows"])
    agg = compare_aggregates(area_agg, pref_lookup)

    area_beds_meta = json.loads((PROCESSED_DIR / "area_beds.csv.meta.json").read_text(encoding="utf-8"))
    pref_beds_meta = json.loads(
        (PROCESSED_DIR / "prefecture_beds.csv.meta.json").read_text(encoding="utf-8")
    )
    mie_meta = json.loads(MIE_AREA_MUNI_META.read_text(encoding="utf-8"))

    kwargs = dict(
        area_meta=loaded["area_meta"],
        area_beds_meta=area_beds_meta,
        pref_beds_meta=pref_beds_meta,
        geo_metadata=loaded["geo_metadata"],
        area_rows=loaded["area_rows"],
        area_beds_rows=loaded["area_beds_rows"],
        pref_beds_rows=loaded["pref_beds_rows"],
        geo_by_code=loaded["geo_by_code"],
        area_by_code=loaded["area_by_code"],
        matched=matched,
        area_only=area_only,
        geo_only=geo_only,
        join_rows=join_rows,
        xxx_codes=xxx_codes,
        agg_result=agg,
        mie_meta=mie_meta,
        boundaries_metadata=loaded["boundaries_metadata"],
    )
    md1 = build_report_markdown(**kwargs)
    md2 = build_report_markdown(**kwargs)
    assert md1 == md2
