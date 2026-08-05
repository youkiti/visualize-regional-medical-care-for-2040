# -*- coding: utf-8 -*-
"""tools/verify_r6_bundle.py のテスト。

ネットワーク越しのダウンロード自体はテストしない(CIでは実行しない前提の
スクリプトのため)。`verify()` はローカルのzipファイルパスを受け取るだけの
純粋な関数なので、リポジトリに既にコミット済みの `R6/` 配下のファイルを
その場でzip化し直してテストできる(ネットワーク不要)。
"""
import zipfile

import pytest

from tools.lib.provenance import REPO_ROOT, recorded_hash
from tools.verify_r6_bundle import verify

R6_DIR = REPO_ROOT / "R6"
R6_BASENAMES = [
    "別添４①（構想区域の病床数等の状況）.pdf",
    "別添４②（都道府県の病床数等の状況）.xlsx",
    "別添４③（構想区域の病床数等の状況）.xlsx",
    "別添５①（構想区域の詳細状況）.pdf",
    "別添５②（構想区域の詳細状況）.xlsx",
]


def _make_zip(tmp_path, basenames, *, corrupt=None, extra_entries=None):
    """`basenames`(R6/配下のファイル名)からzipを組み立てる。

    `corrupt` に basename を渡すと、そのエントリの中身を破壊して書き込む
    (SHA-256不一致を検証するため)。`extra_entries` は
    {basename: bytes} で、SHA256SUMSに記録の無い追加エントリを混ぜられる。
    """
    zip_path = tmp_path / "test_bundle.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in basenames:
            data = (R6_DIR / name).read_bytes()
            if name == corrupt:
                data = data + b"\x00tampered"
            zf.writestr(name, data)
        for name, data in (extra_entries or {}).items():
            zf.writestr(name, data)
    return zip_path


def test_verify_succeeds_for_committed_r6_files_rezipped(tmp_path):
    """コミット済みの `R6/` 配下5ファイルをその場でzip化すると、全件が
    `SHA256SUMS` の記録値と一致することを確認する(実際のダウンロードzipの
    往復と同じ経路をネットワーク無しで再現する)。
    """
    zip_path = _make_zip(tmp_path, R6_BASENAMES)
    verified = verify(zip_path)
    assert verified == 5


def test_verify_raises_on_sha256_mismatch(tmp_path):
    zip_path = _make_zip(
        tmp_path, R6_BASENAMES, corrupt="別添４②（都道府県の病床数等の状況）.xlsx"
    )
    with pytest.raises(SystemExit):
        verify(zip_path)


def test_verify_raises_when_entry_not_recorded_in_sha256sums(tmp_path):
    """SHA256SUMSに記録の無い基底名のエントリが混ざっていれば中断すること。"""
    zip_path = _make_zip(
        tmp_path,
        [R6_BASENAMES[0]],
        extra_entries={"存在しないファイル.xlsx": b"dummy"},
    )
    with pytest.raises(SystemExit):
        verify(zip_path)


def test_recorded_hashes_exist_for_all_expected_basenames():
    """このテストの前提(R6_BASENAMESが5ファイル全てSHA256SUMSに記録済み)を
    独立に確認しておく(recorded_hash()が別の理由でSystemExitしていないか)。
    """
    for name in R6_BASENAMES:
        digest = recorded_hash(f"R6/{name}")
        assert len(digest) == 64
        int(digest, 16)
