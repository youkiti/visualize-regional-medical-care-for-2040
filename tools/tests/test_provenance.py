# -*- coding: utf-8 -*-
"""tools/lib/provenance.py の完全性検証関数のテスト。"""
import pytest

from tools.lib.provenance import REPO_ROOT, recorded_hash, sha256, verify_source

R7_XLSX = "R7/001722915.xlsx"


def test_sha256_matches_recorded_hash_for_known_file():
    expected = recorded_hash(R7_XLSX)
    actual = sha256(REPO_ROOT / R7_XLSX)
    assert actual == expected
    # SHA-256は64桁の16進文字列
    assert len(actual) == 64
    int(actual, 16)


def test_verify_source_ok_returns_recorded_hash():
    h = verify_source(R7_XLSX)
    assert h == recorded_hash(R7_XLSX)


def test_recorded_hash_missing_path_aborts():
    with pytest.raises(SystemExit):
        recorded_hash("R7/does_not_exist.xlsx")


def test_verify_source_missing_path_aborts():
    with pytest.raises(SystemExit):
        verify_source("R7/does_not_exist.xlsx")
