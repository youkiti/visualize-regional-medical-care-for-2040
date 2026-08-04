# -*- coding: utf-8 -*-
"""帳票Excel(結合セル・複数行ヘッダー・区域ごとの繰り返しブロック)を
位置ベースで抽出する各パーサが共用する、汎用の検証ユーティリティ。

`tools/parse_prefecture_beds.py` に実装していたものをここへ集約し、
`tools/parse_area_beds.py` 等の他パーサからも共通利用できるようにする。
"""


class LayoutMismatchError(Exception):
    """帳票のレイアウトが想定(サブヘッダー・ラベル位置)と異なる場合に送出する。"""


def expect(actual, expected, message):
    """`actual == expected` を検証し、不一致なら `LayoutMismatchError` を送出する。"""
    if actual != expected:
        raise LayoutMismatchError(f"{message}: 期待={expected!r} 実際={actual!r}")


def expect_int(value, *, block, row, col):
    """数値セルの値が整数(またはinteger値のfloat)であることを検証する。

    素朴な `int(value)` は非整数の float を黙って切り捨て(`1234.7` ->
    `1234`)、`None` なら意味の分からない `TypeError` になる。真正性を
    担保するパイプラインで「静かに値が変わる」のは最悪の失敗モードのため、
    int、または `float.is_integer()` が真の float 以外はブロック番号・行・
    列・実際の値を添えて `LayoutMismatchError` で中断する。
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise LayoutMismatchError(
        f"ブロック{block} 行{row} 列{col}: セルの値が整数ではありません: {value!r}"
    )


def normalize_header_text(v) -> str:
    """ヘッダーセルの値を比較用に正規化する(改行除去・前後空白除去)。"""
    if v is None:
        return ""
    return str(v).replace("\n", "").strip()


def read_header_row(ws, header_row: int, col_start: int, col_end: int):
    """ヘッダー行を正規化した文字列のタプルとして読む(ブロック間比較用)。

    `col_start`〜`col_end`(両端含む)の範囲のみを対象とする。呼び出し側で、
    ブロックごとに値が変わって当然の列(ブロック番号列やブロックごとの
    通し番号ラベル列など)をあらかじめ除外した範囲を渡すこと。
    """
    return tuple(
        normalize_header_text(ws.cell(row=header_row, column=c).value)
        for c in range(col_start, col_end + 1)
    )
