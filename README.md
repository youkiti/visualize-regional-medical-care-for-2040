# 2040年に向けた地域医療構想の可視化

厚生労働省「[2040年に向けた地域医療構想](https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000080850_00014.html)」の公開データ（病床機能報告・医療需要推計）を、**データの真正性（出典・非改変）を担保した形で**可視化するプロジェクト。

地域の医療の現状を誰でも把握できるよう、地図中心の閲覧サイトを GitHub Pages で公開し、加工済みデータの CSV ダウンロードも提供する。

**公開サイト**: https://youkiti.github.io/visualize-regional-medical-care-for-2040/

## 提供予定の機能

- **地図表示（3階層）**: 都道府県 → 構想区域（339 の二次医療圏）→ 医療機関ポイントのドリルダウン
- **可視化する指標**:
  - 病床機能別（高度急性期/急性期/回復期/慢性期）の病床数と将来必要量の比較
  - 在宅（訪問診療）・外来の医療需要推計（2024→2050年度、年度スライダー）
  - 医療機関別の病床数・診療実績・医師数
  - 患者の流入・流出（NDB 2024年度、構想区域間・3区分別。相手区域の内訳と地図での塗り分け）
- **CSV ダウンロード**:
  - 表示条件で絞り込んだ CSV（4種、いずれも由来ヘッダー付き）: 地図に表示中の指標を全339区域ぶん／選択区域1つの基礎情報・病床・医療需要推計／選択区域の医療機関一覧×21指標／選択区域の患者の流入元・流出先の内訳
  - 加工済みデータセットの一括ダウンロード: `data/processed/` の CSV 15本＋各 `.meta.json`＋`README.md`＋`MANIFEST.tsv` を1本の ZIP にまとめて配布（出典メタデータ・SHA-256 同梱）

詳細は [doc/REQUIREMENTS.md](doc/REQUIREMENTS.md) を参照。

## リポジトリ構成

| パス | 内容 |
|---|---|
| `R7/` | 令和7年度公表の生データ（**編集禁止**、ファイル名は厚労省のファイルID） |
| `R6/` | 令和6年度公表の生データ（**編集禁止**、別添資料名） |
| `ksj/` | 国土数値情報（国土交通省）のジオデータ（**編集禁止**）。二次医療圏境界（A38）・医療機関位置（P04）。A38 はサイズ超過のため Git 管理外（下記参照） |
| `tools/` | データ取得・加工スクリプト（`fetch_ksj_geodata.py`・`parse_prefecture_beds.py`・`parse_area_beds.py`・`build_area_boundaries.py`・`verify_area_join.py`・`build_web_data.py` ほか）と共通基盤（`tools/lib/`）・テスト（`tools/tests/`） |
| `SHA256SUMS` | 生データの SHA-256 ハッシュ（完全性検証用） |
| `doc/` | ドキュメント（[要件定義](doc/REQUIREMENTS.md)・[データ来歴](doc/DATA_SOURCES.md)） |
| `data/processed/` | 加工済みデータ（構想区域境界 GeoJSON、都道府県別・構想区域別病床数等の CSV/JSON。ファイル内 or 同名 `.meta.json` に由来メタデータ同梱） |
| `web/` | 可視化サイト本体（Vite + React + MapLibre GL）。`data/processed/` を正本として `npm run dev`/`build` 時に表示用データ（一括ダウンロード用 ZIP を含む）を自動生成する |

## 可視化サイトをローカルで動かす

```bash
cd web
npm ci
npm run dev
```

`http://localhost:5173` で開く。`predev`/`prebuild` が `data/processed/` から `web/src/generated/`（Git管理外）を自動生成するため、`data/processed/` を再生成した後もコマンド一発で反映される。

## GitHub Pages への公開

`main` への push で [.github/workflows/deploy-pages.yml](.github/workflows/deploy-pages.yml) が自動でビルド・デプロイする。**初回のみ、リポジトリの Settings → Pages で「Source」を "GitHub Actions" に切り替える必要がある**（ワークフローを置くだけでは有効化されない、リポジトリ管理者の手動操作）。

## データの真正性

- 生データ（`R6/`・`R7/`・`ksj/`）は取得時のまま無加工で保持し、一切編集しない。
- 全ファイルの出典 URL・取得日は [doc/DATA_SOURCES.md](doc/DATA_SOURCES.md) に記録している。
- 医療圏境界（`ksj/A38-20/`、1.13GB）は GitHub の 100MB 制限を超えるためコミットしないが、ハッシュを `SHA256SUMS` に記録し、[tools/fetch_ksj_geodata.py](tools/fetch_ksj_geodata.py) で再取得・照合できる。
- 改変されていないことは誰でも検証できる:

  ```bash
  # Git Bash / Linux / macOS（クローン直後はGit管理外のA38をスキップ）
  sha256sum -c --ignore-missing SHA256SUMS

  # 全データ取得済みのローカル環境では全量検証
  sha256sum -c SHA256SUMS
  ```

  ```powershell
  # PowerShell
  Get-FileHash -Algorithm SHA256 <file>   # SHA256SUMS の値と照合
  ```

- 加工データにも由来メタデータ（出典 URL・公表年度・元ファイルのハッシュ）を持たせ、可視化画面には出典を表示する。

## データ利用について

本リポジトリが扱うデータは厚生労働省が公開する公的統計であり、出典を明記のうえ利用する。利用条件は厚労省サイトの[利用規約](https://www.mhlw.go.jp/chosakuken/index.html)（政府標準利用規約準拠）に従う。

なお、病床機能報告の集計値と「将来の必要量」は計算方法が異なるため単純比較できない（厚労省注記）。本プロジェクトの可視化でも併記時には必ず注意書きを表示する。

## 開発状況

- [x] 生データ収集・出典/ハッシュ記録（R6・R7）
- [x] 要件定義（[doc/REQUIREMENTS.md](doc/REQUIREMENTS.md)）
- [x] GitHub Actions による生データの完全性検証（`sha256sum -c`）
- [x] 地理データ収集（国土数値情報 二次医療圏境界 A38・医療機関 P04、`ksj/`）
- [x] 二次医療圏境界の軽量 GeoJSON 生成（`data/processed/iryoken2_A38-20.geojson`、由来メタデータ同梱）
- [x] Excel パーサ基盤（`tools/lib/`：完全性検証・コード正規化・由来メタデータ付きCSV出力）とテスト（`pytest`）・CI（`.github/workflows/test-pipeline.yml`）
- [x] Excel パーサ: 都道府県別の病床数等（`tools/parse_prefecture_beds.py` → `data/processed/prefecture_*.csv`）
- [x] Excel パーサ: 構想区域別の病床数等（`tools/parse_area_beds.py` → `data/processed/area_*.csv`）
- [x] 地理データ突合（構想区域 × 二次医療圏境界、[doc/JOIN_VERIFICATION.md](doc/JOIN_VERIFICATION.md)）と可視化用境界 GeoJSON 生成（`data/processed/area_boundaries_R7.geojson`）
- [x] 可視化サイト実装（Vite + React + MapLibre GL、339構想区域のコロプレス表示、`web/`）
- [x] GitHub Actions によるビルド・Pages デプロイ（[.github/workflows/deploy-pages.yml](.github/workflows/deploy-pages.yml)）
- [x] Excel パーサ: 医療需要推計（`tools/parse_demand_forecast.py` → `data/processed/demand_*.csv`）
- [x] Excel パーサ: 医療機関別の病床数・診療実績等（`tools/parse_facility_beds.py` → `data/processed/facility_*.csv`）と国土数値情報 P04 との名寄せ（[doc/FACILITY_LINKAGE.md](doc/FACILITY_LINKAGE.md)）
- [x] CSV ダウンロード（表示条件で絞り込んだ CSV 4種と、加工済みデータセットの一括 ZIP）
- [x] Excel パーサ: 患者の流入率・流出率（`tools/parse_patient_flow.py` → `data/processed/patient_flow*.csv`）と、区域パネル・地図での可視化
