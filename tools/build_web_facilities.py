# -*- coding: utf-8 -*-
"""可視化サイトが直接読み込む表示用データセット
`data/processed/area_facilities_R7.json` を、既にコミット済みの加工CSV
(`facility_basic.csv`・`facility_observations.csv`・`facility_functions.csv`・
`facility_geo_linkage.csv`)と境界GeoJSON(`area_boundaries_R7.geojson`、
area_codeの一致検証にのみ使用しジオメトリは読まない)から生成する。

M5後半「医療機関UI」の Chunk A(データ層のみ)。フロントエンド(`web/`配下)は
別チャンクで扱うため、本スクリプトは`web/`配下には一切触れない。

処理内容:
  1. 4つのCSV・area_boundaries_R7.geojson(area_codeの一致検証にのみ使用)を
     読み込む
  2. 検証1〜13(下記)を行い、違反があれば SystemExit で中断する(静かに
     握りつぶさない)
  3. 医療機関11,760件をfacility_observations.csvのmetric×bed_functionの組
     (既知の21種、`METRICS`)で横持ちし、`values`/`value_status`の21要素配列
     へ変換する。医療機関機能(facility_functions.csv)・座標
     (facility_geo_linkage.csv)を突き合わせ、339構想区域ごとにまとめる
  4. facility_basic.csv/facility_observations.csv/facility_functions.csv.meta.json
     の `source` を実行時に読み込んで引き継ぎ、`metadata.source` を構築する
     (出典情報のハードコードによる二重管理を避ける)。
     facility_geo_linkage.csv.meta.json は P04名寄せの成果物で `source` の
     形自体が異なる(下記「metadataのsourceが2系統に分かれる理由」参照)ため、
     `metadata.geo_linkage_source` へ別枠で格納する
  5. UTF-8・LF・末尾改行1つで出力する。ただし整形は `json.dump(indent=2)`
     一発ではなく `dump_json()` による決定的な独自整形を用いる(下記
     「出力フォーマット」参照)

検証1〜13:
   1. facility_basic.csv/facility_observations.csv/facility_functions.csvの
      全行がpublished_fy=='R7'(facility_geo_linkage.csvにはpublished_fy列が
      無いため対象外。P04名寄せの成果物であり「公表年度」という概念自体を
      持たない。将来列が追加された場合に備え、存在すれば検証だけはしておく)
   2. facility_basic.csvのrecord_idに重複が無く、ちょうど11,760件
   3. facility_basic.csv/facility_observations.csv/facility_geo_linkage.csvの
      record_id集合が完全一致する
   4. facility_basic.csvのarea_code集合とarea_boundaries_R7.geojsonの
      area_code集合が完全一致し339件
   5. facility_observations.csvがrecord_id×21指標をちょうど1件ずつ持つ
      (=246,960行。過不足・重複を検出する)
   6. metric/bed_functionの組が既知の21種(`METRICS`)のみ
   7. value_statusが既知の5種(observed/source_dash/not_disclosed/
      not_reported/blank)のみ(CLAUDE.md「センチネル値の罠」。本ファイルでは
      'XXX'(not_calculated)は実測データに出現しないため、5種のみを既知とする)
   8. value_status=='observed'の行はvalueが有限の数値として解釈でき、それ
      以外の行はvalueが空文字である(逆方向、observedでない行にvalueが
      入っていないことも確認する)
   9. facility_geo_linkage.csvでlongitude/latitudeが入っている行はちょうど
      10,244件で、経度が122〜154・緯度が20〜46の範囲に収まる(日本の範囲外の
      座標を弾く)。match_status=='matched'と座標の有無が一致することも確認
      する(位置の推測はしない方針、doc/REQUIREMENTS.md §4.3)
  10. facility_functions.csvのrecord_idがfacility_basic.csvの部分集合
  11. area_name/pref_name/pref_codeがfacility_basic.csv内でarea_codeごとに
      一貫し、area_codeの上2桁がpref_codeと一致する
  12. 出力の全施設についてvalues/value_statusの長さがちょうど21
  13. 出力(areas[].facilities)の総数がfacility_basic.csvの行数(11,760)と
      一致し、record_idが区域をまたいで重複せず、facility_basic.csvの
      record_id集合と完全一致する(「区域へ重複なく割り当てられた」ことの
      最終防衛線。検証3・5・12が個々のCSVの整合を保証していても、build_areas()
      でのグルーピング自体にバグがあれば検出できないため、出力後の構造に
      対して独立に確認する)

metadataのsourceが2系統に分かれる理由:
  facility_basic.csv・facility_observations.csv・facility_functions.csvは
  いずれもR7/001723127.xlsx由来で、meta.jsonのsourceは同じ形
  (name/source_file/source_sha256/…)を持つため3つを照合したうえで
  `metadata.source`へ採用する。一方 facility_geo_linkage.csv はP04名寄せの
  成果物で、meta.jsonのsourceは全く別の形(name/inputs/license/page_urlの
  みで、source_file/source_sha256を持たない)。同じキー集合として扱うと
  KeyErrorで落ちるため、`metadata.geo_linkage_source`へ独立に格納する。

出力フォーマット(2026-08-05に「compactな一行JSON」から変更):
  最初は`indent`なしのcompact JSON(6.6MB)を検討したが、一行JSONはgit diffが
  全く読めず、再生成時にどの区域が変わったのか追えない。そこで
  `dump_json()`により、トップレベルの`metadata`/`metrics`/
  `value_status_labels`は`indent=2`で可読に、`areas`は要素(構想区域)ごとに
  1行のcompact JSONとして書き出す(1区域1行の決定的フォーマット)。
  サイズはcompact版とほぼ変わらず(区域数339行ぶんの改行が増えるのみ)、
  区域単位の差分がgit diffで追える形になる。

出力の`values`/`value_status`は`metrics`と同じ順序の21要素配列。
指標名をキーにしたオブジェクトにすると正本が15MB超に増えるため配列にして
いる(対応関係は`metrics`と`fields`に明記する)。

浮動小数点は`float()`した値をそのまま出す(丸めない)。整数として表現できる
値は`int`で出す(例: 病床数582は`582`であって`582.0`ではない)。座標も
丸めない(facility_geo_linkage.csvの文字列を`float()`しただけの値)。

生成日時は埋め込まない(CLAUDE.md参照。再現性テストが翌日に壊れるため)。

必要環境: Python 3.11+

使い方:
    PYTHONIOENCODING=utf-8 python tools/build_web_facilities.py
"""
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lib.provenance import REPO_ROOT, sha256

FACILITY_BASIC_CSV = REPO_ROOT / "data" / "processed" / "facility_basic.csv"
FACILITY_OBSERVATIONS_CSV = REPO_ROOT / "data" / "processed" / "facility_observations.csv"
FACILITY_FUNCTIONS_CSV = REPO_ROOT / "data" / "processed" / "facility_functions.csv"
FACILITY_GEO_LINKAGE_CSV = REPO_ROOT / "data" / "processed" / "facility_geo_linkage.csv"
FACILITY_GEO_AUDIT_CSV = REPO_ROOT / "data" / "processed" / "facility_geo_audit.csv"
AREA_BOUNDARIES_GEOJSON = REPO_ROOT / "data" / "processed" / "area_boundaries_R7.geojson"
OUT_PATH = REPO_ROOT / "data" / "processed" / "area_facilities_R7.json"

FACILITY_BASIC_META_PATH = Path(str(FACILITY_BASIC_CSV) + ".meta.json")
FACILITY_OBSERVATIONS_META_PATH = Path(str(FACILITY_OBSERVATIONS_CSV) + ".meta.json")
FACILITY_FUNCTIONS_META_PATH = Path(str(FACILITY_FUNCTIONS_CSV) + ".meta.json")
FACILITY_GEO_LINKAGE_META_PATH = Path(str(FACILITY_GEO_LINKAGE_CSV) + ".meta.json")
FACILITY_GEO_AUDIT_META_PATH = Path(str(FACILITY_GEO_AUDIT_CSV) + ".meta.json")

NUM_FACILITIES = 11760
NUM_AREAS = 339
# facility_geo_linkage.csv(P04名寄せの成果物)が座標を与えている件数。
EXPECTED_GEOCODED_COUNT = 10244
# うち、医療情報ネットの公表座標との検算(facility_geo_audit.csv)で
# 1km以上離れていた件数。**この施設の座標は画面に出さない**(下記
# AUDIT_STATUS_CONFLICT の扱い、doc/FACILITY_GEO_AUDIT.md参照)。
EXPECTED_COORDINATE_WITHDRAWN_COUNT = 76
# P04名寄せで座標が付かなかった施設(1,516件)のうち、医療情報ネットの公表座標
# (facility_geo_audit.csv)で一意に同定できた(reference_status=='unique')ため
# 座標源として採用した件数(M13で座標源が2系統になった)。
EXPECTED_REFERENCE_ADOPTED_COUNT = 758
# 上記のうち、reference_status=='unique_municipality_unverified'
# (原典の病床機能報告が未報告で所在地欄が空のため市区町村を検証できない)
# として採用しなかった件数。
EXPECTED_REFERENCE_UNVERIFIED_COUNT = 72
# 採用した758件のうち、参照座標が落ちる構想区域(reference_area_code)が原典の
# area_codeと異なる件数(非空)。棄却理由ではなく観測事実として件数を固定する
# (名称・市区町村までは一致を確認済みで、区域判定の食い違いは境界ポリゴン側の
# 誤差の問題であり、施設同一性を否定する材料ではないため採用の可否には影響しない)。
EXPECTED_REFERENCE_AREA_CODE_MISMATCH_COUNT = 9
# 採用した758件のうち、参照座標がどの構想区域ポリゴンにも属さない(空)件数。
# 上記と同じく観測事実であり、採用の可否には影響しない。
EXPECTED_REFERENCE_AREA_CODE_MISSING_COUNT = 3
# 実際に地図へ出す座標の件数。P04名寄せ由来(取り下げ76件を除く)+
# 医療情報ネット由来(採用758件)の合計。
EXPECTED_DISPLAYED_COORDINATE_COUNT = (
    EXPECTED_GEOCODED_COUNT - EXPECTED_COORDINATE_WITHDRAWN_COUNT + EXPECTED_REFERENCE_ADOPTED_COUNT
)

# facility_geo_audit.csvのaudit_status。付与済み座標と参照座標が離れすぎて
# いる(=2つの公表物が別の位置を示している)ことを表す値。
AUDIT_STATUS_CONFLICT = "conflict"

# facility_geo_audit.csvのreference_status。医療情報ネット側の座標を座標源
# として採用してよいかどうかの判定に使う2値のみ定数化する(他の値
# (none/municipality_mismatch/ambiguous)は「採用しない」で一括りに扱うため
# 定数化しない)。
REFERENCE_STATUS_UNIQUE = "unique"
REFERENCE_STATUS_UNIQUE_MUNICIPALITY_UNVERIFIED = "unique_municipality_unverified"

# facilities[].coordinate_sourceの2値。座標源がどちらの公表物由来かを表す
# (M13。P04名寄せが優先、医療情報ネットは補完)。
COORDINATE_SOURCE_KSJ_P04 = "ksj_p04"
COORDINATE_SOURCE_IRYOJOHO = "iryojoho"

# 日本の陸域を大きく包含する範囲(検証9)。与那国島(東経約122.9度)から
# 南鳥島(東経約153.98度)、沖ノ鳥島(北緯約20.4度)から択捉島(北緯約45.5度)
# までを余裕を持って覆う。日本の範囲外の座標(名寄せの誤りやP04側の異常値)
# を弾くための粗いガード。
JAPAN_LON_RANGE = (122, 154)
JAPAN_LAT_RANGE = (20, 46)

VALUE_STATUS_OBSERVED = "observed"
VALUE_STATUS_SOURCE_DASH = "source_dash"
VALUE_STATUS_NOT_DISCLOSED = "not_disclosed"
VALUE_STATUS_NOT_REPORTED = "not_reported"
VALUE_STATUS_BLANK = "blank"

# facility_observations.csvのvalue_statusの既知の5種(検証7)。'XXX'
# (not_calculated)は他帳票(001723349)の前例に備えてパーサ側に分岐があるが、
# 本ファイルの実測データでは一度も出現しないため既知の種類に含めない
# (CLAUDE.md「センチネル値の罠」、tools/parse_facility_beds.py参照)。
VALUE_STATUS_LABELS = {
    VALUE_STATUS_OBSERVED: "実測値",
    # 'source_dash'はtools/parse_facility_beds.pyもfacility_observations.csv.meta.json
    # のfields.value_statusも「原典が'-'」としか説明しておらず、'-'の意味(非該当なのか
    # 未算出なのか等)を原典側で明記した注記は見つからなかった。CLAUDE.md「データ真正性の
    # ルール」に従い、原典が言っていない解釈(「非該当・未算出」等)を足さず、事実のみを述べる。
    VALUE_STATUS_SOURCE_DASH: "原典が「-」",
    VALUE_STATUS_NOT_DISCLOSED: "非公表（NDBの利用に関するガイドラインにより一部非公表）",
    VALUE_STATUS_NOT_REPORTED: "未報告（病床機能報告を未報告の医療機関）",
    VALUE_STATUS_BLANK: "空欄（原典セルが空欄）",
}

# facility_observations.csvのmetric×bed_functionの組(既知の21種、検証6)を
# 表示順に定義する。keyは英字の安定キー(スネークケース)で、原典の語から
# 機械的に導いた一意な識別子。areas[].facilities[].values/value_statusは
# この順序の21要素配列になる(対応関係はfields参照)。
METRICS = [
    {"key": "beds_total", "metric": "病床数", "bed_function": "休棟中等含む計", "label": "病床数（休棟中等含む計）"},
    {"key": "beds_high_acute", "metric": "病床数", "bed_function": "高度急性期", "label": "病床数（高度急性期）"},
    {"key": "beds_acute", "metric": "病床数", "bed_function": "急性期", "label": "病床数（急性期）"},
    {"key": "beds_recovery", "metric": "病床数", "bed_function": "回復期", "label": "病床数（回復期）"},
    {"key": "beds_chronic", "metric": "病床数", "bed_function": "慢性期", "label": "病床数（慢性期）"},
    {"key": "beds_suspended", "metric": "病床数", "bed_function": "休棟中等", "label": "病床数（休棟中等）"},
    {"key": "doctors_fulltime", "metric": "医師数（常勤）", "bed_function": "", "label": "医師数（常勤）"},
    {"key": "doctors_parttime", "metric": "医師数（非常勤）", "bed_function": "", "label": "医師数（非常勤）"},
    {"key": "doctors_per_100beds", "metric": "医師数（100床当たり）", "bed_function": "", "label": "医師数（100床当たり）"},
    {"key": "ambulance", "metric": "救急車の受入件数", "bed_function": "", "label": "救急車の受入件数"},
    {"key": "general_anesthesia", "metric": "全身麻酔手術件数", "bed_function": "", "label": "全身麻酔手術件数"},
    {"key": "deliveries", "metric": "分娩件数", "bed_function": "", "label": "分娩件数"},
    {"key": "surgeries_total", "metric": "手術総数", "bed_function": "", "label": "手術総数"},
    {"key": "alos_high_acute", "metric": "平均在棟日数", "bed_function": "高度急性期", "label": "平均在棟日数（高度急性期）"},
    {"key": "alos_acute", "metric": "平均在棟日数", "bed_function": "急性期", "label": "平均在棟日数（急性期）"},
    {"key": "alos_recovery", "metric": "平均在棟日数", "bed_function": "回復期", "label": "平均在棟日数（回復期）"},
    {"key": "alos_chronic", "metric": "平均在棟日数", "bed_function": "慢性期", "label": "平均在棟日数（慢性期）"},
    {"key": "new_admissions_high_acute", "metric": "新規入棟患者", "bed_function": "高度急性期", "label": "新規入棟患者（高度急性期）"},
    {"key": "new_admissions_acute", "metric": "新規入棟患者", "bed_function": "急性期", "label": "新規入棟患者（急性期）"},
    {"key": "new_admissions_recovery", "metric": "新規入棟患者", "bed_function": "回復期", "label": "新規入棟患者（回復期）"},
    {"key": "new_admissions_chronic", "metric": "新規入棟患者", "bed_function": "慢性期", "label": "新規入棟患者（慢性期）"},
]
assert len(METRICS) == 21, "METRICSは21件でなければなりません"
assert len({m["key"] for m in METRICS}) == len(METRICS), "METRICSのkeyに重複があります"

# (metric, bed_function) -> key の逆引き(facility_observations.csvの行から
# METRICSのインデックスを引くために使う)。
METRIC_KEY_BY_PAIR = {(m["metric"], m["bed_function"]): m["key"] for m in METRICS}
assert len(METRIC_KEY_BY_PAIR) == len(METRICS), "METRICSの(metric,bed_function)の組に重複があります"
METRIC_KEYS_IN_ORDER = [m["key"] for m in METRICS]

# メタデータへ引き継ぐfacility_basic.csv.meta.json / facility_observations.csv.meta.json /
# facility_functions.csv.meta.jsonのsourceブロックのキー。3ファイルとも同一の
# R7/001723127.xlsxから派生しているため値は一致するはず(build_metadata()で照合する)。
SOURCE_KEYS = (
    "name",
    "publisher",
    "url",
    "page_url",
    "fiscal_year",
    "source_file",
    "source_sha256",
    "source_sheet",
    "acquired_date",
    "license",
    "original_title",
    "original_notes",
)

FIELD_DESCRIPTIONS = {
    "metrics": (
        "facility_observations.csvから抽出した21指標の定義(表示順)。各要素は"
        "{key, metric, bed_function, label}。keyは英字の安定キーで、"
        "areas[].facilities[].values/value_statusの対応するインデックスを指す"
    ),
    "metrics[].key": "英字の安定キー(スネークケース)。原典の語から機械的に導いた一意な識別子",
    "metrics[].metric": "facility_observations.csvのmetric列の原文(例 '病床数'・'医師数（常勤）')",
    "metrics[].bed_function": "facility_observations.csvのbed_function列の原文。無い指標(医師数・診療実績)では空文字",
    "metrics[].label": "画面表示用の日本語ラベル(metricとbed_functionを組み合わせたもの)",
    "value_status_labels": (
        "value_statusの取り得る値(observed/source_dash/not_disclosed/not_reported/blank)ごとの"
        "日本語ラベル。facility_observations.csvのvalue_status(CLAUDE.md「センチネル値の罠」参照)"
        "をそのまま引き継ぐ"
    ),
    "areas": "339構想区域の配列(area_codeの昇順)",
    "area_code": "構想区域(二次医療圏)コード(ゼロ埋め4桁の文字列)",
    "area_name": "構想区域名",
    "pref_code": "都道府県コード(ゼロ埋め2桁の文字列)",
    "pref_name": "都道府県名",
    "facility_count": "この区域に属する医療機関数(facility_basic.csvの行数)",
    "geocoded_count": (
        "この区域内で実際にcoordinatesを持つ(=地図に点として出る)医療機関数。"
        "座標源は2系統(P04名寄せ由来+医療情報ネット由来)あり、両方の合計。"
        "match_status=='matched'であっても、検算で座標を取り下げた施設"
        "(coordinate_withdrawnがtrue)はここに数えない"
    ),
    "reference_geocoded_count": (
        "geocoded_countのうち、医療情報ネットの公表座標を採用した(coordinate_source=="
        "'iryojoho')医療機関数。P04名寄せで座標が得られなかった施設のみが対象"
    ),
    "coordinate_withdrawn_count": (
        "この区域内で、P04名寄せでは座標が付いたが検算(facility_geo_audit.csv)で"
        "取り下げた医療機関数。facility_count = 地図に出る数(geocoded_count) + "
        "座標が無い数 + この数、という関係になる"
    ),
    "facilities": "この区域内の医療機関の配列。原典の並び順(facility_basic.csvのsource_row昇順=病床数降順)を保つ",
    "facilities[].record_id": (
        "facility_basic.csvのrecord_idと同一。恒久的な施設IDではない点に留意"
        "(原典の行位置由来。facility_basic.csv.meta.jsonのfields.record_id参照)"
    ),
    "facilities[].facility_name": "医療機関名(facility_basic.csvより)",
    "facilities[].municipality": (
        "所在地(市区町村、facility_basic.csvより)。未報告の医療機関"
        "(value_status='not_reported'の施設)は原典側で所在地欄も空欄のため空文字になる"
    ),
    "facilities[].values": (
        "21要素の配列(トップレベルmetricsと同じ順序・インデックス対応)。"
        "value_status=='observed'の要素のみ数値(整数として表現できる値はint、"
        "それ以外はfloat、丸めない)。それ以外はnull(欠測ではない。理由はvalue_status参照)"
    ),
    "facilities[].value_status": "21要素の配列(values・トップレベルmetricsと同じ順序・インデックス対応)。各要素の意味はvalue_status_labels参照",
    "facilities[].functions": (
        "該当する医療機関機能の日本語名の配列(facility_functions.csvより、原典の列順)。"
        "該当が無い施設ではこのキー自体を省略する(0件を意味する空配列にはしない。"
        "facility_functions.csv.meta.jsonのcaveat参照: 空欄が「非該当」か「未回答」かを"
        "機械的に判別できないため)"
    ),
    "facilities[].match_status": (
        "facility_geo_linkage.csvのmatch_status(全施設に必ず存在)。'matched'=P04名寄せが"
        "一意に決まった/'candidate_only'=あいまい一致の候補のみ/'unmatched'=候補なしまたは"
        "信頼できる候補が絞れない。詳細はdoc/FACILITY_LINKAGE.md参照。**座標の有無は"
        "match_statusからは導けない**('matched'でも検算(facility_geo_audit.csv)で"
        "取り下げていれば座標なし。'matched'でなくても医療情報ネットの公表座標を採用"
        "していれば座標あり。座標の有無はcoordinatesキーの有無で判定すること"
        "(coordinate_sourceは座標を持つ施設について出所を知りたいときに見るもの、"
        "という位置づけ)"
    ),
    "facilities[].coordinates": (
        "[経度, 緯度](度、JGD2011)。位置の推測はしない方針により、座標が特定できた"
        "施設にのみ存在する(doc/REQUIREMENTS.md §4.3参照)。本フィールドを持つ施設は"
        "必ずcoordinate_sourceも持つ(座標源の内訳はcoordinate_source参照)。座標は丸めない"
    ),
    "facilities[].coordinate_source": (
        "座標の出所。'ksj_p04'=国土数値情報P04-20とのP04名寄せ由来(facility_geo_linkage.csv、"
        "match_status=='matched'かつ検算で取り下げていない施設)/'iryojoho'=医療情報ネットの"
        "公表座標を採用(facility_geo_audit.csv、P04名寄せで座標が得られず医療情報ネット側で"
        "reference_status=='unique'と一意に同定できた758件のみ、M13)。coordinatesを持つ"
        "施設にのみ存在し、持たない施設ではキー自体を省略する"
    ),
    "facilities[].coordinate_withdrawn": (
        "trueの場合、P04名寄せでは座標が付いた(match_status=='matched')が、"
        "医療情報ネットの公表座標との検算で1km以上離れていた(facility_geo_audit.csvの"
        "audit_status=='conflict')ため、**この可視化サイトでは座標を出さない**ことを表す。"
        "該当しない施設ではこのキー自体を省略する。値を補正した(参照側の座標を採用した)のでは"
        "ない点に注意(doc/FACILITY_GEO_AUDIT.md・doc/DECISION_FACILITY_COORDINATES.md参照)"
    ),
}


def _load_csv_rows(path: Path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_geojson_area_codes(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)
    return {feat["properties"]["area_code"] for feat in gj["features"]}


def _select(d: dict, keys) -> dict:
    return {k: d[k] for k in keys}


def _to_number(raw: str):
    """CSV文字列を数値へ変換する。整数として表現できる値はint、それ以外は
    floatで返す(丸めない。例: '582' -> 582 だが '12.5' -> 12.5)。"""
    value = float(raw)
    if value.is_integer():
        return int(value)
    return value


def validate_and_index(basic_rows, observation_rows, function_rows, geo_rows, audit_rows, geo_codes):
    """検証1〜11を行い、違反があれば SystemExit で中断する。

    戻り値: (basic_id_set, obs_index, geo_index, functions_index, withdrawn, reference_adopted)
      basic_id_set: facility_basic.csvのrecord_idの集合
      obs_index: {record_id: {metric_key: (value, value_status)}} (21件ずつ)
      geo_index: {record_id: (match_status, [lon, lat] または None)}
      functions_index: {record_id: [function_name, ...]} (該当が無い施設はキー自体が無い)
      withdrawn: 検算(facility_geo_audit.csv)で座標を取り下げたrecord_idの集合
      reference_adopted: {record_id: [lon, lat]} P04名寄せで座標が無い施設のうち、
        医療情報ネットの公表座標(facility_geo_audit.csv)を座標源として採用した
        ものだけを持つ(M13)
    """
    # 検証1: published_fyが全てR7(facility_basic.csv/facility_observations.csv/
    # facility_functions.csv)。facility_geo_linkage.csvにはpublished_fy列が無い
    # ため対象外(P04名寄せの成果物であり「公表年度」の概念自体を持たない)。
    for name, rows in (
        ("facility_basic.csv", basic_rows),
        ("facility_observations.csv", observation_rows),
        ("facility_functions.csv", function_rows),
    ):
        bad_fy = sorted({r["published_fy"] for r in rows} - {"R7"})
        if bad_fy:
            raise SystemExit(f"検証1失敗: {name}にR7以外のpublished_fyがあります: {bad_fy}")
    # 将来facility_geo_linkage.csvにpublished_fy列が追加された場合に備え、
    # 存在すれば検証だけはしておく(現状は列が無いため素通りする)。
    if geo_rows and "published_fy" in geo_rows[0]:
        bad_geo_fy = sorted({r["published_fy"] for r in geo_rows} - {"R7"})
        if bad_geo_fy:
            raise SystemExit(f"検証1失敗: facility_geo_linkage.csvにR7以外のpublished_fyがあります: {bad_geo_fy}")

    # 検証2: facility_basic.csvのrecord_idに重複が無く、ちょうど11,760件
    basic_ids = [r["record_id"] for r in basic_rows]
    if len(basic_ids) != NUM_FACILITIES:
        raise SystemExit(
            f"検証2失敗: facility_basic.csvが{NUM_FACILITIES}行ちょうどではありません(実際{len(basic_ids)}行)"
        )
    dup_ids = sorted(k for k, n in Counter(basic_ids).items() if n > 1)
    if dup_ids:
        raise SystemExit(f"検証2失敗: facility_basic.csvのrecord_idに重複があります: {dup_ids[:10]}")
    basic_id_set = set(basic_ids)

    # 検証3: facility_basic.csv/facility_observations.csv/facility_geo_linkage.csvの
    # record_id集合が完全一致する
    obs_ids = {r["record_id"] for r in observation_rows}
    geo_ids = {r["record_id"] for r in geo_rows}
    sets = {
        "facility_basic.csv": basic_id_set,
        "facility_observations.csv": obs_ids,
        "facility_geo_linkage.csv": geo_ids,
    }
    if not (basic_id_set == obs_ids == geo_ids):
        all_ids = set().union(*sets.values())
        missing = {name: sorted(all_ids - ids)[:5] for name, ids in sets.items()}
        raise SystemExit(
            "検証3失敗: record_id集合がfacility_basic.csv/facility_observations.csv/"
            f"facility_geo_linkage.csvで一致しません。件数: basic={len(basic_id_set)} "
            f"observations={len(obs_ids)} geo_linkage={len(geo_ids)}。"
            f"各ファイルに無いIDの例: {missing}"
        )

    # 検証4: facility_basic.csvのarea_code集合とarea_boundaries_R7.geojsonの
    # area_code集合が完全一致し339件
    basic_area_codes = {r["area_code"] for r in basic_rows}
    if basic_area_codes != geo_codes or len(basic_area_codes) != NUM_AREAS:
        raise SystemExit(
            "検証4失敗: facility_basic.csvのarea_code集合"
            f"({len(basic_area_codes)}件)とarea_boundaries_R7.geojsonのarea_code集合"
            f"({len(geo_codes)}件)が一致しないか{NUM_AREAS}件ちょうどではありません。"
            f"geojsonに無いコード={sorted(basic_area_codes - geo_codes)[:10]} "
            f"facility_basicに無いコード={sorted(geo_codes - basic_area_codes)[:10]}"
        )

    # 検証11: area_name/pref_name/pref_codeがfacility_basic.csv内でarea_code
    # ごとに一貫し、area_codeの上2桁がpref_codeと一致する
    area_info_by_code = {}
    for r in basic_rows:
        code = r["area_code"]
        if not (len(code) == 4 and code.isdigit()):
            raise SystemExit(f"検証11失敗: area_codeが4桁の数字文字列ではありません: {code!r}")
        if code[:2] != r["pref_code"]:
            raise SystemExit(f"検証11失敗: area_code={code}の上2桁がpref_code={r['pref_code']!r}と一致しません")
        val = (r["area_name"], r["pref_code"], r["pref_name"])
        if code in area_info_by_code and area_info_by_code[code] != val:
            raise SystemExit(
                f"検証11失敗: area_code={code}のarea_name/pref_name/pref_codeが"
                f"行によって揺れています: {area_info_by_code[code]} != {val}"
            )
        area_info_by_code[code] = val

    # 検証5・6・7・8: facility_observations.csvを1パスで処理する
    # (246,960行、csv.DictReaderで読み込み済みのリストを1回だけ走査)。
    expected_row_count = NUM_FACILITIES * len(METRICS)
    if len(observation_rows) != expected_row_count:
        raise SystemExit(
            f"検証5失敗: facility_observations.csvが{NUM_FACILITIES}×{len(METRICS)}="
            f"{expected_row_count}行ちょうどではありません(実際{len(observation_rows)}行)"
        )

    obs_index = {rid: {} for rid in basic_id_set}
    for r in observation_rows:
        rid = r["record_id"]
        metric = r["metric"]
        bed_function = r["bed_function"]
        status = r["value_status"]
        raw_value = r["value"]

        pair = (metric, bed_function)
        if pair not in METRIC_KEY_BY_PAIR:
            raise SystemExit(f"検証6失敗: 未知のmetric/bed_functionの組です(record_id={rid}): {pair}")
        key = METRIC_KEY_BY_PAIR[pair]

        if status not in VALUE_STATUS_LABELS:
            raise SystemExit(f"検証7失敗: 未知のvalue_statusです(record_id={rid} metric={metric}): {status!r}")

        record_map = obs_index[rid]
        if key in record_map:
            raise SystemExit(
                f"検証5失敗: record_id={rid}でmetric={metric!r} bed_function={bed_function!r}が重複しています"
            )

        if status == VALUE_STATUS_OBSERVED:
            if raw_value == "":
                raise SystemExit(
                    f"検証8失敗: value_status='observed'なのにvalueが空です(record_id={rid} metric={metric})"
                )
            try:
                value = _to_number(raw_value)
            except (TypeError, ValueError):
                raise SystemExit(
                    f"検証8失敗: valueが数値として解釈できません(record_id={rid} metric={metric}): {raw_value!r}"
                )
            if not math.isfinite(value):
                raise SystemExit(
                    f"検証8失敗: valueが有限の数値ではありません(record_id={rid} metric={metric}): {raw_value!r}"
                )
        else:
            if raw_value != "":
                raise SystemExit(
                    f"検証8失敗: value_status={status!r}なのにvalueが空文字ではありません"
                    f"(record_id={rid} metric={metric}): {raw_value!r}"
                )
            value = None

        record_map[key] = (value, status)

    incomplete = sorted(rid for rid, m in obs_index.items() if len(m) != len(METRICS))
    if incomplete:
        raise SystemExit(
            f"検証5失敗: record_idごとに{len(METRICS)}指標が揃っていません(過不足): {incomplete[:10]}"
        )

    # 検証9: facility_geo_linkage.csvの座標
    geo_index = {}
    coord_count = 0
    for r in geo_rows:
        rid = r["record_id"]
        status = r["match_status"]
        lon_raw, lat_raw = r["longitude"], r["latitude"]
        has_lon = lon_raw != ""
        has_lat = lat_raw != ""
        if has_lon != has_lat:
            raise SystemExit(f"検証9失敗: record_id={rid}のlongitude/latitudeの有無が非対称です")
        has_coord = has_lon
        if has_coord != (status == "matched"):
            raise SystemExit(
                f"検証9失敗: record_id={rid}のmatch_status={status!r}と座標の有無が一致しません"
                f"(座標あり={has_coord})"
            )
        coordinates = None
        if has_coord:
            lon = float(lon_raw)
            lat = float(lat_raw)
            lon_min, lon_max = JAPAN_LON_RANGE
            lat_min, lat_max = JAPAN_LAT_RANGE
            if not (lon_min <= lon <= lon_max):
                raise SystemExit(f"検証9失敗: record_id={rid}の経度が日本の範囲外です: {lon}")
            if not (lat_min <= lat <= lat_max):
                raise SystemExit(f"検証9失敗: record_id={rid}の緯度が日本の範囲外です: {lat}")
            coordinates = [lon, lat]
            coord_count += 1
        geo_index[rid] = (status, coordinates)

    if coord_count != EXPECTED_GEOCODED_COUNT:
        raise SystemExit(
            f"検証9失敗: 座標付き施設が{EXPECTED_GEOCODED_COUNT}件ちょうどではありません(実際{coord_count}件)"
        )

    # 検証14: facility_geo_audit.csv(医療情報ネットの公表座標との検算)
    # 座標を取り下げる対象を確定する。取り下げは「値の補正」ではなく
    # 「検算で否定された座標を画面に出さない」措置(doc/FACILITY_GEO_AUDIT.md)。
    audit_ids = {r["record_id"] for r in audit_rows}
    if audit_ids != set(geo_index):
        raise SystemExit(
            "検証14失敗: facility_geo_audit.csvのrecord_id集合がfacility_geo_linkage.csvと"
            f"一致しません(audit={len(audit_ids)} linkage={len(geo_index)})"
        )
    withdrawn = {r["record_id"] for r in audit_rows if r["audit_status"] == AUDIT_STATUS_CONFLICT}
    if len(withdrawn) != EXPECTED_COORDINATE_WITHDRAWN_COUNT:
        raise SystemExit(
            f"検証14失敗: audit_status=='{AUDIT_STATUS_CONFLICT}'が"
            f"{EXPECTED_COORDINATE_WITHDRAWN_COUNT}件ちょうどではありません(実際{len(withdrawn)}件)。"
            "監査の入力が変わった場合はEXPECTED_COORDINATE_WITHDRAWN_COUNTを更新すること"
        )
    without_coordinate = sorted(rid for rid in withdrawn if geo_index[rid][1] is None)
    if without_coordinate:
        raise SystemExit(
            "検証14失敗: 座標を持たない施設がconflictとして報告されています"
            f"(検算は座標がある施設にのみ成立するはずです): {without_coordinate[:10]}"
        )

    # 検証15: facility_geo_audit.csv(医療情報ネットの公表座標)を、P04名寄せで
    # 座標が付かなかった施設(coordinates is None)への補完として採用する
    # (M13)。P04が優先なので、coordinates is not Noneの行ではreference関連
    # 列を一切見ない。
    reference_adopted = {}
    reference_unverified_count = 0
    reference_area_mismatch_count = 0
    reference_area_missing_count = 0
    lon_min, lon_max = JAPAN_LON_RANGE
    lat_min, lat_max = JAPAN_LAT_RANGE
    for r in audit_rows:
        rid = r["record_id"]
        _, coordinates = geo_index[rid]
        if coordinates is not None:
            continue
        ref_status = r["reference_status"]
        if ref_status == REFERENCE_STATUS_UNIQUE:
            lon_raw = r["reference_longitude"]
            lat_raw = r["reference_latitude"]
            if lon_raw == "" or lat_raw == "":
                raise SystemExit(
                    "検証15失敗: reference_status=='unique'なのにreference_longitude/"
                    f"reference_latitudeが空です(record_id={rid})"
                )
            lon = float(lon_raw)
            lat = float(lat_raw)
            if not (lon_min <= lon <= lon_max):
                raise SystemExit(f"検証15失敗: record_id={rid}の参照経度が日本の範囲外です: {lon}")
            if not (lat_min <= lat <= lat_max):
                raise SystemExit(f"検証15失敗: record_id={rid}の参照緯度が日本の範囲外です: {lat}")
            reference_adopted[rid] = [lon, lat]
            ref_area_code = r["reference_area_code"]
            if ref_area_code == "":
                reference_area_missing_count += 1
            elif ref_area_code != r["area_code"]:
                reference_area_mismatch_count += 1
        elif ref_status == REFERENCE_STATUS_UNIQUE_MUNICIPALITY_UNVERIFIED:
            reference_unverified_count += 1

    if len(reference_adopted) != EXPECTED_REFERENCE_ADOPTED_COUNT:
        raise SystemExit(
            "検証15失敗: 医療情報ネット座標を採用した件数が"
            f"{EXPECTED_REFERENCE_ADOPTED_COUNT}件ちょうどではありません(実際{len(reference_adopted)}件)"
        )
    if reference_unverified_count != EXPECTED_REFERENCE_UNVERIFIED_COUNT:
        raise SystemExit(
            f"検証15失敗: reference_status=='{REFERENCE_STATUS_UNIQUE_MUNICIPALITY_UNVERIFIED}'の件数が"
            f"{EXPECTED_REFERENCE_UNVERIFIED_COUNT}件ちょうどではありません(実際{reference_unverified_count}件)"
        )
    if reference_area_mismatch_count != EXPECTED_REFERENCE_AREA_CODE_MISMATCH_COUNT:
        raise SystemExit(
            "検証15失敗: 採用した座標のうちreference_area_codeがarea_codeと異なる件数が"
            f"{EXPECTED_REFERENCE_AREA_CODE_MISMATCH_COUNT}件ちょうどではありません"
            f"(実際{reference_area_mismatch_count}件)"
        )
    if reference_area_missing_count != EXPECTED_REFERENCE_AREA_CODE_MISSING_COUNT:
        raise SystemExit(
            "検証15失敗: 採用した座標のうちreference_area_codeが空の件数が"
            f"{EXPECTED_REFERENCE_AREA_CODE_MISSING_COUNT}件ちょうどではありません"
            f"(実際{reference_area_missing_count}件)"
        )

    # 検証10: facility_functions.csvのrecord_idがfacility_basic.csvの部分集合
    functions_index = {}
    for r in function_rows:
        rid = r["record_id"]
        if rid not in basic_id_set:
            raise SystemExit(f"検証10失敗: facility_functions.csvにfacility_basic.csvに無いrecord_idがあります: {rid!r}")
        functions_index.setdefault(rid, []).append(r["function_name"])

    return basic_id_set, obs_index, geo_index, functions_index, withdrawn, reference_adopted


def build_areas(basic_rows, obs_index, geo_index, functions_index, withdrawn, reference_adopted):
    """facility_basic.csvの行をarea_codeごとにまとめ、検証12を満たす
    areas配列を組み立てる(area_code昇順、facilitiesはsource_row昇順)。

    `withdrawn`は検算(facility_geo_audit.csv)で座標を取り下げたrecord_idの集合。
    該当施設は`coordinates`を出力せず`coordinate_withdrawn`をtrueにする
    (一覧からは消さない。全21指標はそのまま出す)。

    `reference_adopted`はP04名寄せで座標が無い施設のうち、医療情報ネットの
    公表座標を座標源として採用したrecord_id -> [lon, lat](M13)。座標決定の
    優先順位は (1) 検算で取り下げなら座標なし (2) P04名寄せの座標があれば
    それを使う(coordinate_source='ksj_p04') (3) 医療情報ネット採用なら
    それを使う(coordinate_source='iryojoho') (4) いずれも無ければ座標なし。
    """
    by_area = {}
    for r in basic_rows:
        by_area.setdefault(r["area_code"], []).append(r)

    areas = []
    for area_code in sorted(by_area):
        rows = sorted(by_area[area_code], key=lambda r: int(r["source_row"]))
        first = rows[0]

        facilities = []
        geocoded_count = 0
        reference_geocoded_count = 0
        withdrawn_count = 0
        for r in rows:
            rid = r["record_id"]
            record_map = obs_index[rid]
            values = [record_map[key][0] for key in METRIC_KEYS_IN_ORDER]
            value_status = [record_map[key][1] for key in METRIC_KEYS_IN_ORDER]
            # 検証12: 出力の全施設についてvalues/value_statusの長さがちょうど21
            if len(values) != len(METRICS) or len(value_status) != len(METRICS):
                raise SystemExit(
                    f"検証12失敗: record_id={rid}のvalues/value_statusの長さが{len(METRICS)}ではありません"
                )

            facility = {
                "record_id": rid,
                "facility_name": r["facility_name"],
                "municipality": r["municipality"],
                "values": values,
                "value_status": value_status,
            }
            funcs = functions_index.get(rid)
            if funcs:
                facility["functions"] = funcs

            match_status, coordinates = geo_index[rid]
            facility["match_status"] = match_status
            if rid in withdrawn:
                # 検算で否定された座標は出さない。match_statusは名寄せの結果
                # そのままにする(facility_geo_linkage.csvと食い違わせない)。
                facility["coordinate_withdrawn"] = True
                withdrawn_count += 1
            elif coordinates is not None:
                facility["coordinates"] = coordinates
                facility["coordinate_source"] = COORDINATE_SOURCE_KSJ_P04
                geocoded_count += 1
            elif rid in reference_adopted:
                # P04名寄せで座標が無い施設への補完(M13)。
                facility["coordinates"] = list(reference_adopted[rid])
                facility["coordinate_source"] = COORDINATE_SOURCE_IRYOJOHO
                geocoded_count += 1
                reference_geocoded_count += 1

            facilities.append(facility)

        areas.append(
            {
                "area_code": area_code,
                "area_name": first["area_name"],
                "pref_code": first["pref_code"],
                "pref_name": first["pref_name"],
                "facility_count": len(facilities),
                "geocoded_count": geocoded_count,
                "reference_geocoded_count": reference_geocoded_count,
                "coordinate_withdrawn_count": withdrawn_count,
                "facilities": facilities,
            }
        )
    return areas


def validate_areas_output(areas, basic_id_set) -> None:
    """検証13: areas[].facilitiesの総数がfacility_basic.csvの行数と一致し、
    record_idが区域をまたいで重複せず、facility_basic.csvのrecord_id集合と
    完全一致することを確認する(「区域へ重複なく割り当てられた」ことの
    最終防衛線。検証3・5・12は個々のCSVの整合を保証するが、build_areas()の
    グルーピング自体にバグがあった場合は出力後の構造を見ないと検出できない)。

    検証16: 出力(areas[].facilities)に対して座標関連キーの不変条件を確認する
    (build_metadata()のprocessing.stepsが主張している内容をビルド時に担保する。
    これまでpytest側にしか無かった検査で、build_areas()の分岐が正しく実装
    されていれば通るはずだが、出力後の構造に対する独立の防衛線として置く)。
      - coordinatesを持つ施設は必ずcoordinate_sourceを持ち、値は
        COORDINATE_SOURCE_KSJ_P04・COORDINATE_SOURCE_IRYOJOHOのいずれかである
      - coordinatesを持たない施設はcoordinate_sourceを持たない
      - coordinate_withdrawnがtrueの施設はcoordinatesを持たない
    """
    all_ids = [f["record_id"] for area in areas for f in area["facilities"]]
    if len(all_ids) != NUM_FACILITIES:
        raise SystemExit(
            f"検証13失敗: areas[].facilitiesの総数が{NUM_FACILITIES}件ちょうどではありません(実際{len(all_ids)}件)"
        )
    counts = Counter(all_ids)
    dup = sorted(k for k, n in counts.items() if n > 1)
    if dup:
        raise SystemExit(f"検証13失敗: record_idが区域をまたいで重複しています: {dup[:10]}")
    output_id_set = set(all_ids)
    if output_id_set != basic_id_set:
        raise SystemExit(
            "検証13失敗: areas[].facilitiesのrecord_id集合がfacility_basic.csvと一致しません。"
            f"不足={sorted(basic_id_set - output_id_set)[:10]} 余剰={sorted(output_id_set - basic_id_set)[:10]}"
        )

    known_coordinate_sources = {COORDINATE_SOURCE_KSJ_P04, COORDINATE_SOURCE_IRYOJOHO}
    for area in areas:
        for f in area["facilities"]:
            rid = f["record_id"]
            has_coordinates = "coordinates" in f
            has_source = "coordinate_source" in f
            if has_coordinates and not has_source:
                raise SystemExit(
                    f"検証16失敗: record_id={rid}はcoordinatesを持ちながらcoordinate_sourceを持ちません"
                )
            if has_source and not has_coordinates:
                raise SystemExit(
                    f"検証16失敗: record_id={rid}はcoordinate_sourceを持ちながらcoordinatesを持ちません"
                )
            if has_source and f["coordinate_source"] not in known_coordinate_sources:
                raise SystemExit(
                    f"検証16失敗: record_id={rid}のcoordinate_sourceが未知の値です: {f['coordinate_source']!r}"
                )
            if f.get("coordinate_withdrawn") and has_coordinates:
                raise SystemExit(
                    f"検証16失敗: record_id={rid}はcoordinate_withdrawn=trueなのにcoordinatesを持っています"
                )


def build_metadata(basic_meta, observations_meta, functions_meta, geo_meta, audit_meta, inputs) -> dict:
    basic_source = _select(basic_meta["source"], SOURCE_KEYS)
    observations_source = _select(observations_meta["source"], SOURCE_KEYS)
    functions_source = _select(functions_meta["source"], SOURCE_KEYS)
    if not (basic_source == observations_source == functions_source):
        raise SystemExit(
            "facility_basic.csv.meta.json / facility_observations.csv.meta.json / "
            "facility_functions.csv.meta.json の source が一致しません(3つとも同一の"
            f"R7/001723127.xlsxから派生しているはずです)。basic={basic_source} "
            f"observations={observations_source} functions={functions_source}"
        )

    metadata_source = dict(basic_source)
    metadata_source["derived_via"] = [
        {"csv": "data/processed/facility_basic.csv", "meta": "data/processed/facility_basic.csv.meta.json"},
        {
            "csv": "data/processed/facility_observations.csv",
            "meta": "data/processed/facility_observations.csv.meta.json",
        },
        {
            "csv": "data/processed/facility_functions.csv",
            "meta": "data/processed/facility_functions.csv.meta.json",
        },
    ]

    # facility_geo_linkage.csv.meta.jsonはP04名寄せの成果物で、sourceの形が
    # 本体(001723127.xlsx)とは異なる(name/inputs/license/page_urlのみで、
    # source_file/source_sha256を持たない)。同じ形として扱うとKeyErrorに
    # なるため、本体sourceとは別キー(geo_linkage_source)として並べる。
    geo_linkage_source = dict(geo_meta["source"])
    # metadata.source.derived_viaと形を揃えるため(1要素でも)配列にする。
    # 既存の表示用JSON(area_indicators_R7.json・area_demand_R7.json)でも
    # derived_viaは配列であり、CLAUDE.md「可視化実装で判明した罠」11番
    # (表示用JSONごとにmetadataの形が揃わずReact側が落ちる)を自ら踏まないため。
    geo_linkage_source["derived_via"] = [
        {
            "csv": "data/processed/facility_geo_linkage.csv",
            "meta": "data/processed/facility_geo_linkage.csv.meta.json",
        },
    ]

    # facility_geo_audit.csv.meta.jsonもP04本体とは異なる形(name/inputs/
    # page_url/reference_snapshot_dateのみで、source_file/source_sha256を
    # 持たない)。M13で医療情報ネットの公表座標を座標源として採用したため、
    # geo_linkage_sourceと同じ流儀で独立キー(geo_audit_source)に格納する。
    geo_audit_source = dict(audit_meta["source"])
    geo_audit_source["derived_via"] = [
        {
            "csv": "data/processed/facility_geo_audit.csv",
            "meta": "data/processed/facility_geo_audit.csv.meta.json",
        },
    ]

    # 入力CSVごとにcaveatの内容が異なるため、入力CSV名をキーにした辞書で
    # 全部保持する(1つ選ぶと他の注記が失われる。build_web_demand.pyと同じ判断)。
    # 'coordinate_adoption'のみ入力CSV名ではなく、本スクリプトが下す座標源
    # 採用方針そのものの説明(厚労省公表物の欠陥ではないためknown_issuesには
    # 入れない。CLAUDE.md「欠陥でない事実をknown_issuesに入れないこと」M12)。
    caveat = {
        "facility_basic": basic_meta["processing"]["caveat"],
        "facility_observations": observations_meta["processing"]["caveat"],
        "facility_functions": functions_meta["processing"]["caveat"],
        "facility_geo_linkage": geo_meta["processing"]["caveat"],
        "facility_geo_audit": audit_meta["processing"]["caveat"],
        "coordinate_adoption": (
            "座標源は2系統(P04名寄せを優先、医療情報ネットは補完)。P04名寄せで座標が"
            "付かなかった1,516件のうち、医療情報ネット側で一意に同定できた758件"
            "(facility_geo_audit.csvのreference_status=='unique')は参照座標を採用した"
            "(coordinate_source='iryojoho')。残り72件はreference_status=='unique_"
            "municipality_unverified'(原典の病床機能報告が未報告で所在地欄が空のため"
            "市区町村を検証できない)として採用しなかった。それ以外の686件"
            "(none/municipality_mismatch/ambiguous)も座標を与えない。採用した758件のうち"
            "12件は参照座標が落ちる構想区域(reference_area_code)が原典のarea_codeと異なる"
            "(9件)か、どの区域にも属さない(3件)が、名称・市区町村までは一致を確認済みで"
            "あり、区域判定の食い違いは境界ポリゴン側の誤差の問題であって施設同一性を"
            "否定する材料ではないため、この12件も座標を出す対象に含めている。"
        ),
    }

    # 原典側の既知の欠陥は入力CSVのmeta.jsonから拾って集約する(この場で
    # 新規に定義しない)。現状はfacility_basic.csvの
    # facility_basic_summary_hospital_count_mismatch と、facility_geo_audit.csvの
    # facility_coordinate_conflicts_with_published_reference の2件。
    known_issues = (
        list(basic_meta.get("known_issues", []))
        + list(observations_meta.get("known_issues", []))
        + list(functions_meta.get("known_issues", []))
        + list(geo_meta.get("known_issues", []))
        + list(audit_meta.get("known_issues", []))
    )

    return {
        "title": "構想区域別 医療機関一覧（病床数・医師数・診療実績・機能・座標、可視化サイト表示用）",
        "source": metadata_source,
        "geo_linkage_source": geo_linkage_source,
        "geo_audit_source": geo_audit_source,
        "processing": {
            "script": "tools/build_web_facilities.py",
            "inputs": inputs,
            "steps": [
                "facility_basic.csv・facility_observations.csv・facility_functions.csv・"
                "facility_geo_linkage.csv・area_boundaries_R7.geojson"
                "(area_code集合の一致検証にのみ使用)を読み込み",
                "facility_basic.csv/facility_observations.csv/facility_functions.csvの"
                "全行がpublished_fy=='R7'であることを確認(facility_geo_linkage.csvには"
                "published_fy列が無いため対象外、検証1)",
                "facility_basic.csvのrecord_idに重複が無く、ちょうど11,760件であることを確認(検証2)",
                "facility_basic.csv/facility_observations.csv/facility_geo_linkage.csvの"
                "record_id集合が完全一致することを確認(検証3)",
                "facility_basic.csvのarea_code集合とarea_boundaries_R7.geojsonの"
                "area_code集合が完全一致し339件であることを確認(検証4)",
                "area_name/pref_name/pref_codeがfacility_basic.csv内でarea_codeごとに"
                "一貫し、area_codeの上2桁がpref_codeと一致することを確認(検証11)",
                "facility_observations.csvがrecord_id×21指標をちょうど1件ずつ持つ"
                "(246,960行)ことを確認(検証5)",
                "metric/bed_functionの組が既知の21種のみであることを確認(検証6)",
                "value_statusが既知の5種(observed/source_dash/not_disclosed/"
                "not_reported/blank)のみであることを確認(検証7)",
                "value_status=='observed'の行はvalueが有限の数値、それ以外の行は"
                "valueが空文字であることを確認(検証8。逆方向も確認)",
                "facility_geo_linkage.csvでlongitude/latitudeが入っている行がちょうど"
                "10,244件で、経度122〜154・緯度20〜46の範囲に収まり、"
                "match_status=='matched'と座標の有無が一致することを確認(検証9)",
                "facility_functions.csvのrecord_idがfacility_basic.csvの部分集合であることを確認(検証10)",
                "metric×bed_functionの21指標をvalues/value_status配列へ変換し、"
                "医療機関機能・座標を突き合わせてarea_code昇順・facilitiesは"
                "source_row昇順(=病床数降順)でareasを構築",
                "出力の全施設についてvalues/value_statusの長さがちょうど21であることを確認(検証12)",
                "areas[].facilitiesの総数が11,760件ちょうどで、record_idが区域をまたいで"
                "重複せず、facility_basic.csvのrecord_id集合と完全一致することを確認(検証13)",
                "facility_geo_audit.csv(医療情報ネットの公表座標との検算)のrecord_id集合が"
                "facility_geo_linkage.csvと一致し、audit_status=='conflict'が76件ちょうどで、"
                "その全件が座標を持つ施設であることを確認(検証14)",
                "audit_status=='conflict'の76件はcoordinatesを出力せずcoordinate_withdrawn=trueに"
                "する(一覧・21指標はそのまま出す)",
                "P04名寄せで座標が付かなかった施設について、facility_geo_audit.csvの"
                "reference_status=='unique'の758件は医療情報ネットの公表座標を座標源として"
                "採用し(coordinate_source='iryojoho')、'unique_municipality_unverified'の"
                "72件・その他686件は採用しないことを確認(検証15)",
                "coordinatesを出力する施設は必ずcoordinate_sourceを持ち('ksj_p04'または"
                "'iryojoho')、coordinate_sourceを持つ施設は必ずcoordinatesを持ち、"
                "coordinate_withdrawn=trueの施設はcoordinatesを持たないことを確認"
                "(検証16)。地図に出る座標は10,244-76+758=10,926件になる"
                "(P04由来10,168件+医療情報ネット由来758件)",
            ],
            "caveat": caveat,
        },
        "fields": FIELD_DESCRIPTIONS,
        "known_issues": known_issues,
    }


def dump_json(payload: dict) -> str:
    """`metadata`/`metrics`/`value_status_labels`は`indent=2`で可読に、
    `areas`は要素(構想区域)ごとに1行のcompact JSONとして直列化する。

    一行の巨大JSON(compact)はgit diffが読めず、再生成時にどの区域が
    変わったのか追えないための決定的フォーマット(詳細はモジュールdocstring
    「出力フォーマット」参照)。`areas`が空になることは無い(339件固定)が、
    空リストでも壊れないようにしている。
    """
    parts = ["{"]
    for key in ("metadata", "metrics", "value_status_labels"):
        parts.append(
            json.dumps(key, ensure_ascii=False) + ": " + json.dumps(payload[key], ensure_ascii=False, indent=2) + ","
        )
    parts.append('"areas": [')
    areas = payload["areas"]
    for i, area in enumerate(areas):
        line = json.dumps(area, ensure_ascii=False, separators=(",", ":"))
        parts.append(line + ("," if i < len(areas) - 1 else ""))
    parts.append("]")
    parts.append("}")
    return "\n".join(parts) + "\n"


def build_and_write(out_path: Path) -> Path:
    """入力4CSV(+境界GeoJSON)を読み込み・検証・変換し、`out_path`へ表示用
    データセットのJSONを書き出す(再現性テストでの再利用のため、出力先を
    引数化している)。

    戻り値: 書き出したファイルのPath。
    """
    basic_rows = _load_csv_rows(FACILITY_BASIC_CSV)
    observation_rows = _load_csv_rows(FACILITY_OBSERVATIONS_CSV)
    function_rows = _load_csv_rows(FACILITY_FUNCTIONS_CSV)
    geo_rows = _load_csv_rows(FACILITY_GEO_LINKAGE_CSV)
    audit_rows = _load_csv_rows(FACILITY_GEO_AUDIT_CSV)
    geo_codes = _load_geojson_area_codes(AREA_BOUNDARIES_GEOJSON)
    print(
        f"[ok] 入力読み込み: facility_basic.csv={len(basic_rows)}行 "
        f"facility_observations.csv={len(observation_rows)}行 "
        f"facility_functions.csv={len(function_rows)}行 "
        f"facility_geo_linkage.csv={len(geo_rows)}行 "
        f"facility_geo_audit.csv={len(audit_rows)}行 "
        f"area_boundaries_R7.geojson={len(geo_codes)}区域"
    )

    basic_id_set, obs_index, geo_index, functions_index, withdrawn, reference_adopted = validate_and_index(
        basic_rows, observation_rows, function_rows, geo_rows, audit_rows, geo_codes
    )
    print(
        "[ok] 検証1〜11・14〜15: published_fy・record_id一意性(11760)・record_id集合一致・"
        "area_code集合一致(339)・区域内一貫性・21指標の過不足なし・metric/bed_function既知性・"
        "value_status既知性・value整合・座標整合(10244件)・facility_functions部分集合・"
        f"検算で取り下げる座標({len(withdrawn)}件)・医療情報ネット採用座標({len(reference_adopted)}件)を確認"
    )

    areas = build_areas(basic_rows, obs_index, geo_index, functions_index, withdrawn, reference_adopted)
    validate_areas_output(areas, basic_id_set)
    total_facilities = sum(a["facility_count"] for a in areas)
    total_geocoded = sum(a["geocoded_count"] for a in areas)
    total_reference_geocoded = sum(a["reference_geocoded_count"] for a in areas)
    total_withdrawn = sum(a["coordinate_withdrawn_count"] for a in areas)
    if total_geocoded != EXPECTED_DISPLAYED_COORDINATE_COUNT:
        raise SystemExit(
            f"検証14失敗: 地図に出す座標が{EXPECTED_DISPLAYED_COORDINATE_COUNT}件ちょうどでは"
            f"ありません(実際{total_geocoded}件)"
        )
    if total_reference_geocoded != EXPECTED_REFERENCE_ADOPTED_COUNT:
        raise SystemExit(
            "検証15失敗: 医療情報ネット由来の座標が全区域合計で"
            f"{EXPECTED_REFERENCE_ADOPTED_COUNT}件ちょうどではありません(実際{total_reference_geocoded}件)"
        )
    print(
        f"[ok] areas構築+検証12〜16: {len(areas)}区域 施設計{total_facilities}件"
        f"(地図に出す座標{total_geocoded}件[医療情報ネット由来{total_reference_geocoded}件を含む] "
        f"/ 検算で取り下げ{total_withdrawn}件)"
    )

    with open(FACILITY_BASIC_META_PATH, "r", encoding="utf-8") as f:
        basic_meta = json.load(f)
    with open(FACILITY_OBSERVATIONS_META_PATH, "r", encoding="utf-8") as f:
        observations_meta = json.load(f)
    with open(FACILITY_FUNCTIONS_META_PATH, "r", encoding="utf-8") as f:
        functions_meta = json.load(f)
    with open(FACILITY_GEO_LINKAGE_META_PATH, "r", encoding="utf-8") as f:
        geo_meta = json.load(f)
    with open(FACILITY_GEO_AUDIT_META_PATH, "r", encoding="utf-8") as f:
        audit_meta = json.load(f)

    inputs = [
        {"path": "data/processed/facility_basic.csv", "sha256": sha256(FACILITY_BASIC_CSV)},
        {"path": "data/processed/facility_observations.csv", "sha256": sha256(FACILITY_OBSERVATIONS_CSV)},
        {"path": "data/processed/facility_functions.csv", "sha256": sha256(FACILITY_FUNCTIONS_CSV)},
        {"path": "data/processed/facility_geo_linkage.csv", "sha256": sha256(FACILITY_GEO_LINKAGE_CSV)},
        {"path": "data/processed/facility_geo_audit.csv", "sha256": sha256(FACILITY_GEO_AUDIT_CSV)},
        {"path": "data/processed/area_boundaries_R7.geojson", "sha256": sha256(AREA_BOUNDARIES_GEOJSON)},
    ]
    metadata = build_metadata(
        basic_meta, observations_meta, functions_meta, geo_meta, audit_meta, inputs
    )

    output = {
        "metadata": metadata,
        "metrics": METRICS,
        "value_status_labels": VALUE_STATUS_LABELS,
        "areas": areas,
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = dump_json(output)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    print(f"[ok] 出力: {out_path}")
    print(f"     区域数: {len(areas)} 施設数: {total_facilities} 座標あり: {total_geocoded}")
    print(f"     サイズ: {out_path.stat().st_size:,} bytes")
    print(f"     sha256 = {sha256(out_path)}")

    return out_path


def main() -> None:
    build_and_write(OUT_PATH)


if __name__ == "__main__":
    main()
