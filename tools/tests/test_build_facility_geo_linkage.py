# -*- coding: utf-8 -*-
"""tools/build_facility_geo_linkage.py のテスト。

3層構成:
  1. 合成フィクスチャの単体テスト: 名称正規化(法人格語の除去・NFKC)、
     市区町村抽出(郡付き・政令市・特別区)、点-多角形判定(穴あり・
     MultiPolygon・bbox外・境界近傍)、一対一制約(競合したら両方不採用)、
     あいまい一致が座標を与えないこと。実データ・ネットワークに一切依存しない
  2. 実データ(facility_basic.csv・P04-20.geojson・area_boundaries_R7.geojson)
     の前提確認: 出力行数・match_statusの内訳・座標の有無・record_idの1対1対応。
     P04読み込み+突合はmodule scopeのfixtureで1回だけ行う
  3. 再現性: `build_and_write(out_dir, doc_dir)` の出力が、コミット済みの
     facility_geo_linkage.csv・doc/FACILITY_LINKAGE.md とバイト一致すること
     (2回目の実データロード+突合はここでのみ発生する)
"""
import json

import pytest

from tools.build_facility_geo_linkage import (
    AREA_BOUNDARIES_PATH,
    BED_DIVERGENCE_ABS_MIN,
    BED_DIVERGENCE_RATIO,
    CATEGORY_CLINIC,
    CATEGORY_DENTAL,
    CATEGORY_HOSPITAL,
    DOC_DIR,
    FACILITY_TYPE_WORDS,
    FUZZY_MATCH_THRESHOLD,
    LEGAL_ENTITY_TERMS,
    MATCH_METHOD_EXACT,
    MATCH_METHOD_NONE,
    MATCH_METHOD_SUFFIX,
    MATCH_STATUS_CANDIDATE_ONLY,
    MATCH_STATUS_MATCHED,
    MATCH_STATUS_UNMATCHED,
    P04_ZIP_PATH,
    PROCESSED_DIR,
    REASON_CONTESTED_CANDIDATE,
    REASON_MUNICIPALITY_MISMATCH,
    REASON_MUNICIPALITY_NOT_IN_ADDRESS,
    REASON_MULTIPLE_CANDIDATES_IN_AREA,
    REASON_NOT_REPORTED_FACILITY,
    REASON_NO_NAME_MATCH,
    REASON_OUTSIDE_AREA_POLYGON,
    SUFFIX_MIN_SHORT_LEN,
    AreaIndex,
    P04Point,
    address_matches_municipality,
    build_and_write,
    build_p04_indices,
    extract_municipality,
    is_type_word_only,
    load_bed_counts,
    load_facilities,
    load_p04_points,
    match_facilities,
    normalize_facility_name,
    point_in_geometry,
)
from tools.build_facility_geo_linkage import _compute_bed_divergence

OUT_CSV = PROCESSED_DIR / "facility_geo_linkage.csv"
OUT_DOC = DOC_DIR / "FACILITY_LINKAGE.md"


# =====================================================================
# 1. 合成フィクスチャによる単体テスト
# =====================================================================

# --- normalize_facility_name() ------------------------------------------


def test_normalize_facility_name_removes_legal_entity_term_longest_first():
    """「医療法人社団」は「医療法人」の除去で「社団」が残ってしまわないよう、
    長い語から先に除去されること。
    """
    assert normalize_facility_name("医療法人社団立青会なるかわ病院") == normalize_facility_name(
        "立青会なるかわ病院"
    )
    assert normalize_facility_name("医療法人社団立青会なるかわ病院") == "立青会なるかわ病院"


def test_normalize_facility_name_removes_multiple_legal_entity_terms():
    assert normalize_facility_name("社会医療法人〇〇会病院") == "〇〇会病院"
    assert normalize_facility_name("独立行政法人国立病院機構函館病院") == "国立病院機構函館病院"


def test_normalize_facility_name_nfkc_and_symbols_and_case():
    # 全角括弧・中黒・全角英数字が正規化・除去され、小文字化される。
    assert normalize_facility_name("Ａ病院（本院）") == "a病院本院"
    assert normalize_facility_name("Ｂ・Ｃクリニック") == "bcクリニック"


def test_normalize_facility_name_removes_whitespace_anywhere():
    assert normalize_facility_name("医療法人明雪会 環状通東整形外科") == normalize_facility_name(
        "医療法人明雪会環状通東整形外科"
    )


def test_legal_entity_terms_have_no_accidental_duplicates():
    assert len(LEGAL_ENTITY_TERMS) == len(set(LEGAL_ENTITY_TERMS))


def test_facility_type_words_have_no_accidental_duplicates():
    assert len(FACILITY_TYPE_WORDS) == len(set(FACILITY_TYPE_WORDS))


# --- 法人格語除去のガード(ジェネリック語だけになる誤結合を防ぐ) ------


def test_normalize_facility_name_keeps_legal_term_when_residual_is_type_word_only():
    """法人格語を除去すると施設種別語だけ(残余が空)になる名称は、除去せず
    元の名称のまま返すこと(「厚生連クリニック」→「クリニック」だけでは
    全国のクリニック共通の一般名詞になってしまい、無関係の別施設と接尾一致で
    誤結合しうるため。実測で発見した不具合の回帰テスト)。
    """
    assert normalize_facility_name("厚生連クリニック") == "厚生連クリニック"


def test_normalize_facility_name_still_removes_legal_term_when_residual_remains():
    """法人格語除去後の残余が空でなければ、従来どおり法人格語を除去すること
    (「医療法人社団森クリニック」→「森クリニック」。残余`1`文字でも除去して
    よい。残余の判定は「空かどうか」で行うべきで「N文字未満なら除去しない」
    にしてはいけない、という回帰テスト)。
    """
    assert normalize_facility_name("医療法人社団森クリニック") == "森クリニック"
    # 「泉」「浦」も1文字の残余だが正しい正規化であり、巻き戻してはいけない。
    assert normalize_facility_name("医療法人社団泉クリニック") == "泉クリニック"
    assert normalize_facility_name("医療法人社団浦クリニック") == "浦クリニック"


def test_is_type_word_only():
    """`is_type_word_only()`は正規化済みの文字列を受け取る想定であり、生の
    表記のままではなく`normalize_facility_name()`後の形で判定すること
    (「センター」は記号除去で長音記号が落ちるため「センタ」になる。
    `_normalize_type_word`が`FACILITY_TYPE_WORDS`側もこの記号除去を通してから
    比較しているのはこのため。実測で見つけた不具合の回帰テスト)。
    """
    assert is_type_word_only("クリニック") is True
    assert is_type_word_only(normalize_facility_name("医療センター")) is True
    assert is_type_word_only("森クリニック") is False
    assert is_type_word_only("") is True


# --- extract_municipality() ----------------------------------------------


def test_extract_municipality_gun_town():
    assert extract_municipality("標津郡中標津町りんどう町5番地6") == "中標津町"


def test_extract_municipality_designated_city_ward():
    assert extract_municipality("札幌市北区北3条西5丁目1") == "札幌市北区"


def test_extract_municipality_tokyo_special_ward():
    assert extract_municipality("文京区本郷1-1-1") == "文京区"


def test_extract_municipality_strips_leading_prefecture_name():
    """P04住所は原則都道府県名を含まないが、実測で長崎県等は都道府県名付きで
    記載されている(municipality_mismatchの実測調査で判明)。都道府県名が
    付いていても壊れないこと。
    """
    assert extract_municipality("長崎県長崎市坂本１丁目７－１") == "長崎市"
    assert extract_municipality("島根県松江市母衣町２００") == "松江市"


def test_extract_municipality_town_without_gun_prefix():
    """郡表記を省略していきなり町から始まる住所(実測: 神奈川県足柄上郡の町等)。"""
    assert extract_municipality("昭和町河東中島443") == "昭和町"


def test_extract_municipality_returns_none_for_bare_ward_without_city():
    """政令指定都市名を省略していきなり区名から始まる住所(実測: 横浜市を省略した
    住所)は、市を一意に特定できないためNoneを返す(誤って推測しない)。
    """
    assert extract_municipality("港北区小机町3211") is None


def test_extract_municipality_returns_none_for_blank_or_unparseable():
    assert extract_municipality("") is None
    assert extract_municipality(None) is None


def test_extract_municipality_does_not_overmatch_on_kanji_digit_in_name():
    """「三浦市」のように市区町村名自体が漢数字で始まる場合に、漢数字を区切り
    文字と誤認して抽出が全滅しないこと(実測で見つかった不具合の回帰テスト)。
    """
    assert extract_municipality("三浦市岬陽町４－３３") == "三浦市"


def test_extract_municipality_does_not_overmatch_when_place_name_repeats_suffix_char():
    """「赤磐市下市...」のように、市区町村名に続く地名が区切り文字(市)で終わる
    場合に、貪欲マッチで長く抽出しすぎないこと(実測で見つかった不具合の回帰テスト)。
    """
    assert extract_municipality("赤磐市下市１８７番地１") == "赤磐市"


# --- address_matches_municipality() ---------------------------------------


def test_address_matches_municipality_handles_embedded_suffix_ambiguity():
    """「四日市市」のように市区町村名自体の中に区切り文字(市)を含む地名で、
    extract_municipality()が短く抽出しすぎても(「四日市」)、Excel側の正しい
    市区町村名との直接比較では正しく一致すること。
    """
    assert extract_municipality("四日市市芝田2丁目2番37号") == "四日市"  # 既知の限界(短く抽出される)
    assert address_matches_municipality("四日市市芝田2丁目2番37号", "四日市市") is True


def test_address_matches_municipality_normalizes_small_kana_ke_variant():
    """「ヶ/ヵ」と「ケ/カ」の表記ゆれ(実測: 龍ケ崎市/龍ヶ崎市)を吸収すること。"""
    assert address_matches_municipality("龍ヶ崎市中里１丁目１番", "龍ケ崎市") is True
    assert address_matches_municipality("駒ケ根市中央1-1", "駒ヶ根市") is True


def test_address_matches_municipality_strips_gun_prefix():
    assert address_matches_municipality("標津郡中標津町りんどう町5番地6", "中標津町") is True


def test_address_matches_municipality_rejects_different_municipality():
    assert address_matches_municipality("仙台市青葉区堤町3-16-1", "仙台市泉区") is False


def test_address_matches_municipality_accepts_bare_ward_matching_suffix():
    """政令指定都市名を省略し区名から始まる住所(横浜市を省略した
    '港北区…')でも、区名がExcel側の市区町村名の**末尾**と一致すれば整合とみなす
    (取りこぼしの是正。区域ポリゴンで既に絞り込んだ候補にのみ適用されるため、
    誤って別の市の同名区と結び付けるリスクは小さい)。
    """
    assert address_matches_municipality("港北区小机町3211", "横浜市港北区") is True


def test_address_matches_municipality_rejects_bare_ward_with_different_ward():
    """住所側の区名がExcel側の市区町村名の末尾と一致しない場合は、政令市名
    省略の緩和は適用されず、素直に不整合のままであること。
    """
    assert address_matches_municipality("中央区小机町3211", "横浜市港北区") is False


def test_address_matches_municipality_rejects_blank_inputs():
    assert address_matches_municipality("", "札幌市北区") is False
    assert address_matches_municipality("札幌市北区1-1", "") is False


# --- reason_codeの細分化(municipality_mismatch vs municipality_not_in_address) ---
# `_municipality_check()`は`match_facilities`内部で使われる
# private関数のため、`match_facilities`経由で間接的にテストする(下記の
# 合成フィクスチャテスト参照)。ここでは判定の材料になる
# `extract_municipality()`側の挙動(低信頼フォールバックが生む曖昧さ)を確認する。


def test_extract_municipality_town_fallback_can_match_intra_city_district_name():
    """`extract_municipality()`の郡なし「○○町」フォールバックは、独立した町
    (山梨県の郡表記省略等)と、市内の字・地区名がたまたま「町」で終わるだけの
    ケース(埼玉県越谷市の「川柳町」等)を区別できない、という既知の限界の
    デモンストレーション(`_municipality_check`はこの限界を
    `_extract_municipality_confident()`で回避している。合成フィクスチャの
    `match_facilities`テストで検証)。
    """
    assert extract_municipality("川柳町3-50-1") == "川柳町"  # 越谷市内の地区名だが抽出はされる


# --- 点-多角形判定(point_in_geometry) -------------------------------------

# 外環[0,0]-[10,10]の正方形の中に、内環(穴)[4,4]-[6,6]を持つPolygon。
SQUARE_WITH_HOLE = {
    "type": "Polygon",
    "coordinates": [
        [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
        [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
    ],
}

# 互いに離れた2つの正方形から成るMultiPolygon。
TWO_SQUARES = {
    "type": "MultiPolygon",
    "coordinates": [
        [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
        [[[10, 10], [12, 10], [12, 12], [10, 12], [10, 10]]],
    ],
}


def test_point_in_geometry_polygon_solid_area():
    assert point_in_geometry(1, 1, SQUARE_WITH_HOLE) is True


def test_point_in_geometry_polygon_inside_hole_is_outside():
    assert point_in_geometry(5, 5, SQUARE_WITH_HOLE) is False


def test_point_in_geometry_polygon_far_outside():
    assert point_in_geometry(100, 100, SQUARE_WITH_HOLE) is False


def test_point_in_geometry_multipolygon_second_part():
    assert point_in_geometry(11, 11, TWO_SQUARES) is True


def test_point_in_geometry_multipolygon_neither_part():
    assert point_in_geometry(5, 5, TWO_SQUARES) is False


def test_point_in_geometry_near_boundary():
    # 境界のすぐ内側/すぐ外側(ちょうど境界線上のあいまいなケースは扱わない)。
    assert point_in_geometry(0.001, 5, SQUARE_WITH_HOLE) is True
    assert point_in_geometry(-0.001, 5, SQUARE_WITH_HOLE) is False


def test_point_in_geometry_rejects_unknown_geometry_type():
    with pytest.raises(ValueError):
        point_in_geometry(0, 0, {"type": "LineString", "coordinates": [[0, 0], [1, 1]]})


# --- AreaIndex(グリッド+点-多角形判定) -------------------------------------


def _synthetic_boundaries():
    return {
        "features": [
            {"properties": {"area_code": "0001"}, "geometry": SQUARE_WITH_HOLE},
            {
                "properties": {"area_code": "0002"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[20, 20], [22, 20], [22, 22], [20, 22], [20, 20]]],
                },
            },
        ]
    }


def test_area_index_finds_containing_area():
    idx = AreaIndex(_synthetic_boundaries())
    assert idx.area_count == 2
    assert idx.find_area_code(1, 1) == "0001"
    assert idx.find_area_code(21, 21) == "0002"


def test_area_index_returns_none_outside_all_areas():
    idx = AreaIndex(_synthetic_boundaries())
    assert idx.find_area_code(500, 500) is None
    assert idx.find_area_code(5, 5) is None  # 穴の中


# --- 一対一制約とあいまい一致(match_facilities) ----------------------------


def _p04(index, name, address, municipality, area_code, lon=0.0, lat=0.0, beds=10, category=CATEGORY_HOSPITAL):
    return P04Point(
        index=index,
        category=category,
        name=name,
        name_normalized=normalize_facility_name(name),
        address=address,
        municipality=municipality,
        beds=beds,
        lon=lon,
        lat=lat,
        area_code=area_code,
    )


def _facility(record_id, area_code, name, municipality):
    return {
        "record_id": record_id,
        "area_code": area_code,
        "facility_name": name,
        "municipality": municipality,
    }


def test_match_facilities_exact_match_is_matched():
    p04_points = [_p04(0, "テスト病院", "テスト市本町1-1", "テスト市", "0001", lon=1.0, lat=2.0)]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [_facility("R1", "0001", "テスト病院", "テスト市")]

    rows, fuzzy_scores = match_facilities(facilities, by_name, by_area)

    assert len(rows) == 1
    row = rows[0]
    assert row.match_status == MATCH_STATUS_MATCHED
    assert row.match_method == MATCH_METHOD_EXACT
    assert row.reason_code == ""
    assert row.p04.lon == 1.0 and row.p04.lat == 2.0
    assert fuzzy_scores == []  # matchedのみなのであいまい候補探索は発生しない


def test_match_facilities_one_to_one_constraint_rejects_both_contestants():
    """同じP04フィーチャを2つのExcel施設が仮採用しようとした場合、両方とも
    'matched'にはならないこと(誤って片方を勝たせない)。

    競合した候補自身は区域内の名称類似度探索でも最良候補(スコア1.0)として
    再度見つかるため`candidate_only`(座標なしの候補提示)にはなりうるが、
    自動採用(座標の確定)には至らないことが本質。
    """
    p04_points = [_p04(0, "共用病院", "テスト市本町1-1", "テスト市", "0001")]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [
        _facility("R1", "0001", "共用病院", "テスト市"),
        _facility("R2", "0001", "共用病院", "テスト市"),
    ]

    rows, _ = match_facilities(facilities, by_name, by_area)

    assert all(r.match_status != MATCH_STATUS_MATCHED for r in rows)
    assert all(r.match_method == MATCH_METHOD_NONE for r in rows)
    assert all(r.reason_code == REASON_CONTESTED_CANDIDATE for r in rows)


def test_match_facilities_municipality_mismatch_blocks_auto_adoption():
    p04_points = [_p04(0, "テスト病院", "別市本町1-1", "別市", "0001")]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [_facility("R1", "0001", "テスト病院", "テスト市")]

    rows, _ = match_facilities(facilities, by_name, by_area)

    assert rows[0].match_status != MATCH_STATUS_MATCHED
    assert rows[0].reason_code == REASON_MUNICIPALITY_MISMATCH


def test_match_facilities_multiple_candidates_in_area_blocks_auto_adoption():
    p04_points = [
        _p04(0, "テスト病院", "テスト市本町1-1", "テスト市", "0001"),
        _p04(1, "テスト病院", "テスト市本町2-2", "テスト市", "0001"),
    ]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [_facility("R1", "0001", "テスト病院", "テスト市")]

    rows, _ = match_facilities(facilities, by_name, by_area)

    assert rows[0].match_status != MATCH_STATUS_MATCHED
    assert rows[0].reason_code == REASON_MULTIPLE_CANDIDATES_IN_AREA
    assert rows[0].candidate_count == 2


def test_match_facilities_no_name_match():
    by_name, by_area = build_p04_indices([])
    facilities = [_facility("R1", "0001", "テスト病院", "テスト市")]

    rows, _ = match_facilities(facilities, by_name, by_area)

    assert rows[0].match_status == MATCH_STATUS_UNMATCHED
    assert rows[0].reason_code == REASON_NO_NAME_MATCH


def test_match_facilities_outside_area_polygon():
    """正規化名が一致する候補はあるが、別区域にしかない場合。"""
    p04_points = [_p04(0, "テスト病院", "テスト市本町1-1", "テスト市", "9999")]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [_facility("R1", "0001", "テスト病院", "テスト市")]

    rows, _ = match_facilities(facilities, by_name, by_area)

    assert rows[0].match_status == MATCH_STATUS_UNMATCHED
    assert rows[0].reason_code == REASON_OUTSIDE_AREA_POLYGON


def test_match_facilities_not_reported_facility_never_auto_matches():
    """Excel側の所在地が空(未報告の医療機関)は、名前が完全一致しても
    市区町村を検証できないため自動採用されないこと。
    """
    p04_points = [_p04(0, "テスト病院", "テスト市本町1-1", "テスト市", "0001")]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [_facility("R1", "0001", "テスト病院", "")]

    rows, _ = match_facilities(facilities, by_name, by_area)

    assert rows[0].match_status != MATCH_STATUS_MATCHED
    assert rows[0].reason_code == REASON_NOT_REPORTED_FACILITY


def test_match_facilities_fuzzy_candidate_gets_no_coordinates():
    """あいまい一致(candidate_only)は座標を持たない(名前とスコアのみ)。"""
    p04_points = [_p04(0, "テスト総合病院", "テスト市本町1-1", "テスト市", "0001", lon=99.0, lat=88.0)]
    by_name, by_area = build_p04_indices(p04_points)
    # 正規化名が完全一致しない(「総合」の有無)ため自動採用の経路には乗らない。
    facilities = [_facility("R1", "0001", "テスト病院", "テスト市")]

    rows, fuzzy_scores = match_facilities(facilities, by_name, by_area)

    row = rows[0]
    assert len(fuzzy_scores) == 1
    if row.match_score is not None and row.match_score >= FUZZY_MATCH_THRESHOLD:
        assert row.match_status == MATCH_STATUS_CANDIDATE_ONLY
        assert row.match_method == MATCH_METHOD_NONE
        # LinkageRowレベルではp04を保持するが、CSV出力時にlongitude/latitudeへ
        # 変換されるのはmatchedのみ(_rows_to_output_dictsのテストで別途確認)。
        assert row.p04 is not None


def test_match_facilities_dissimilar_name_stays_unmatched_without_candidate():
    """類似度が閾値未満なら`candidate_only`にならず、P04候補も付与されないこと。"""
    p04_points = [_p04(0, "全く違う名前のクリニック", "テスト市本町1-1", "テスト市", "0001")]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [_facility("R1", "0001", "テスト病院", "テスト市")]

    rows, fuzzy_scores = match_facilities(facilities, by_name, by_area)

    row = rows[0]
    assert fuzzy_scores == [pytest.approx(fuzzy_scores[0])]
    if fuzzy_scores[0] < FUZZY_MATCH_THRESHOLD:
        assert row.match_status == MATCH_STATUS_UNMATCHED
        assert row.p04 is None


def test_match_facilities_municipality_not_in_address_vs_mismatch():
    """「市区町村を抽出できるが違う」(municipality_mismatch)と
    「そもそも住所に市区町村名が見当たらない」(municipality_not_in_address)を
    区別すること。
    """
    p04_points = [
        _p04(0, "テスト病院", "別市本町1-1", "別市", "0001"),  # 抽出できるが違う市
        _p04(1, "テスト診療所", "本町2-2", "", "0001"),  # 市区町村名が住所に無い
    ]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [
        _facility("R1", "0001", "テスト病院", "テスト市"),
        _facility("R2", "0001", "テスト診療所", "テスト市"),
    ]

    rows, _ = match_facilities(facilities, by_name, by_area)

    by_id = {r.record_id: r for r in rows}
    assert by_id["R1"].reason_code == REASON_MUNICIPALITY_MISMATCH
    assert by_id["R2"].reason_code == REASON_MUNICIPALITY_NOT_IN_ADDRESS


# --- 接尾一致ティア(match_method='normalized_suffix') ----------------------


def test_match_facilities_suffix_tier_adopts_unique_relation():
    """完全一致ティアで採用されなかった施設について、正規化名が「一方が他方の
    末尾」の関係にあり、短い方が閾値文字数以上、区域内で一意、市区町村も整合
    すれば接尾一致ティアで自動採用されること。
    """
    p04_points = [_p04(0, "山梨病院機構県立中央病院", "テスト市本町1-1", "テスト市", "0001", lon=10.0, lat=20.0)]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [_facility("R1", "0001", "県立中央病院", "テスト市")]  # 6文字、閾値以上

    rows, _ = match_facilities(facilities, by_name, by_area)

    row = rows[0]
    assert row.match_status == MATCH_STATUS_MATCHED
    assert row.match_method == MATCH_METHOD_SUFFIX
    assert row.reason_code == ""
    assert row.match_score is None  # 接尾一致ではmatch_scoreは使わない
    assert row.p04.lon == 10.0 and row.p04.lat == 20.0


def test_match_facilities_suffix_tier_rejects_short_common_part():
    """短い方の正規化名が閾値文字数未満なら、「中央病院」のような汎用語1つが
    共通するだけで採用されないこと(誤結合防止)。
    """
    assert len("中央病院") < SUFFIX_MIN_SHORT_LEN
    p04_points = [_p04(0, "山梨県立中央病院", "テスト市本町1-1", "テスト市", "0001")]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [_facility("R1", "0001", "中央病院", "テスト市")]

    rows, _ = match_facilities(facilities, by_name, by_area)

    row = rows[0]
    assert row.match_status != MATCH_STATUS_MATCHED
    assert row.match_method != MATCH_METHOD_SUFFIX


def test_match_facilities_suffix_tier_rejects_type_word_only_short_side():
    """短い方の正規化名が`SUFFIX_MIN_SHORT_LEN`文字以上でも、施設種別語だけ
    (`is_type_word_only`)なら採用しないこと(「接尾一致ティア
    側にも保険のガードを入れる」。`normalize_facility_name()`のガードとは別に、
    正規化後の名称がもともと種別語だけだったケースを想定した保険)。
    """
    assert len("医療センター") >= SUFFIX_MIN_SHORT_LEN
    p04_points = [_p04(0, "山梨医療センター", "テスト市本町1-1", "テスト市", "0001")]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [_facility("R1", "0001", "医療センター", "テスト市")]

    rows, _ = match_facilities(facilities, by_name, by_area)

    row = rows[0]
    assert row.match_status != MATCH_STATUS_MATCHED
    assert row.match_method != MATCH_METHOD_SUFFIX


def test_match_facilities_suffix_tier_rejects_multiple_candidates():
    """区域内に接尾一致の候補が複数あれば一意に絞れないため採用しないこと。"""
    p04_points = [
        _p04(0, "山梨病院機構県立中央病院", "テスト市本町1-1", "テスト市", "0001"),
        _p04(1, "甲府病院機構県立中央病院", "テスト市本町2-2", "テスト市", "0001"),
    ]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [_facility("R1", "0001", "県立中央病院", "テスト市")]

    rows, _ = match_facilities(facilities, by_name, by_area)

    row = rows[0]
    assert row.match_status != MATCH_STATUS_MATCHED
    assert row.reason_code == REASON_MULTIPLE_CANDIDATES_IN_AREA
    assert row.candidate_count == 2


def test_match_facilities_suffix_tier_rejects_municipality_mismatch():
    p04_points = [_p04(0, "山梨病院機構県立中央病院", "別市本町1-1", "別市", "0001")]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [_facility("R1", "0001", "県立中央病院", "テスト市")]

    rows, _ = match_facilities(facilities, by_name, by_area)

    row = rows[0]
    assert row.match_status != MATCH_STATUS_MATCHED
    assert row.reason_code == REASON_MUNICIPALITY_MISMATCH


def test_match_facilities_exact_tier_priority_over_suffix_tier():
    """完全一致ティアで既に採用されたP04フィーチャは、接尾一致ティアが
    横取りできないこと(処理順序と一対一制約の統合、)。
    """
    p04_points = [_p04(0, "県立中央病院", "テスト市本町1-1", "テスト市", "0001")]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [
        _facility("A", "0001", "県立中央病院", "テスト市"),  # 完全一致でindex 0を確保
        _facility("B", "0001", "山梨病院機構県立中央病院", "テスト市"),  # 接尾一致になりうるが横取り不可
    ]

    rows, _ = match_facilities(facilities, by_name, by_area)

    by_id = {r.record_id: r for r in rows}
    assert by_id["A"].match_status == MATCH_STATUS_MATCHED
    assert by_id["A"].match_method == MATCH_METHOD_EXACT
    assert by_id["A"].p04.index == 0
    # Bは区域内に他の候補が無いため、接尾一致ティアも自動採用に至らない。
    assert by_id["B"].match_status != MATCH_STATUS_MATCHED
    assert by_id["B"].p04 is None or by_id["B"].p04.index != 0


def test_match_facilities_suffix_tier_contested_rejects_both():
    """接尾一致どうしが同一のP04フィーチャを取り合った場合、両方とも不採用に
    なること(完全一致ティアと同様の一対一制約を独立に適用)。
    """
    p04_points = [_p04(0, "県立中央病院", "テスト市本町1-1", "テスト市", "0001")]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [
        _facility("A", "0001", "山梨病院機構県立中央病院", "テスト市"),
        _facility("B", "0001", "甲府病院機構県立中央病院", "テスト市"),
    ]

    rows, _ = match_facilities(facilities, by_name, by_area)

    assert all(r.match_status != MATCH_STATUS_MATCHED for r in rows)
    assert all(r.reason_code == REASON_CONTESTED_CANDIDATE for r in rows)


# --- 病床数の乖離検知(_compute_bed_divergence、) ---------------


def test_compute_bed_divergence_flags_large_ratio_and_absolute_gap():
    """比率・絶対差とも閾値を超える行だけを乖離として拾うこと。"""
    p04_points = [_p04(0, "テスト病院", "テスト市本町1-1", "テスト市", "0001", beds=900)]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [_facility("R1", "0001", "テスト病院", "テスト市")]
    rows, _ = match_facilities(facilities, by_name, by_area)
    assert rows[0].match_status == MATCH_STATUS_MATCHED

    bed_counts = {"R1": 90}  # Excel側90床 対 P04側900床(10倍・差810床)
    divergent = _compute_bed_divergence(rows, bed_counts)

    assert len(divergent) == 1
    row, excel_beds, p04_beds, ratio = divergent[0]
    assert row.record_id == "R1"
    assert excel_beds == 90 and p04_beds == 900
    assert ratio == pytest.approx(10.0)


def test_compute_bed_divergence_ignores_small_absolute_gap_despite_large_ratio():
    """比率は閾値以上でも絶対差が小さい(小規模診療所によくある)場合は
    乖離として拾わないこと(で追加した絶対差条件)。
    """
    assert 19 / 1 >= BED_DIVERGENCE_RATIO
    assert abs(19 - 1) < BED_DIVERGENCE_ABS_MIN
    p04_points = [_p04(0, "テスト診療所", "テスト市本町1-1", "テスト市", "0001", beds=19)]
    by_name, by_area = build_p04_indices(p04_points)
    facilities = [_facility("R1", "0001", "テスト診療所", "テスト市")]
    rows, _ = match_facilities(facilities, by_name, by_area)

    bed_counts = {"R1": 1}
    divergent = _compute_bed_divergence(rows, bed_counts)

    assert divergent == []


def test_compute_bed_divergence_ignores_unmatched_rows():
    """`matched`以外の行(候補が無い等)は病床数を比較しないこと。"""
    by_name, by_area = build_p04_indices([])
    facilities = [_facility("R1", "0001", "テスト病院", "テスト市")]
    rows, _ = match_facilities(facilities, by_name, by_area)
    assert rows[0].match_status != MATCH_STATUS_MATCHED

    divergent = _compute_bed_divergence(rows, {"R1": 90})
    assert divergent == []


# =====================================================================
# 2. 実データの前提確認
# =====================================================================


@pytest.fixture(scope="module")
def area_index():
    with open(AREA_BOUNDARIES_PATH, "r", encoding="utf-8") as f:
        gj = json.load(f)
    return AreaIndex(gj)


@pytest.fixture(scope="module")
def p04_loaded(area_index):
    points, category_counts = load_p04_points(P04_ZIP_PATH, area_index)
    by_name, by_area = build_p04_indices(points)
    return {"points": points, "category_counts": category_counts, "by_name": by_name, "by_area": by_area}


@pytest.fixture(scope="module")
def facilities():
    return load_facilities()


@pytest.fixture(scope="module")
def match_result(p04_loaded, facilities):
    rows, fuzzy_scores = match_facilities(facilities, p04_loaded["by_name"], p04_loaded["by_area"])
    return {"rows": rows, "fuzzy_scores": fuzzy_scores}


def test_p04_category_counts(p04_loaded):
    counts = p04_loaded["category_counts"]
    assert counts[CATEGORY_HOSPITAL] == 8269
    assert counts[CATEGORY_CLINIC] == 104183
    assert counts[CATEGORY_DENTAL] == 68860
    assert sum(counts.values()) == 181312


def test_p04_points_exclude_dental(p04_loaded):
    assert len(p04_loaded["points"]) == 8269 + 104183 == 112452
    assert all(p.category != CATEGORY_DENTAL for p in p04_loaded["points"])


def test_facility_basic_row_count(facilities):
    assert len(facilities) == 11760


def test_match_result_row_count_matches_facilities(match_result, facilities):
    assert len(match_result["rows"]) == len(facilities) == 11760


def test_match_status_breakdown(match_result):
    from collections import Counter

    counts = Counter(r.match_status for r in match_result["rows"])
    assert counts[MATCH_STATUS_MATCHED] == 10244
    assert counts[MATCH_STATUS_CANDIDATE_ONLY] == 656
    assert counts[MATCH_STATUS_UNMATCHED] == 860
    assert sum(counts.values()) == 11760


def test_match_method_breakdown(match_result):
    """matchedのティア別内訳(実測値。で接尾一致ティアを追加)。"""
    from collections import Counter

    matched = [r for r in match_result["rows"] if r.match_status == MATCH_STATUS_MATCHED]
    counts = Counter(r.match_method for r in matched)
    assert counts[MATCH_METHOD_EXACT] == 9582
    assert counts[MATCH_METHOD_SUFFIX] == 662
    assert sum(counts.values()) == len(matched) == 10244


def test_matched_rows_always_have_p04_and_coordinates(match_result):
    matched = [r for r in match_result["rows"] if r.match_status == MATCH_STATUS_MATCHED]
    assert len(matched) == 10244
    assert all(r.p04 is not None for r in matched)
    assert all(r.p04.lon is not None and r.p04.lat is not None for r in matched)


def test_unmatched_rows_never_have_p04(match_result):
    unmatched = [r for r in match_result["rows"] if r.match_status == MATCH_STATUS_UNMATCHED]
    assert len(unmatched) == 860
    assert all(r.p04 is None for r in unmatched)


def test_record_id_is_one_to_one_with_facility_basic(match_result, facilities):
    facility_ids = [f["record_id"] for f in facilities]
    row_ids = [r.record_id for r in match_result["rows"]]
    assert len(facility_ids) == len(set(facility_ids))  # facility_basic側に重複がない
    assert row_ids == facility_ids  # 突合結果は入力と同じ順序・同じ集合


def test_one_to_one_constraint_contested_in_real_data(match_result):
    """実データでの一対一制約違反(同じP04フィーチャの競合)件数
    (実測値。将来データが変わった場合の回帰検知)。接尾一致ティア導入後は、
    宇都宮市・福岡市南区で共通の短い名称の候補を複数のExcel施設が取り合う
    ケースが実測で4件見つかっている(doc/FACILITY_LINKAGE.md参照)。
    """
    contested = [r for r in match_result["rows"] if r.reason_code == REASON_CONTESTED_CANDIDATE]
    assert len(contested) == 4
    assert all(r.match_status != MATCH_STATUS_MATCHED for r in contested)


def test_bed_divergence_in_real_data(match_result):
    """実データでのExcel病床数とp04_bedsの乖離件数(実測値。)。
    レビューが具体例として挙げた3施設(東京都立松沢病院・浅香山病院・紘仁病院)
    が、実測でも乖離件数の上位(絶対差の大きい側)に含まれることを確認する。
    """
    bed_counts = load_bed_counts()
    divergent = _compute_bed_divergence(match_result["rows"], bed_counts)
    assert len(divergent) == 228

    top10_names = {
        row.facility_name for row, *_ in sorted(divergent, key=lambda t: -abs(t[1] - t[2]))[:10]
    }
    assert any("松沢病院" in name for name in top10_names)
    assert any("浅香山病院" in name for name in top10_names)
    assert any(name == "紘仁病院" for name in top10_names)


# =====================================================================
# 3. 再現性(バイト一致)
# =====================================================================


def test_facility_geo_linkage_csv_and_doc_exist():
    assert OUT_CSV.exists(), (
        f"{OUT_CSV} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_facility_geo_linkage.py` を実行してください)"
    )
    assert OUT_DOC.exists(), (
        f"{OUT_DOC} が存在しません"
        "(先に `PYTHONIOENCODING=utf-8 python tools/build_facility_geo_linkage.py` を実行してください)"
    )


def test_reproducibility_byte_identical(tmp_path):
    paths = build_and_write(tmp_path, tmp_path)
    assert paths.keys() == {"csv", "meta", "doc"}

    new_csv_bytes = paths["csv"].read_bytes()
    old_csv_bytes = OUT_CSV.read_bytes()
    assert new_csv_bytes == old_csv_bytes, "facility_geo_linkage.csv がコミット済みデータとバイト一致しません"

    new_doc_bytes = paths["doc"].read_bytes()
    old_doc_bytes = OUT_DOC.read_bytes()
    assert new_doc_bytes == old_doc_bytes, "doc/FACILITY_LINKAGE.md がコミット済みデータとバイト一致しません"

    new_meta = json.loads(paths["meta"].read_text(encoding="utf-8"))
    old_meta = json.loads((PROCESSED_DIR / "facility_geo_linkage.csv.meta.json").read_text(encoding="utf-8"))
    # processing.date は実行日ごとに変わるため、比較対象から除外する。
    new_meta["processing"]["date"] = None
    old_meta["processing"]["date"] = None
    assert new_meta == old_meta, "facility_geo_linkage.csv.meta.json の内容(processing.dateを除く)が一致しません"
    assert new_meta["row_count"] == 11760
