# -*- coding: utf-8 -*-
"""`data/processed/facility_basic.csv`(339構想区域×医療機関、11,760件、
`tools/parse_facility_beds.py` の成果物)の各医療機関に、国土数値情報
「医療機関データ」P04-20（`ksj/P04-20/P04-20_GML.zip`、令和2年度、点データ）を
突合して座標を与える。

## 設計方針(重要): マッチ率ではなく「誤結合の少なさ」と「監査可能性」

このスクリプトは`verify_*`という名前を持たない。実際にやっているのは検証
(既に正しいと分かっている2つのものを照合すること)ではなく、あいまいさを伴う
レコードリンケージ(ヒューリスティックに同一実体を推定すること)であり、
名前で過大な保証を主張しないためである。

位置の推測はしない(`doc/REQUIREMENTS.md` §4.3): 自動採用(`match_status=
'matched'`)は下記の高信頼条件を**すべて**満たす場合のみに限り、あいまいな
一致は座標を与えず候補(`match_status='candidate_only'`)として報告するだけに
とどめる。マッチ率を最大化するために閾値を緩めることはしていない。誤って
別の医療機関の座標を採用してしまうことは、座標が無いことよりも悪い結果だと
考えるためである。

## 突合の手順

1. **P04の読み込み**(`iter_p04_raw_features`): zip内 `P04-20.geojson`
   (69MB)を、「1フィーチャ1行」という改行レイアウトに依存せずストリーム的に
   読む(`json.JSONDecoder().raw_decode` をバッファ上で逐次適用し、消費済みの
   先頭を捨てながら進める)。歯科診療所(`P04_001 == 3`)は除外し、必要な属性
   (分類・名称・住所・病床数・座標・フィーチャ通番)だけを軽量な
   `P04Point` に落として保持する(生JSONツリー全体は保持しない)。

2. **名称の正規化**(`normalize_facility_name`): NFKC正規化→空白/記号除去→
   小文字化→法人格語(`LEGAL_ENTITY_TERMS`)の除去。決定的(乱数を使わない)。

3. **点-多角形判定**(`AreaIndex`): 339構想区域ポリゴン
   (`data/processed/area_boundaries_R7.geojson`)に対し、0.5度グリッドで
   候補区域を絞ってからレイキャスティングで判定する(MultiPolygon・穴に対応)。
   これを全P04点(非歯科)に対して一度だけ行い、`p04_index -> area_code`
   (どの区域にも属さない点は`None`)を得る。全P04点×全区域の総当たりはしない
   (グリッドで候補区域を絞ってからのみ判定するため)。

4. **自動採用の条件は2ティア**(`match_facilities`):
   - **完全一致ティア**(`match_method='normalized_exact'`): 正規化名が
     完全一致する候補が、その構想区域ポリゴン内にちょうど1件あり、かつ
     市区町村が整合する(`address_matches_municipality`。P04住所からの
     独自抽出(`extract_municipality`)同士を比較するのではなく、
     facility_basic.csvの正しい市区町村名を直接prefix比較する。理由は
     `address_matches_municipality`のdocstring参照。政令指定都市名を省略し
     区名から始まる住所(例 横浜市を省略した`'港北区…'`)も、区名がExcel側の
     市区町村名の**末尾**と一致すれば整合とみなす)場合のみ「仮採用」する。
   - **接尾一致ティア**(`match_method='normalized_suffix'`): 完全一致
     ティアで採用されなかった施設について、正規化名が「一方が他方の末尾」の
     関係(法人名等の有無だけが違う。例: Excel`山梨県立中央病院` ×
     P04`地方独立行政法人山梨県立病院機構山梨県立中央病院`)にあり、短い方が
     `SUFFIX_MIN_SHORT_LEN`文字以上、区域内にちょうど1件、かつ市区町村が
     整合する場合のみ「仮採用」する。**完全一致ティアで既に採用済みのP04
     フィーチャは候補から除外する**(2つのティアが同じフィーチャを取り合わ
     ないようにする)。
   - いずれのティアも、同じP04フィーチャを複数のExcel施設が仮採用した場合
     (一対一制約違反)は、その全員を不採用にする(`contested_candidate`、
     `_resolve_contested`をティアごとに独立して適用)。

5. **あいまい一致は自動採用しない**: 上記いずれのティアでも採用に至らなかった
   施設について、その区域内のP04候補(自動採用済みのフィーチャを除く)全件
   との名称類似度(`difflib.SequenceMatcher`)を計算し、最良の候補が閾値
   (`FUZZY_MATCH_THRESHOLD`、根拠は下記)以上であれば`candidate_only`として
   名前とスコアだけ出力する(座標は空のまま)。

## FUZZY_MATCH_THRESHOLDの根拠

自動採用に至らなかったExcel施設について、区域内P04候補プールとの最良類似度
(`difflib.SequenceMatcher`)の分布を実測し(スコア帯別のヒストグラムは
`doc/FACILITY_LINKAGE.md`「あいまい一致(candidate_only)の代表例と閾値の根拠」
に実測値がある)、0.8を閾値に選んだ。`FUZZY_MATCH_THRESHOLD = 0.8` は座標を
与えない`candidate_only`の閾値であるため(誤って`matched`にするわけではない)、
多少緩めに倒しても実害が小さいことも踏まえている。

## 入力

- `ksj/P04-20/P04-20_GML.zip`(29MB・コミット済み)内 `P04-20_GML/P04-20.geojson`
- `data/processed/area_boundaries_R7.geojson`(339構想区域ポリゴン)
- `data/processed/facility_basic.csv`(339区域×医療機関、11,760件)
- `data/processed/facility_observations.csv`(病床規模帯の算出用。病床数
  「休棟中等含む計」のみ使用)

## 出力

1. `data/processed/facility_geo_linkage.csv`(+ `.meta.json`)
2. `doc/FACILITY_LINKAGE.md`(生成レポート。生成日時は埋め込まない)

必要環境: Python 3.11+(追加依存なし。点-多角形判定は純Python実装)

使い方:
    PYTHONIOENCODING=utf-8 python tools/build_facility_geo_linkage.py
"""
import csv
import datetime
import hashlib
import io
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lib.provenance import REPO_ROOT, sha256, verify_source, write_csv_with_meta

PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DOC_DIR = REPO_ROOT / "doc"

P04_ZIP_PATH_IN_REPO = "ksj/P04-20/P04-20_GML.zip"
P04_ZIP_PATH = REPO_ROOT / P04_ZIP_PATH_IN_REPO
P04_MEMBER_NAME = "P04-20_GML/P04-20.geojson"

EXCEL_PATH_IN_REPO = "R7/001723127.xlsx"

AREA_BOUNDARIES_PATH = PROCESSED_DIR / "area_boundaries_R7.geojson"
FACILITY_BASIC_CSV = PROCESSED_DIR / "facility_basic.csv"
FACILITY_OBSERVATIONS_CSV = PROCESSED_DIR / "facility_observations.csv"

OUT_CSV = PROCESSED_DIR / "facility_geo_linkage.csv"
OUT_DOC = DOC_DIR / "FACILITY_LINKAGE.md"

P04_SOURCE_PAGE = "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P04-v3_0.html"
LICENSE_NOTE = (
    "厚生労働省ホームページ利用規約（政府標準利用規約準拠） "
    "https://www.mhlw.go.jp/chosakuken/index.html / "
    "国土数値情報ダウンロードサービス利用約款（オープンデータ）"
)

# P04_001(医療機関分類): 1=病院 / 2=診療所 / 3=歯科診療所(突合対象外)。
CATEGORY_HOSPITAL = 1
CATEGORY_CLINIC = 2
CATEGORY_DENTAL = 3

# --- match_status / match_method / reason_code ---------------------------

MATCH_STATUS_MATCHED = "matched"
MATCH_STATUS_CANDIDATE_ONLY = "candidate_only"
MATCH_STATUS_UNMATCHED = "unmatched"

MATCH_METHOD_EXACT = "normalized_exact"
MATCH_METHOD_SUFFIX = "normalized_suffix"
MATCH_METHOD_NONE = "none"

REASON_NO_NAME_MATCH = "no_name_match"
REASON_OUTSIDE_AREA_POLYGON = "outside_area_polygon"
REASON_MUNICIPALITY_MISMATCH = "municipality_mismatch"
REASON_MUNICIPALITY_NOT_IN_ADDRESS = "municipality_not_in_address"
REASON_MULTIPLE_CANDIDATES_IN_AREA = "multiple_candidates_in_area"
REASON_CONTESTED_CANDIDATE = "contested_candidate"
REASON_NOT_REPORTED_FACILITY = "not_reported_facility"

REASON_LABELS = {
    "": "(自動採用)",
    REASON_NO_NAME_MATCH: "正規化名が完全一致するP04候補が全国に存在しない",
    REASON_OUTSIDE_AREA_POLYGON: "正規化名が一致する候補はあるが、当該構想区域のポリゴン内にはない",
    REASON_MUNICIPALITY_MISMATCH: "区域内に候補は1件あるが、P04住所から市区町村は抽出できるがExcel側と異なる",
    REASON_MUNICIPALITY_NOT_IN_ADDRESS: (
        "区域内に候補は1件あるが、P04住所から市区町村そのものを抽出できない"
        "(市区町村名を省略した住所。埼玉県の一部市に多い)"
    ),
    REASON_MULTIPLE_CANDIDATES_IN_AREA: "正規化名(または接尾一致)が一致する候補が区域内に複数ある(区域内で一意に絞れない)",
    REASON_CONTESTED_CANDIDATE: "同一のP04候補を複数のExcel施設が仮採用しようとした(一対一制約違反)",
    REASON_NOT_REPORTED_FACILITY: "Excel側が「未報告」の医療機関で所在地(市区町村)が空のため、市区町村の整合を検証できない",
}

# あいまい一致(candidate_only)の閾値。根拠はモジュールdocstring
# 「FUZZY_MATCH_THRESHOLDの根拠」および doc/FACILITY_LINKAGE.md 参照。
FUZZY_MATCH_THRESHOLD = 0.8

# 接尾一致ティア(match_method='normalized_suffix')の採用条件の1つ。正規化名の
# 短い方がこの文字数未満なら、「中央病院」のような汎用語1つが偶然両者に共通
# するだけで誤結合しかねないため採用しない。
SUFFIX_MIN_SHORT_LEN = 5

# 点-多角形判定の候補区域を絞るグリッドのセルサイズ(度)。339区域(日本全国)に対し
# 経験的に1セルあたり平均2区域程度まで絞れることを確認済み(0.5度で実測)。
GRID_CELL_DEG = 0.5


# ===========================================================================
# 1. 医療機関名の正規化
# ===========================================================================

# 法人格語(brief記載の語をそのまま定数化)。除去は長い語から先に行う
# (`_LEGAL_ENTITY_TERMS_BY_LENGTH_DESC`)ことで、「医療法人社団」を先に除去
# せずに「医療法人」だけを除去してしまい「社団」が残る、という部分除去を防ぐ。
#
# 「社会医療法人社団」「社会医療法人財団」「特定医療法人社団」は、実データに
# 実在することを確認して追加した複合語(「社会医療法人」+「医療法人社団」/
# 「医療法人財団」のように2つの短い語が重なり合う位置に出現するため、複合語を
# 明示的に登録しないと重なりのどちらを先に除去するかで結果が変わってしまう。
# 例: 「社会医療法人財団董仙会」は「社会医療法人」(6文字)と「医療法人財団」
# (6文字)が「医療法人」の4文字を共有して重なっており、複合語を登録しない
# 状態では除去順序によって「財団董仙会」または「社会董仙会」という不完全な
# 結果になっていた(実測で発見した不具合。順序は`set`のハッシュ順に依存して
# 実行のたびに変わるため、非決定的な不具合でもあった)。「特定医療法人財団」は
# 実データには見当たらないが、同型の法人格として将来に備えて登録しておく。
LEGAL_ENTITY_TERMS = (
    "社会医療法人社団",
    "社会医療法人財団",
    "特定医療法人社団",
    "特定医療法人財団",
    "医療法人社団",
    "医療法人財団",
    "医療法人",
    "社会医療法人",
    "特定医療法人",
    "独立行政法人",
    "国立研究開発法人",
    "地方独立行政法人",
    "国立大学法人",
    "公立大学法人",
    "学校法人",
    "公益社団法人",
    "一般社団法人",
    "公益財団法人",
    "一般財団法人",
    "社会福祉法人",
    "恩賜財団",
    "厚生農業協同組合連合会",
    "農業協同組合連合会",
    "厚生連",
    "国民健康保険団体連合会",
    "共済組合連合会",
)
# 第2キー(文字列そのもの)まで指定するのは、`set(...)`の反復順が
# PYTHONHASHSEEDに依存し実行のたびに変わるため。同じ長さの語が複数ある本リスト
# では、長さだけをキーにすると同じ長さの語同士の順序が実行ごとに変わってしまい
# (実測で見つけた非決定性の不具合)、除去対象が重なり合う語同士(上記コメント
# 参照)で結果が変わりうる。文字列そのものを第2キーに加えることで常に同じ順序
# になる。
_LEGAL_ENTITY_TERMS_BY_LENGTH_DESC = tuple(
    sorted(set(LEGAL_ENTITY_TERMS), key=lambda term: (-len(term), term))
)

_WHITESPACE_RE = re.compile(r"[\s　]+")
# 中黒・括弧類・句読点・ハイフン類等の記号(NFKC後の全角/半角どちらの形も
# 拾えるよう両方含めておく)。長音記号「ー」もここで除去されるため、下記
# `FACILITY_TYPE_WORDS`の語をそのまま(除去前の表記で)`in`/`replace`に使うと
# 「センター」→「センタ」のように正規化済みテキストと噛み合わなくなる
# (実測で見つけた不具合)。そのため`_FACILITY_TYPE_WORDS_BY_LENGTH_DESC`は
# 各語をこの正規表現で正規化してから使う。
_SYMBOL_RE = re.compile(
    "[" + re.escape("・･｡｢｣「」『』【】()（）[]｛｝{}<>〈〉《》〔〕、。，．,.!！?？:：;；~～-ー－―_/／\\｜|") + "]+"
)

# 施設種別語(病院・診療所の種別、および診療科名)。法人格語を
# 除去した結果がこれらの語だけ(=種別語を取り除くと何も残らない)になる名称は、
# 医療機関名としての識別力を失っており(例: 「厚生連クリニック」から「厚生連」
# を除去すると「クリニック」になり、これは全国のクリニック共通の一般名詞に
# すぎない)、接尾一致ティアで無関係の別施設と誤結合しうる
# (`normalize_facility_name`のガード・`_find_suffix_relation_candidates`の
# ガード、いずれも参照)。網羅的なリストではない(診療科名は多数存在する)ため
# あくまで防御的なガード用。
FACILITY_TYPE_WORDS = (
    "病院", "医院", "診療所", "クリニック", "医療センター", "センター",
    "歯科医院", "歯科診療所", "歯科クリニック", "歯科", "薬局",
    "内科", "外科", "眼科", "耳鼻科", "耳鼻咽喉科", "皮膚科", "皮膚泌尿器科",
    "産婦人科", "産科", "婦人科", "小児科", "精神科", "神経科", "神経内科",
    "心療内科", "整形外科", "形成外科", "美容外科", "脳神経外科",
    "呼吸器科", "呼吸器内科", "循環器科", "循環器内科", "消化器科", "消化器内科",
    "泌尿器科", "放射線科", "麻酔科", "リハビリテーション科", "リハビリ科",
    "アレルギー科", "腫瘍内科", "乳腺外科", "肛門科", "胃腸科",
)


def _normalize_type_word(word: str) -> str:
    """`FACILITY_TYPE_WORDS`の1語を、`normalize_facility_name()`が実際の
    テキストへ適用するのと同じNFKC正規化・小文字化・記号除去を適用してから
    返す(「センター」の長音記号のように、記号除去で消える文字を語の定義に
    含んでいても、正規化済みテキストとの比較で正しく機能するようにするため)。
    """
    text = unicodedata.normalize("NFKC", word)
    text = text.lower()
    text = _SYMBOL_RE.sub("", text)
    return text


_FACILITY_TYPE_WORDS_BY_LENGTH_DESC = tuple(
    sorted({_normalize_type_word(w) for w in FACILITY_TYPE_WORDS}, key=lambda term: (-len(term), term))
)


def _residual_after_removing_type_words(text: str) -> str:
    """`text`から`FACILITY_TYPE_WORDS`の語(正規化済み)を(長い語から先に)
    全て取り除いた残余を返す。残余が空文字なら、`text`は施設種別語(と、
    既に除去済みの法人格語)だけで構成されていたことを意味する。
    """
    for word in _FACILITY_TYPE_WORDS_BY_LENGTH_DESC:
        if word in text:
            text = text.replace(word, "")
    return text


def normalize_facility_name(name: str) -> str:
    """医療機関名を突合用に正規化する(決定的。乱数は使わない)。

    NFKC正規化 → 小文字化 → 空白除去 → 記号除去 → 法人格語の除去、の順。
    法人格語は空白/記号を除去した**後**に除去する(語の途中に全角空白が
    挟まっている表記でも確実に除去できるようにするため)。

    ⚠ 法人格語除去のガード(レビューで発見された誤結合の根本原因への対処):
    法人格語を除去した結果が施設種別語(`FACILITY_TYPE_WORDS`)だけになる場合
    (=種別語を取り除くと残余が**空**になる場合)は、法人格語を除去せず、
    除去前の名称を採用する。例:
      - 「厚生連クリニック」→ 法人格語「厚生連」を除去すると「クリニック」に
        なり、これは種別語だけ(除去すると残余が空)なので、除去せず
        「厚生連クリニック」のまま返す(全国の「クリニック」と誤って接尾一致
        しないようにするため)。
      - 「医療法人社団森クリニック」→ 法人格語「医療法人社団」を除去すると
        「森クリニック」になり、これは種別語「クリニック」を取り除いても
        「森」が残る(空にならない)ので、そのまま「森クリニック」を返す
        (正しい正規化であり、巻き戻すとP04側の「森クリニック」と一致しなく
        なってしまう。残余の判定を「空かどうか」ではなく「◯文字未満」等に
        してはいけない理由はここにある)。
    """
    text = unicodedata.normalize("NFKC", name)
    text = text.lower()
    text = _WHITESPACE_RE.sub("", text)
    text = _SYMBOL_RE.sub("", text)
    before_legal_removal = text
    after_legal_removal = text
    for term in _LEGAL_ENTITY_TERMS_BY_LENGTH_DESC:
        if term in after_legal_removal:
            after_legal_removal = after_legal_removal.replace(term, "")
    if _residual_after_removing_type_words(after_legal_removal) == "":
        return before_legal_removal
    return after_legal_removal


def is_type_word_only(normalized_name: str) -> bool:
    """既に正規化済みの名称が、施設種別語だけ(=種別語を取り除くと残余が空)で
    構成されているかを判定する。接尾一致ティアの保険のガード
    (`_find_suffix_relation_candidates`)で使う。空文字列に対しても
    (取り除く対象が無い=残余は空文字列のままなので)`True`を返す。
    """
    return _residual_after_removing_type_words(normalized_name) == ""


# ===========================================================================
# 2. 市区町村名の抽出(P04住所文字列から)
# ===========================================================================

# 政令指定都市(令和2年度時点、P04のデータ年度に合わせる。以降新設なし)。
DESIGNATED_CITIES = (
    "札幌市", "仙台市", "さいたま市", "千葉市", "横浜市", "川崎市", "相模原市",
    "新潟市", "静岡市", "浜松市", "名古屋市", "京都市", "大阪市", "堺市",
    "神戸市", "岡山市", "広島市", "北九州市", "福岡市", "熊本市",
)

# 東京都特別区(23区)。
TOKYO_23_WARDS = (
    "千代田区", "中央区", "港区", "新宿区", "文京区", "台東区", "墨田区",
    "江東区", "品川区", "目黒区", "大田区", "世田谷区", "渋谷区", "中野区",
    "杉並区", "豊島区", "北区", "荒川区", "板橋区", "練馬区", "足立区",
    "葛飾区", "江戸川区",
)

# 47都道府県(brief記載どおりP04住所は都道府県名を含まないのが原則だが、実測で
# 一部の県(長崎県・島根県・宮崎県等)は都道府県名を含めて記載していることが
# 判明した。都道府県名が付いていても壊れないよう、抽出前に先頭から取り除く)。
PREFECTURE_NAMES = (
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
)

# 住所の区切り文字として使う数字クラス。半角/全角のアラビア数字のみ
# (実測: P04住所の丁目/番地はアラビア数字表記のみで、漢数字は使われない一方、
# 「三笠市」「千歳市」「八王子市」のような市区町村名自体に漢数字を含む例は
# 多数あるため、漢数字をここに含めると市区町村名の先頭が漢数字の場合に抽出が
# 全滅する。過去にこの版で `三浦市...` が抽出できない不具合を実測で発見し修正した)。
_DIGIT_CLASS = "0-9０-９"
# いずれも非貪欲(`+?`)にして、区切り文字(区/郡/市)の**最初の**出現で止める。
# 貪欲(`+`)だと「赤磐市下市187番地1」のように、市区町村名の後ろに続く地名が
# たまたま同じ区切り文字で終わる場合(この例では「下市」という地名が「市」で
# 終わる)に、正規表現が最長一致(「赤磐市下市」)を優先してしまい市区町村名を
# 誤って長く抽出する不具合が実測で見つかったため(修正前)。
_WARD_SUFFIX_RE = re.compile(rf"^([^{_DIGIT_CLASS}]+?区)")
_GUN_TOWN_RE = re.compile(rf"^([^{_DIGIT_CLASS}]+?郡)([^{_DIGIT_CLASS}]+?(?:町|村))")
_CITY_RE = re.compile(rf"^([^{_DIGIT_CLASS}]+?市)")
# 郡表記を省略して直接「○○町」「○○村」から始まる住所がある(実測: 神奈川県
# 足柄上郡の町等)ためのフォールバック(郡+町村パターンが不一致だった場合のみ試す)。
_TOWN_VILLAGE_RE = re.compile(rf"^([^{_DIGIT_CLASS}]+?(?:町|村))")


def _strip_prefecture_prefix(address: str) -> str:
    """住所先頭の都道府県名を検出して取り除く(無ければそのまま返す)。"""
    for pref in PREFECTURE_NAMES:
        if address.startswith(pref):
            return address[len(pref):]
    return address


def _extract_municipality_core(address: str, *, allow_low_confidence_fallback: bool):
    """`extract_municipality()`と`_extract_municipality_confident()`が共有する
    抽出本体。`allow_low_confidence_fallback=False`のときは、郡表記を伴わない
    `_TOWN_VILLAGE_RE`フォールバック(下記docstring参照)を
    使わない。
    """
    if not address:
        return None
    address = _strip_prefecture_prefix(address)
    if not address:
        return None
    for city in DESIGNATED_CITIES:
        if address.startswith(city):
            rest = address[len(city):]
            m = _WARD_SUFFIX_RE.match(rest)
            return city + m.group(1) if m else None
    m = _GUN_TOWN_RE.match(address)
    if m:
        return m.group(2)
    for ward in TOKYO_23_WARDS:
        if address.startswith(ward):
            return ward
    m = _CITY_RE.match(address)
    if m:
        return m.group(1)
    if not allow_low_confidence_fallback:
        return None
    m = _TOWN_VILLAGE_RE.match(address)
    # 「区」を含む場合は誤抽出とみなして採用しない(実測: 政令指定都市名を
    # 省略して区名から書き始める住所(例 横浜市を省略した'港北区小机町...')が
    # 一部存在し、この場合 `_TOWN_VILLAGE_RE` は「港北区小機町」のように区名+
    # 地名を一体で拾ってしまう。町村名自体に「区」を含むことは通常ないため、
    # 含んでいれば安全側でNoneを返す。この住所パターンは市区町村名を正しく
    # 復元できないため未マッチのままになる、doc/FACILITY_LINKAGE.md「限界」参照)。
    if m and "区" not in m.group(1):
        return m.group(1)
    return None


def extract_municipality(address: str):
    """P04住所文字列から市区町村名を抽出する。

    政令指定都市は区名まで(`'札幌市北区'`)、特別区は区名のみ(`'文京区'`)、
    郡は除去して町村名のみ(`'標津郡中標津町...'` -> `'中標津町'`)を返す
    (`data/processed/facility_basic.csv`の`municipality`列と同じ形式に揃える
    ため)。抽出できない場合は例外を送出せず`None`を返す(突合の判定材料と
    しては「一致しない」扱いで十分であり、住所形式の揺れ全てを網羅する
    汎用パーサを目指すものではないため)。

    P04住所は原則として都道府県名を含まないが、実測で一部県(長崎県・島根県・
    宮崎県等)は都道府県名付きで記載されているため、まず先頭の都道府県名を
    取り除いてから以下の判定に進む。

    ⚠ 既知の限界(regexの構造的な限界。`address_matches_municipality()`参照):
    「四日市市」「野々市市」のように市区町村名自体の中に区切り文字(市/町/村/郡)
    と同じ文字を含む地名では、非貪欲マッチが最初の出現で止まるため短く抽出
    しすぎる場合がある(例: `'四日市市...'` → `'四日市'`)。突合の可否判定
    (`match_facilities`)はこの関数の結果だけに頼らず、`address_matches_municipality()`
    でExcel側の正しい市区町村名を直接prefix比較することでこの限界を補っている。

    ⚠ もう1つの既知の限界(郡なしの`_TOWN_VILLAGE_RE`フォールバック): 「昭和町
    河東中島443」(山梨県、郡表記省略の**独立した町**)を拾うために、郡表記を
    伴わない「○○町/村」もフォールバックとして受理している。しかし同じ形は
    「川柳町3-50-1」(埼玉県越谷市、市内の**字・地区名**が偶然「町」で終わる
    だけで独立した市区町村ではない)も拾ってしまい、区別する手がかりが住所
    文字列だけからは無い。この関数の戻り値(`p04_municipality`列として出力)は
    どちらのケースでも同じ形(非None)になるが、突合可否の判定
    (`_municipality_check`)はこの区別が必要なため、低信頼フォールバックを
    使わない`_extract_municipality_confident()`を別に用意している。
    """
    return _extract_municipality_core(address, allow_low_confidence_fallback=True)


def _extract_municipality_confident(address: str):
    """`extract_municipality()`と同じだが、郡なしの`_TOWN_VILLAGE_RE`
    フォールバック(信頼度が低い。上記`extract_municipality()`のdocstring
    「もう1つの既知の限界」参照)を使わない。`_municipality_check()`が
    `municipality_mismatch`(市区町村を抽出できるが違う)と
    `municipality_not_in_address`(そもそも住所に市区町村名相当のものが
    見当たらない)を区別するために使う内部専用のヘルパーであり、
    `p04_municipality`列(監査用の表示値、`extract_municipality()`の担当)には
    影響しない。
    """
    return _extract_municipality_core(address, allow_low_confidence_fallback=False)


_LEADING_GUN_RE = re.compile(rf"^[^{_DIGIT_CLASS}]+?郡")
# 政令指定都市名を省略していきなり区名から始まる住所(実測: 横浜市等を省略した
# 住所)を検出するための、先頭の区名だけを取り出す正規表現。`extract_municipality()`
# はこの形の住所からNoneを返す設計のまま変えず(情報列用の抽出仕様は据え置き)、
# 突合の可否判定(`address_matches_municipality`)だけがこの区名を使う。
_LEADING_WARD_RE = re.compile(rf"^([^{_DIGIT_CLASS}]+?区)")

# 地名表記ゆれ: 小書きの片仮名「ヶ」「ヵ」と通常大の「ケ」「カ」は同じ地名の
# 別表記として混在することが実測でわかっている(例: 「龍ケ崎市」(facility_basic.csv)
# と「龍ヶ崎市」(P04)、「駒ヶ根市」と「駒ケ根市」)。市区町村整合の判定でのみ
# 両者を同一視する(名称正規化`normalize_facility_name`や`extract_municipality`
# の出力表示は元表記のまま変更しない)。
_KANA_KE_VARIANTS = str.maketrans({"ヶ": "ケ", "ヵ": "カ"})


def address_matches_municipality(address: str, municipality: str) -> bool:
    """P04住所が、Excel側の市区町村名(`municipality`。facility_basic.csvの値、
    常に正しい完全な市区町村名)と整合するかを判定する。

    `extract_municipality()`(正規表現による抽出)は、「四日市市」「野々市市」
    「玉村町」「上市町」のように市区町村名自体の中に区切り文字(市/町/村/郡)と
    同じ文字を含む地名で、非貪欲マッチが最初の出現で止まるため短く抽出しすぎる
    ことが実測でわかっている(構造的な限界であり、住所文字列だけからは正しい
    切れ目を一般には判定できない)。この関数は`extract_municipality()`の抽出
    結果に頼らず、Excel側から**既に分かっている正しい市区町村名**を、都道府県名
    (先頭にあれば)・郡名(先頭にあれば。`municipality`は郡を含まない形なので
    郡付き住所ではそのままだと一致しない)を除去した住所に対して直接prefix比較
    することで、この限界を回避する(`municipality`はfacility_basic.csvの値であり、
    常に「札幌市北区」「中標津町」のような完全な形なので、prefix一致で十分)。

    郡の有無を先験的に知らないため、郡を除去した場合/しない場合の両方で
    prefix一致を試す(郡が無い住所では除去しても変化しないため無害)。
    「ヶ/ヵ」と「ケ/カ」の表記ゆれも比較前に同一視する。

    ⚠ 政令指定都市名を省略した住所: P04住所が市名を省いて
    区名から直接始まる場合(例 `'港北区小机町3211'`、横浜市を省略)、上記の
    prefix比較はいずれも成立しない(住所が`municipality`(`'横浜市港北区'`)で
    始まらないため)。しかしこの場合でも、住所先頭の区名がExcel側の
    `municipality`の**末尾**と一致するなら(`'横浜市港北区'.endswith('港北区')`)、
    整合とみなしてよい: 区名という具体的な情報はP04住所に含まれており、
    どの市の区であるかはこの時点で既にExcel側(区域ポリゴンで絞り込み済みの
    候補)の`municipality`自身が示しているため、これは判定の緩和ではなく
    本来拾えるはずの取りこぼしの是正である。`extract_municipality()`の
    仕様(この形の住所からは`None`を返す)は変更しない。
    """
    if not address or not municipality:
        return False
    stripped = _strip_prefecture_prefix(address).translate(_KANA_KE_VARIANTS)
    municipality = municipality.translate(_KANA_KE_VARIANTS)
    if stripped.startswith(municipality):
        return True
    m = _LEADING_GUN_RE.match(stripped)
    if m and stripped[m.end():].startswith(municipality):
        return True
    m = _LEADING_WARD_RE.match(stripped)
    if m and municipality.endswith(m.group(1)):
        return True
    return False


def _municipality_check(address: str, municipality: str):
    """市区町村整合を判定し、`(整合したか, 整合しなかった場合のreason_code)`
    を返す(整合した場合はreason_codeは空文字)。

    「市区町村を抽出できるが違う」(`municipality_mismatch`)と
    「そもそも住所に市区町村名が出現しない」(`municipality_not_in_address`。
    埼玉県の一部市のように、市名そのものを省略した住所)は原因も対処も異なる
    ため区別する。後者かどうかは`_extract_municipality_confident()`
    (`extract_municipality()`から、郡なし「○○町/村」という信頼度の低い
    フォールバックを除いたもの)が`None`を返すかで判定する。低信頼フォール
    バックを含む`extract_municipality()`をそのまま使わない理由: 「川柳町
    3-50-1」(埼玉県越谷市の字・地区名)のように、市内の地区名が偶然「町」で
    終わるだけで独立した市区町村ではない場合でも`extract_municipality()`は
    値を返してしまい、`municipality_mismatch`(市区町村を抽出できるが違う)
    と誤分類してしまう。`p04_municipality`列(監査用の表示値)には影響しない。
    (`address_matches_municipality()`が独自に緩和しているケース(政令市の
    区始まり住所)は、その緩和が効けば先に`True`になるため、ここに到達する
    時点で残っているのは緩和も効かなかった住所のみ)。
    """
    if address_matches_municipality(address, municipality):
        return True, ""
    if _extract_municipality_confident(address) is None:
        return False, REASON_MUNICIPALITY_NOT_IN_ADDRESS
    return False, REASON_MUNICIPALITY_MISMATCH


# 診断用: 政令指定都市名(市区町村)を省略していきなり区名から始まる住所を
# 大まかに検出する(`extract_municipality`がNoneを返した住所のうち、この形に
# 見えるものの件数をレポート「9. 限界」に載せるため。1〜4文字+「区」で始まる
# 住所を広く拾うヒューリスティックであり、これ自体を突合の判定には使わない)。
_BARE_WARD_RE = re.compile(rf"^[^{_DIGIT_CLASS}]{{1,4}}区")


def count_bare_ward_addresses(points) -> int:
    """`extract_municipality`が`None`を返したP04点のうち、政令指定都市名を
    省略していきなり区名から始まる住所に見えるものの件数を数える
    (診断用。doc/FACILITY_LINKAGE.md「9. 限界」参照)。
    """
    count = 0
    for p in points:
        if p.municipality is not None:
            continue
        address = p.address
        if not address:
            continue
        for pref in PREFECTURE_NAMES:
            if address.startswith(pref):
                address = address[len(pref):]
                break
        if _BARE_WARD_RE.match(address):
            count += 1
    return count


# ===========================================================================
# 3. P04-20.geojson のストリーム読み込み
# ===========================================================================


def iter_p04_raw_features(zip_path: Path, member_name: str = P04_MEMBER_NAME, chunk_size: int = 1 << 20):
    """P04-20.geojsonの`features`配列を、ファイル全体を一度に読み切らずに
    1フィーチャずつ返すジェネレータ。

    「1フィーチャ1行」という改行レイアウトには依存しない(`json.JSONDecoder()
    .raw_decode`をバッファ上で逐次適用し、1オブジェクト読むたびに消費済みの
    先頭を捨てる)。将来mapshaper等の出力形式(改行位置)が変わっても壊れない。
    """
    decoder = json.JSONDecoder()
    marker = '"features"'
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(member_name) as raw:
            text_stream = io.TextIOWrapper(raw, encoding="utf-8")
            buf = ""
            # --- "features" キーの直後の "[" までスキップ ---
            while True:
                idx = buf.find(marker)
                if idx != -1:
                    bracket_idx = buf.find("[", idx)
                    if bracket_idx != -1:
                        buf = buf[bracket_idx + 1:]
                        break
                chunk = text_stream.read(chunk_size)
                if not chunk:
                    raise ValueError(f"{member_name}: \"features\"配列の開始が見つかりません")
                buf += chunk

            # --- 1オブジェクトずつ取り出す ---
            pos = 0
            while True:
                while pos < len(buf) and buf[pos] in " \t\r\n,":
                    pos += 1
                while pos >= len(buf):
                    chunk = text_stream.read(chunk_size)
                    if not chunk:
                        raise ValueError(f"{member_name}: features配列の終端']'が見つかりません")
                    buf += chunk
                if buf[pos] == "]":
                    break
                while True:
                    try:
                        obj, end = decoder.raw_decode(buf, pos)
                        break
                    except json.JSONDecodeError:
                        chunk = text_stream.read(chunk_size)
                        if not chunk:
                            raise
                        buf += chunk
                yield obj
                pos = end
                # 消費済みの先頭を捨ててバッファを縮める(メモリを増やし続けない)。
                if pos > chunk_size:
                    buf = buf[pos:]
                    pos = 0


# ===========================================================================
# 4. 点-多角形判定(純Python、追加依存なし)
# ===========================================================================


def _geometry_bbox(geometry: dict):
    """Polygon/MultiPolygonのbbox `(minx, miny, maxx, maxy)` を求める。"""
    gtype = geometry["type"]
    depth = {"Polygon": 2, "MultiPolygon": 3}.get(gtype)
    if depth is None:
        raise ValueError(f"Polygon/MultiPolygon以外のジオメトリです: {gtype!r}")
    xs, ys = [], []

    def walk(coords, d):
        if d == 0:
            xs.append(coords[0])
            ys.append(coords[1])
        else:
            for c in coords:
                walk(c, d - 1)

    walk(geometry["coordinates"], depth)
    return min(xs), min(ys), max(xs), max(ys)


def _point_in_ring(x: float, y: float, ring) -> bool:
    """標準的なレイキャスティング(交差数の偶奇判定)による点-環内判定。"""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _point_in_polygon_coords(x: float, y: float, polygon_coords) -> bool:
    """`polygon_coords`(`[外環, 内環(穴)1, 内環2, ...]`)に対する点-多角形判定。"""
    if not polygon_coords:
        return False
    if not _point_in_ring(x, y, polygon_coords[0]):
        return False
    for hole in polygon_coords[1:]:
        if _point_in_ring(x, y, hole):
            return False
    return True


def point_in_geometry(x: float, y: float, geometry: dict) -> bool:
    """GeoJSON geometry(Polygon/MultiPolygon)に対する点-多角形判定。"""
    gtype = geometry["type"]
    if gtype == "Polygon":
        return _point_in_polygon_coords(x, y, geometry["coordinates"])
    if gtype == "MultiPolygon":
        return any(_point_in_polygon_coords(x, y, poly) for poly in geometry["coordinates"])
    raise ValueError(f"Polygon/MultiPolygon以外のジオメトリです: {gtype!r}")


class AreaIndex:
    """339構想区域ポリゴンに対する点-多角形判定を、グリッドで候補区域を
    絞ってから行う索引。全P04点×全区域の総当たりを避けるためのもの。
    """

    def __init__(self, boundaries_geojson: dict, *, cell_deg: float = GRID_CELL_DEG):
        self._cell_deg = cell_deg
        self._areas = []
        for feat in boundaries_geojson["features"]:
            bbox = _geometry_bbox(feat["geometry"])
            self._areas.append(
                {"area_code": feat["properties"]["area_code"], "bbox": bbox, "geometry": feat["geometry"]}
            )
        self._grid = defaultdict(list)
        for area in self._areas:
            minx, miny, maxx, maxy = area["bbox"]
            for gx in range(self._cell(minx), self._cell(maxx) + 1):
                for gy in range(self._cell(miny), self._cell(maxy) + 1):
                    self._grid[(gx, gy)].append(area)

    def _cell(self, v: float) -> int:
        return int(v // self._cell_deg)

    @property
    def area_count(self) -> int:
        return len(self._areas)

    def find_area_code(self, lon: float, lat: float):
        """`(lon, lat)`を含む構想区域のarea_codeを返す。どの区域にも
        属さなければ`None`(境界簡略化時の離島除去等で実際に発生する。
        doc/FACILITY_LINKAGE.md「限界」参照)。
        """
        key = (self._cell(lon), self._cell(lat))
        for area in self._grid.get(key, ()):
            minx, miny, maxx, maxy = area["bbox"]
            if not (minx <= lon <= maxx and miny <= lat <= maxy):
                continue
            if point_in_geometry(lon, lat, area["geometry"]):
                return area["area_code"]
        return None


# ===========================================================================
# 5. P04点の読み込み・索引構築
# ===========================================================================


@dataclass(frozen=True)
class P04Point:
    index: int  # P04-20.geojson features配列内の通し番号(0始まり、歯科除外前の位置)
    category: int  # P04_001(1=病院/2=診療所)
    name: str
    name_normalized: str
    address: str
    municipality: object  # str または None(extract_municipalityが抽出できなかった場合)
    beds: object  # int または None
    lon: float
    lat: float
    area_code: object  # str または None(どの構想区域のポリゴンにも属さない場合)


def _coerce_beds(raw):
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    return None


def load_p04_points(zip_path: Path, area_index: AreaIndex):
    """P04-20.geojsonを読み、歯科診療所を除外した`P04Point`のリストと、
    全フィーチャ(歯科診療所含む)の分類別件数`Counter`を返す。

    `index`はP04-20.geojsonの元の`features`配列内での通し番号(歯科診療所を
    含む全フィーチャに対する連番)であり、除外後のリスト内位置ではない
    (`p04_feature_index`として出力に残し、原典フィーチャを一意に指せるように
    するため)。分類別件数もここで同じ1回の走査から集計する(内訳集計のために
    69MBのzip内メンバーを二重に読まないため)。
    """
    points = []
    category_counts = Counter()
    for idx, feat in enumerate(iter_p04_raw_features(zip_path)):
        props = feat["properties"]
        category = props["P04_001"]
        category_counts[category] += 1
        if category == CATEGORY_DENTAL:
            continue
        name = props["P04_002"]
        address = props["P04_003"]
        lon, lat = feat["geometry"]["coordinates"][:2]
        points.append(
            P04Point(
                index=idx,
                category=category,
                name=name,
                name_normalized=normalize_facility_name(name),
                address=address,
                municipality=extract_municipality(address),
                beds=_coerce_beds(props.get("P04_008")),
                lon=lon,
                lat=lat,
                area_code=area_index.find_area_code(lon, lat),
            )
        )
    return points, category_counts


def build_p04_indices(points):
    """P04点のリストから、名称索引(`{正規化名: [P04Point, ...]}`)と
    区域内索引(`{area_code: [P04Point, ...]}`。どの区域にも属さない点は
    含まない)を構築する。
    """
    by_name = defaultdict(list)
    by_area = defaultdict(list)
    for p in points:
        by_name[p.name_normalized].append(p)
        if p.area_code is not None:
            by_area[p.area_code].append(p)
    return dict(by_name), dict(by_area)


# ===========================================================================
# 6. Excel側(facility_basic.csv)の読み込み
# ===========================================================================


def load_facilities(path: Path = FACILITY_BASIC_CSV):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


BED_BAND_400_PLUS = "400床以上"
BED_BAND_100_399 = "100〜399床"
BED_BAND_1_99 = "1〜99床（0床を含む、該当2件のみ）"
BED_BAND_NOT_REPORTED = "未報告"

BED_BAND_ORDER = [BED_BAND_400_PLUS, BED_BAND_100_399, BED_BAND_1_99, BED_BAND_NOT_REPORTED]


def load_bed_size_bands(path: Path = FACILITY_OBSERVATIONS_CSV):
    """`facility_observations.csv`から各医療機関(record_id)の病床規模帯を
    求める(病床数「休棟中等含む計」のみ使用)。値が観測できない
    (`value_status`が`observed`以外)場合は`未報告`帯に入れる
    (`not_reported`と`blank`のいずれも含む。件数はdoc/FACILITY_LINKAGE.md参照)。
    """
    bands = {}
    with open(path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["metric"] != "病床数" or row["bed_function"] != "休棟中等含む計":
                continue
            record_id = row["record_id"]
            if row["value_status"] != "observed":
                bands[record_id] = BED_BAND_NOT_REPORTED
                continue
            value = int(row["value"])
            if value >= 400:
                bands[record_id] = BED_BAND_400_PLUS
            elif value >= 100:
                bands[record_id] = BED_BAND_100_399
            else:
                bands[record_id] = BED_BAND_1_99
    return bands


# p04_bedsとExcel側病床数の突合可否検証への流用を防ぐための
# 閾値。両者とも正の値のときのみ比較する(0除算・意味の無い比較を避ける)。
#
# 単純な比率(倍率)だけを閾値にすると、病床数が1桁の小規模診療所(Excel側が
# 「休棟中等含む計」で1床、P04側が診療所の法定上限に近い19床、等)が大量に
# 混入し、実測したところ比率2倍以上だけで476件、うち多くが絶対差20床未満の
# 小規模診療所だった(診療所の法定病床数上限が19床であることに起因すると
# みられる、別の定義差)。レビューが指摘した「精神病床等を含む総病床数 対
# 一般・療養病床のみ」という定義差は、実測した3例(東京都立松沢病院: Excel
# 90床/P04 898床=約10.0倍・差808床、浅香山病院: 223/1015=約4.6倍・差792床、
# 紘仁病院: 161/940=約5.8倍・差779床)が示すとおり**絶対差も大きい**病院規模の
# 施設で起きている。そこで「比率2倍以上」**かつ**「絶対差100床以上」の両方を
# 満たす場合のみ「大きく乖離」とみなす(絶対差の閾値100床は、実測3例の絶対差
# (779〜808床)よりかなり保守的に小さい値としつつ、小規模診療所のノイズ
# (絶対差はほぼ20床未満)を確実に除外できる水準として選んだ)。
BED_DIVERGENCE_RATIO = 2.0
BED_DIVERGENCE_ABS_MIN = 100


def load_bed_counts(path: Path = FACILITY_OBSERVATIONS_CSV):
    """`facility_observations.csv`から各医療機関(record_id)のExcel側病床数
    (「休棟中等含む計」、観測できた場合のみ)を取得する。

    `p04_beds`(P04側、令和2年度・総病床数)との突合可否検証
    (`_compute_bed_divergence`)に使う。観測できない(`value_status`が
    `observed`以外)場合はキー自体を持たない(0や未報告を大きい/小さいとして
    誤って比較しないため)。
    """
    counts = {}
    with open(path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["metric"] != "病床数" or row["bed_function"] != "休棟中等含む計":
                continue
            if row["value_status"] != "observed":
                continue
            counts[row["record_id"]] = int(row["value"])
    return counts


def _compute_bed_divergence(rows, bed_counts: dict):
    """`matched`行について、Excel側病床数(`bed_counts`)とP04側病床数
    (`row.p04.beds`)を突き合わせ、大きく乖離する(`BED_DIVERGENCE_RATIO`倍
    以上**かつ**絶対差`BED_DIVERGENCE_ABS_MIN`床以上)行のリストを
    `(row, excel_beds, p04_beds, ratio)`として返す。
    両者とも観測できて共に正の値の行のみ対象にする。
    決定的な順序: `rows`の順序をそのまま保つ。
    """
    divergent = []
    for row in rows:
        if row.match_status != MATCH_STATUS_MATCHED:
            continue
        excel_beds = bed_counts.get(row.record_id)
        p04_beds = row.p04.beds if row.p04 else None
        if not excel_beds or not p04_beds:  # None または 0 は比較対象外
            continue
        ratio = max(excel_beds, p04_beds) / min(excel_beds, p04_beds)
        if ratio >= BED_DIVERGENCE_RATIO and abs(excel_beds - p04_beds) >= BED_DIVERGENCE_ABS_MIN:
            divergent.append((row, excel_beds, p04_beds, ratio))
    return divergent


# ===========================================================================
# 7. 突合(マッチング)
# ===========================================================================


@dataclass
class LinkageRow:
    record_id: str
    area_code: str
    facility_name: str
    facility_name_normalized: str
    municipality: str
    match_status: str
    match_method: str
    reason_code: str
    candidate_count: int
    match_score: object  # float または None
    p04: object  # P04Point または None


def match_facilities(facilities, by_name: dict, by_area: dict):
    """Excel側全施設をP04候補と突合する。

    戻り値: `(rows, fuzzy_scores)`。
      rows: `LinkageRow`のリスト(`facilities`と同じ順序)。
      fuzzy_scores: 完全一致・接尾一致いずれのティアでも自動採用に至らなかった
        施設のうち、区域内P04候補プール(自動採用済みのP04フィーチャを除く)が
        空でなかったものの「最良類似度」のリスト(閾値未満のものも含む)。
        `FUZZY_MATCH_THRESHOLD`の根拠(スコア分布のヒストグラム)に使う。

    3段階で処理する:
      1. **完全一致ティア**(`match_method='normalized_exact'`): 正規化名の
         完全一致 + 区域内一意 + 市区町村整合、を満たす施設を「仮採用」する。
         同じP04候補を複数施設が仮採用した場合は一対一制約違反として全員を
         `contested_candidate`に落とす(`_resolve_contested`)。
      2. **接尾一致ティア**(`match_method='normalized_suffix'`): 完全一致
         ティアで採用されなかった施設について、正規化名が「一方が他方の末尾」
         の関係にあり(例: Excel`山梨県立中央病院` × P04`地方独立行政法人
         山梨県立病院機構山梨県立中央病院`)、短い方が`SUFFIX_MIN_SHORT_LEN`
         文字以上で、区域内にちょうど1件、かつ市区町村整合を満たす場合のみ
         採用する。**完全一致ティアで既に採用済みのP04フィーチャは候補から
         除外する**(同じフィーチャを2つのティアで取り合わない)。このティア
         でも一対一制約(同じP04フィーチャの競合)を独立に適用する。
      3. **あいまい一致**(`candidate_only`): 上記いずれでも採用に至らなかった
         施設について、区域内P04候補(既に自動採用済みのフィーチャを除く)
         全件との名称類似度であいまい候補を探す(`_attach_fuzzy_candidates`)。
         座標は与えない。

    接尾一致ティアを完全一致ティアと**別**にしている理由: 完全一致ティアは
    名称のみで機械的に(閾値やスコアなしで)一意に定まるため、監査対象を
    「完全一致のみ」に絞り込みたい場面(例: 高い確信度が必要な用途)でも
    `match_method`で単純にフィルタできる。両者を混ぜてしまうと、法人格・
    通称の有無で名称が食い違うだけの正当な同一施設(完全一致ティアの対象外)
    と、たまたま部分文字列が一致するだけの別施設を、同じ精度として扱う
    ことになり、監査可能性が下がる。
    """
    rows = []
    tentative_exact_by_record_id = {}

    for facility in facilities:
        record_id = facility["record_id"]
        area_code = facility["area_code"]
        name = facility["facility_name"]
        municipality = facility["municipality"] or ""
        normalized = normalize_facility_name(name)

        candidates_all = by_name.get(normalized, [])
        candidates_in_area = [c for c in candidates_all if c.area_code == area_code]

        if not municipality:
            reason = REASON_NOT_REPORTED_FACILITY
            candidate_count = len(candidates_in_area)
        elif not candidates_all:
            reason = REASON_NO_NAME_MATCH
            candidate_count = 0
        elif not candidates_in_area:
            reason = REASON_OUTSIDE_AREA_POLYGON
            candidate_count = len(candidates_all)
        elif len(candidates_in_area) > 1:
            reason = REASON_MULTIPLE_CANDIDATES_IN_AREA
            candidate_count = len(candidates_in_area)
        else:
            candidate = candidates_in_area[0]
            ok, reason = _municipality_check(candidate.address, municipality)
            candidate_count = 1
            if ok:
                tentative_exact_by_record_id[record_id] = candidate

        rows.append(
            LinkageRow(
                record_id=record_id,
                area_code=area_code,
                facility_name=name,
                facility_name_normalized=normalized,
                municipality=municipality,
                match_status=MATCH_STATUS_UNMATCHED,  # 後段で確定させる
                match_method=MATCH_METHOD_NONE,
                reason_code=reason,
                candidate_count=candidate_count,
                match_score=None,
                p04=None,
            )
        )

    rows_by_record_id = {r.record_id: r for r in rows}
    claimed_p04_indices = set()

    contested_exact = _resolve_contested(tentative_exact_by_record_id)
    for record_id, p04 in tentative_exact_by_record_id.items():
        row = rows_by_record_id[record_id]
        if record_id in contested_exact:
            row.reason_code = REASON_CONTESTED_CANDIDATE
            continue
        row.match_status = MATCH_STATUS_MATCHED
        row.match_method = MATCH_METHOD_EXACT
        row.reason_code = ""
        row.p04 = p04
        claimed_p04_indices.add(p04.index)

    tentative_suffix_by_record_id = _find_suffix_tier_matches(rows, by_area, claimed_p04_indices)
    contested_suffix = _resolve_contested(tentative_suffix_by_record_id)
    for record_id, p04 in tentative_suffix_by_record_id.items():
        row = rows_by_record_id[record_id]
        if record_id in contested_suffix:
            row.reason_code = REASON_CONTESTED_CANDIDATE
            continue
        row.match_status = MATCH_STATUS_MATCHED
        row.match_method = MATCH_METHOD_SUFFIX
        row.reason_code = ""
        row.p04 = p04
        claimed_p04_indices.add(p04.index)

    fuzzy_scores = _attach_fuzzy_candidates(rows, by_area, claimed_p04_indices)

    return rows, fuzzy_scores


def _resolve_contested(tentative_p04_by_record_id: dict) -> set:
    """一対一制約: 同じP04フィーチャ(`p04.index`)を複数のExcel施設が
    仮採用していたら、その全員を不採用にする。不採用にしたrecord_idの集合を返す。

    完全一致ティア・接尾一致ティアそれぞれの仮採用マップに対して独立に呼ぶ
    (ティアをまたいだ競合は、接尾一致ティアが完全一致ティア採用済みの
    フィーチャをそもそも候補から除外しているため発生しない)。
    """
    claims = defaultdict(list)
    for record_id, p04 in tentative_p04_by_record_id.items():
        claims[p04.index].append(record_id)
    contested = set()
    for p04_index, record_ids in claims.items():
        if len(record_ids) > 1:
            contested.update(record_ids)
    return contested


def _find_suffix_relation_candidates(normalized_name: str, pool):
    """`pool`(区域内P04候補、既に自動採用済みのフィーチャは除外済み)から、
    `normalized_name`と正規化名が「一方が他方の末尾」の関係(`a.endswith(b)`
    または`b.endswith(a)`)にあり、短い方が`SUFFIX_MIN_SHORT_LEN`文字以上の
    候補を返す(決定的な順序: `pool`の順序をそのまま保つ)。

    完全一致(`a == b`)は対象外(完全一致ティアの対象であり、ここで二重に
    扱うと「候補が複数」の判定が完全一致どうしの重複でも誤って発火するため)。

    ⚠ 保険のガード: 短い方が施設種別語だけ(`is_type_word_only`)の場合も除外
    する。`normalize_facility_name()`側のガードで大半は防げるはずだが
    (法人格語除去後に種別語だけになる場合は除去前の名称を返す)、法人格語
    リストに無い語で種別語だけの短い名称が生じるケースに備えた二重の防御
    (接尾一致ティア側の保険のガード)。
    """
    matches = []
    if not normalized_name:
        return matches
    for c in pool:
        other = c.name_normalized
        if not other or other == normalized_name:
            continue
        if len(other) <= len(normalized_name):
            shorter, longer = other, normalized_name
        else:
            shorter, longer = normalized_name, other
        if len(shorter) < SUFFIX_MIN_SHORT_LEN:
            continue
        if not longer.endswith(shorter):
            continue
        if is_type_word_only(shorter):
            continue
        matches.append(c)
    return matches


def _find_suffix_tier_matches(rows, by_area: dict, claimed_p04_indices: set) -> dict:
    """接尾一致ティアの仮採用マップ(`{record_id: P04Point}`)を構築する。

    完全一致ティアで採用済みの行(`match_status == MATCHED`)はスキップする。
    区域内候補プールから完全一致ティアで採用済みのP04フィーチャ
    (`claimed_p04_indices`)を除外したうえで、`_find_suffix_relation_candidates`
    を適用する:
      - 候補0件: 何もしない(既存のreason_codeを保持)
      - 候補1件: 市区町村整合を満たせば仮採用。満たさなければreason_codeを
        その理由(`municipality_mismatch`/`municipality_not_in_address`)に
        更新する(完全一致ティアの理由より具体的な診断のため上書きする)
      - 候補2件以上: `multiple_candidates_in_area`に更新する(区域内で
        一意に絞れない、という状態は完全一致ティアの理由より正確な診断)
    """
    tentative = {}
    for row in rows:
        if row.match_status == MATCH_STATUS_MATCHED:
            continue
        if not row.municipality:
            continue  # not_reported_facility(市区町村が空)は対象外
        pool = [c for c in by_area.get(row.area_code, []) if c.index not in claimed_p04_indices]
        candidates = _find_suffix_relation_candidates(row.facility_name_normalized, pool)
        if not candidates:
            continue
        if len(candidates) > 1:
            row.reason_code = REASON_MULTIPLE_CANDIDATES_IN_AREA
            row.candidate_count = len(candidates)
            continue
        candidate = candidates[0]
        ok, reason = _municipality_check(candidate.address, row.municipality)
        row.candidate_count = 1
        if ok:
            tentative[row.record_id] = candidate
        else:
            row.reason_code = reason
    return tentative


def _attach_fuzzy_candidates(rows, by_area: dict, claimed_p04_indices: set):
    """`matched`にならなかった行について、区域内P04候補(自動採用済みの
    フィーチャを除く)との名称類似度であいまい候補を探し、閾値
    (`FUZZY_MATCH_THRESHOLD`)以上なら`candidate_only`として`match_score`・
    候補P04を付与する。

    tie-break(同点スコアの候補が複数ある場合)は`p04.index`昇順で決定的に選ぶ。

    戻り値: 区域内候補プールが空でなかった全行の最良類似度のリスト(閾値未満も
    含む。`FUZZY_MATCH_THRESHOLD`の根拠に使う、`match_facilities`のdocstring参照)。
    """
    fuzzy_scores = []
    for row in rows:
        if row.match_status == MATCH_STATUS_MATCHED:
            continue
        pool = [c for c in by_area.get(row.area_code, []) if c.index not in claimed_p04_indices]
        if not pool:
            continue
        scored = sorted(
            (
                (SequenceMatcher(None, row.facility_name_normalized, c.name_normalized).ratio(), c)
                for c in pool
            ),
            key=lambda t: (-t[0], t[1].index),
        )
        best_score, best_candidate = scored[0]
        fuzzy_scores.append(best_score)
        if best_score >= FUZZY_MATCH_THRESHOLD:
            row.match_status = MATCH_STATUS_CANDIDATE_ONLY
            row.match_score = round(best_score, 4)
            row.p04 = best_candidate
            row.candidate_count = len(pool)
    return fuzzy_scores


# ===========================================================================
# 8. 出力
# ===========================================================================

FIELDS_LINKAGE = {
    "record_id": "facility_basic.csvのrecord_idと対応する外部キー(制約はfacility_basic.csv側のfields.record_id参照)",
    "area_code": "構想区域コード(facility_basic.csvより。Excel側の所属区域。P04側から独立に決まる値ではない)",
    "facility_name": "医療機関名(facility_basic.csvより、正規化前)",
    "facility_name_normalized": "normalize_facility_name()による正規化後の医療機関名(NFKC正規化・空白/記号除去・小文字化・法人格語除去)",
    "municipality": "所在地(市区町村、facility_basic.csvより)。未報告の医療機関では空",
    "match_status": (
        "突合結果。'matched'=高信頼条件を満たし座標を自動採用/'candidate_only'="
        "あいまい一致の候補のみ(座標なし)/'unmatched'=候補なしまたは信頼できる"
        "候補が絞れない(座標なし)"
    ),
    "match_method": (
        "採用方法(2ティア、doc/FACILITY_LINKAGE.md「1. 目的と方法」参照)。"
        "'normalized_exact'=正規化名の完全一致+区域内一意+市区町村整合/"
        "'normalized_suffix'=正規化名が「一方が他方の末尾」の関係(法人名等の"
        "有無のみの違い)+区域内一意+短い方が" + str(SUFFIX_MIN_SHORT_LEN) + "文字"
        "以上+市区町村整合/'none'=matched以外"
    ),
    "reason_code": (
        "matchedに至らなかった理由(matched行は空)。'no_name_match'=正規化名が"
        "完全一致する候補が全国に存在しない/'outside_area_polygon'=候補はあるが"
        "当該区域のポリゴン内にない/'municipality_mismatch'=区域内に候補は1件"
        "あるがP04住所から抽出した市区町村がExcel側と異なる/"
        "'municipality_not_in_address'=区域内に候補は1件あるがP04住所に"
        "市区町村名そのものが見当たらない(市名を省略した住所。埼玉県の一部市に"
        "多い。市区町村を抽出できるが違う'municipality_mismatch'とは原因が"
        "異なる)/'multiple_candidates_in_area'=正規化名の完全一致または接尾"
        "一致の候補が区域内に複数あり一意に絞れない(P04側の重複登録が原因の"
        "場合がある。doc/FACILITY_LINKAGE.md参照)/'contested_candidate'=同一の"
        "P04候補を複数のExcel施設が仮採用しようとした(一対一制約違反)/"
        "'not_reported_facility'=Excel側が「未報告」で所在地が空のため"
        "市区町村を検証できない"
    ),
    "candidate_count": (
        "この行の判定に用いた候補数。match_status='candidate_only'の行では"
        "区域内P04候補プール(名称類似度を計算した全候補、自動採用済みの"
        "フィーチャを除く)の件数。reason_code='multiple_candidates_in_area'の"
        "行では、区域内で正規化名の完全一致または接尾一致の関係にあった候補数。"
        "それ以外の行では正規化名が完全一致する候補の件数(区域内、reason_code="
        "'outside_area_polygon'のみ全国)"
    ),
    "match_score": (
        "match_status='candidate_only'のときのみ値を持つ(それ以外は空)。"
        "facility_name_normalizedとp04_name_normalizedのdifflib.SequenceMatcher"
        "類似度(0〜1、閾値はFUZZY_MATCH_THRESHOLD=" + str(FUZZY_MATCH_THRESHOLD) + "、"
        "根拠はdoc/FACILITY_LINKAGE.md参照)"
    ),
    "p04_feature_index": "P04-20.geojsonのfeatures配列内での通し番号(0始まり、歯科診療所を含む全フィーチャに対する連番)。matched/candidate_only以外では空",
    "p04_name": "P04側の医療機関名(P04_002、正規化前)。matched/candidate_only以外では空",
    "p04_name_normalized": "normalize_facility_name()によるP04側名称の正規化後の値",
    "p04_category": "P04側の医療機関分類(P04_001)。1=病院/2=診療所(歯科診療所3は突合対象外)",
    "p04_address": "P04側の所在地文字列(P04_003、都道府県名を含まない原文)",
    "p04_municipality": "extract_municipality()でp04_addressから抽出した市区町村名。抽出できない場合は空",
    "p04_beds": (
        "P04側の病床数(P04_008)。令和2年度時点の値であり、facility_basic.csvの"
        "病床数(令和7年度)とは時点が異なる。**定義も異なる**: P04側は精神病床・"
        "結核病床等を含む総病床数、facility_observations.csvの病床数(「休棟中等"
        "含む計」)は一般・療養病床のみ。この定義差により両者は大きく食い違う"
        "場合があり(精神科病床を主とする病院で顕著、doc/FACILITY_LINKAGE.md"
        "「9. 限界」に実測件数と代表例あり)、参考情報にとどめること。突合の"
        "妥当性検証や、可視化でExcel側の病床数と並べて見せる用途には使わない"
    ),
    "longitude": (
        "P04側の経度(度、JGD2011)。match_status='matched'の行にのみ値を持つ"
        "(位置の推測はしないため、'candidate_only'は候補の名前・住所等の識別情報"
        "とスコアのみを出力し座標は与えない。doc/REQUIREMENTS.md §4.3参照)"
    ),
    "latitude": "P04側の緯度(度、JGD2011)。longitudeと同様、match_status='matched'の行にのみ値を持つ",
}

CAVEAT = (
    "位置の推測はしない(doc/REQUIREMENTS.md §4.3): 自動採用(match_status="
    "'matched')は(1)正規化名の完全一致(match_method='normalized_exact')、"
    "または(2)正規化名が一方が他方の末尾の関係にあり短い方が一定文字数以上"
    "(match_method='normalized_suffix')のいずれかに加え、区域内一意+市区町村"
    "整合+一対一制約の全てを満たす場合のみで、あいまいな一致は座標を与えず"
    "candidate_onlyとして候補のみ報告する。"
    "P04は令和2年度・Excel(facility_basic.csv)は令和7年度公表であり、5年の"
    "開差がある(開設・閉院・改称・移転が未マッチの一因になりうるが、個別の"
    "未マッチ理由を「改称」「閉院」等と断定はしない。観測できるのは「名称"
    "一致候補なし」等の事実のみ)。詳細な方法・実測値はdoc/FACILITY_LINKAGE.md"
    "を参照。未マッチの医療機関は地図上のポイント表示には使わず、一覧表示"
    "でのみ扱うこと。"
)


def _rows_to_output_dicts(rows):
    """`LinkageRow`のリストを出力用dictのリストへ変換する。

    座標(longitude/latitude)は`match_status='matched'`の行にのみ与える。
    `candidate_only`は「候補の名前とスコアだけ」出力し座標は空のままにする
    (位置の推測をしないという方針、モジュールdocstring・
    doc/REQUIREMENTS.md §4.3参照)。P04側の名称・住所等(監査用の識別情報)は
    matched/candidate_onlyの両方で出力する。
    """
    out = []
    for r in rows:
        p04 = r.p04
        has_coords = p04 is not None and r.match_status == MATCH_STATUS_MATCHED
        out.append(
            {
                "record_id": r.record_id,
                "area_code": r.area_code,
                "facility_name": r.facility_name,
                "facility_name_normalized": r.facility_name_normalized,
                "municipality": r.municipality,
                "match_status": r.match_status,
                "match_method": r.match_method,
                "reason_code": r.reason_code,
                "candidate_count": r.candidate_count,
                "match_score": r.match_score if r.match_score is not None else "",
                "p04_feature_index": p04.index if p04 else "",
                "p04_name": p04.name if p04 else "",
                "p04_name_normalized": p04.name_normalized if p04 else "",
                "p04_category": p04.category if p04 else "",
                "p04_address": p04.address if p04 else "",
                "p04_municipality": (p04.municipality or "") if p04 else "",
                "p04_beds": p04.beds if p04 and p04.beds is not None else "",
                "longitude": p04.lon if has_coords else "",
                "latitude": p04.lat if has_coords else "",
            }
        )
    return out


OUTPUT_HEADER = [
    "record_id",
    "area_code",
    "facility_name",
    "facility_name_normalized",
    "municipality",
    "match_status",
    "match_method",
    "reason_code",
    "candidate_count",
    "match_score",
    "p04_feature_index",
    "p04_name",
    "p04_name_normalized",
    "p04_category",
    "p04_address",
    "p04_municipality",
    "p04_beds",
    "longitude",
    "latitude",
]


# ===========================================================================
# 9. レポート(doc/FACILITY_LINKAGE.md)
# ===========================================================================


def _fmt_pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "-"
    return f"{numerator / denominator * 100:.1f}%"


def build_report_markdown(
    *,
    rows,
    facilities,
    p04_points,
    by_name: dict,
    area_index: AreaIndex,
    bed_bands: dict,
    bed_counts: dict,
    p04_category_counts: dict,
    fuzzy_scores: list,
) -> str:
    """`doc/FACILITY_LINKAGE.md`の本文を組み立てる(生成日時は含めない)。

    実行時間(P04読み込み・突合の所要秒数)も、実行のたびに変わりバイト一致の
    再現性テストを壊すため(CLAUDE.md「生成物には生成日時を埋め込まない」と
    同じ理由)、レポート本文には含めない。標準出力へのログ(`build_and_write`
    の`print()`)にのみ出す。
    """
    lines = []
    a = lines.append

    total = len(rows)
    status_counts = Counter(r.match_status for r in rows)
    reason_counts = Counter(r.reason_code for r in rows if r.match_status != MATCH_STATUS_MATCHED)

    a("# 医療機関データ(P04)突合レポート")
    a("")
    a("このファイルは `python tools/build_facility_geo_linkage.py` が生成する。手で編集しないこと。")
    a("再生成コマンド: `PYTHONIOENCODING=utf-8 python tools/build_facility_geo_linkage.py`")
    a("")

    # --- 1. 目的と方法 -----------------------------------------------------
    a("## 1. 目的と方法")
    a("")
    a(
        "`data/processed/facility_basic.csv`(339構想区域×医療機関、"
        f"{len(facilities)}件、令和7年度公表)の各医療機関に、国土数値情報"
        "「医療機関データ」P04-20(`ksj/P04-20/P04-20_GML.zip`、令和2年度、点データ)"
        "を突合して座標を与える試み。"
    )
    a("")
    a(
        "**保守的採用にした理由**: このスクリプトは`verify_*`という名前を持たない。"
        "実際にやっているのは検証(既に正しいと分かっている2つのものを照合すること)"
        "ではなく、あいまいさを伴うレコードリンケージ(ヒューリスティックに同一"
        "実体を推定すること)である。マッチ率を最大化するのではなく、**誤結合の"
        "少なさ**と**監査可能性**を最適化する設計とした: 自動採用"
        "(`match_status='matched'`)は高信頼条件をすべて満たす場合のみに限り、"
        "あいまいな一致は座標を与えず候補(`candidate_only`)として報告するに"
        "とどめる。誤って別の医療機関の座標を採用することは、座標が無いことよりも"
        "悪い結果になる(可視化の利用者が誤った場所の医療機関情報を見ることに"
        "なる)ため。未マッチの医療機関は地図上のポイント表示には使わず、"
        "一覧表示でのみ扱う方針とする(`doc/REQUIREMENTS.md` §4.3)。"
    )
    a("")
    a(
        "自動採用(`matched`)は**2ティア**で構成する(レビューで判明した2つの"
        "取りこぼしパターンへの対処。詳細は各項目末尾の理由参照):"
    )
    a("")
    a("### 完全一致ティア(`match_method='normalized_exact'`)")
    a("")
    a("以下を**すべて**満たす場合のみ:")
    a("")
    a("1. 正規化名(`normalize_facility_name()`。NFKC正規化・空白/記号除去・小文字化・法人格語除去)が完全一致する候補が、Excel施設の所属区域ポリゴン内にちょうど1件")
    a(
        "2. 市区町村の整合(`address_matches_municipality()`): P04住所(先頭の"
        "都道府県名を除去)が、Excel側の市区町村名(facility_basic.csvの値。"
        "常に「札幌市北区」のような完全な形)で始まっている。**政令指定都市名を"
        "省略し区名から始まる住所**(例 横浜市を省略した`'港北区小机町…'`)も、"
        "区名がExcel側の市区町村名の**末尾**と一致すれば整合とみなす"
        "(例 `'港北区…'` × `'横浜市港北区'` → 整合。区域ポリゴンで既に絞り込んだ"
        "候補について、Excel側が既に持っている正しい市区町村名の末尾と照合する"
        "だけなので、これは判定の緩和ではなく本来拾えるはずの取りこぼしの是正"
        "である。実測でこの是正により151件回収できた、全て神奈川県)"
    )
    a("3. 一対一制約: 同じP04フィーチャを複数のExcel施設が仮採用していない(競合したら両方とも不採用)")
    a("")
    a("### 接尾一致ティア(`match_method='normalized_suffix'`)")
    a("")
    a(
        "完全一致ティアでは、Excel側とP04側のどちらか一方だけが法人名や"
        "「総合病院」等の通称を伴う場合(例: Excel`山梨県立中央病院` × "
        "P04`地方独立行政法人山梨県立病院機構山梨県立中央病院`、"
        "Excel`公益財団法人操風会岡山旭東病院` × P04`岡山旭東病院`)を"
        "取りこぼす(正規化しても完全一致しないため)。これが`no_name_match`の"
        "主因になっていた。以下を**すべて**満たす場合のみ追加で採用する:"
    )
    a("")
    a(
        "1. 完全一致ティアで採用されなかった施設について、区域内のP04候補"
        "(**完全一致ティアで既に採用済みのフィーチャを除く**)のうち、正規化名が"
        "「一方が他方の末尾」の関係(`a.endswith(b) or b.endswith(a)`)にある"
        "ものがちょうど1件"
    )
    a(f"2. 短い方の正規化名が{SUFFIX_MIN_SHORT_LEN}文字以上(「中央病院」のような汎用語1つが偶然共通するだけの誤結合を防ぐ)")
    a("3. 市区町村の整合(完全一致ティアと同じ`address_matches_municipality()`の判定)")
    a("4. 一対一制約(完全一致ティアとは独立に適用。競合したら両方とも不採用)")
    a("")
    a(
        "**接尾一致ティアを完全一致ティアと別のティアにしている理由**: 完全一致"
        "ティアは名称のみで機械的に(スコアや閾値なしで)一意に定まるため、"
        "`match_method`で単純にフィルタするだけで「完全一致のみ」に絞り込める。"
        "両者を1つのティアに混ぜてしまうと、法人格や通称の有無だけが違う正当な"
        "同一施設と、たまたま部分文字列が一致するだけの別施設を同じ精度として"
        "扱うことになり、監査可能性が下がる。`match_score`は接尾一致では使わない"
        "(`difflib.SequenceMatcher`のスコアではなく、文字列の包含関係という"
        "別の基準で判定しているため空のまま)。"
    )
    a("")
    a(
        "点-多角形判定(どの構想区域に属するか)は、339区域ポリゴンに対し"
        f"{GRID_CELL_DEG}度グリッドで候補区域を絞ってからレイキャスティング"
        "(MultiPolygon・穴に対応)で行い、全P04点×全区域の総当たりは避けている。"
        "P04にはExcel側と異なり都道府県コード・市区町村コードが無いため"
        "(住所文字列のみ)、この点-多角形判定が同名市区町村(例: 府中市"
        "(東京/広島)・伊達市(北海道/福島))を切り分ける役割を担う。"
    )
    a("")

    # --- 2. 全体のマッチ率 --------------------------------------------------
    a("## 2. 全体のマッチ率")
    a("")
    a("| match_status | 件数 | 割合 |")
    a("|---|---|---|")
    for status in (MATCH_STATUS_MATCHED, MATCH_STATUS_CANDIDATE_ONLY, MATCH_STATUS_UNMATCHED):
        cnt = status_counts.get(status, 0)
        a(f"| {status} | {cnt} | {_fmt_pct(cnt, total)} |")
    a(f"| 合計 | {total} | 100.0% |")
    a("")
    a("`matched`(自動採用)のティア別内訳:")
    a("")
    method_counts = Counter(r.match_method for r in rows if r.match_status == MATCH_STATUS_MATCHED)
    matched_total = status_counts.get(MATCH_STATUS_MATCHED, 0)
    a("| match_method | 件数 | 割合(matched中) |")
    a("|---|---|---|")
    for method in (MATCH_METHOD_EXACT, MATCH_METHOD_SUFFIX):
        cnt = method_counts.get(method, 0)
        a(f"| {method} | {cnt} | {_fmt_pct(cnt, matched_total)} |")
    a(f"| 合計 | {matched_total} | 100.0% |")
    a("")

    # --- 3. reason_code別内訳 -----------------------------------------------
    a("## 3. reason_code別内訳(matched以外)")
    a("")
    a("| reason_code | 件数 | 内容 |")
    a("|---|---|---|")
    non_matched_total = total - status_counts.get(MATCH_STATUS_MATCHED, 0)
    for reason in (
        REASON_NO_NAME_MATCH,
        REASON_OUTSIDE_AREA_POLYGON,
        REASON_MUNICIPALITY_MISMATCH,
        REASON_MUNICIPALITY_NOT_IN_ADDRESS,
        REASON_MULTIPLE_CANDIDATES_IN_AREA,
        REASON_CONTESTED_CANDIDATE,
        REASON_NOT_REPORTED_FACILITY,
    ):
        cnt = reason_counts.get(reason, 0)
        a(f"| {reason} | {cnt} | {REASON_LABELS[reason]} |")
    a(f"| 合計(matched以外) | {non_matched_total} | |")
    a("")
    contested_facility_count = reason_counts.get(REASON_CONTESTED_CANDIDATE, 0)
    a(
        f"一対一制約(同じP04フィーチャを複数のExcel施設が仮採用しようとした場合、"
        f"全員を不採用にする)により不採用になった件数: {contested_facility_count}件。"
    )
    a("")

    multiple_rows = [r for r in rows if r.reason_code == REASON_MULTIPLE_CANDIDATES_IN_AREA]
    dup_examples = []
    for r in multiple_rows:
        pool = by_name.get(r.facility_name_normalized, [])
        same_name_in_area = [c for c in pool if c.area_code == r.area_code]
        if len(same_name_in_area) > 1:
            dup_examples.append((r, same_name_in_area))
    # レビューで名指しされた例(P04側の重複登録: 表記の空白の有無だけが違う2つの
    # レコードが正規化後に同一の文字列になる)があれば、代表例の先頭に出す。
    dup_examples.sort(key=lambda t: 0 if "牧田総合病院" in t[0].facility_name else 1)
    a(
        f"`multiple_candidates_in_area`(候補が複数あり一意に絞れないため不採用のまま)"
        f"は{len(multiple_rows)}件。うち{len(dup_examples)}件は、区域内に**正規化名が"
        "完全に同一のP04フィーチャが複数存在する**ケースである。これには2通りの原因が"
        "混在する: (a) P04側で同一の実在施設が重複登録されている(例えば表記の空白の"
        "有無だけが違う2つのレコードが正規化後には同一の文字列になる。下表の"
        "「牧田総合病院」参照)、(b) たまたま同一名称の別施設がExcel側にもP04側にも"
        "複数存在する(下表の「渡辺眼科医院」は仙台市青葉区と塩竈市の異なる医療機関)。"
        "いずれも名称のみからは一意に決定できないため、本スクリプトは両方とも採用しない"
        "(P04側の重複登録そのものを名寄せ・統合することも本スクリプトの対象外とする)。"
        "代表例:"
    )
    a("")
    a("| Excel施設名 | 区域 | 市区町村 | 正規化名 | P04側の同名候補(住所) |")
    a("|---|---|---|---|---|")
    for r, cands in dup_examples[:5]:
        area_name = _area_name(facilities, r.area_code)
        addr_list = "；".join(f"{c.name}({c.address})" for c in cands)
        a(f"| {r.facility_name} | {r.area_code}{area_name} | {r.municipality} | {r.facility_name_normalized} | {addr_list} |")
    a("")
    a("これらは`unmatched`または`candidate_only`のまま残る(座標は自動採用しない)。")
    a("")

    # --- 4. 都道府県別マッチ率 -----------------------------------------------
    a("## 4. 都道府県別マッチ率")
    a("")
    pref_by_record_id = {f["record_id"]: (f["pref_code"], f["pref_name"]) for f in facilities}
    pref_total = Counter()
    pref_matched = Counter()
    for r in rows:
        pref_code, pref_name = pref_by_record_id[r.record_id]
        key = (pref_code, pref_name)
        pref_total[key] += 1
        if r.match_status == MATCH_STATUS_MATCHED:
            pref_matched[key] += 1
    pref_rates = {
        key: (pref_matched.get(key, 0) / pref_total[key] if pref_total[key] else 0.0) for key in pref_total
    }
    ranked = sorted(pref_rates.items(), key=lambda kv: (kv[1], kv[0]))
    min_key, min_rate = ranked[0]
    max_key, max_rate = ranked[-1]
    a(
        f"47都道府県中、マッチ率が最も低いのは{min_key[1]}"
        f"({pref_matched.get(min_key, 0)}/{pref_total[min_key]}件、{_fmt_pct(pref_matched.get(min_key, 0), pref_total[min_key])})、"
        f"最も高いのは{max_key[1]}"
        f"({pref_matched.get(max_key, 0)}/{pref_total[max_key]}件、{_fmt_pct(pref_matched.get(max_key, 0), pref_total[max_key])})。"
    )
    a("")
    a("| 都道府県コード | 都道府県 | 施設数 | matched | マッチ率 |")
    a("|---|---|---|---|---|")
    for (pref_code, pref_name), _rate in sorted(pref_rates.items(), key=lambda kv: kv[0]):
        tot = pref_total[(pref_code, pref_name)]
        mat = pref_matched.get((pref_code, pref_name), 0)
        a(f"| {pref_code} | {pref_name} | {tot} | {mat} | {_fmt_pct(mat, tot)} |")
    a("")

    # --- 5. 病床規模別マッチ率 -----------------------------------------------
    a("## 5. 病床規模別マッチ率")
    a("")
    a(
        "`facility_observations.csv`の病床数(「休棟中等含む計」)から求めた"
        "規模帯別(値が観測できない医療機関は`未報告`帯)。"
    )
    a("")
    band_total = Counter()
    band_matched = Counter()
    for r in rows:
        band = bed_bands.get(r.record_id, BED_BAND_NOT_REPORTED)
        band_total[band] += 1
        if r.match_status == MATCH_STATUS_MATCHED:
            band_matched[band] += 1
    a("| 病床規模 | 施設数 | matched | マッチ率 |")
    a("|---|---|---|---|")
    for band in BED_BAND_ORDER:
        tot = band_total.get(band, 0)
        mat = band_matched.get(band, 0)
        a(f"| {band} | {tot} | {mat} | {_fmt_pct(mat, tot)} |")
    a("")

    # --- 6. あいまい一致(candidate_only)の代表例と閾値の根拠 -------------------
    a("## 6. あいまい一致(candidate_only)の代表例と閾値の根拠")
    a("")
    candidate_rows = [r for r in rows if r.match_status == MATCH_STATUS_CANDIDATE_ONLY]
    a(f"`candidate_only`(座標を与えないあいまい候補)の件数: {len(candidate_rows)}件。")
    a("")
    a(
        f"**閾値の根拠**: `FUZZY_MATCH_THRESHOLD = {FUZZY_MATCH_THRESHOLD}`。自動採用に"
        "至らなかった全施設のうち、区域内P04候補プールが空でなかった"
        f"{len(fuzzy_scores)}件について、区域内候補との最良類似度"
        "(`difflib.SequenceMatcher`)の分布を実測すると以下のとおり"
        "(閾値未満のスコアも含む全件の分布):"
    )
    a("")
    a("| スコア帯 | 件数 |")
    a("|---|---|")
    score_bins = [
        (0.0, 0.5, "0.5未満"),
        (0.5, 0.6, "0.5以上0.6未満"),
        (0.6, 0.7, "0.6以上0.7未満"),
        (0.7, 0.8, "0.7以上0.8未満"),
        (0.8, 0.9, "0.8以上0.9未満"),
        (0.9, 1.0, "0.9以上1.0未満"),
        (1.0, 1.0 + 1e-9, "1.0(完全一致)"),
    ]
    for lo, hi, label in score_bins:
        cnt = sum(1 for s in fuzzy_scores if lo <= s < hi)
        a(f"| {label} | {cnt} |")
    a("")
    below_threshold = sum(1 for s in fuzzy_scores if s < FUZZY_MATCH_THRESHOLD)
    at_or_above_threshold = sum(1 for s in fuzzy_scores if s >= FUZZY_MATCH_THRESHOLD)
    a(
        f"閾値{FUZZY_MATCH_THRESHOLD}未満: {below_threshold}件(`unmatched`のまま)。"
        f"{FUZZY_MATCH_THRESHOLD}以上: {at_or_above_threshold}件(`candidate_only`として報告)。"
        "スコア1.0(名称は完全一致するが市区町村不一致・区域内複数・一対一制約違反等"
        "で自動採用に至らなかった候補)は、そのまま高スコアの`candidate_only`として"
        "扱われ、人手確認の対象として残る。"
    )
    a("")
    a("代表例(スコア降順、上位10件):")
    a("")
    a("| Excel施設名 | 正規化名 | P04候補名 | 候補正規化名 | スコア | 区域 |")
    a("|---|---|---|---|---|---|")
    for r in sorted(candidate_rows, key=lambda r: -(r.match_score or 0))[:10]:
        area_name = _area_name(facilities, r.area_code)
        a(
            f"| {r.facility_name} | {r.facility_name_normalized} | {r.p04.name} | "
            f"{r.p04.name_normalized} | {r.match_score} | {r.area_code}{area_name} |"
        )
    a("")

    # --- 7. 未マッチの代表例 -------------------------------------------------
    a("## 7. 未マッチ(unmatched)の代表例")
    a("")
    unmatched_rows = [r for r in rows if r.match_status == MATCH_STATUS_UNMATCHED]
    a(f"`unmatched`(候補なし、または信頼できる候補が絞れない)の件数: {len(unmatched_rows)}件。代表例(reason_code別、各3件まで):")
    a("")
    a("| reason_code | Excel施設名 | 区域 | 市区町村 |")
    a("|---|---|---|---|")
    for reason in (
        REASON_NO_NAME_MATCH,
        REASON_OUTSIDE_AREA_POLYGON,
        REASON_MUNICIPALITY_MISMATCH,
        REASON_MUNICIPALITY_NOT_IN_ADDRESS,
        REASON_MULTIPLE_CANDIDATES_IN_AREA,
        REASON_CONTESTED_CANDIDATE,
        REASON_NOT_REPORTED_FACILITY,
    ):
        examples = [r for r in unmatched_rows if r.reason_code == reason][:3]
        for r in examples:
            area_name = _area_name(facilities, r.area_code)
            a(f"| {reason} | {r.facility_name} | {r.area_code}{area_name} | {r.municipality or '(空)'} |")
    a("")

    # --- 8. P04の読み込み内訳と実行時間 --------------------------------------
    a("## 8. P04の読み込み内訳と実行時間")
    a("")
    a("| 区分 | 件数 |")
    a("|---|---|")
    a(f"| 病院(P04_001=1) | {p04_category_counts.get(CATEGORY_HOSPITAL, 0)} |")
    a(f"| 診療所(P04_001=2) | {p04_category_counts.get(CATEGORY_CLINIC, 0)} |")
    a(f"| 歯科診療所(P04_001=3、突合対象外) | {p04_category_counts.get(CATEGORY_DENTAL, 0)} |")
    a(f"| 合計(features配列の全件数) | {sum(p04_category_counts.values())} |")
    a("")
    unassigned = sum(1 for p in p04_points if p.area_code is None)
    a(
        f"突合対象(病院+診療所)の{len(p04_points)}件のうち、{unassigned}件はどの構想区域"
        "ポリゴンにも属さなかった(離島除去等で境界データから外れた地点。「9. 限界」参照)。"
    )
    a(
        "実行時間(P04読み込み・突合それぞれの所要秒数)は実行環境により変動し、"
        "埋め込むと再生成のたびにこのレポートへ差分が出てしまうため"
        "(バイト一致の再現性テストが壊れる)、ここには記載しない。"
        "`python tools/build_facility_geo_linkage.py` 実行時の標準出力ログに"
        "毎回の実測値が出力される。"
    )
    a("")

    # --- 9. 限界 -------------------------------------------------------------
    a("## 9. 限界")
    a("")
    a(
        "- **5年の開差**: P04は令和2年度、Excel(`facility_basic.csv`)は令和7年度公表であり、"
        "5年の間に開設・閉院・改称・移転があった医療機関は名称や所在地が一致しなくなる。"
        "ただし本レポート・出力データは個別の未マッチ理由を「改称」「閉院」等と断定しない"
        "(観測できるのは「正規化名が完全一致する候補が見つからない」等の事実のみであり、"
        "その原因が開設/閉院/改称/移転/表記差のいずれであるかはこのデータからは分からない)。"
    )
    a(
        "- **境界の出自**: 三重県8区域(2405〜2412)の境界(`data/processed/area_boundaries_R7.geojson`)"
        "は国土数値情報の公表物ではなく、市区町村ポリゴンから合成した派生物である"
        "(`boundary_source`フィールドで区別できる。詳細は`doc/JOIN_VERIFICATION.md`参照)。"
        "この8区域内の点-多角形判定は、この派生境界に対して行っている。"
    )
    a(
        f"- **境界の簡略化による離島除去**: 面積1km²未満の離島は`area_boundaries_R7.geojson`"
        "生成時に除去されているため、離島の医療機関(P04側の点)はどの区域ポリゴンにも属さず"
        f"({unassigned}件、上記「8.」参照)、区域内候補として扱われない。"
    )
    a(
        "- **名寄せの限界**: `normalize_facility_name()`・`extract_municipality()`はいずれも"
        "決定的なヒューリスティックであり、住所表記や施設名表記の全ての揺れを網羅するもの"
        "ではない。"
    )
    bare_ward_count = count_bare_ward_addresses(p04_points)
    a(
        f"- **政令指定都市名を省略した住所**: P04住所は都道府県名を含まないのが原則だが"
        "(実測で長崎県・島根県・宮崎県等の一部は都道府県名付きで記載されており、"
        "`extract_municipality()`は先頭の都道府県名を検出して除去したうえで処理する)、"
        "政令指定都市についても市名を省略していきなり区名から書き始める住所が実測で"
        f"約{bare_ward_count}件見つかった(例: 横浜市を省略した「港北区小机町3211」)。"
        "`address_matches_municipality()`は、区名がExcel側の市区町村名の末尾と一致"
        "すれば整合とみなす(「1. 目的と方法」参照。実測で151件回収)ため、区域内に"
        "候補が一意に絞れる場合は自動採用できる。それでも解決しない残りのケース"
        "(例えば区域内の候補が複数ある、または区名自体が一致しない)は、"
        "`extract_municipality()`(情報列`p04_municipality`用、この関数の仕様は"
        "変更していない)がこの形の住所から市区町村名を復元できないため"
        "`municipality_not_in_address`または`multiple_candidates_in_area`のまま"
        "残り、座標は自動採用されない(誤結合を避けるための意図的な保守側への倒し)。"
    )
    a(
        "- **市区町村名そのものを省略した住所**: 政令指定都市の区に限らず、一部の"
        "(主に埼玉県の)市でも、市名を省略して大字・町名から直接書き始める住所が"
        "実測で見つかった(例: 「戸田市立市民医療センター」の所在地は「戸田市」"
        "を含まない「美女木4-20-1」)。この住所には市区町村名に相当するものが"
        "文字列としてそもそも存在しないため、`municipality_not_in_address`"
        "(`municipality_mismatch`とは別に分類。上記「3.」参照)に"
        "分類される。「川柳町3-50-1」(Excel側`越谷市`)のように、市内の字・地区名"
        "が偶然「町」で終わるだけで独立した市区町村ではない住所も同様に扱う"
        "(`extract_municipality()`の郡なし「○○町/村」フォールバックは、住所形式"
        "だけからは独立した町(例: 山梨県の郡表記省略)と市内の地区名を区別できない"
        "ため、`municipality_not_in_address`の判定には低信頼フォールバックを使わない"
        "`_extract_municipality_confident()`を別に用いている。`p04_municipality`列"
        "(監査用の表示値)自体は`extract_municipality()`のままで変更していない)。"
        "この形の住所は市区町村の整合を検証できず`municipality_not_in_address`の"
        "まま残る(座標を推測しないという方針どおりの挙動)。"
    )
    a(
        "- **行政区域の再編による正当な不一致**: 浜松市は2024年1月に7区"
        "(中区・東区・西区・南区・北区・浜北区・天竜区)から3区(中央区・浜名区・"
        "天竜区)へ再編されている。P04(令和2年度、旧7区)とfacility_basic.csv"
        "(令和7年度、新3区)はこの再編の前後にまたがるため、同一施設でも区名が"
        "一致せず`municipality_mismatch`になる。これは名寄せの不具合ではなく、"
        "参照している行政区域そのものが異なる時点のものであることによる正当な不一致。"
    )
    a(
        "- **地名の表記ゆれ(小書き片仮名)**: 「龍ケ崎市」と「龍ヶ崎市」、「駒ヶ根市」と"
        "「駒ケ根市」のように、小書きの「ヶ/ヵ」と通常大の「ケ/カ」が原典間で混在する"
        "地名がある。`address_matches_municipality()`はこの表記ゆれを比較前に"
        "吸収するが、`p04_municipality`列(監査用の表示値)は原典の表記のまま変更"
        "していない。"
    )
    divergent = _compute_bed_divergence(rows, bed_counts)
    both_observed = sum(
        1 for r in rows if r.match_status == MATCH_STATUS_MATCHED and bed_counts.get(r.record_id) and r.p04.beds
    )
    psych_named = sum(1 for row, *_ in divergent if "精神" in row.facility_name)
    a(
        "- **`p04_beds`とExcel側病床数は定義が異なり、突合の妥当性検証には使えない**"
        ": `matched`行についてExcel側病床数"
        "(`facility_observations.csv`の「病床数」「休棟中等含む計」)と`p04_beds`を"
        f"突き合わせたところ、両者とも観測できた{both_observed}件中、"
        f"比率{BED_DIVERGENCE_RATIO}倍以上**かつ**絶対差{BED_DIVERGENCE_ABS_MIN}床以上"
        f"乖離する行が**{len(divergent)}件**あった(実測値。閾値の設定根拠は"
        "`BED_DIVERGENCE_RATIO`/`BED_DIVERGENCE_ABS_MIN`のコメント参照。単純な"
        "比率だけを閾値にすると、病床数が1桁の小規模診療所"
        "(診療所の法定病床数上限19床に起因するとみられる、Excel1床/P04 19床"
        "等)が多数混入し実態を見えにくくするため、絶対差も条件に加えている)。"
        "これは誤結合ではなく**定義差**によるもの: P04側(`P04_008`)は精神病床・"
        "結核病床等を含む**総病床数**である一方、Excel側(病床機能報告)は"
        "**一般・療養病床のみ**を対象とする。乖離が大きい行の施設名を確認すると、"
        "精神科病床を主とする病院とみられるものが多い(下表参照。例えば"
        "東京都立松沢病院・浅香山病院・紘仁病院は、いずれも一般に精神科病院"
        "として知られる)。ただし施設名からの目視確認であり、P04・Excelいずれの"
        "データにも診療科別の病床区分は含まれないため網羅的な確認はできない"
        f"(施設名に「精神」を含むもの{psych_named}/{len(divergent)}件、"
        "精神科病院の名称は必ずしも「精神」を含まないため過小な数値)。"
        "したがって`p04_beds`は参考情報にとどめ、**可視化でExcel側の病床数と"
        "並べて(あたかも同じ定義の値であるかのように)見せてはならない**。"
        "代表例(絶対差降順、上位10件):"
    )
    a("")
    a("| Excel施設名 | 区域 | Excel病床数 | p04_beds | 差(床) | 倍率 |")
    a("|---|---|---|---|---|---|")
    for row, excel_beds, p04_beds, ratio in sorted(divergent, key=lambda t: -abs(t[1] - t[2]))[:10]:
        area_name = _area_name(facilities, row.area_code)
        a(
            f"| {row.facility_name} | {row.area_code}{area_name} | {excel_beds} | {p04_beds} | "
            f"{abs(excel_beds - p04_beds)} | {ratio:.1f}倍 |"
        )
    a("")
    a(
        "- **未マッチ施設の扱い**: 未マッチ(`unmatched`/`candidate_only`)の医療機関は地図上の"
        "ポイント表示には使わず、一覧表示でのみ扱うこと(`doc/REQUIREMENTS.md` §4.3)。"
    )
    a("")

    # --- 10. 再現手順 ---------------------------------------------------
    a("## 10. 再現手順")
    a("")
    a("```bash")
    a("PYTHONIOENCODING=utf-8 python tools/build_facility_geo_linkage.py")
    a("```")
    a("")
    a(
        "上記の実測値は `tools/tests/test_build_facility_geo_linkage.py` にpytestの"
        "期待値として固定してあり、`pytest` で継続的に検証される。"
    )
    a("")

    return "\n".join(lines) + "\n"


def _area_name(facilities, area_code: str) -> str:
    for f in facilities:
        if f["area_code"] == area_code:
            return f["area_name"]
    return ""


# ===========================================================================
# 10. エントリポイント
# ===========================================================================


def _sha256_zip_member(zip_path: Path, member_name: str) -> str:
    h = hashlib.sha256()
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(member_name) as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def build_and_write(out_dir: Path, doc_dir: Path) -> dict:
    """全処理(読み込み→突合→出力)を実行する。

    `out_dir`に`facility_geo_linkage.csv`(+`.meta.json`)を、`doc_dir`に
    `FACILITY_LINKAGE.md`を出力する。テスト(再現性の検証)から一時ディレクトリを
    渡して呼べるよう出力先をパラメータ化してある。

    戻り値: `{"csv": ..., "meta": ..., "doc": ...}` の`Path`辞書。
    """
    import time

    out_dir = Path(out_dir)
    doc_dir = Path(doc_dir)

    excel_sha256 = verify_source(EXCEL_PATH_IN_REPO)
    print(f"[ok] 生データ検証: {EXCEL_PATH_IN_REPO} = {excel_sha256[:16]}...")
    p04_zip_sha256 = verify_source(P04_ZIP_PATH_IN_REPO)
    print(f"[ok] 生データ検証: {P04_ZIP_PATH_IN_REPO} = {p04_zip_sha256[:16]}...")
    p04_member_sha256 = _sha256_zip_member(P04_ZIP_PATH, P04_MEMBER_NAME)
    print(f"[ok] zip内メンバー検証: {P04_MEMBER_NAME} = {p04_member_sha256[:16]}...")
    boundaries_sha256 = sha256(AREA_BOUNDARIES_PATH)
    print(f"[ok] {AREA_BOUNDARIES_PATH.name} = {boundaries_sha256[:16]}...")
    facility_basic_sha256 = sha256(FACILITY_BASIC_CSV)
    print(f"[ok] {FACILITY_BASIC_CSV.name} = {facility_basic_sha256[:16]}...")

    with open(AREA_BOUNDARIES_PATH, "r", encoding="utf-8") as f:
        boundaries_geojson = json.load(f)
    area_index = AreaIndex(boundaries_geojson)
    print(f"[ok] {AREA_BOUNDARIES_PATH.name} 読み込み: {area_index.area_count}区域")

    t0 = time.time()
    p04_points, p04_category_counts = load_p04_points(P04_ZIP_PATH, area_index)
    by_name, by_area = build_p04_indices(p04_points)
    p04_load_seconds = time.time() - t0
    print(
        f"[ok] P04読み込み: 病院+診療所={len(p04_points)}件"
        f"(病院={p04_category_counts.get(CATEGORY_HOSPITAL, 0)}"
        f" 診療所={p04_category_counts.get(CATEGORY_CLINIC, 0)}"
        f" 歯科除外={p04_category_counts.get(CATEGORY_DENTAL, 0)}) {p04_load_seconds:.1f}秒"
    )

    facilities = load_facilities()
    print(f"[ok] facility_basic.csv 読み込み: {len(facilities)}件")
    bed_bands = load_bed_size_bands()
    bed_counts = load_bed_counts()

    t0 = time.time()
    rows, fuzzy_scores = match_facilities(facilities, by_name, by_area)
    match_seconds = time.time() - t0
    status_counts = Counter(r.match_status for r in rows)
    print(
        f"[ok] 突合完了({match_seconds:.1f}秒): "
        f"matched={status_counts.get(MATCH_STATUS_MATCHED, 0)} "
        f"candidate_only={status_counts.get(MATCH_STATUS_CANDIDATE_ONLY, 0)} "
        f"unmatched={status_counts.get(MATCH_STATUS_UNMATCHED, 0)}"
    )

    today = datetime.date.today().isoformat()
    source = {
        "name": "facility_basic.csv(構想区域別医療機関一覧) × 国土数値情報P04-20(医療機関データ点)のレコードリンケージ",
        "inputs": [
            {
                "file": EXCEL_PATH_IN_REPO,
                "role": "突合対象の医療機関一覧(名称・所在地・区域)の原典",
                "source_sha256": excel_sha256,
            },
            {
                "file": P04_ZIP_PATH_IN_REPO,
                "role": "座標の付与元(国土数値情報 医療機関データ、令和2年度)",
                "source_sha256": p04_zip_sha256,
            },
            {
                "file": f"{P04_ZIP_PATH_IN_REPO} 内 {P04_MEMBER_NAME}",
                "role": "zip内メンバーそのもののハッシュ(抽出手順の監査用)",
                "source_sha256": p04_member_sha256,
            },
            {
                "file": "data/processed/area_boundaries_R7.geojson",
                "role": "点-多角形判定に用いた339構想区域ポリゴン",
                "source_sha256": boundaries_sha256,
            },
            {
                "file": "data/processed/facility_basic.csv",
                "role": "突合対象そのもの(コミット済みデータのハッシュ、再現性の監査用)",
                "source_sha256": facility_basic_sha256,
            },
        ],
        "license": LICENSE_NOTE,
        "page_url": P04_SOURCE_PAGE,
    }
    processing = {
        "script": "tools/build_facility_geo_linkage.py",
        "date": today,
        "method": (
            "マッチ率ではなく誤結合の少なさと監査可能性を最適化した保守的なレコード"
            "リンケージ。自動採用(matched)は2ティア: (1)normalized_exact=正規化名の"
            "完全一致+区域内一意+市区町村整合、(2)normalized_suffix=正規化名が"
            "一方が他方の末尾の関係(法人名等の有無のみの違い)+区域内一意+短い方が"
            f"{SUFFIX_MIN_SHORT_LEN}文字以上+市区町村整合。いずれも一対一制約を独立に"
            "適用する。あいまい一致は座標を与えずcandidate_onlyとして候補のみ報告する"
            "(詳細はdoc/FACILITY_LINKAGE.md参照)"
        ),
        "fuzzy_match_threshold": FUZZY_MATCH_THRESHOLD,
        "suffix_tier_min_short_length": SUFFIX_MIN_SHORT_LEN,
        "steps": [
            "verify_source()でR7/001723127.xlsxとksj/P04-20/P04-20_GML.zipのSHA-256をSHA256SUMSと照合",
            "P04-20.geojsonをストリーム読み込みし、歯科診療所(P04_001=3)を除外",
            "医療機関名を正規化(NFKC正規化・空白/記号除去・小文字化・法人格語除去)",
            "339構想区域ポリゴンに対しグリッド索引+レイキャスティングで各P04点の所属区域を判定",
            "完全一致ティア: 正規化名の完全一致+区域内一意+市区町村整合を満たす候補のみ仮採用し、一対一制約(同一P04フィーチャの競合)違反があれば全員不採用",
            "接尾一致ティア: 完全一致ティアで採用されなかった施設について、完全一致ティアで採用済みのフィーチャを除いた区域内候補から、正規化名が一方が他方の末尾の関係(短い方が閾値文字数以上)にあるものが1件だけの場合のみ、市区町村整合と一対一制約を満たせば仮採用",
            "いずれのティアでも仮採用に至らなかった施設は、自動採用済みのフィーチャを除いた区域内P04候補との名称類似度を計算し、閾値以上ならcandidate_onlyとして候補のみ報告(座標なし)",
        ],
        "caveat": CAVEAT,
    }

    output_dicts = _rows_to_output_dicts(rows)
    output_tuples = [tuple(d[h] for h in OUTPUT_HEADER) for d in output_dicts]

    csv_path, meta_path = write_csv_with_meta(
        out_dir / "facility_geo_linkage.csv",
        OUTPUT_HEADER,
        output_tuples,
        title="構想区域別医療機関(facility_basic.csv) × 国土数値情報P04-20 の座標突合結果",
        source=source,
        processing=processing,
        fields=FIELDS_LINKAGE,
    )
    print(f"[ok] 出力: {csv_path} ({len(output_tuples)}行)")

    report_md = build_report_markdown(
        rows=rows,
        facilities=facilities,
        p04_points=p04_points,
        by_name=by_name,
        area_index=area_index,
        bed_bands=bed_bands,
        bed_counts=bed_counts,
        p04_category_counts=p04_category_counts,
        fuzzy_scores=fuzzy_scores,
    )
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / "FACILITY_LINKAGE.md"
    with open(doc_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(report_md)
    print(f"[ok] 出力: {doc_path}")

    return {"csv": csv_path, "meta": meta_path, "doc": doc_path}


def main():
    build_and_write(PROCESSED_DIR, DOC_DIR)


if __name__ == "__main__":
    main()
