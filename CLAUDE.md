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
| 001723366.xlsx | （R6版なし） | 構想区域間の患者流入率・流出率（2シート「流入率」「流出率」、各22,035行＝**65行×339ブロック**。1ブロック内に3区分の表が**横並び**） |
| 001728462.xlsx | （R6版なし） | 在宅（訪問診療）・外来の医療需要推計 2024→2050年度（2シート） |

**別添４②（都道府県）・別添４③（構想区域）はR6版も出力対象**で、`tools/parse_prefecture_beds.py`・`tools/parse_area_beds.py` が1本のCSVにR7・R6を`published_fy`列で並存させる（M9）。別添５②（医療機関個票）はR6のファイル自体は存在するが、`tools/parse_facility_beds.py` はまだR7のみに対応する。

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

`data/processed/area_indicators_R7.json`（`tools/build_web_data.py` が生成、339構想区域の2025年実績vs2025年必要数）・`data/processed/prefecture_indicators_R7.json`（`tools/build_web_prefecture.py` が生成、47都道府県+全国の病床と需要）・`data/processed/prefecture_boundaries_R7.geojson`（`tools/build_prefecture_boundaries.py` が生成、47都道府県）・`data/processed/area_demand_R7.json`（`tools/build_web_demand.py` が生成、339構想区域×2区分×6年度の医療需要推計）・`data/processed/area_yoy_R6_R7.json`（`tools/build_web_yoy.py` が生成、339構想区域のR6→R7年度間比較。見込量2025(R6)・実績2025(R7)・実績2024(R6)）・`data/processed/area_facilities_R7.json`（`tools/build_web_facilities.py` が生成、11,760医療機関×21指標）・`data/processed/area_flow_R7.json`（`tools/build_web_flow.py` が生成、339区域×2方向×3区分の患者流入出）・`data/processed/area_boundaries_R7.geojson`、および加工済みCSV16本＋各`.meta.json`（`data/processed/*.csv`。一覧は `web/scripts/lib/bundle.mjs` の `BUNDLE_CSV_FILES` が持つ）を正本として、`web/scripts/sync-data.mjs` が `web/src/generated/`（**Git管理外**、`predev`/`prebuild` から自動実行）・`web/public/facilities/`・`web/public/flow/`・`web/public/downloads/`（いずれも同じくGit管理外）へ表示用データを合成する:

| 生成物 | 用途 |
|---|---|
| `area_indicators.json` | 正本の忠実コピー（改行のみLF正規化）。**バンドルに取り込み**、パネル・検索・分位計算・出典表示に使う |
| `area_demand.json` | 需要推計の正本の忠実コピー。**バンドルに取り込み**、パネルの需要テーブル・年度ラベル・出典表示に使う |
| `area_yoy.json` | R6→R7年度間比較の正本の忠実コピー（改行のみLF正規化、約290KB）。**バンドルに取り込み**、パネルの年度間比較テーブル・出典表示に使う |
| `area_map.json` | 境界GeoJSON + フラット化した指標プロパティ（約4.9MB）。**`?url` インポートでファイルURLのみをバンドルに含め、MapLibreにfetchさせる**（メインスレッドでパースしない）。需要は `<区分>_<年>`（値）と `<区分>_r_<年>`（2024年度比）の24プロパティ、年度間比較は分母0の機能を除いたプロパティを持つ |
| `area_index.json` | 選択・bbox解決用の軽量インデックス（`area_code`・`boundary_source`・bboxのみ）。**バンドルに取り込み**、地図の表示状態に依存せず区域選択を解決する |
| `facility_summary.json` | 医療機関の区域別件数＋21指標の定義＋`value_status` のラベル＋出典（約38KB）。**バンドルに取り込み**、shard取得前でも件数を出せるようにし、出典欄と指標ラベルの正本にする |
| `public/facilities/<区域コード>.json` × 339 | 区域ごとの医療機関の全データ（21指標＋機能＋座標）。**バンドルせず、区域を選んだときに1本だけfetchする**（合計6.8MB・gzipで中央値2.2KB／最大24KB） |
| `public/flow/area_flow.json` | 患者の流入出の正本の忠実コピー（約499KB・gzip約126KB）。**バンドルせず、区域を初めて選んだときに1回だけfetchして以後は使い回す**。339分割していないのは、全体で1本しかなく取得先が選択に依存しないため（罠14の競合が原理的に起きない） |
| `public/downloads/chiiki-iryo-koso_processed-csv_R6_R7.zip` | 加工済みCSV16本＋各 `.meta.json`＋`README.md`＋`MANIFEST.tsv`（計34エントリ・約2.4MB）。**バンドルせず、リンクからブラウザに直接ダウンロードさせる** |
| `public/downloads/area_boundaries_R7.geojson` | 正本の忠実コピー（単体利用向け。ZIPには入れない） |
| `src/generated/download_manifest.json` | ZIP/GeoJSONのサイズ・SHA-256・収録CSV一覧（約3.9KB）。**バンドルに取り込み**、一括DLセクションの表示に使う |
| `prefecture_indicators.json` | 都道府県（概観レイヤ）の正本の忠実コピー（約75KB）。**バンドルに取り込み**、都道府県パネル・分位計算・出典表示に使う |
| `pref_map.json` | 都道府県境界 + フラット化した指標プロパティ（約2.5MB・gzip650KB）。`area_map.json` と同じく**`?url` インポートでMapLibreにfetchさせる**。プロパティ名も `a_/n_/r_<機能>`・`<区分>_<年>` と区域側と同一 |

正本は `data/processed/` の1箇所のみ。`data/processed/` を再生成したら `sync-data`（＝`predev`/`prebuild`）が自動で追随する。

**CSVを1本増やすと `web/scripts/lib/bundle.mjs` の `BUNDLE_CSV_FILES` への追加が必須**（`sync-data` がこの配列と `data/processed/*.csv` の実在一覧を突合してビルドを落とす）。加えて**「CSV○本」「○エントリ」と件数を書いた記述がコード・コメント・テスト・ドキュメントに散っている**ので、`grep -rn '<旧件数>本'` で全て直すこと（M7で13→15本にしたとき、`bundle.mjs`・`bundle.test.ts`・`sync-data.mjs` のコメント・`types.ts` のJSDoc・`CLAUDE.md`・`README.md` の6か所に出現した）。

### パース時の注意（帳票形式のExcel）

- 需要推計（001728462）以外は**帳票レイアウト**（結合セル・複数行ヘッダー・区域ごとの繰り返しブロック）。`pandas.read_excel` の素朴な読み込みでは崩れるため、位置ベースで抽出する。
- 001728462 は比較的整形済み: **4行目=年度ラベル行**（`2024年度`・`2030年度（現状投影）`…）、**5行目=見出し行**、データは6行目から339行（2シートともレイアウト同一・コード昇順）。年は列位置ではなく4行目の文字列から抽出すること（他の帳票と同じ規律）。**2024年度だけ「（現状投影）」が付かない**ため、解釈せず原文を `year_label` 列に保持している（`tools/parse_demand_forecast.py`）。
- **需要推計の単位・基準の罠**: 値は「**レセプト件数/月**」であって患者数・人数ではない。人口列も「人口(2024年**度**)」と「人口(2040年)」で年度/年が混在し、さらに `area_basic.csv` の `population_2020`（国勢調査）とは出典自体が別。**画面で併記するときは必ず出典と基準年を書き分けること。**
- **基準人口の年が公表物どうしで食い違っている罠**: 001728462.xlsx の5行目の見出しは `人口(2024年度)` だが、**同じ公表回の公式説明書 001728467.pdf は同じ列を「人口(2025年)」とし、出典を総務省「住民基本台帳人口」（2025年）と明記している**（2040年の列は両者とも2040年で一致し、説明書の出典は社人研「日本の地域別将来推計人口」2040年推計）。**どちらかが誤っている疑いがあるが公表物からは決められない**ため、列名 `population_2024` はExcelの見出し表記のまま据え置き、**説明書側への読み替えはしない**。`known_issues` の `demand_population_base_year_conflict` に記録済み（下記「原典側の欠陥の記録先」）。**画面で人口を年と結び付けて見せるときは、この不一致を明示すること**（`AreaPanel` は基準人口のラベルから年を外し、※注記で不一致を説明している）。なお `EXPECTED_HEADER_AE` が見出し文字列を検証しているので、将来Excel側が2025年表記へ直ればパーサが落ちて気付ける。
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
- **R6の②の流出入はR7と別概念**: R7はR列(18)に推計流出/流入患者割合の2値（0〜1）、R6はQ列(17)に「（一般病床患者流出入）」の単一値で**値域 -0.893〜0.434 と負値を取る**。`area_basic.csv` では `net_flow_rate`（R6のみ）と `outflow_rate`/`inflow_rate`（R7のみ）に分けてある。**並べて比較・可視化してはならない**（`area_basic_r6_net_flow_rate_different_concept` 参照）。
- **R6原典に実績セルの欠測が1件ある**: 区域コード0102「南檜山」の高度急性期・2015実績。`EXPECTED_MISSING_BEDS` と完全一致することを検証しており、**合計から逆算して埋めない**（実データは 399 = 202+0+197 なので0と逆算できてしまうが、やらない）。
- **R6の②も `parse_sheet(ws, published_fy)` で読める**（M9でR6を出力対象化した。かつては読めなかった）: 上記2点（流出入の別概念・実績欠測1件）は `SOURCES[<年度>]["flow_items"]` と `EXPECTED_MISSING_BEDS` に構造化して吸収しており、列位置は都度サブヘッダー文字列から解決する。
- **流入率・流出率（001723366）にはブロック番号列が無い**: 1ブロック65行×339ブロックだが、**区域サマリ行のA列は都道府県コード（1〜47）で連番ではない**（北海道の21区域はすべて `1`）。連番検証を前提とする `iter_fixed_blocks()` は使えないので、`tools/parse_patient_flow.py` は位置を算術生成し、**(1) グリッドが `ws.max_row`(22035)にちょうど一致 (2) A列の都道府県コードが `area_basic.csv` と一致 (3) 339区域コードが重複なく `area_basic.csv` と完全一致** の3点でブロック位置のずれを担保している。`assert_repeated_header()` は使える。
- **同じ帳票で1ブロック内に3つの表が横並びになる**（同上）: 区分ヘッダーは B列(2)=`高度急性期+急性期`・J列(10)=`包括期`・R列(18)=`慢性期` で、各表は6列（都道府県コード／都道府県名／構想区域コード／構想区域名／空／率）。行数は表ごとに独立（実測 0〜50行）。
- **`包括期` は病床機能報告の4区分（高度急性期／急性期／回復期／慢性期）に存在しない区切り**。流入出の3区分と病床の4区分を機械的に対応づけないこと。
- **この帳票のセンチネルは Excel のエラー値 `'#VALUE!'`**（`'XXX'`・`'*'` ではない）: 流出率シートの慢性期で2区域（`1313` 島しょ・`4207` 上五島）だけ、**行まるごと**（相手区域コード・名称・率のすべてが）`'#VALUE!'`／空になっている。`value_status` で `observed` と区別して保持する。
- **流入率・流出率は合計しても1にならない**: 原典が「一定数以上の患者がいる区域のみ表示」しているため（実測の最小は0.517）。**足りない分は0ではなく打ち切り**なので、画面でもCSVでも「表示分以外」として明示すること。
- **「全体の流入率／流出率」は3区分の合計ではない**: 339区域×2シート=678件すべてで `1 −（高度急性期+急性期の自区域シェア）` と**厳密に一致**する。「全体」の語のまま画面に出さないこと（`known_issues` の `flow_overall_rate_equals_acute_phase_complement`）。パーサはこの関係が崩れたら中断する。
- **この流入率・流出率（NDB・2024年度）は `area_basic.csv` の推計流出／流入患者割合（患者調査・2023年）とは別物**。原典の注記と出典説明書（`R7/001723348.pdf`）が明示的に「異なる」と述べている。画面で並べるときは出典と対象年を必ず書き分ける。

### 外部データとの名寄せ（P04）の罠

医療機関に座標を与える `tools/build_facility_geo_linkage.py`（M5）で踏んだもの。結論と全実測値は `doc/FACILITY_LINKAGE.md`（生成物）にある。

- **P04には都道府県コードも市区町村コードも無い**（住所文字列のみ、しかも原則として都道府県名を含まない）。市区町村名だけでは同名市区町村（府中市＝東京/広島、伊達市＝北海道/福島）を切り分けられないので、**区域の確定は住所ではなく点-多角形判定**（`area_boundaries_R7.geojson` に対するレイキャスティング）で行う。
- **政令指定都市の住所は市名を省いて区から始まることがある**（実測3,178件）: `港北区小机町…` は `横浜市港北区` と前方一致しない。**区名がExcel側市区町村の末尾と一致するか**も見ること。これを入れないと神奈川県のマッチ率が91%→53%まで落ち、地図が「神奈川には病院が少ない」という誤った印象を与える。
- **法人格語の除去は、名称を施設種別語だけに削ってしまうことがある**: `厚生連クリニック` → `クリニック` となり `…ロビンの空クリニック` の末尾と一致して誤結合する。**除去後に種別語しか残らないなら除去しない**こと（残余が1文字でも残るなら除去してよい。`医療法人社団森クリニック`→`森クリニック` は正しい）。
- **`p04_beds` は精神・結核病床を含む総病床数で、Excel（病床機能報告）の一般・療養病床とは定義が違う**: 突合の妥当性検証には使えず（乖離228件の大半は精神科病院）、画面で並べて見せてもいけない。
- 自動採用は「正規化名の完全一致または接尾一致」＋「区域ポリゴン内で一意」＋「市区町村整合」＋「一対一制約」を**全て**満たす場合のみ。あいまい一致（`candidate_only`）には座標を与えない（`doc/REQUIREMENTS.md` §4.3「位置の推測はしない」）。

### 原典側の欠陥の記録先（`known_issues`）

**厚労省の公表物そのものが抱える欠陥（値の誤り・複製・未算出・公表物どうしの矛盾）は、値を補正せず `known_issues` へ構造化して記録する。** 散文の `caveat` に書き足さないこと（後でまとめて扱えなくなる）。

- 定義場所は各パーサの `KNOWN_ISSUES` 定数（`tools/parse_area_beds.py`・`tools/parse_demand_forecast.py`・`tools/parse_facility_beds.py`・`tools/parse_patient_flow.py`）。1件 = `id`（安定した英数字キー）・`scope`（`csv` と対象列/区域）・`summary`・`evidence`（根拠を配列で）・`action`（このリポジトリでの扱い）。
- 導線は **KNOWN_ISSUES → 各CSVの `meta.json` → 表示用JSON → 画面の出典欄「データの既知の問題」** で、途中に手作業はない。`scope.csv` で行き先が決まる（`parse_demand_forecast.py` の `known_issues_for()`）ので、**新しい欠陥は `KNOWN_ISSUES` へ1件足すだけでよい**。
- `write_csv_with_meta(known_issues=None)` は `known_issues` キー自体を出力しない（既存出力とのバイト一致を保つため）。空リストと `None` を取り違えないこと。
- 表示用JSON側は `build_web_data.py`・`build_web_demand.py`・`build_web_flow.py` が入力CSVの `meta.json` から集約する（**その場で新規に書き足さない**。ただし「表示用データセットを作る過程で下した判断」は例外で、`area_indicators_2024_actual_excluded` がその例）。
- 画面側は `SourceNotes.tsx` の `KnownIssues` が病床・需要・医療機関・患者の流入出を同じ形で描画する。**描画してよいのは `summary`・`action` の文字列だけ**（`scope` はオブジェクト・`evidence` は配列なので、そのまま描画すると罠11を踏む）。
- 現在の登録件数は病床3件（うち1件は `build_web_data.py` 側）・需要1件・医療機関1件・患者の流入出2件。テストが形（id重複なし・必須キー・`scope.csv` の実在）を固定しているので、形を崩すと落ちる。

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
# パーサ（生データ → data/processed/*.csv）。①②（都道府県・構想区域）は既定でR7+R6の両方を出力し、published_fyで1本のCSVに並存させる（--source all|R7|R6、既定all）
PYTHONIOENCODING=utf-8 python tools/parse_prefecture_beds.py     # 都道府県 → prefecture_*.csv
PYTHONIOENCODING=utf-8 python tools/parse_area_beds.py           # 構想区域 → area_*.csv
PYTHONIOENCODING=utf-8 python tools/parse_demand_forecast.py     # 構想区域別医療需要推計 → demand_*.csv
PYTHONIOENCODING=utf-8 python tools/parse_facility_beds.py       # 医療機関個票（339シート）→ facility_*.csv（R7のみ）
PYTHONIOENCODING=utf-8 python tools/parse_patient_flow.py        # 患者の流入率・流出率 → patient_flow*.csv（要 area_basic.csv）

# 三重県の市町対応表（→ data/reference/mie_area_municipalities.csv）
PYTHONIOENCODING=utf-8 python tools/build_mie_area_municipalities.py

# R6生データの入手元確認（→ doc/DATA_SOURCES.md の記載を裏付け。要ネットワーク、CIでは実行されない）
PYTHONIOENCODING=utf-8 python tools/verify_r6_bundle.py

# 突合検証（→ data/processed/area_geo_join.csv と doc/JOIN_VERIFICATION.md）
PYTHONIOENCODING=utf-8 python tools/verify_area_join.py

# R6→R7の年度間比較の検証（→ data/processed/area_yoy_diff.csv と doc/YOY_VERIFICATION.md）
PYTHONIOENCODING=utf-8 python tools/verify_yoy_R6_R7.py

# 医療機関とP04（国土数値情報）の名寄せ（→ facility_geo_linkage.csv と doc/FACILITY_LINKAGE.md）
PYTHONIOENCODING=utf-8 python tools/build_facility_geo_linkage.py

# 境界GeoJSON（要 Node.js・要 ksj/A38-20 zip = Git管理外。CIでは実行されない）
PYTHONIOENCODING=utf-8 python tools/build_iryoken2_geojson.py    # → iryoken2_A38-20.geojson（335二次医療圏）
PYTHONIOENCODING=utf-8 python tools/build_area_boundaries.py     # → area_boundaries_R7.geojson（339構想区域・可視化用）

# 都道府県境界（要 Node.js のみ。入力は上記のコミット済みGeoJSONなのでksj/A38-20は不要）
PYTHONIOENCODING=utf-8 python tools/build_prefecture_boundaries.py  # → prefecture_boundaries_R7.geojson（47都道府県）

# 可視化サイト向け表示用データセット（→ area_indicators_R7.json）
PYTHONIOENCODING=utf-8 python tools/build_web_data.py
PYTHONIOENCODING=utf-8 python tools/build_web_demand.py      # → area_demand_R7.json（医療需要推計）
PYTHONIOENCODING=utf-8 python tools/build_web_facilities.py  # → area_facilities_R7.json（医療機関×21指標）
PYTHONIOENCODING=utf-8 python tools/build_web_yoy.py          # → area_yoy_R6_R7.json（R6→R7年度間比較）
PYTHONIOENCODING=utf-8 python tools/build_web_prefecture.py  # → prefecture_indicators_R7.json（都道府県。要 prefecture_boundaries_R7.geojson）
PYTHONIOENCODING=utf-8 python tools/build_web_flow.py        # → area_flow_R7.json（患者の流入率・流出率）

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
11. **表示用JSONを増やすと metadata の形は揃わない**（M4）: `area_demand_R7.json` は原典が2シートあるため `source_sheet`・`original_title` が**配列**、入力CSVが2本あるため `processing.caveat` が**オブジェクト**（`area_indicators_R7.json` はどちらも文字列）。`types.ts` で `AreaIndicators*` 型を使い回さず別型にすること。**React はオブジェクトをそのまま描画できない**ので、出典表示で必ず踏む。`area_facilities_R7.json` はさらに形が違い、`source`（001723127.xlsx由来）に加えて **`geo_linkage_source`（P04名寄せ由来で `source_file`/`source_sha256` を持たない別の形）を並置**し、`processing.caveat` は入力CSV4本ぶんの4キーを持つ。
12. **数MB規模の表示用JSONは「1区域1行」の決定的フォーマットで出す**（M5後半）: `area_facilities_R7.json` は compact な一行JSONだと6.6MB、`indent=2` だと15.1MB。前者は git diff が全く読めず「再生成でどの区域が変わったか」を追えない。`metadata`/`metrics` だけ `indent=2` にし、`areas` は要素ごとに1行の compact JSON として書く（`build_web_facilities.py` の `dump_json()`）。サイズは compact とほぼ同じで、区域単位の差分が読める。**独自整形は決定的にすること**（バイト一致の再現性テストが前提）。
13. **遅延fetchする生成物は `web/public/` に置き、URLは `import.meta.env.BASE_URL` から組む**（M5後半）: `import.meta.glob('...', {query:'?url', eager:true})` は一見きれいだが、(a) Vite は既定で4KB未満の asset を base64 で JS にインライン化するため小さい shard が初期JSに埋め込まれ、(b) URLを得るのに `import: 'default'` が要り、(c) 339件ぶんのURL表が初期JSに載る。`public/` なら Vite が dist へコピーするだけ。ただし `base: './'` なので**絶対パス `/facilities/…` を書くと GitHub Pages のサブパスで404になる**。また `sync-data` は書き出し前にディレクトリを一掃すること（区域が減ったとき古い shard が dist に残る）。
14. **区域切替の競合状態は `AbortController` だけでは潰せない**（M5後半）: (a) キャッシュヒット時はそもそも fetch が起きず、(b) `abort()` 時点でネットワーク取得が既に完了していれば `.then` が先に解決しうる。**応答を反映する直前に「今も同じ区域が選ばれているか」を確認する**こと（`facilityShard.ts` の `createFacilityShardLoader`）。この判定を React から切り離した純関数の状態機械にしておくと、jsdom無しの vitest でもテストできる。
15. **HTMLテーブルの展開行は他の行と列幅を共有する**（M5後半）: 施設一覧の折りたたみを `<tr><td colSpan>` で作ると、数値列（`white-space: nowrap`）の幅に引きずられて、幅360pxのサイドパネルの外へ内容が押し出される。`tsc`・vitest・`vite build` はどれも検出せず、**実機で見て初めて分かる**。`position: sticky; left: 0` と幅の上限で閉じ込める。
16. **`mousemove` をレイヤごとに複数登録すると、どちらが最後に状態を書くかがレイヤ登録順に依存する**（M5後半）: 施設ポイントは区域ポリゴンの真上に乗るので同じ座標で両方がヒットし、ツールチップが二重に出うる。**単一の `mousemove` で `queryRenderedFeatures` を優先順に呼び、常にどちらか一方だけを選ぶ**（既存の `click` ハンドラと同じ書き方）。canvas外へ一気に抜けた場合の保険として `mouseout` も要る。
17. **ダウンロード用CSVと正本CSVは別物にする**（M6）: 正本 `data/processed/*.csv` は BOMなし・LF（バイト一致の再現性テストの前提）。画面から落とすCSVはExcelで開く用途なので BOM付き・CRLF。同じ既定値で両方を作ろうとしないこと。ZIPに入れるのは**正本のバイト列そのまま**（BOM付与も改行変換もしない）で、ZIP内CSVのSHA-256が `data/processed/` と一致することが真正性の担保になる。
18. **画面表示用のフォーマッタをCSVに流用しない**（M6）: `formatInteger()` は3桁区切りを入れるため、CSVに使うと `1,234` がCSVの区切りと衝突する（クォートされて数値として読めなくなる）。CSVは生値を出し、丸めるのは派生値（比・変化率）だけにする。
19. **`tsconfig` に `noUncheckedIndexedAccess` が無い**（M6）: `Record<string, number>` への添字アクセスが実行時 `undefined` を返す経路（例: 年度キーの取り違え）が型検査を素通りし、そのままCSVへ文字列 `"undefined"` が静かに混ざる。シリアライザ側（`toCsvText`）で `undefined` を検出して落とすこと。
20. **公表物が言っていない年を出力に足さない**（M6）: 推計流出/流入患者割合には原典もmeta.jsonも対象年を書いていないので、CSVの `year` 列は空欄にする（基準人口の年の不一致と同じ理由。断定すると公表物にない主張になる）。
21. **自前のZIPは書きっぱなしにしない**（M6）: 依存を増やさないため `node:zlib` だけでZIPを組み立てているが、書いた直後に読み直して全エントリが元データとバイト一致することを検証する。決定性のためタイムスタンプは固定値にする（生成日時を入れると同じ入力でもバイトが変わる）。
22. **幅360pxのパネルに4列テーブルを `width: 100%` で押し込むと列が潰れる**（M6）: 「内容」列が1〜3文字ずつ折り返して読めなくなる。`width: max-content; min-width: 100%` にして、はみ出しは `overflow-x: auto` のラッパへ逃がす（罠15と同じく、実機で見るまで分からない）。
23. **上位階層の境界は、原典から作り直さず下位階層の境界をディゾルブして作る**（M8）: 都道府県境界を `ksj/A38-20` から都道府県単位で作り直すと、簡略化（Visvalingam）の挙動が入力ポリゴンの粒度に依存するため、同じ海岸線が構想区域レイヤと微妙に食い違う。区域の塗りの上に県境を重ねる描き方では、これが「県境が海へはみ出す／内陸へ食い込む」という**目に見える破綻**になる。コミット済みの `area_boundaries_R7.geojson` を `pref_code` でディゾルブすれば、県境は必ず区域境界の部分集合になり、しかも入力がGit管理下なので `ksj/A38-20`（1.13GB・Git管理外）に依存せず再生成できる。面積は全国合計・県別とも実測差 0.0000%（＝純粋な集合演算）。
24. **階層を増やしたら分位・凡例の文言・ホバー状態を階層ごとに分ける**（M8）: (a) 分位（`actual`/`need`）は47都道府県と339区域で別物なので、母集団を level で切り替えないと凡例の区分が実データの分布から外れる。(b) 凡例・注記の「区域」という語と件数（「339区域の…」）は都道府県表示では嘘になる。(c) **表示単位の切替はボタン操作なのでカーソルは地図の外にあり、`mousemove` が追加発火しない**ため、切替時に明示的に `setHover(null)` とホバー輪郭フィルタの解除をしないと、前の階層のツールチップだけが残る（罠16の親戚）。
25. **層をまたぐ値は「公表値」と「本リポジトリの集計値」を混ぜない**（M8）: 病床は厚労省が都道府県別を公表している（001722915.xlsx）が、医療需要（001728462.xlsx）は構想区域単位しか無い。同じパネルに並ぶ2つの表が、一方は公表値・もう一方は派生値になる。**派生であることは `known_issues` に構造化して記録し**（`prefecture_demand_aggregated_by_this_repository`）、値の真横にも注記を置く。合計は必ず**ソート済みの順序**で足すこと（集合やdictのイテレーション順に依存すると浮動小数点の末尾ビットが揺れ、バイト一致の再現性テストが壊れる）。
26. **選択区域を起点にした塗り分けは、フィーチャプロパティを増やさずに `match` 式で作れる**（M7）: 相手区域のコロプレスは、選択のたびに `['match', ['get','area_code'], コード, 色, …, 既定色]` を組み直して `setPaintProperty` すれば済み、`area_map.json`（＝`merge.mjs` と生成物）に手を入れる必要がない。相手区域は1区域あたり10〜20件なので式も小さい。ただし**ケースが0個の `['match', input, fallback]` はMapLibreで不正**なので、塗る対象が1件も無いときは式ではなく単色の文字列を返すこと。境界は分位ではなく固定にする（罠9と同じ理由）。
27. **遅延取得する表示用データは「区域ごとに分割」とは限らない**（M7）: `area_flow.json` は339区域ぶん全体で499KB（gzip 126KB）の1本。**取得先が選択に依存しないので罠14の競合状態が原理的に起きず**、`facilityShard.ts` のような状態機械は要らない（Promiseを1つキャッシュするだけ）。分割するかどうかはサイズではなく「**取得先が選択に依存するか**」で決める。
28. **遅延取得したデータの出典は、取得が終わるまで画面に出せない**（M7）: `SourceNotes` の流入出ブロックは `flowMetadata` が null の間はブロックごと描画しない。要件§6「すべての可視化に出典を表示」は「**その可視化が出ている間は必ず出典も出ている**」ことで満たす。バンドル済みJSONと同じつもりで書くと未取得時に落ちる。
29. **構成比の横棒は、最大の要素にも必ず棒を描く**（M7）: 自区域内完結率（例 65.8%）にだけ棒が無く相手区域（数%）にだけ棒があると、視覚的な主従が逆転して構成比として読めない。**スケールは絶対（率×100%）に固定し、そのグループの最大値で正規化しない**（区域・区分を切り替えるたびに見た目の意味が変わるため）。罠15・22と同じく実機で見るまで分からない。
30. **`published_fy` で年度を並存させると、R7限定を暗黙の前提にしている下流が静かに壊れる**（M9）: `area_basic.csv` が678行になった瞬間、`verify_area_join.py`（`area_code` 重複で `ValueError`）・`build_area_boundaries.py`（同）・`build_web_data.py`（検証1）が落ちた。`verify_area_join.py` は `area_beds.csv`/`prefecture_beds.csv` も読んで都道府県へ集計しているので、**落ちずに集計値だけ静かに変わる経路もあった**。年度を足したら「R7だけを前提にしている消費者」を全部洗うこと。
31. **病床系CSVの `meta.json` の `source` は配列**（M9。`published_fy` 付き。他のCSVは dict のまま）: `meta["source"]["source_file"]` と書いている箇所が壊れる。実際に `verify_area_join.py` のレポート生成・`build_web_data.py`・`web/scripts/lib/bundle.mjs`（ZIP同梱READMEの出典グルーピング）の3箇所で踏んだ。**`source[0]` だけ見る回避も不可**（R6の出典が消える）。
32. **`known_issues` は消費側で `scope.published_fy` を見て絞る**（M9）: R6行についての欠陥を、R7行のみで構成される `area_indicators_R7.json` に載せると、画面の「データの既知の問題」が誤誘導になる。`published_fy` キーが無いものは両年度に当てはまるので残す。
33. **`published_fy` に無い値を発明しない**（M9）: 複数公表回にまたがる派生値（比など）に `'R6+R7'` のような値を入れると、利用者が `data/processed/*.csv` へ結合し直せなくなる。**横持ちなら列名側に由来を入れ**（`plan_2025_r6`・`actual_2025_r7`）、**長持ちなら空欄にして理由を note 列に書く**（罠20と同じ規律）。
34. **zipのエントリ名は言語エンコーディングフラグ（0x800）を見て復号を分岐する**（M9）: 立っていなければ `zipfile` は cp437 でデコードしたままなので `name.encode("cp437").decode("cp932")` で戻す。無条件に変換すると UTF-8 フラグ付きの zip で `UnicodeEncodeError` になる。
35. **配布物の名前に年度を入れたら、中身が変わったときに改名する**（M9）: 一括DL ZIP が `..._R7.zip` のままR6の行を含むと、名前が中身と食い違う。`BUNDLE_ROOT`/`BUNDLE_FILE_NAME` の1箇所を直せば `sync-data.mjs`・`download_manifest.json` は追随するが、`downloadAssets.test.ts` のリテラルと各ドキュメントの本数記述は手で直す必要がある。

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

**M5後半「医療機関UI」完了**:
- 表示用データセット `tools/build_web_facilities.py` → `data/processed/area_facilities_R7.json`（339区域・11,760施設・**21指標すべて**・約6.8MB）。検証13項目で中断する。`values`/`value_status` を21要素の配列で持ち、`metrics` が並び順を定義する（指標名をキーにしたオブジェクトだと15MB超になる）
- `web/scripts/sync-data.mjs` が正本を339分割して `web/public/facilities/<区域コード>.json` を書き、区域を選んだときに1本だけfetchする。**21指標を全部持ったまま、一度に全部は読み込まない**（gzipで中央値2.2KB／最大24KB）
- 区域パネルに医療機関一覧（既定は病床数6列、行を展開するとその施設の21指標すべてを5グループで表示）。グループ分けは `metrics[].metric` の文字列から機械的に導き、未知の指標は「その他」へ落として消さない
- 欠測は `—` ＋ 日本語ラベル（`title` と視覚的に隠したテキスト）で `'*'`（NDB非公表）・`'-'`・`未報告`・空欄を区別する。**座標を持たない1,516件も一覧には出す**（「地図に表示なし」バッジ付き。`doc/REQUIREMENTS.md` §4.3「位置の推測はしない」）
- 地図には**選択中の区域の施設のみ**を点で表示する（全国10,244点の一括表示はしない。要件 §3.2 のドリルダウンに沿い、座標の二重保持と低ズームでの過密表示を避けるため）。円の半径は病床数、病床数が欠測の施設も最小半径で描く（欠測を0床にしない）
- 実装で判明した罠は「可視化実装で判明した罠」節の12〜16に記録

**M6「CSVダウンロード + 加工データ一括配布」完了**: 要件 `doc/REQUIREMENTS.md` §3.3 の2方式をどちらも実装した。
- **①表示条件絞り込みCSV**（`web/src/lib/downloads.ts` の3関数、`web/src/lib/csv.ts` の `toCsvText` でシリアライズ）:
  - `buildAreaTableCsv` — 地図に表示中の指標（病床機能1つ or 需要区分1つ×年度1つ）を全339区域ぶん（Controls「表示中のデータをCSV」）
  - `buildAreaDetailCsv` — 選択中の区域1つの基礎情報・病床・医療需要推計をlong形式で（AreaPanel「この区域の指標をCSV」）
  - `buildFacilityCsv` — 選択中の区域の医療機関一覧×21指標をlong形式で（FacilityList「一覧をCSV」）。座標を持たない施設も行として出す
  - 3関数とも由来ヘッダー（`#`行、出典・出力条件・注記）をCSV本文の先頭に埋め込む（`buildPreamble`）。ダウンロード実行は `triggerDownload.ts` に分離
- **②加工済みデータ一括DL**: `web/scripts/sync-data.mjs` が `data/processed/` の加工済みCSV16本＋各`.meta.json`をZIP化し `web/public/downloads/chiiki-iryo-koso_processed-csv_R6_R7.zip`（34エントリ・約2.4MB）として書き出す。ZIP本体の組み立ては依存ゼロの自前実装（`web/scripts/lib/zip.mjs`）、MANIFEST.tsv・README.mdの内容は `web/scripts/lib/bundle.mjs`。`web/public/downloads/area_boundaries_R7.geojson`（正本の単体コピー）も同時に書き出す。画面側は `BulkDownload.tsx` が `download_manifest.json` を表示するだけで、ZIP自体はブラウザの通常のダウンロードに任せる（CSV本数・エントリ数・ファイル名はその後のM7・M9で上記の通り更新された）
- 実装で判明した罠は「可視化実装で判明した罠」節の17〜22に記録

**M8「都道府県階層（概観レイヤ）」完了**: 要件 `doc/REQUIREMENTS.md` §3.1 の3階層のうち未着手だった都道府県層を実装した。
- 境界 `tools/build_prefecture_boundaries.py` → `data/processed/prefecture_boundaries_R7.geojson`（47都道府県・約2.4MB）。**コミット済みの `area_boundaries_R7.geojson` を `pref_code` でディゾルブする**ので、`ksj/A38-20`（Git管理外）に依存せず再生成でき、県境が必ず区域境界の部分集合になる（罠23）。検証5項目、面積の実測差は全国合計・県別とも 0.0000%
- 表示用データセット `tools/build_web_prefecture.py` → `data/processed/prefecture_indicators_R7.json`（47都道府県＋`national`・約75KB）。検証13項目のうち中心は**検証8「都道府県の2025年病床が構想区域(area_beds.csv)の合計と完全一致する」**（470キー全一致）と**検証9「全国＝47都道府県の合計」**。厚労省の別々の公表ファイル（001722915.xlsx と 001723349.xlsx）の内部整合の確認でもあり、概観層と主表示層で数字が食い違わないことの担保
- **病床は厚労省の都道府県別公表値そのもの／医療需要と基準人口は構想区域からの集計（派生値）**。派生であることは `known_issues` の `prefecture_demand_aggregated_by_this_repository` に記録し、パネルの注記・凡例・出典欄へ自動で流している（罠25）
- `web/` に表示単位トグル（都道府県／構想区域）を追加。**構想区域表示中は県境を線で重ねる**（同じ `pref_map.json` を線レイヤとしてだけ使う）。都道府県パネルは病床5機能・需要2区分×6年度・全国（参考、折りたたみ）と「この県の構想区域を見る」ドリルダウン（区域へ切り替えて県のbboxへズーム）を持つ
- 全国は境界を持たない（47都道府県の和集合を描いても情報が増えないため）。`prefectures` 配列とは別の `national` キーに置き、都道府県を選んだときの参考値としてのみ表示する
- 分位・凡例の文言・ホバー状態は階層ごとに分ける（罠24）。配色（発散7色・固定境界）は区域層と共通なので、層を切り替えても同じ色は同じ比を意味する
- 実装で判明した罠は「可視化実装で判明した罠」節の23〜25に記録

**M7「患者の流入・流出」完了**:
- パーサ `tools/parse_patient_flow.py` → `patient_flow.csv`（10,408行 = 339区域×2方向×3区分×相手区域）・`patient_flow_total.csv`（678行 = 原典の「全体の流入率/流出率」）。**この帳票にはブロック番号の連番列が無い**ため、位置は算術生成し、グリッドが `max_row` に一致すること・A列の都道府県コード・339区域コードの3点で担保している（上記「パース時の注意」参照）
- 表示用データセット `tools/build_web_flow.py` → `data/processed/area_flow_R7.json`（約499KB・検証13項目で中断）。**339×2×3=2,034グループを全て materialize する**（原典にデータ行が1行も無いグループが6件あり、表示側が `undefined` を踏まないようにするため）。自区域行が無いグループが12件あることも検証で固定している
- 配信は `web/public/flow/area_flow.json`（バンドルせず、区域を初めて選んだときに1回だけfetch。罠27）。加工済みCSV一括ZIPは13本→15本（32エントリ）になった（その後M9で16本・34エントリへ更新）
- 区域パネルに「患者の流入・流出（NDB 2024年度）」セクション（方向×区分のトグル・自区域内完結率・相手区域トップN・**打ち切り分の明示**・CSVダウンロード）。地図は**選択区域を起点に相手区域を塗り分ける**オーバーレイ（既定OFF、指標セレクタ操作で自動解除）
- 原典側の欠陥2件を `known_issues` に登録（`flow_overall_rate_equals_acute_phase_complement`・`flow_outflow_chronic_value_error_cells`）
- 実装で判明した罠は「可視化実装で判明した罠」節の26〜29に記録

**M9「R6→R7 年度間比較」完了**:
- R6の入手元を実取得で確定（`tools/verify_r6_bundle.py`。zip の SHA-256 `0889fa8f…f30f39f`、同梱5ファイルが `SHA256SUMS` と全件一致）
- 両パーサ（`tools/parse_prefecture_beds.py`・`tools/parse_area_beds.py`）が R7+R6 を1本のCSVに `published_fy` で並存させる（`area_beds.csv` 35,595行・`area_basic.csv` 678行 ほか）
- **突合の結論**（`tools/verify_yoy_R6_R7.py` → `doc/YOY_VERIFICATION.md`）: 339区域のコード・名称は完全一致。2015〜2023実績と2025必要数は全1695セル一致。**2024実績だけ1281/1695セルで不一致で、R6側が健全**（R6の区域別2024実績は都道府県版と235/235キーで一致、R7は230/235で不一致）。**都道府県レベルはR6/R7で完全一致するため比較対象にしない**
- 画面に載せた指標は2つだけ（見込量比・実績の1年変化。`tools/build_web_yoy.py` → `data/processed/area_yoy_R6_R7.json`）。固定境界 `YOY_RATIO_BIN_EDGES = [0.85, 0.93, 0.98, 1.02, 1.075, 1.18]`（乗法対称で2指標の色の意味を揃え、合計の中央ビンが47%に収まる境界を選定。より粗い候補は62%に収まり分解能不足だった）
- 分母0（高度急性期70区域・回復期5・慢性期6）は既存の「算出不可」機構で塗る（0倍として塗らない）
- **並行して main に統合された M7（患者の流入・流出）・M8（都道府県階層）とマージし、両機能を統合**（`published_fy` の年度並存が M7・M8 側の「R7限定を暗黙の前提にした」下流を壊す意味論的衝突を解消した。詳細は下記罠30〜35）
- 実装で判明した罠は「可視化実装で判明した罠」節の30〜35に記録

**未実装**: 都道府県ぶんの絞り込みCSV（M6の `buildAreaTableCsv` は常に339構想区域を出す。都道府県表示中はボタンのラベルでその旨を示している）。
