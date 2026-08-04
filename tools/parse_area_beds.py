# -*- coding: utf-8 -*-
"""厚労省「②構想区域の病床数等」(R7: 001723349.xlsx / R6: 別添４③)の帳票Excel
を tidy CSV へ変換する。

帳票のブロック構造(3行目開始・1ブロック15行)は都道府県版
(`tools/parse_prefecture_beds.py`、001722915.xlsx)と完全に同一だが、
以下の点が異なる:

  - ブロック数は339(構想区域ごと)。A列のブロック番号は1始まりの連番
    1..339(都道府県版は全国=0始まり)
  - 各ブロックの内訳(top=ブロック先頭行)にD/F/H列で「都道府県」と
    「構想区域」の2階層のコード・名称を持つ
  - R列(18)に推計流出/流入患者割合を持つ(top+2/top+4がラベル行、
    top+3/top+5が値行)。都道府県版にはこれに相当する項目がない

処理内容:
  1. `verify_source()` で元データのSHA-256を `SHA256SUMS` と照合(改変検知)
  2. openpyxl(`data_only=True`)でシートを開き、3行目から15行ずつ・339ブロック
     を走査
  3. サブヘッダー行(各ブロック先頭+8行目)の文字列("2015実績"等)から
     実績/見込量/必要数の列を解決する(都道府県版と同様、公表年度により
     列位置が異なるためハードコードしない。下記「R6との列ずれ」参照)
  4. 全339ブロックのサブヘッダー行が先頭ブロックと完全一致することを検証し、
     不一致ならレイアウト変更とみなして例外で中断する(取りこぼし防止)
  5. R列(18)のラベル("（推計流出患者割合）"/"（推計流入患者割合）")を
     値を読む前に検証する(R列は位置でハードコードするため、ラベルが
     動いたら必ず失敗させる)
  6. 3つの tidy CSV + 由来メタデータ(`<csv名>.meta.json`)を `data/processed/`
     に出力する
       - area_beds.csv: 病床数(実績/見込量/必要数 × 5機能 × 年)
       - area_bed_report_rate.csv: 病床機能報告の報告率
       - area_basic.csv: 基礎情報(2020人口・面積・推計流出入患者割合)

⚠ R6との列ずれ: R6(別添４③)は実績年が1年少なく(2015, 2018〜2024)、その
分だけ見込量/必要数の列がR7よりも1列前にずれる。見込量の対象年も異なる
(R6=2025年見込量 / R7=2026年見込量)。そのため列は位置ではなく、サブヘッダー
行の文字列から都度解決する(`tools/lib/block_report.py` の
`resolve_columns` / `classify_bed_column`)。

⚠ R6は現状 `parse_sheet()` では読めない: R6は帳票構造そのものがR7と異なり、
R列(18)に「推計流出患者割合」「推計流入患者割合」を別々に持つR7に対し、
R6は「（一般病床患者流出入）」という単一の値をQ列(17)の別の行位置に持つ
(別概念の可能性が高く、単純な列ずれではない)。加えて原典に実績セルの欠測が
1件あり(ブロック2「南檜山」高度急性期の2015実績、行28・列6が空)、病床数
セル走査で `expect_int` が例外を送出する。`SOURCES` に R6 を定義している
のは、列ずれ追随のヘッダーレベル回帰テスト(`test_r6_r7_year_layout_regression`)
から `load_sheet("R6")` を使うためであり、`parse_sheet()` にR6を通す用途では
ない。

⚠ 既知のデータ品質問題(値は勝手に直さず原典どおり出力し、meta.jsonの
`known_issues` に記録する):
  1. area_beds.csv の「2024実績」列が「2025実績」列と全1695セル完全同一
     (都道府県版は両者が別値であり、上流の複製ミスとみられる)
  2. area_basic.csv の推計流出/流入患者割合が、三重県の8区域(2405〜2412)
     でのみ文字列 'XXX'(令和2年度の二次医療圏4圏域から8構想区域へ細分化
     されており、算出できていないため)

必要環境: Python 3.11+, openpyxl

使い方:
    python tools/parse_area_beds.py [--source R7]
"""
import argparse
import datetime
import sys
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import openpyxl

from tools.lib.block_report import (
    assert_repeated_header,
    classify_bed_column,
    iter_fixed_blocks,
    resolve_columns,
)
from tools.lib.codes import normalize_area_code, normalize_pref_code
from tools.lib.layout import LayoutMismatchError, expect, expect_int
from tools.lib.provenance import REPO_ROOT, verify_source, write_csv_with_meta

# 各公表年度の元データ設定。CLI(--source)では現時点で R7 のみ受け付ける
# (R6 出力は未対応、パース自体はテストから `load_sheet("R6")` で直接
# 利用できる)。都道府県パーサ(parse_prefecture_beds.py)と同じ流儀。
SOURCES = {
    "R7": {
        "name": "②構想区域の病床数等（別添４）",
        "path_in_repo": "R7/001723349.xlsx",
        "sheet_name": "構想区域別必要量との比較",
        "download_url": "https://www.mhlw.go.jp/content/10800000/001723349.xlsx",
        "fiscal_year": "令和7年度（2025年度）",
        "acquired_date": "2026-08-04",
    },
    "R6": {
        "name": "別添４③（構想区域の病床数等の状況）",
        "path_in_repo": "R6/別添４③（構想区域の病床数等の状況）.xlsx",
        "sheet_name": "構想区域別必要量との比較",
        # R6出力は今回未対応のためmeta.jsonには使わない(`parse_sheet()` に
        # R6を通すとブロック2「南檜山」の実績セル欠測で例外になる。上記
        # docstring「⚠ R6は現状 parse_sheet() では読めない」参照)。
        # ここにR6を定義しているのは列ずれ追随のヘッダーレベル回帰テスト
        # (test_r6_r7_year_layout_regression)が `load_sheet("R6")` を使うため。
        "download_url": None,
        "fiscal_year": "令和6年度",
        "acquired_date": None,
    },
}

SOURCE_PAGE_URL = "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000080850_00014.html"
LICENSE_NOTE = (
    "厚生労働省ホームページ利用規約（政府標準利用規約準拠） "
    "https://www.mhlw.go.jp/chosakuken/index.html"
)
CAVEAT = (
    "病床機能報告の集計結果(実績)と将来の病床数の必要量(必要数)は計算方法が"
    "異なることから、単純に比較するのではなく、詳細な分析や検討を行った上で"
    "地域医療構想調整会議で協議を行うことが重要(原典C2注記より)。可視化で"
    "これらを併記する際は、この点を注記として必ず表示すること。また年度ごと"
    "に報告率が異なることにも留意する。"
)

BLOCK_TOP0 = 3   # 最初のブロック(block.index=0, 構想区域コード101)の先頭行
BLOCK_SIZE = 15  # 1ブロックあたりの行数
NUM_BLOCKS = 339  # 構想区域数

BED_FUNCTIONS = ["合計", "高度急性期", "急性期", "回復期", "慢性期"]

OUTFLOW_LABEL = "（推計流出患者割合）"
INFLOW_LABEL = "（推計流入患者割合）"

PREF_CODE_DESC = "都道府県コード(ゼロ埋め2桁の文字列、01=北海道…47=沖縄県、原典の都道府県コード順)"
PREF_NAME_DESC = "都道府県名"
AREA_CODE_DESC = (
    "構想区域(二次医療圏)コード(ゼロ埋め4桁の文字列)。上2桁が都道府県コードと一致する"
)
AREA_NAME_DESC = "構想区域名"
PUBLISHED_FY_DESC = (
    "公表年度を表す識別子。'R7'=令和7年度公表分。将来R6等の行を追加する際のキー"
)

FIELDS_BEDS = {
    "published_fy": PUBLISHED_FY_DESC,
    "pref_code": PREF_CODE_DESC,
    "pref_name": PREF_NAME_DESC,
    "area_code": AREA_CODE_DESC,
    "area_name": AREA_NAME_DESC,
    "bed_function": "病床機能区分(合計/高度急性期/急性期/回復期/慢性期)。合計は他4区分の和",
    "series": "系列。実績=病床機能報告の報告値、見込量=直近年からの見込み、必要数=2025年の必要病床数",
    "year": "対象年(西暦)。実績・見込量・必要数それぞれの対象年は公表年度により異なる(下記caveat参照)",
    "beds": "病床数(床)",
}
FIELDS_REPORT_RATE = {
    "published_fy": PUBLISHED_FY_DESC,
    "pref_code": PREF_CODE_DESC,
    "pref_name": PREF_NAME_DESC,
    "area_code": AREA_CODE_DESC,
    "area_name": AREA_NAME_DESC,
    "year": "報告率の対象年(実績年のみ)",
    "report_rate": "病床機能報告の報告率(原典値をそのまま。丸めていない0〜1の割合)",
}
FIELDS_BASIC = {
    "published_fy": PUBLISHED_FY_DESC,
    "pref_code": PREF_CODE_DESC,
    "pref_name": PREF_NAME_DESC,
    "area_code": AREA_CODE_DESC,
    "area_name": AREA_NAME_DESC,
    "population_2020": "2020年国勢調査人口(人単位の整数)。原典の万人値を10000倍し四捨五入",
    "population_2020_source_value": "原典の人口値(万人単位、丸めなし)",
    "population_2020_source_unit": "population_2020_source_value の単位(万人)",
    "area_2020_km2": "2020年面積(km2)。原典の浮動小数点誤差を除くため小数2桁に丸め",
    "outflow_rate": (
        "推計流出患者割合(0〜1)。原典が数値の場合のみ値を持つ。三重県の8区域では"
        "原典が'XXX'のため空(outflow_rate_source_value参照)"
    ),
    "outflow_rate_source_value": "推計流出患者割合の原典値(数値または'XXX'をそのまま)",
    "inflow_rate": (
        "推計流入患者割合(0〜1)。原典が数値の場合のみ値を持つ。三重県の8区域では"
        "原典が'XXX'のため空(inflow_rate_source_value参照)"
    ),
    "inflow_rate_source_value": "推計流入患者割合の原典値(数値または'XXX'をそのまま)",
}

STEPS_COMMON = [
    "openpyxl(data_only=True)でシートを開き、3行目から15行ずつの339ブロック(構想区域ごと)を走査",
    "サブヘッダー行(実績/見込量/必要数の列見出し)の文字列から列を解決(公表年度により列位置が異なるためハードコードしない)",
    "全339ブロックのサブヘッダー行が先頭ブロックと完全一致することを検証(不一致ならレイアウト変更とみなし中断)",
]

KNOWN_ISSUES = [
    {
        "id": "area_beds_2024_actual_duplicated_as_2025",
        "scope": {"csv": "area_beds.csv", "series": "実績", "year": 2024},
        "summary": (
            "構想区域別の「2024実績」列が「2025実績」列と全セルで完全に同一な値になっている"
            "(原典のR7/001723349.xlsxそのものの問題)"
        ),
        "evidence": [
            "2024実績列と2025実績列が339区域×5機能=1695セル全てで一致",
            "構想区域の実績を都道府県コードで集計し都道府県版(001722915.xlsx)の"
            "2024年実績と突合すると、2585キー(47都道府県×5機能×11系列相当)中"
            "230キーが2024年に集中して不一致になる",
        ],
        "action": (
            "値は原典どおり出力している(勝手に補正しない)。可視化では構想区域"
            "レベルの2024年実績を用いないこと(2025年実績または都道府県レベルの"
            "2024年実績を使うこと)"
        ),
    },
    {
        "id": "area_basic_outflow_inflow_rate_xxx_mie",
        "scope": {
            "csv": "area_basic.csv",
            "area_codes": ["2405", "2406", "2407", "2408", "2409", "2410", "2411", "2412"],
        },
        "summary": (
            "三重県の8構想区域(2405〜2412)のみ、推計流出患者割合・推計流入患者割合が"
            "原典で文字列'XXX'(未算出)になっている"
        ),
        "evidence": [
            "他331区域は0〜1の数値だが、三重県の8区域のみ'XXX'",
            "三重県は令和2年度時点の二次医療圏4圏域から令和7年度の構想区域では"
            "8区域へ細分化されており、細分化後の区域単位での流出入率が算出されていない",
        ],
        "action": (
            "outflow_rate/inflow_rateは空(欠測)とし、原典値は"
            "outflow_rate_source_value/inflow_rate_source_valueに'XXX'のまま保持している"
        ),
    },
]


@dataclass
class ParseResult:
    published_fy: str
    title: str
    notes: list
    beds_rows: list = field(default_factory=list)
    report_rate_rows: list = field(default_factory=list)
    basic_rows: list = field(default_factory=list)


def _convert_man_to_person(value_man) -> int:
    """人口(万人)を人単位の整数へ変換する(万人 -> 人、四捨五入)。

    検証の意図は「原典の万人値が本当に(小数4桁までの)人単位の整数か」の
    確認であり、`round()` の性質上ほぼ必ず真になってしまう `>= 0.5` という
    閾値では実質的に検証にならない。許容誤差は `1e-6` とする。
    """
    scaled = float(value_man) * 10000
    person = round(scaled)
    if abs(scaled - person) >= 1e-6:
        raise ValueError(f"人口換算の丸め誤差が大きすぎます: {value_man} -> {scaled}")
    return person


def _split_rate(value):
    """推計流出/流入患者割合の原典セル値を (数値 or None, 原典値) に分解する。

    原典が数値(0〜1)ならその値をそのまま採用する。三重県の8区域のように
    非数値(文字列'XXX')の場合は数値側をNoneにし、原典値はそのまま保持する
    (CLAUDE.mdの流儀: 値を勝手に補正・欠落させず、原典値を併記する)。
    """
    if isinstance(value, bool):
        raise LayoutMismatchError(f"推計流出/流入患者割合セルの値が不正です: {value!r}")
    if isinstance(value, (int, float)):
        if not (0 <= value <= 1):
            raise LayoutMismatchError(
                f"推計流出/流入患者割合セルの値が0〜1の範囲外です: {value!r}"
            )
        return value, value
    return None, value


def parse_sheet(ws, published_fy: str) -> ParseResult:
    """帳票シートを339ブロック走査し、tidy行を組み立てる。

    `ws` は openpyxl の Worksheet(`data_only=True` で開いたもの)。
    """
    title = ws["C1"].value
    c2 = ws["C2"].value
    notes = c2.split("\n") if c2 else []

    max_col = ws.max_column
    # A列(ブロック番号)と最終列(ブロックごとの通し番号ラベル)はブロックにより
    # 値が変わって当然のため、サブヘッダー比較の対象範囲から除外する。
    header_col_start = 2
    header_col_end = max_col - 1
    result = ParseResult(published_fy=published_fy, title=title, notes=notes)

    # 構想区域コードは1始まりの連番1..339。`assert_repeated_header` で
    # 複数回走査するため、ジェネレータのままではなくリスト化しておく。
    blocks = list(
        iter_fixed_blocks(
            ws,
            first_row=BLOCK_TOP0,
            block_size=BLOCK_SIZE,
            count=NUM_BLOCKS,
            first_number=1,
        )
    )

    reference_header = assert_repeated_header(
        ws, blocks, row_offset=8, col_start=header_col_start, col_end=header_col_end
    )
    col_map = resolve_columns(
        reference_header, col_start=header_col_start, classify=classify_bed_column
    )

    seen_area_codes = set()
    pref_name_by_code = {}

    for block in blocks:
        top = block.top_row

        pref_label_row = top + 2
        expect(
            ws.cell(row=pref_label_row, column=4).value,
            "都道府県",
            f"ブロック{block.index}: 都道府県ラベル行(D列)",
        )
        pref_code_num = ws.cell(row=pref_label_row, column=6).value
        pref_name = ws.cell(row=pref_label_row, column=8).value
        pref_code = normalize_pref_code(pref_code_num)

        area_label_row = top + 3
        expect(
            ws.cell(row=area_label_row, column=4).value,
            "構想区域",
            f"ブロック{block.index}: 構想区域ラベル行(D列)",
        )
        area_code_num = ws.cell(row=area_label_row, column=6).value
        area_name = ws.cell(row=area_label_row, column=8).value
        area_code = normalize_area_code(area_code_num)

        # 構想区域コードの上2桁は都道府県コードと一致する規則になっている
        # (AREA_CODE_DESC参照)ため、その規則が原典でも保たれていることを検証する。
        expect(
            area_code[:2],
            pref_code,
            f"ブロック{block.index}: 構想区域コード{area_code}の上2桁が都道府県コード{pref_code}と不一致",
        )
        if area_code in seen_area_codes:
            raise LayoutMismatchError(
                f"ブロック{block.index}: 構想区域コード{area_code}が重複しています"
            )
        seen_area_codes.add(area_code)

        if pref_code in pref_name_by_code and pref_name_by_code[pref_code] != pref_name:
            raise LayoutMismatchError(
                f"ブロック{block.index}: 都道府県コード{pref_code}の都道府県名が"
                f"ブロック間で一致しません({pref_name_by_code[pref_code]!r} != {pref_name!r})"
            )
        pref_name_by_code[pref_code] = pref_name

        pop_row = top + 4
        expect(
            ws.cell(row=pop_row, column=4).value,
            "2020国勢調査人口",
            f"ブロック{block.index}: 人口ラベル行(D列)",
        )
        population_source_value = ws.cell(row=pop_row, column=6).value

        area_row = top + 5
        expect(
            ws.cell(row=area_row, column=4).value,
            "2020面積",
            f"ブロック{block.index}: 面積ラベル行(D列)",
        )
        area_source_value = ws.cell(row=area_row, column=6).value

        # R列(18)は位置でハードコードしているため、値を読む前にラベルが
        # 想定どおりの行位置にあることを検証する(ラベルが動いていたら
        # ここで必ず失敗させ、誤った列を静かに読むことを防ぐ)。
        expect(
            ws.cell(row=pref_label_row, column=18).value,
            OUTFLOW_LABEL,
            f"ブロック{block.index}: 推計流出患者割合ラベル行(R列)",
        )
        outflow_rate, outflow_source_value = _split_rate(
            ws.cell(row=area_label_row, column=18).value
        )

        expect(
            ws.cell(row=pop_row, column=18).value,
            INFLOW_LABEL,
            f"ブロック{block.index}: 推計流入患者割合ラベル行(R列)",
        )
        inflow_rate, inflow_source_value = _split_rate(
            ws.cell(row=area_row, column=18).value
        )

        section_row = top + 6
        expect(
            ws.cell(row=section_row, column=3).value,
            "○病床数の状況",
            f"ブロック{block.index}: 病床数セクション見出し行(C列)",
        )

        # (series, year) ごとに5機能分の病床数を集め、後段で「合計」==4機能の和を検証する。
        block_beds_by_key = {}
        for i, bed_function in enumerate(BED_FUNCTIONS):
            row = top + 9 + i
            expect(
                ws.cell(row=row, column=5).value,
                bed_function,
                f"ブロック{block.index}: 病床機能ラベル行(E列, {bed_function})",
            )
            # A列のブロック番号は反復インデックス(1始まり)であり構想区域コードそのもの
            # ではないため、代わりにB列(病床機能行)とF列(構想区域ラベル行、area_code)の
            # 構想区域コードが一致することを検証する(本来常に一致するはずの結合キー)。
            expect(
                normalize_area_code(ws.cell(row=row, column=2).value),
                area_code,
                f"ブロック{block.index}: 病床機能行(B列)の構想区域コードが不一致",
            )
            for col, (series, year) in col_map.items():
                value = ws.cell(row=row, column=col).value
                beds = expect_int(value, block=block.index, row=row, col=col)
                result.beds_rows.append(
                    {
                        "published_fy": published_fy,
                        "pref_code": pref_code,
                        "pref_name": pref_name,
                        "area_code": area_code,
                        "area_name": area_name,
                        "bed_function": bed_function,
                        "series": series,
                        "year": year,
                        "beds": beds,
                    }
                )
                block_beds_by_key.setdefault((series, year), {})[bed_function] = beds

        # 「合計」が他4機能の和と一致することを検証する(静かに値がずれるのを防ぐ)。
        for (series, year), funcs in block_beds_by_key.items():
            parts_sum = sum(funcs[f] for f in ("高度急性期", "急性期", "回復期", "慢性期"))
            expect(
                funcs["合計"],
                parts_sum,
                f"ブロック{block.index} {series}{year}年: 「合計」が4機能の和と不一致",
            )

        rate_row = top + 9 + len(BED_FUNCTIONS)
        expect(
            ws.cell(row=rate_row, column=5).value,
            "（報告率）",
            f"ブロック{block.index}: 報告率ラベル行(E列)",
        )
        # 病床機能行と同様、B列(報告率行)とF列(area_code)の構想区域コードが
        # 一致することを検証する(本来常に一致するはずの結合キー)。
        expect(
            normalize_area_code(ws.cell(row=rate_row, column=2).value),
            area_code,
            f"ブロック{block.index}: 報告率行(B列)の構想区域コードが不一致",
        )
        for col, (series, year) in col_map.items():
            if series != "実績":
                continue
            value = ws.cell(row=rate_row, column=col).value
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise LayoutMismatchError(
                    f"ブロック{block.index} 行{rate_row} 列{col}: "
                    f"報告率セルの値が数値ではありません: {value!r}"
                )
            if not (0 <= value <= 1):
                raise LayoutMismatchError(
                    f"ブロック{block.index} 行{rate_row} 列{col}: "
                    f"報告率セルの値が0〜1の範囲外です: {value!r}"
                )
            result.report_rate_rows.append(
                {
                    "published_fy": published_fy,
                    "pref_code": pref_code,
                    "pref_name": pref_name,
                    "area_code": area_code,
                    "area_name": area_name,
                    "year": year,
                    "report_rate": value,
                }
            )

        population_2020 = _convert_man_to_person(population_source_value)
        area_2020_km2 = round(float(area_source_value), 2)
        result.basic_rows.append(
            {
                "published_fy": published_fy,
                "pref_code": pref_code,
                "pref_name": pref_name,
                "area_code": area_code,
                "area_name": area_name,
                "population_2020": population_2020,
                "population_2020_source_value": population_source_value,
                "population_2020_source_unit": "万人",
                "area_2020_km2": area_2020_km2,
                "outflow_rate": outflow_rate,
                "outflow_rate_source_value": outflow_source_value,
                "inflow_rate": inflow_rate,
                "inflow_rate_source_value": inflow_source_value,
            }
        )

    return result


def load_sheet(source_key: str):
    """`SOURCES[source_key]` の設定に従い対象xlsxのシートを開く。

    元データのSHA-256を `SHA256SUMS` と照合したうえで開く。
    戻り値: (worksheet, source_config, source_sha256)
    """
    cfg = SOURCES[source_key]
    source_sha256 = verify_source(cfg["path_in_repo"])
    print(f"[ok] 生データ検証: {cfg['path_in_repo']} = {source_sha256[:16]}...")
    xlsx_path = REPO_ROOT / cfg["path_in_repo"]
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb[cfg["sheet_name"]]
    return ws, cfg, source_sha256


def _rows_to_tuples(rows, header):
    return [tuple(r[h] for h in header) for r in rows]


def build_and_write(source_key: str, out_dir: Path) -> dict:
    """指定ソースをパースし、3つのCSV+meta.jsonを `out_dir` へ出力する。

    書き出したCSVパスの辞書({"beds": ..., "report_rate": ..., "basic": ...})
    を返す(再現性テスト等での再利用を想定)。
    """
    out_dir = Path(out_dir)
    ws, cfg, source_sha256 = load_sheet(source_key)
    result = parse_sheet(ws, published_fy=source_key)
    print(
        f"[ok] パース完了: beds={len(result.beds_rows)}行 "
        f"report_rate={len(result.report_rate_rows)}行 basic={len(result.basic_rows)}行"
    )

    today = datetime.date.today().isoformat()
    base_source = {
        "name": cfg["name"],
        "publisher": "厚生労働省",
        "url": cfg["download_url"],
        "page_url": SOURCE_PAGE_URL,
        "fiscal_year": cfg["fiscal_year"],
        "source_file": cfg["path_in_repo"],
        "source_sha256": source_sha256,
        "source_sheet": cfg["sheet_name"],
        "acquired_date": cfg["acquired_date"],
        "license": LICENSE_NOTE,
        "original_title": result.title,
        "original_notes": result.notes,
    }

    beds_header = [
        "published_fy",
        "pref_code",
        "pref_name",
        "area_code",
        "area_name",
        "bed_function",
        "series",
        "year",
        "beds",
    ]
    beds_csv, _ = write_csv_with_meta(
        out_dir / "area_beds.csv",
        beds_header,
        _rows_to_tuples(result.beds_rows, beds_header),
        title="構想区域別 病床数(実績/見込量/必要数)",
        source=base_source,
        processing={
            "script": "tools/parse_area_beds.py",
            "date": today,
            "steps": STEPS_COMMON
            + ["派生比率列(2025年必要数に対する比等)は再計算可能なため出力対象から除外"],
            "caveat": CAVEAT,
        },
        fields=FIELDS_BEDS,
        known_issues=[KNOWN_ISSUES[0]],
    )
    print(f"[ok] 出力: {beds_csv} ({len(result.beds_rows)}行)")

    rate_header = [
        "published_fy",
        "pref_code",
        "pref_name",
        "area_code",
        "area_name",
        "year",
        "report_rate",
    ]
    rate_csv, _ = write_csv_with_meta(
        out_dir / "area_bed_report_rate.csv",
        rate_header,
        _rows_to_tuples(result.report_rate_rows, rate_header),
        title="構想区域別 病床機能報告の報告率",
        source=base_source,
        processing={
            "script": "tools/parse_area_beds.py",
            "date": today,
            "steps": STEPS_COMMON
            + ["各ブロックの（報告率）行から実績年の値のみを抽出(見込量・必要数列は報告率を持たない)"],
            "caveat": CAVEAT,
        },
        fields=FIELDS_REPORT_RATE,
    )
    print(f"[ok] 出力: {rate_csv} ({len(result.report_rate_rows)}行)")

    basic_header = [
        "published_fy",
        "pref_code",
        "pref_name",
        "area_code",
        "area_name",
        "population_2020",
        "population_2020_source_value",
        "population_2020_source_unit",
        "area_2020_km2",
        "outflow_rate",
        "outflow_rate_source_value",
        "inflow_rate",
        "inflow_rate_source_value",
    ]
    basic_csv, _ = write_csv_with_meta(
        out_dir / "area_basic.csv",
        basic_header,
        _rows_to_tuples(result.basic_rows, basic_header),
        title="構想区域別 基礎情報(2020年人口・面積・推計流出入患者割合)",
        source=base_source,
        processing={
            "script": "tools/parse_area_beds.py",
            "date": today,
            "steps": STEPS_COMMON
            + [
                "人口(万人)を10000倍し四捨五入して人単位に変換(population_2020)。原典値は population_2020_source_value に保持",
                "面積の浮動小数点誤差を除くため小数2桁に丸め(area_2020_km2)",
                "推計流出/流入患者割合は原典が数値の場合のみ採用し、'XXX'等の非数値は空にして原典値を*_source_valueに保持",
            ],
            "caveat": CAVEAT,
        },
        fields=FIELDS_BASIC,
        known_issues=[KNOWN_ISSUES[1]],
    )
    print(f"[ok] 出力: {basic_csv} ({len(result.basic_rows)}行)")

    return {"beds": beds_csv, "report_rate": rate_csv, "basic": basic_csv}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--source",
        choices=["R7"],
        default="R7",
        help="対象の公表年度データ(現時点はR7のみ。R6は将来対応)",
    )
    args = ap.parse_args()

    out_dir = REPO_ROOT / "data" / "processed"
    build_and_write(args.source, out_dir)


if __name__ == "__main__":
    main()
