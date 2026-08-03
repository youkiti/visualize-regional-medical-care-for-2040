# -*- coding: utf-8 -*-
"""国土数値情報（国土交通省）から医療圏・医療機関の全国版データを取得するスクリプト。

対象:
  - A38-20_GML.zip 医療圏データ 第2.0版（令和2年度、一次〜三次医療圏の面データ、約1.13GB）
  - P04-20_GML.zip 医療機関データ 第3.0版（令和2年度、病院・診療所の点データ、約27.6MB）

国土数値情報ダウンロードサービスの正規フロー（アンケート案内モーダル →
confirmダイアログ → ダウンロード）をSeleniumでそのまま辿る。
アンケートは公式の「スキップする」ボタンで省略する。

取得後は `ksj/<データセット>/` に配置し、SHA-256を表示するので
`SHA256SUMS` および `doc/DATA_SOURCES.md` の記録と照合すること。

必要環境: Python 3.11+, selenium 4.x, Google Chrome

使い方:
    python tools/fetch_ksj_geodata.py
"""
import hashlib
import shutil
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

REPO_ROOT = Path(__file__).resolve().parent.parent
STAGING = REPO_ROOT / "ksj" / "_staging"

TARGETS = [
    # (データページURL, ファイル名, 配置先ディレクトリ, 公称サイズMB, タイムアウト秒)
    (
        "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P04-v3_0.html",
        "P04-20_GML.zip",
        REPO_ROOT / "ksj" / "P04-20",
        27.6,
        600,
    ),
    (
        "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A38-v2_0.html",
        "A38-20_GML.zip",
        REPO_ROOT / "ksj" / "A38-20",
        1133.39,
        3600,
    ),
]


def log(msg: str) -> None:
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wait_download(dirpath: Path, filename: str, timeout: int) -> Path:
    """Chromeのダウンロード完了（.crdownload消滅＋サイズ安定）を待つ。"""
    final = dirpath / filename
    deadline = time.time() + timeout
    last_report = 0.0
    while time.time() < deadline:
        parts = list(dirpath.glob("*.crdownload"))
        if final.exists() and not parts:
            size = final.stat().st_size
            time.sleep(2)
            if final.stat().st_size == size:
                return final
        now = time.time()
        if now - last_report >= 20:
            cur = sum(p.stat().st_size for p in parts if p.exists())
            if not parts and final.exists():
                cur = final.stat().st_size
            log(f"  downloading {filename}: {cur / 1_000_000:,.1f} MB")
            last_report = now
        time.sleep(3)
    raise TimeoutError(f"timeout waiting for {filename}")


def main() -> None:
    STAGING.mkdir(parents=True, exist_ok=True)

    opts = Options()
    opts.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(STAGING),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )
    opts.add_argument("--window-size=1400,1000")

    driver = webdriver.Chrome(options=opts)
    try:
        for page, fname, dest_dir, size_mb, timeout in TARGETS:
            dest = dest_dir / fname
            if dest.exists():
                log(f"skip (already present): {dest}")
                log(f"  sha256 = {sha256(dest)}")
                continue

            log(f"open {page}")
            driver.get(page)
            link = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located(
                    (By.XPATH, f'//a[contains(@onclick, "\'{fname}\'")]')
                )
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", link)
            log(f"clicked download link for {fname} (approx {size_mb} MB)")

            # セッション初回のみアンケート案内モーダルが出る。2回目以降は
            # モーダルなしで即confirm()が出るため、まずalertを待ち、
            # 出なければモーダルを「スキップする」で閉じてから再度待つ。
            try:
                WebDriverWait(driver, 5).until(EC.alert_is_present())
            except TimeoutException:
                skip_btns = driver.find_elements(
                    By.CSS_SELECTOR, ".modal-container.active .modal-close"
                )
                if skip_btns:
                    log("questionnaire modal shown -> clicking skip")
                    driver.execute_script("arguments[0].click();", skip_btns[0])
                WebDriverWait(driver, 20).until(EC.alert_is_present())

            alert = driver.switch_to.alert
            log(f"confirm dialog: {alert.text!r} -> accept")
            alert.accept()

            got = wait_download(STAGING, fname, timeout)
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(got), str(dest))
            log(f"saved: {dest} ({dest.stat().st_size:,} bytes)")
            log(f"  sha256 = {sha256(dest)}")
    finally:
        driver.quit()

    if STAGING.exists() and not any(STAGING.iterdir()):
        STAGING.rmdir()
    log("ALL DONE — SHA256SUMS / doc/DATA_SOURCES.md と照合してください")


if __name__ == "__main__":
    main()
