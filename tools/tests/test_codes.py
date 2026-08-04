# -*- coding: utf-8 -*-
"""tools/lib/codes.py の正規化関数のテスト。"""
import pytest

from tools.lib.codes import normalize_area_code, normalize_pref_code


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "00"),
        ("0", "00"),
        (1, "01"),
        (" 1 ", "01"),
        (47, "47"),
        ("47", "47"),
        (5, "05"),
        (1.0, "01"),  # openpyxlが数値セルをfloatで返すケース
        (47.0, "47"),
        (0.0, "00"),
    ],
)
def test_normalize_pref_code_ok(value, expected):
    assert normalize_pref_code(value) == expected


@pytest.mark.parametrize("value", [-1, 48, "abc", None, "", 100, 1.5, 47.5])
def test_normalize_pref_code_error(value):
    with pytest.raises(ValueError):
        normalize_pref_code(value)


@pytest.mark.parametrize(
    "value,expected",
    [
        (101, "0101"),
        ("101", "0101"),
        ("0101", "0101"),
        (0, "0000"),
        (9999, "9999"),
        (1, "0001"),
        (101.0, "0101"),  # openpyxlが数値セルをfloatで返すケース(M2の構想区域コードで発生)
        (0.0, "0000"),
        (9999.0, "9999"),
    ],
)
def test_normalize_area_code_ok(value, expected):
    assert normalize_area_code(value) == expected


@pytest.mark.parametrize("value", [-1, 10000, "abc", None, "", 101.5, 9999.5])
def test_normalize_area_code_error(value):
    with pytest.raises(ValueError):
        normalize_area_code(value)
