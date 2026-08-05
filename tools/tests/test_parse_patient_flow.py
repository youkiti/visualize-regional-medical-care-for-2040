# -*- coding: utf-8 -*-
"""tools/parse_patient_flow.py のテスト。

`test_parse_demand_forecast.py` の3層構成に倣う: 実データ(R7/001723366.xlsx)の
前提確認はmodule scopeのfixtureで1回だけパースし(全走査は40〜50秒かかる)、
構造・スポット値・センチネル('#VALUE!')・area_basic.csvとの整合・レイアウト
崩れ検知(LayoutMismatchError)・再現性(バイト一致)を検証する。

⚠ レイアウト崩れ検知テストは(demand_forecastと同様に)各テストごとに
`load_workbook()` を新規に呼ぶ(module fixtureのworkbookを直接改変すると、
以降のテストが汚染された状態を見ることになるため)。1回30〜50秒かかるため、
テストファイル全体の実行には数分かかる。
"""
import json

import pytest

from tools.lib.provenance import REPO_ROOT, recorded_hash, verify_source
from tools.parse_patient_flow import (
    BLOCK_SIZE,
    FIRST_ROW,
    KNOWN_ISSUES,
    LayoutMismatchError,
    NUM_BLOCKS,
    OFFSET_CATEGORY_HEADER,
    OFFSET_OVERALL,
    OFFSET_SUBHEADER,
    SHEET_INFLOW,
    SHEET_OUTFLOW,
    VALUE_STATUS_ERROR,
    VALUE_STATUS_OBSERVED,
    _load_area_basic_reference,
    build_and_write,
    known_issues_for,
    load_workbook,
    parse_sheet,
)

PROCESSED_DIR = REPO_ROOT / "data" / "processed"


@pytest.fixture(scope="module")
def workbook():
    wb, source_sha256 = load_workbook()
    return {"wb": wb, "source_sha256": source_sha256}


@pytest.fixture(scope="module")
def area_basic_ref():
    return _load_area_basic_reference()


@pytest.fixture(scope="module")
def inflow_result(workbook, area_basic_ref):
    ws = workbook["wb"][SHEET_INFLOW]
    return parse_sheet(ws, direction=SHEET_INFLOW, area_basic_ref=area_basic_ref)


@pytest.fixture(scope="module")
def outflow_result(workbook, area_basic_ref):
    ws = workbook["wb"][SHEET_OUTFLOW]
    return parse_sheet(ws, direction=SHEET_OUTFLOW, area_basic_ref=area_basic_ref)


# --- 構造(行数・ブロック数・区域コードの形式) --------------------------------


def test_sheet_names(workbook):
    assert workbook["wb"].sheetnames == [SHEET_INFLOW, SHEET_OUTFLOW]


def test_block_count_is_339(inflow_result, outflow_result):
    assert len(inflow_result.block_summaries) == NUM_BLOCKS == 339
    assert len(outflow_result.block_summaries) == NUM_BLOCKS == 339


def test_flow_row_count(inflow_result, outflow_result):
    # 流入率5,203行 + 流出率5,205行 = patient_flow.csv 10,408行
    assert len(inflow_result.flow_rows) == 5203
    assert len(outflow_result.flow_rows) == 5205
    assert len(inflow_result.flow_rows) + len(outflow_result.flow_rows) == 10408


def test_total_row_count(inflow_result, outflow_result):
    # 339区域 × 2方向 = patient_flow_total.csv 678行
    assert len(inflow_result.total_rows) == 339
    assert len(outflow_result.total_rows) == 339
    assert len(inflow_result.total_rows) + len(outflow_result.total_rows) == 678


def test_area_code_format_and_uniqueness(inflow_result):
    codes = [row[0] for row in inflow_result.block_summaries]
    assert len(codes) == len(set(codes)) == 339
    for code in codes:
        assert isinstance(code, str)
        assert len(code) == 4
        assert code.isdigit()


# --- スポット値(原典との整合。実測値をそのまま使用) ---------------------------


def test_spot_values_0101_inflow_acute_phase(inflow_result):
    rows = sorted(
        (r for r in inflow_result.flow_rows if r["area_code"] == "0101" and r["phase"] == "高度急性期+急性期"),
        key=lambda r: r["rank"],
    )
    assert len(rows) == 4
    assert rows[0]["partner_area_code"] == "0101"
    assert rows[0]["rate"] == 0.9062844376965826
    assert rows[1]["partner_area_code"] == "0102"
    assert rows[1]["rate"] == 0.04220060329093418
    assert rows[2]["partner_area_code"] == "0103"
    assert rows[2]["rate"] == 0.03450749414206655
    assert rows[3]["partner_area_code"] == "0104"
    assert rows[3]["rate"] == 0.0045019022300602195


def test_spot_overall_rate_0101(inflow_result, outflow_result):
    in_total = next(r for r in inflow_result.total_rows if r["area_code"] == "0101")
    out_total = next(r for r in outflow_result.total_rows if r["area_code"] == "0101")
    assert in_total["overall_rate"] == 0.09371556230341738
    assert out_total["overall_rate"] == 0.033216957073430975


def test_spot_outflow_acute_self_rate_0101(outflow_result):
    row = next(
        r
        for r in outflow_result.flow_rows
        if r["area_code"] == "0101" and r["phase"] == "高度急性期+急性期" and r["partner_area_code"] == "0101"
    )
    assert row["rate"] == 0.966783042926569


def test_spot_inflow_other_phase_self_rates_0101(inflow_result):
    row_bundled = next(
        r
        for r in inflow_result.flow_rows
        if r["area_code"] == "0101" and r["phase"] == "包括期" and r["partner_area_code"] == "0101"
    )
    row_chronic = next(
        r
        for r in inflow_result.flow_rows
        if r["area_code"] == "0101" and r["phase"] == "慢性期" and r["partner_area_code"] == "0101"
    )
    assert row_bundled["rate"] == 0.9351719625916906
    assert row_chronic["rate"] == 0.9488514140062714


# --- '#VALUE!'センチネル(value_status='error') -------------------------------


def test_value_error_rows(inflow_result, outflow_result):
    all_rows = inflow_result.flow_rows + outflow_result.flow_rows
    error_rows = [r for r in all_rows if r["value_status"] == VALUE_STATUS_ERROR]
    assert len(error_rows) == 2
    keys = {(r["direction"], r["phase"], r["area_code"]) for r in error_rows}
    assert keys == {("流出率", "慢性期", "1313"), ("流出率", "慢性期", "4207")}
    for r in error_rows:
        assert r["rate"] is None
        assert r["rate_source_value"] == "#VALUE!"
        assert r["partner_pref_code"] is None
        assert r["partner_pref_name"] is None
        assert r["partner_area_code"] is None
        assert r["partner_area_name"] is None
        assert r["rank"] == 1


def test_no_value_error_rows_in_inflow(inflow_result):
    assert not any(r["value_status"] == VALUE_STATUS_ERROR for r in inflow_result.flow_rows)


def test_inflow_chronic_zero_row_areas(inflow_result):
    """流入率シートの慢性期の表が0行になる区域が実測どおり6件ちょうどであること。"""
    codes_with_chronic_rows = {r["area_code"] for r in inflow_result.flow_rows if r["phase"] == "慢性期"}
    all_codes = {row[0] for row in inflow_result.block_summaries}
    zero_row_codes = all_codes - codes_with_chronic_rows
    assert zero_row_codes == {"0502", "0508", "1313", "1704", "4207", "4209"}


# --- 全グループで率が降順・相手区域コードに重複なし --------------------------


def test_rates_descending_and_partners_unique_within_groups(inflow_result, outflow_result):
    for result in (inflow_result, outflow_result):
        groups = {}
        for r in result.flow_rows:
            if r["value_status"] != VALUE_STATUS_OBSERVED:
                continue
            groups.setdefault((r["area_code"], r["phase"]), []).append(r)
        for (area_code, phase), rows in groups.items():
            rows_sorted = sorted(rows, key=lambda r: r["rank"])
            rates = [r["rate"] for r in rows_sorted]
            assert rates == sorted(rates, reverse=True), (result.direction, area_code, phase)
            partner_codes = [r["partner_area_code"] for r in rows_sorted]
            assert len(partner_codes) == len(set(partner_codes)), (result.direction, area_code, phase)
            assert [r["rank"] for r in rows_sorted] == list(range(1, len(rows_sorted) + 1))


# --- area_basic.csv との整合 -------------------------------------------------


def test_area_code_set_matches_area_basic(inflow_result, outflow_result, area_basic_ref):
    for result in (inflow_result, outflow_result):
        codes = {row[0] for row in result.block_summaries}
        assert codes == set(area_basic_ref.keys())


def test_partner_names_match_area_basic(inflow_result, outflow_result, area_basic_ref):
    for result in (inflow_result, outflow_result):
        for r in result.flow_rows:
            if r["value_status"] != VALUE_STATUS_OBSERVED:
                continue
            ref = area_basic_ref[r["partner_area_code"]]
            assert r["partner_pref_name"] == ref["pref_name"], (result.direction, r)
            assert r["partner_area_name"] == ref["area_name"], (result.direction, r)


def test_block_summary_matches_area_basic(inflow_result, area_basic_ref):
    for area_code, pref_code, pref_name, area_name, population_source_value, area_source_value in inflow_result.block_summaries:
        ref = area_basic_ref[area_code]
        assert pref_code == ref["pref_code"]
        assert pref_name == ref["pref_name"]
        assert area_name == ref["area_name"]
        assert population_source_value == ref["population_2020_source_value"]
        assert round(float(area_source_value), 2) == ref["area_2020_km2"]


# --- レイアウト崩れ検知(LayoutMismatchError) -----------------------------
#
# `wb.save()` は一切呼ばない(R7/ 配下は編集禁止のため)メモリ上の改変のみ。
# module scopeのworkbookフィクスチャは他のテストが再利用するため、ここでは
# `load_workbook()` で新規に読み込む。1回30〜50秒かかるため、4ケースを
# 1つのテスト関数にまとめてロードは1回だけにする(各ケースごとに新規ロード
# すると合計2〜3分かかってしまう)。各ケースは「改変 → pytest.raises →
# 元の値へ復元」の順で行い、次のケースが前のケースの改変を引きずらないように
# する。最後に1回だけ `verify_source()` で生データ非改変を確認する。


def test_layout_drift_is_detected_for_key_validations():
    """代表的な4つのレイアウト崩れがLayoutMismatchErrorとして検知されるか。

    ケース1〜3は既存の検証(サブヘッダー・区分ヘッダー・ラベル)、ケース4は
    検証14(「全体のX率」が「高度急性期+急性期」の自区域率の余事象と厳密一致
    すること)が実際に働くかを確認する。検証14はKNOWN_ISSUESの
    flow_overall_rate_equals_acute_phase_complementを守る仕組みそのものなので、
    エラーメッセージにそのidが含まれることも確認する。
    """
    wb, _ = load_workbook()
    ws = wb[SHEET_INFLOW]
    ref = _load_area_basic_reference()

    # ケース1: サブヘッダー行の「構想区域コード」を書き換える
    # (`assert_repeated_header()`、全339ブロックの一致検証で検知されるはず)
    row = FIRST_ROW + BLOCK_SIZE + OFFSET_SUBHEADER  # ブロック1(2つ目の区域)のサブヘッダー行
    col = 2 + 2  # 「高度急性期+急性期」グループの「構想区域コード」列
    original = ws.cell(row=row, column=col).value
    assert original == "構想区域コード"
    ws.cell(row=row, column=col).value = "改変された見出し"
    with pytest.raises(LayoutMismatchError):
        parse_sheet(ws, direction=SHEET_INFLOW, area_basic_ref=ref)
    ws.cell(row=row, column=col).value = original

    # ケース2: 区分ヘッダー「包括期」を書き換える
    row = FIRST_ROW + OFFSET_CATEGORY_HEADER  # ブロック0(先頭区域)の区分ヘッダー行
    col = 10  # 「包括期」
    original = ws.cell(row=row, column=col).value
    assert original == "包括期"
    ws.cell(row=row, column=col).value = "改変された区分"
    with pytest.raises(LayoutMismatchError):
        parse_sheet(ws, direction=SHEET_INFLOW, area_basic_ref=ref)
    ws.cell(row=row, column=col).value = original

    # ケース3: 「全体の流入率」ラベルを書き換える
    row = FIRST_ROW + OFFSET_OVERALL  # ブロック0(先頭区域)の「全体の流入率」行
    col = 2
    original = ws.cell(row=row, column=col).value
    assert original == "全体の流入率"
    ws.cell(row=row, column=col).value = "改変されたラベル"
    with pytest.raises(LayoutMismatchError):
        parse_sheet(ws, direction=SHEET_INFLOW, area_basic_ref=ref)
    ws.cell(row=row, column=col).value = original

    # ケース4(新規): ブロック0の「全体の流入率」の値(D列)を書き換える。
    # 検証14がこれを「高度急性期+急性期」自区域率の余事象(1-rate)との
    # 不一致として検知し、known_issueのidをメッセージに含めて中断するはず。
    row = FIRST_ROW + OFFSET_OVERALL  # ブロック0(先頭区域)の「全体の流入率」行
    col = 4
    original = ws.cell(row=row, column=col).value
    assert original == 0.09371556230341738
    ws.cell(row=row, column=col).value = 0.5
    with pytest.raises(LayoutMismatchError, match="flow_overall_rate_equals_acute_phase_complement"):
        parse_sheet(ws, direction=SHEET_INFLOW, area_basic_ref=ref)
    ws.cell(row=row, column=col).value = original

    assert verify_source("R7/001723366.xlsx") == recorded_hash("R7/001723366.xlsx")


# --- 原典側の既知の欠陥(known_issues) ---------------------------------------

CSV_NAMES = [
    "patient_flow.csv",
    "patient_flow_total.csv",
]


def test_known_issues_have_the_required_shape():
    """KNOWN_ISSUESの各件がid/scope/summary/evidence/actionを持ち、scope.csvが
    実在の出力CSVを指すこと。今後ここへ足していくための形の固定。"""
    assert KNOWN_ISSUES
    ids = [issue["id"] for issue in KNOWN_ISSUES]
    assert len(ids) == len(set(ids)), f"idが重複している: {ids}"
    for issue in KNOWN_ISSUES:
        assert issue["scope"]["csv"] in CSV_NAMES, issue["id"]
        for key in ("id", "summary", "action"):
            assert isinstance(issue[key], str) and issue[key], (issue["id"], key)
        assert isinstance(issue["evidence"], list) and issue["evidence"], issue["id"]


def test_known_issues_for_routes_by_scope_csv():
    """known_issues_for()がscope.csvで振り分け、該当なしではNoneを返すこと
    (Noneのときmeta.jsonにknown_issuesキー自体を出さないため、空リストと
    区別されることが重要)。"""
    assert known_issues_for("存在しない.csv") is None
    routed = {name: known_issues_for(name) or [] for name in CSV_NAMES}
    assert sum(len(v) for v in routed.values()) == len(KNOWN_ISSUES)
    for name, issues in routed.items():
        for issue in issues:
            assert issue["scope"]["csv"] == name


def test_overall_rate_complement_issue_is_recorded():
    issue = next(i for i in KNOWN_ISSUES if i["id"] == "flow_overall_rate_equals_acute_phase_complement")
    assert issue["scope"]["csv"] == "patient_flow_total.csv"
    evidence = " ".join(issue["evidence"])
    assert "678" in evidence
    assert "0101" in evidence


def test_value_error_cells_issue_is_recorded():
    issue = next(i for i in KNOWN_ISSUES if i["id"] == "flow_outflow_chronic_value_error_cells")
    assert issue["scope"]["csv"] == "patient_flow.csv"
    assert set(issue["scope"]["area_codes"]) == {"1313", "4207"}
    assert issue["scope"]["direction"] == "流出率"
    assert issue["scope"]["phase"] == "慢性期"


# --- 再現性(バイト一致) -----------------------------------------------------


def test_reproducibility_byte_identical(tmp_path):
    paths = build_and_write(tmp_path)
    assert paths.keys() == {"flow", "total"}
    expected_sha256 = recorded_hash("R7/001723366.xlsx")

    for name in CSV_NAMES:
        committed_path = PROCESSED_DIR / name
        assert committed_path.exists(), (
            f"{committed_path} が存在しません"
            "(先に `python tools/parse_patient_flow.py` を実行してください)"
        )
        new_bytes = (tmp_path / name).read_bytes()
        old_bytes = committed_path.read_bytes()
        assert new_bytes == old_bytes, f"{name} がコミット済みデータとバイト一致しません"

        new_meta = json.loads((tmp_path / f"{name}.meta.json").read_text(encoding="utf-8"))
        old_meta = json.loads((PROCESSED_DIR / f"{name}.meta.json").read_text(encoding="utf-8"))

        assert new_meta["source"]["source_sha256"] == expected_sha256
        assert old_meta["source"]["source_sha256"] == expected_sha256

        # processing.date は実行日ごとに変わるため、比較対象から除外する
        new_meta["processing"]["date"] = None
        old_meta["processing"]["date"] = None
        assert new_meta == old_meta, f"{name}.meta.json の内容(processing.dateを除く)が一致しません"
