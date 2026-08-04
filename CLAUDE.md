# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## リポジトリの目的

厚生労働省「[2040年に向けた地域医療構想](https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000080850_00014.html)」の公開データ（病床機能報告・医療需要推計）を、**データの真正性（出典・改変されていないこと）を担保した形で**可視化するリポジトリ。

## データ真正性のルール（最重要）

- `R6/`・`R7/`・`ksj/` 配下の生データは**編集禁止**。加工・集計は必ず別ファイル（例: `data/processed/`）へ出力する。
- 全生データの出典URL・取得日は `doc/DATA_SOURCES.md` に、SHA-256 は `SHA256SUMS`（ルート直下）に記録済み。新規データ追加時は両方に追記する。
- 完全性の検証:
  - Git Bash: `sha256sum -c SHA256SUMS`（`ksj/A38-20` はGit管理外のため、未取得の環境では `sha256sum -c --ignore-missing SHA256SUMS`）
  - PowerShell: `Get-FileHash -Algorithm SHA256 <file>` で `SHA256SUMS` と照合
- 可視化には出典（厚労省ページURL・年度）を表示できるよう、加工データにも由来メタデータを持たせる。

## データ構成

`R7/` は令和7年度公表分（ファイル名は厚労省のファイルID）、`R6/` は令和6年度分（別添名）。年度間でレイアウトは同一なので、パーサは両年度で共用できる。

| R7 | R6 対応ファイル | 内容 |
|---|---|---|
| 001722915.xlsx | 別添４② | 都道府県別の病床数と2025年必要量の比較（1シート、47都道府県+全国の繰り返しブロック） |
| 001723349.xlsx | 別添４③ | 構想区域別の病床数等（1シート約5,000行、339構想区域の繰り返しブロック） |
| 001723127.xlsx | 別添５② | 構想区域ごとの医療機関別病床数・診療実績・医師数（**339シート**、シート名は「101北海道南渡島」形式） |
| 001723366.xlsx | （R6版なし） | 構想区域間の患者流入率・流出率（2シート「流入率」「流出率」、約22,000行、構想区域ごとの繰り返しブロック） |
| 001728462.xlsx | （R6版なし） | 在宅（訪問診療）・外来の医療需要推計 2024→2050年度（2シート） |

出典説明書PDF 3点（001723347・001723348・001728467）も `R7/` に収載。各xlsxのデータ出典・集計方法の公式説明で、可視化の注記を書く際の一次資料。

### ksj/ — 国土数値情報ジオデータ（国土交通省）

| パス | 内容 |
|---|---|
| ksj/A38-20/A38-20_GML.zip | 医療圏データ 第2.0版・令和2年度（一次〜三次医療圏ポリゴン）。**1.13GBのためGit管理外**。`python tools/fetch_ksj_geodata.py` で再取得 |
| ksj/P04-20/P04-20_GML.zip | 医療機関データ 第3.0版・令和2年度（病院・診療所の点データ）。コミット済み |

- 座標系はいずれも JGD2011 地理座標（EPSG:6668）。zip内にシェープファイル・GeoJSON・GML(XML) を同梱（A38 は `_1`=一次、`_2`=二次、`_3`=三次医療圏）。
- 二次医療圏コード `A38b_003` はゼロ埋め4桁文字列（例 `"0101"`）で需要推計ファイルと同形式。病床系ファイルの数値コードとは下記「結合キーの罠」の正規化が必要。
- **`A38-20_1`（一次医療圏）は市区町村単位のポリゴンで、`A38a_001`=行政区域コード（5桁）・`A38a_002`=市区町村名・`A38a_003`=所属する二次医療圏コード（4桁）を持つ**。市区町村を任意の区域単位へディゾルブし直す入口になる（`tools/build_area_boundaries.py` が利用）。
- **A38 と R7 の区割差異は M2 で決着済み**: 339構想区域のうち331区域はコード・名称とも完全一致し、差異は三重県のみ（A38の4二次医療圏がR7では8構想区域へ細分化）。検証の全内容と根拠は `doc/JOIN_VERIFICATION.md`（`tools/verify_area_join.py` が生成）にある。
- 可視化用GeoJSONは2つある。用途を取り違えないこと:
  - `data/processed/iryoken2_A38-20.geojson`（335二次医療圏・約6.7MB）— A38-20_2 の忠実な抽出物。`tools/build_iryoken2_geojson.py` で再生成。突合検証の入力。
  - `data/processed/area_boundaries_R7.geojson`（**339構想区域**・約4.5MB）— 可視化で使うのはこちら。`tools/build_area_boundaries.py` で再生成。全339区域を `A38-20_1` から同一条件でディゾルブしており、**三重県8区域の境界は国土数値情報の公表物ではなく市区町村からの合成派生物**（各フィーチャの `boundary_source` で区別できる）。
- いずれも要 Node.js（mapshaper を npx で取得）。実行時に元zipのSHA-256を検証する。由来メタデータはファイル内 `metadata` に埋め込み済み。

### mie/ — 三重県公式資料

| パス | 内容 |
|---|---|
| mie/001092203.pdf | 「資料４ 第８次三重県医療計画における二次医療圏の設定について」（三重県医療政策課）。コミット済み |

9ページ「現行の二次医療圏・構想区域」が、三重県の4二次医療圏と8構想区域の対応・構成市町（29市町）を示す一次資料。三重県はこの両方を**併存**させており、構想区域は二次医療圏の細分（入れ子構造）。機械可読化した対応表は `data/reference/mie_area_municipalities.csv`（`tools/build_mie_area_municipalities.py` が生成し、A38の構成市区町村・医療機関所在地との5系統の突合で転記を検証する）。

### web/ — 可視化サイト

`data/processed/area_indicators_R7.json`（`tools/build_web_data.py` が生成、339構想区域の2025年実績vs2025年必要数）・`data/processed/area_demand_R7.json`（`tools/build_web_demand.py` が生成、339構想区域×2区分×6年度の医療需要推計）と `data/processed/area_boundaries_R7.geojson` を正本として、`web/scripts/sync-data.mjs` が `web/src/generated/`（**Git管理外**、`predev`/`prebuild` から自動実行）へ表示用データを合成する:

| 生成物 | 用途 |
|---|---|
| `area_indicators.json` | 正本の忠実コピー（改行のみLF正規化）。**バンドルに取り込み**、パネル・検索・分位計算・出典表示に使う |
| `area_demand.json` | 需要推計の正本の忠実コピー。**バンドルに取り込み**、パネルの需要テーブル・年度ラベル・出典表示に使う |
| `area_map.json` | 境界GeoJSON + フラット化した指標プロパティ（約4.9MB）。**`?url` インポートでファイルURLのみをバンドルに含め、MapLibreにfetchさせる**（メインスレッドでパースしない）。需要は `<区分>_<年>`（値）と `<区分>_r_<年>`（2024年度比）の24プロパティを持つ |
| `area_index.json` | 選択・bbox解決用の軽量インデックス（`area_code`・`boundary_source`・bboxのみ）。**バンドルに取り込み**、地図の表示状態に依存せず区域選択を解決する |

正本は `data/processed/` の1箇所のみ。`data/processed/` を再生成したら `sync-data`（＝`predev`/`prebuild`）が自動で追随する。

### パース時の注意（帳票形式のExcel）

- 需要推計（001728462）以外は**帳票レイアウト**（結合セル・複数行ヘッダー・区域ごとの繰り返しブロック）。`pandas.read_excel` の素朴な読み込みでは崩れるため、位置ベースで抽出する。
- 001728462 は比較的整形済み: **4行目=年度ラベル行**（`2024年度`・`2030年度（現状投影）`…）、**5行目=見出し行**、データは6行目から339行（2シートともレイアウト同一・コード昇順）。年は列位置ではなく4行目の文字列から抽出すること（他の帳票と同じ規律）。**2024年度だけ「（現状投影）」が付かない**ため、解釈せず原文を `year_label` 列に保持している（`tools/parse_demand_forecast.py`）。
- **需要推計の単位・基準の罠**: 値は「**レセプト件数/月**」であって患者数・人数ではない。人口列も「人口(2024年**度**)」と「人口(2040年)」で年度/年が混在し、さらに `area_basic.csv` の `population_2020`（国勢調査）とは出典自体が別。**画面で併記するときは必ず出典と基準年を書き分けること。**
- **結合キーの罠**: 構想区域コードは病床系ファイルでは数値 `101`、需要推計ではゼロ埋め文字列 `"0101"`。突合時に正規化が必要。
- **単位の罠**: 人口が「万人」単位の箇所（基礎情報欄）と実数の箇所（需要推計）が混在。
- 病床機能報告の集計値と「将来の必要量」は計算方法が異なり、厚労省自身が単純比較を戒めている（各ファイル冒頭の注記参照）。可視化での併記時は注記を添える。
- **R6の列ずれの罠**: `001722915.xlsx`（①都道府県の病床数等）は R6/R7 で「帳票の行構造（15行×48ブロック）」は同一だが、**実績年の列数が異なる**（R6は2015・2018〜2024年の8年分、R7はそれに2025年実績が加わり9年分）。そのため見込量・必要数の列位置が1列ずれ、見込量の対象年自体も異なる（R6=2025年見込量／R7=2026年見込量）。したがって列は位置（列番号）ではなく、サブヘッダー行の文字列（`2015実績`・`2026見込量`等）から解決すること（`tools/parse_prefecture_beds.py` 参照）。**`001723349.xlsx`（②構想区域の病床数等）にも同じ罠がある**ことを M2 で確認済み。未実装のパーサでも必ず確認すること。
- **①と②は帳票のブロック構造が完全に同一**（3行目開始・1ブロック15行・ブロック内の行オフセットも同じ）。違いはブロック数（48 対 339）、A列のブロック番号の起点（0始まり＝全国が0 対 1始まり）、②が使う追加行（構想区域コード・推計流出入患者割合）だけ。走査の共通部分は `tools/lib/layout.py`（検証ユーティリティ）と `tools/lib/block_report.py`（ブロック走査・ヘッダーからの列解決）にあり、**新しい帳票パーサはこの2つの上に載せること**。行オフセットの意味づけと項目抽出は各パーサ側に残す設計。
- **`001723349.xlsx` の「2024実績」列は「2025実績」列の複製**（339区域×5機能=1695セル全てで同一）。①都道府県版では両者が別値であり、②を都道府県へ集計して①と突合すると2585キー中230キーが2024年だけ不一致になる。**厚労省の公表物側の問題**であり、値は原典どおり出力して `meta.json` の `known_issues` に記録してある。**可視化では構想区域レベルの2024年実績を使わないこと。**
- **センチネル値の罠**: `001723349.xlsx` の推計流出/流入患者割合は、三重県の8区域（2405〜2412）でのみ数値ではなく文字列 `'XXX'`（未算出）。派生比率列には `'-'` も現れる。数値前提で `int()`/`float()` すると静かに壊れるため、非数値は必ず検出して分岐すること。
- **医療機関個票（001723127）は「1構想区域＝1シート」の339シート構成**で、他の帳票（1シート内の繰り返しブロック）とは逆。`block_report.py` は使わない。各シートは1〜9行が区域サマリ、10行目以降が医療機関表（14行目からA列連番、シートにより1〜333件）。ヘッダーは11〜13行の3段＋結合セルなので、**列は (11行,12行,13行) の文字列の三つ組で解決する**（部分一致だと「急性期」が「高度急性期」を拾う）。
- **この帳票のセンチネルは `'XXX'` ではなく `'*'` と `'未報告'`**: `'*'` はNDBガイドラインによる非公表（診療実績4列のみ、3,312セル）、`'未報告'` は病床機能報告そのものが未報告（病床数「休棟中等含む計」列のみ、162セル。この場合は所在地欄まで空になる）。`facility_observations.csv` は値と別に `value_status`（observed/source_dash/blank/not_disclosed/not_reported）を持たせて区別している。**欠測を真偽値1本で持たせないこと。**
- **区域サマリの「④一般・療養病床計」は休棟中等を"除く"が、医療機関表の「③一般・療養病床」は"含む"**: 両者を突合すると339区域中304区域で不一致になるが、差は常に休棟中等の合計と一致する**定義差でバグではない**。機能別（高度急性期〜慢性期）は全区域で一致する。なお医療機関数（一般病院＋有床診療所）は78区域で個票行数と合わず、うち76区域は未報告医療機関の件数で説明できる（残り2区域は原因不明。`meta.json` の `known_issues` に記録済み）。
- **医療機関には恒久IDが無い**: `record_id` は `R7-<区域コード>-<原典行番号>` で、**原典の行位置（病床数降順）由来**。公表年度が変われば同じIDが別施設を指しうるので、年度間比較のキーには使えない。名称からハッシュIDを作るのも不可（改称で変わり同名施設で衝突する）。
- **R6の②は `parse_sheet()` では読めない**: 上記の列ずれに加え、(1) 推計流出入患者割合ではなく「（一般病床患者流出入）」という単一値をQ列(17)の別の行位置に持つ（別概念）、(2) 原典に実績セルの欠測が1件ある（ブロック2「南檜山」高度急性期の2015実績が空）。`SOURCES` に R6 を定義しているのは列ずれ追随のヘッダーレベル回帰テスト用。

### 外部データとの名寄せ（P04）の罠

医療機関に座標を与える `tools/build_facility_geo_linkage.py`（M5）で踏んだもの。結論と全実測値は `doc/FACILITY_LINKAGE.md`（生成物）にある。

- **P04には都道府県コードも市区町村コードも無い**（住所文字列のみ、しかも原則として都道府県名を含まない）。市区町村名だけでは同名市区町村（府中市＝東京/広島、伊達市＝北海道/福島）を切り分けられないので、**区域の確定は住所ではなく点-多角形判定**（`area_boundaries_R7.geojson` に対するレイキャスティング）で行う。
- **政令指定都市の住所は市名を省いて区から始まることがある**（実測3,178件）: `港北区小机町…` は `横浜市港北区` と前方一致しない。**区名がExcel側市区町村の末尾と一致するか**も見ること。これを入れないと神奈川県のマッチ率が91%→53%まで落ち、地図が「神奈川には病院が少ない」という誤った印象を与える。
- **法人格語の除去は、名称を施設種別語だけに削ってしまうことがある**: `厚生連クリニック` → `クリニック` となり `…ロビンの空クリニック` の末尾と一致して誤結合する。**除去後に種別語しか残らないなら除去しない**こと（残余が1文字でも残るなら除去してよい。`医療法人社団森クリニック`→`森クリニック` は正しい）。
- **`p04_beds` は精神・結核病床を含む総病床数で、Excel（病床機能報告）の一般・療養病床とは定義が違う**: 突合の妥当性検証には使えず（乖離228件の大半は精神科病院）、画面で並べて見せてもいけない。
- 自動採用は「正規化名の完全一致または接尾一致」＋「区域ポリゴン内で一意」＋「市区町村整合」＋「一対一制約」を**全て**満たす場合のみ。あいまい一致（`candidate_only`）には座標を与えない（`doc/REQUIREMENTS.md` §4.3「位置の推測はしない」）。

## 環境

- Python 3.11 + openpyxl（依存は `requirements.txt` で管理）。
- ローカル: Windows / 日本語ファイル名あり。Pythonでコンソール出力が文字化けする場合は `PYTHONIOENCODING=utf-8` を付ける。
- Claude Code cloud: Ubuntu。外部ドメイン（`www.mhlw.go.jp`・`nlftp.mlit.go.jp`・`www.pref.mie.lg.jp`）へのアクセスは claude.ai の環境設定 Network access（Custom）で許可する。リポジトリ内の設定ファイルでは制御できない。
- `SHA256SUMS` は LF 固定（`.gitattributes` で管理）。CRLF になると `sha256sum -c` が失敗する。CI（`.github/workflows/verify-data.yml`）が push ごとに完全性を検証する。
- **加工データ・生成ドキュメントは `.gitattributes` で LF 固定にする**（現在 `*.geojson`・`*.csv`・`*.json`・`doc/JOIN_VERIFICATION.md`）。ルートに `* text=auto` があるため指定を忘れると Windows 作業ツリーで CRLF になり、「再生成物がコミット済みファイルとバイト一致するか」の再現性テストが Windows でだけ壊れる。**新しい出力形式（生成される Markdown レポート等を含む）を追加するときは併せて追記すること。**
- **生成物には生成日時を埋め込まない**。埋め込むと再生成のたびに差分が出て、バイト一致の再現性テストが翌日に壊れる。由来の担保には元データのSHA-256（安定値）を使う。CSVの `meta.json` は `processing.date` を持つが、再現性テストはこの項目を比較対象から除外している。

### 実行コマンド

いずれもリポジトリルートで実行する。`data/processed/` の成果物はコミット済みで、再現性テストが「再生成物がコミット済みファイルとバイト一致するか」を検証するため、**元データを差し替えたら再実行してコミットし直すこと**。

```bash
# パーサ（生データ → data/processed/*.csv）
PYTHONIOENCODING=utf-8 python tools/parse_prefecture_beds.py     # 都道府県 → prefecture_*.csv
PYTHONIOENCODING=utf-8 python tools/parse_area_beds.py           # 構想区域 → area_*.csv
PYTHONIOENCODING=utf-8 python tools/parse_demand_forecast.py     # 構想区域別医療需要推計 → demand_*.csv
PYTHONIOENCODING=utf-8 python tools/parse_facility_beds.py       # 医療機関個票（339シート）→ facility_*.csv

# 三重県の市町対応表（→ data/reference/mie_area_municipalities.csv）
PYTHONIOENCODING=utf-8 python tools/build_mie_area_municipalities.py

# 突合検証（→ data/processed/area_geo_join.csv と doc/JOIN_VERIFICATION.md）
PYTHONIOENCODING=utf-8 python tools/verify_area_join.py

# 医療機関とP04（国土数値情報）の名寄せ（→ facility_geo_linkage.csv と doc/FACILITY_LINKAGE.md）
PYTHONIOENCODING=utf-8 python tools/build_facility_geo_linkage.py

# 境界GeoJSON（要 Node.js・要 ksj/A38-20 zip = Git管理外。CIでは実行されない）
PYTHONIOENCODING=utf-8 python tools/build_iryoken2_geojson.py    # → iryoken2_A38-20.geojson（335二次医療圏）
PYTHONIOENCODING=utf-8 python tools/build_area_boundaries.py     # → area_boundaries_R7.geojson（339構想区域・可視化用）

# 可視化サイト向け表示用データセット（→ area_indicators_R7.json）
PYTHONIOENCODING=utf-8 python tools/build_web_data.py
PYTHONIOENCODING=utf-8 python tools/build_web_demand.py  # → area_demand_R7.json（医療需要推計）

# テスト
pytest
```

`doc/JOIN_VERIFICATION.md` は `tools/verify_area_join.py` の**生成物**。手で編集しないこと。

CI は push・pull_request ごとに `test-pipeline.yml`（pytest・`web/` の typecheck/test/build）と `verify-data.yml`（生データのSHA-256検証）を実行する。`ksj/A38-20` はGit管理外のためCIには存在しない。**この zip に依存するスクリプト・テストを書くときは、CIで落ちないよう `skipif` でスキップ可能にすること。**

`main` への push では `deploy-pages.yml` が `web/` をビルドして GitHub Pages へ自動デプロイする（要: リポジトリ Settings → Pages の Source を "GitHub Actions" に切り替え。詳細は README「GitHub Pages への公開」）。

可視化サイト（`web/`）はリポジトリルートではなく `web/` 内で実行する:

```bash
cd web
npm ci             # 依存関係のインストール
npm run dev        # 開発サーバ（predev が sync-data を自動実行）
npm run build      # 型チェック(tsc --noEmit) + Vite ビルド（prebuild が sync-data を自動実行）
npm run test       # vitest
npm run typecheck  # tsc --noEmit のみ
```

## 可視化実装で判明した罠

`web/` の実装（M3・M4）で踏んだもので、次に同じUIを触る人が必ず再発させる類のもの。

1. **MapLibre の `querySourceFeatures` は表示範囲外のタイルを見ない**: 区域検索など「今表示されていない区域」を選ぶ用途には使えない。選択と bbox は別途バンドルしたインデックス（`area_index.json`）から解決する。
2. **`step` 式の stop は厳密昇順でなければならない**: 分位境界は実データで重複する（高度急性期の実績は339区域中69区域が0床なので下位2境界が同値）。重複を潰して区分数を減らし、地図と凡例を同じ境界から生成すること。
3. **スタイルに `glyphs` を置かない（＝外部フォント配信に依存しない）と `symbol`（テキスト）レイヤが使えない**: 区域名はツールチップ・パネル・検索で見せる。
4. **陸と海は塗りの色では分けられない**: 発散配色の中立 `#e1e0d9` も連続配色の淡端 `#cde2fb` も海 `#dde5ec` に対して 1.04:1 しかなく、海の明度をどう選んでもランプのどこかと必ず衝突する。塗りの下に太い線を敷き、内陸は隣接区域の塗りで覆わせて外周だけを縁として残す（ケーシング）。
5. **React 18 StrictMode では map が「生成→破棄→生成」される**: 破棄済みインスタンスのイベントを弾かないと開発時に正常な地図の上へ誤ったエラー表示が出る。クリーンアップで ref を先に null にしてから `map.remove()` し、ハンドラ側で現行インスタンスか確認する。
6. **maplibre-gl の型定義は `error` イベントを DOM の `ErrorEvent` に解決するため `e.sourceId` が型に無い**（実行時には存在する）。`tsconfig` は `allowJs: true` が必要（vitest から `scripts/lib/*.mjs` を import するため）。
7. **MapLibre のフィーチャプロパティはフラットなスカラーのみにする**: クリックイベントで受け取る properties はネストしたオブジェクトが文字列化される。
8. **`web/src/generated/` はGit管理外なので、それを読む npm script には必ず `pre*` フックを付ける**: `predev`・`prebuild`・`pretypecheck` が `sync-data` を呼ぶ。付け忘れると手元（生成物が残っている）では通り、まっさらなチェックアウト＝CI初回だけ落ちる。**`web/` に新しい script を足すときは、生成物を必要とするか確認すること。** `npm run test`（vitest）には `pre*` が**無い**ので、**テストから `src/generated/*` を import してはいけない**（インラインのフィクスチャで書く）。
9. **年度のような可変軸を地図に載せる指標は、分位ではなく固定境界にする**（M4）: 分位だと年度を切り替えるたびに閾値が動き、同じ値が別の色になって時系列の比較にならない。需要の2024年度比は `DEMAND_RATIO_BIN_EDGES = [0.67, 0.83, 0.95, 1.05, 1.2, 1.5]`（1.0中心・ほぼ乗法対称）に固定し、在宅（実データ0.76〜2.02倍）・外来（0.51〜1.23倍）の全年度を1つのスケールで覆っている。
10. **`area_map.json` のフラットなプロパティ名は `web/scripts/lib/merge.mjs`（生成側）と `web/src/lib/metrics.ts`（読み側）の2箇所に分かれる**（M4）: どちらもキー生成関数（`demandValueKey`/`demandRatioKey`）を export し、**両者が同じ文字列を返すことを vitest で検証**している。片方だけ変えると型エラーにならず、地図が無色になるだけで静かに壊れる。
11. **表示用JSONを増やすと metadata の形は揃わない**（M4）: `area_demand_R7.json` は原典が2シートあるため `source_sheet`・`original_title` が**配列**、入力CSVが2本あるため `processing.caveat` が**オブジェクト**（`area_indicators_R7.json` はどちらも文字列）。`types.ts` で `AreaIndicators*` 型を使い回さず別型にすること。**React はオブジェクトをそのまま描画できない**ので、出典表示で必ず踏む。

## ドキュメント

ドキュメントは `doc/` に置く（README・CLAUDE.md はルート）。要件定義は `doc/REQUIREMENTS.md`、データ来歴は `doc/DATA_SOURCES.md`、構想区域と境界の突合検証は `doc/JOIN_VERIFICATION.md`（生成物）、医療機関とP04の名寄せ結果は `doc/FACILITY_LINKAGE.md`（生成物）。

## 現状

要件定義済み（`doc/REQUIREMENTS.md`）。

**M1「パーサ基盤 + 都道府県データ」完了**: 各パーサが共用する基盤（`tools/lib/provenance.py` = 完全性検証・由来メタデータ付きCSV出力、`tools/lib/codes.py` = コード正規化）と、都道府県別病床数のパーサ（`tools/parse_prefecture_beds.py`）・pytest によるテスト（`tools/tests/`）・CI（`.github/workflows/test-pipeline.yml`）。

**M2「構想区域データ + 境界突合」完了**:
- 帳票走査の共通基盤を `tools/lib/layout.py`・`tools/lib/block_report.py` に抽出（都道府県パーサも載せ替え済み）
- 構想区域パーサ `tools/parse_area_beds.py` → `area_beds.csv`（18,645行）・`area_bed_report_rate.csv`（3,051行）・`area_basic.csv`（339行）
- 突合検証 `tools/verify_area_join.py` → `doc/JOIN_VERIFICATION.md`・`area_geo_join.csv`。**331区域一致／三重県8区域のみ差異**という結論と全根拠はこのレポートにある
- 三重県の市町対応表を公式一次資料（`mie/001092203.pdf`）から確定し、5系統の突合で転記を検証（`tools/build_mie_area_municipalities.py`）
- 可視化用の339構想区域境界 `data/processed/area_boundaries_R7.geojson`（`tools/build_area_boundaries.py`）

**M3「最小の公開サイト」完了**:
- 可視化サイト本体を `web/`（Vite + React + MapLibre GL）に実装。339構想区域のコロプレス地図・区域パネル・区域検索・凡例・出典表示
- 指標は「2025年実績 vs 2025年必要数」に限定（`tools/build_web_data.py` → `data/processed/area_indicators_R7.json`。年度が揃い、かつ2024実績の既知欠陥を踏まない唯一の組み合わせ）
- `web/scripts/sync-data.mjs` が `data/processed/` を正本として `web/src/generated/` を生成（詳細は「データ構成」節の `web/` 参照）
- CI に `web/` の typecheck・vitest・build を追加（`test-pipeline.yml`）、GitHub Pages への自動デプロイを追加（`deploy-pages.yml`）
- 実装で判明した罠は「可視化実装で判明した罠」節に記録

**M4「医療需要推計 + 年度スライダー」完了**:
- 需要推計パーサ `tools/parse_demand_forecast.py` → `demand_forecast.csv`（4,068行 = 339区域×2区分×6年度）・`demand_population.csv`（339行）。両シートの区域名・都道府県名を `area_basic.csv` とも相互にも突合して検証する
- 表示用データセット `tools/build_web_demand.py` → `data/processed/area_demand_R7.json`（検証10項目。**基準年2024の値が全区域×区分で0でないことをビルド時に担保**し、表示側の0除算・null分岐を不要にしている）
- `web/` に指標セレクタの需要2区分（在宅（訪問診療）・外来）と**年度スライダー**（2024→2050の6段階）を追加。**地図の主表示は2024年度比の変化率**（絶対値はレセプト件数/月で区域の人口規模に支配されるため、地図には出さずツールチップとパネルで見せる）
- 配色は病床の過不足率と同じ発散7色を再利用し、境界のみ需要用に固定（罠9参照）
- 出典表示に需要推計のブロックを追加（原典2シート・入力CSV2本ぶんの注記をすべて表示）

**M5前半「医療機関パーサ + P04名寄せ」完了**（UIは未着手）:
- 医療機関パーサ `tools/parse_facility_beds.py` → `facility_basic.csv`（11,760施設）・`facility_observations.csv`（246,960行 = 施設×21指標のlong形式。20.5MB）・`facility_functions.csv`（7,574行）。分割の原則は「1施設1行の識別情報はwide、反復次元を持つものはlong」
- 名寄せ `tools/build_facility_geo_linkage.py` → `facility_geo_linkage.csv`・`doc/FACILITY_LINKAGE.md`。**11,760件中10,244件（87.1%）に座標を付与**（完全一致9,582＋接尾一致662）。残りは `candidate_only` 656件・`unmatched` 860件で**座標を与えない**
- 設計方針は「マッチ率ではなく誤結合の少なさと監査可能性を最適化する」。`match_status`（状態）・`match_method`（方法）・`reason_code`（理由）・`candidate_count` を分けて出力し、strict（完全一致）だけに絞り込めるようにしてある
- 踏んだ罠は「外部データとの名寄せ（P04）の罠」節に記録

**未実装**: 流入流出（001723366）のパーサ、M5後半のUI（医療機関ポイント・区域パネルの医療機関一覧）、M6（CSVダウンロード）。
