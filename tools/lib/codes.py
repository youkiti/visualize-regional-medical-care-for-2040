# -*- coding: utf-8 -*-
"""区域コード正規化ユーティリティ。

CLAUDE.md の「結合キーの罠」に対応するための共通関数を提供する:
病床系ファイル(001722915等)ではコードが数値(例 `101`)で入っているのに対し、
医療需要推計(001728462)や地理データ(ksj/A38-20 の `A38b_003`)ではゼロ埋め
文字列(例 `"0101"`)で入っている。突合時はここで同じ表現に正規化してから
キーとして使う。
"""


def _coerce_int(value) -> int:
    """コード値を整数へ変換する共通ヘルパ。

    openpyxl は数値セルを float で返すことがある(例 `101.0`)。整数値の
    float はそのまま整数として受け入れ、非整数(`101.5`)は拒否する。
    それ以外(int・文字列等)は従来どおり `int(str(value).strip())` で解釈する。
    数値として解釈できない場合は `ValueError` を送出する。
    """
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"整数値ではありません: {value!r}")
        return int(value)
    return int(str(value).strip())


def normalize_pref_code(value) -> str:
    """都道府県コードをゼロ埋め2桁の文字列に正規化する。

    数値・文字列いずれの入力も受け付ける(例: `0` / `"0"` -> `"00"`(全国)、
    `1` -> `"01"`、`"47"` -> `"47"`)。整数値の float(`1.0`)も受け付ける
    (openpyxl が数値セルを float で返すことがあるため)。0〜47の範囲外、
    非整数の float、または数値として解釈できない値を渡すと `ValueError` を
    送出する。
    """
    try:
        n = _coerce_int(value)
    except (TypeError, ValueError):
        raise ValueError(f"都道府県コードとして解釈できません: {value!r}")
    if not (0 <= n <= 47):
        raise ValueError(f"都道府県コードの範囲外です(0-47): {value!r}")
    return f"{n:02d}"


def normalize_area_code(value) -> str:
    """構想区域(二次医療圏)コードをゼロ埋め4桁の文字列に正規化する。

    CLAUDE.md「結合キーの罠」: 病床系ファイル(001722915・001723349等)では
    構想区域コードが数値(例 `101`)で格納されているのに対し、医療需要推計
    (001728462)や地理データ(ksj/A38-20 の `A38b_003`)ではゼロ埋め文字列
    (例 `"0101"`)で格納されている。突合(結合キーとして使う)前に必ず
    この関数で表現を揃えること。

    数値・文字列いずれの入力も受け付ける(例: `101` / `"101"` / `"0101"`
    -> `"0101"`)。整数値の float(`101.0`)も受け付ける(openpyxl が数値
    セルを float で返すことがあるため)。0〜9999の範囲外、非整数の float、
    または数値として解釈できない値を渡すと `ValueError` を送出する。
    """
    try:
        n = _coerce_int(value)
    except (TypeError, ValueError):
        raise ValueError(f"構想区域コードとして解釈できません: {value!r}")
    if not (0 <= n <= 9999):
        raise ValueError(f"構想区域コードの範囲外です(0-9999): {value!r}")
    return f"{n:04d}"
