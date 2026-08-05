# -*- coding: utf-8 -*-
"""可視化サイトが直接読み込む表示用データセット
`data/processed/area_flow_R7.json` を、既にコミット済みの加工CSV
(`patient_flow.csv`・`patient_flow_total.csv`)と境界GeoJSON
(`area_boundaries_R7.geojson`、area_codeの一致検証にのみ使用しジオメトリは
読まない)から生成する。

M7「患者の流入率・流出率」の Chunk B(データ層のみ)。フロントエンド
(`web/`配下)は別チャンクで扱うため、本スクリプトは`web/`配下には一切触れない。
入力の `tools/parse_patient_flow.py` / `data/processed/patient_flow*.csv` は
既にレビュー済み・確定であり、本スクリプトからは変更しない。

処理内容:
  1. `patient_flow.csv`・`patient_flow_total.csv`・`area_boundaries_R7.geojson`
     (area_codeの一致検証にのみ使用)を読み込む
  2. 検証1〜13(下記)を行い、違反があれば SystemExit で中断する(静かに
     握りつぶさない)
  3. 339区域 × 2方向(流入率・流出率) × 3区分(高度急性期+急性期/包括期/慢性期)
     = 2,034グループ全てを、原典にデータ行が1行も無いグループ(6件)も含めて
     materialize し、`direction`/`phase` の日本語原文を英字キー
     (inflow/outflow, acute/comprehensive/chronic)へ変換する
  4. `patient_flow.csv.meta.json` / `patient_flow_total.csv.meta.json` の
     `source` を実行時に読み込んで引き継ぎ、`metadata.source` を構築する
     (出典情報のハードコードによる二重管理を避ける)
  5. UTF-8・LF・末尾改行1つで出力する。整形は `json.dump(indent=2)` 一発では
     なく `dump_json()` による決定的な独自整形を用いる(下記「出力フォーマット」
     参照)

検証1〜13(各検証は独立した小さな関数に分割してあり、実データ全体を用意
しなくても壊れたフィクスチャで単体テストできる):
   1. patient_flow.csv / patient_flow_total.csv の全行が published_fy == 'R7'
   2. (area_code, direction, phase, rank) に重複が無く、各グループの rank が
      1から連番であること
   3. patient_flow.csv・patient_flow_total.csv・area_boundaries_R7.geojson の
      area_code集合が3つとも完全一致し339件であること
   4. 各 area_code × 2方向 がちょうど1行ずつ patient_flow_total.csv に存在する
      こと(計678行)
   5. direction が既知の2種のみ、phase が既知の3種のみであること
   6. value_status が observed/error の2種のみ。observed 行は rate が有限の
      数値で0〜1、partner_area_code が4桁の数字文字列。error 行は rate が
      空文字で partner_area_code も空であること
   7. observed 行の partner_area_code が339件の集合に含まれること
   8. 各グループ内で rank 昇順に見たとき率が非増加であること
   9. 各グループで自区域行が高々1件であること。自区域行が無いグループの集合が
      実測どおり(流入率×慢性期・流出率×慢性期のそれぞれ6区域、計12件)である
      こと
  10. 自区域行があるグループで self_rate + Σpartners <= 1 + 1e-9 であること
  11. overall_rate が「1 - (acuteのself_rate)」と厳密一致すること(678件全て。
      崩れたら known_issues の flow_overall_rate_equals_acute_phase_complement
      の記述が古い合図)
  12. area_code が4桁の数字文字列で上2桁が pref_code と一致すること
  13. 出力した areas が339件・全てのグループ(2,034)が materialize されている
      こと

英字キー化(direction/phase)は表示用データ生成側の責務(`build_web_demand.py`
が `在宅（訪問診療）`→`home_care` としているのと同じ)。日本語原文は
`direction_labels`/`phase_labels` に必ず保持し、表示の正本はラベル側である。
`comprehensive` は「包括期」の確定訳ではなく単なる安定キーである点に留意。

`partners` は自区域の行を除いた相手区域のみ、原典の並び(率の降順)をそのまま
保つ。要素は `[相手区域コード, 率]` の2要素配列(区域名は入れない。表示側は
既にバンドル済みの `area_indicators.json` から名前を引ける)。

派生値(表示分の合計・打ち切り残差)は出力しない(再計算可能な派生列は出さない
規律。表示側で `1 - self_rate - Σpartners` を計算できる)。

生成日時は埋め込まない(CLAUDE.md参照。再現性テストが翌日に壊れるため)。

出力フォーマット(`tools/build_web_facilities.py` の `dump_json()` に倣う):
  `metadata`/`directions`/`direction_labels`/`phases`/`phase_labels` は
  `indent=2` で可読に、`areas` は要素(構想区域)ごとに1行のcompact JSONとして
  書き出す(1区域1行の決定的フォーマット。CLAUDE.md「可視化実装で判明した
  罠」12番。区域単位の差分がgit diffで追える)。

必要環境: Python 3.11+(openpyxlは使わない。入力はCSVのみ)。

使い方:
    PYTHONIOENCODING=utf-8 python tools/build_web_flow.py
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

PATIENT_FLOW_CSV = REPO_ROOT / "data" / "processed" / "patient_flow.csv"
PATIENT_FLOW_TOTAL_CSV = REPO_ROOT / "data" / "processed" / "patient_flow_total.csv"
AREA_BOUNDARIES_GEOJSON = REPO_ROOT / "data" / "processed" / "area_boundaries_R7.geojson"
OUT_PATH = REPO_ROOT / "data" / "processed" / "area_flow_R7.json"

PATIENT_FLOW_META_PATH = Path(str(PATIENT_FLOW_CSV) + ".meta.json")
PATIENT_FLOW_TOTAL_META_PATH = Path(str(PATIENT_FLOW_TOTAL_CSV) + ".meta.json")

NUM_AREAS = 339

DIRECTIONS = ["inflow", "outflow"]
DIRECTION_LABELS = {
    "inflow": "流入率",
    "outflow": "流出率",
}
DIRECTION_KEY_BY_JA = {ja: key for key, ja in DIRECTION_LABELS.items()}

PHASES = ["acute", "comprehensive", "chronic"]
PHASE_LABELS = {
    "acute": "高度急性期+急性期",
    "comprehensive": "包括期",
    "chronic": "慢性期",
}
PHASE_KEY_BY_JA = {ja: key for key, ja in PHASE_LABELS.items()}

VALUE_STATUS_OBSERVED = "observed"
VALUE_STATUS_ERROR = "error"
KNOWN_VALUE_STATUSES = {VALUE_STATUS_OBSERVED, VALUE_STATUS_ERROR}

# 検証9: 自区域行が無いグループの集合(実測どおり)。流入率×慢性期の6区域は
# 原典にデータ行が1行も無い(=空グループ)。流出率×慢性期の同じ6区域は、
# うち2区域(1313・4207)がKNOWN_ISSUESのflow_outflow_chronic_value_error_cells
# (Excelのエラー値'#VALUE!')、残り4区域は観測行はあるが自区域行が閾値未満で
# 表示から落ちている(patient_flow.csv.meta.jsonのcaveat参照)。
NO_SELF_ROW_AREA_CODES = ["0502", "0508", "1313", "1704", "4207", "4209"]
EXPECTED_NO_SELF_ROW_GROUPS = {
    (DIRECTION_LABELS["inflow"], PHASE_LABELS["chronic"], code) for code in NO_SELF_ROW_AREA_CODES
} | {
    (DIRECTION_LABELS["outflow"], PHASE_LABELS["chronic"], code) for code in NO_SELF_ROW_AREA_CODES
}

# メタデータへ引き継ぐpatient_flow.csv.meta.json / patient_flow_total.csv.meta.json
# のsourceブロックのキー。両ファイルとも同一のR7/001723366.xlsxから派生して
# いるため値は一致するはず(build_metadata()で照合する)。
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
    "directions": (
        "方向の英字キー一覧(表示順)。inflow=流入率(自区域の医療機関に入院した"
        "患者の住所地別の構成比)、outflow=流出率(自区域に住む患者が入院した"
        "医療機関所在地別の構成比)。日本語原文は direction_labels を参照し、"
        "表示の正本は direction_labels 側である"
    ),
    "direction_labels": "方向キー -> 原典シート名そのままの日本語ラベル(表示用・正本)",
    "phases": (
        "区分の英字キー一覧(表示順)。acute=高度急性期+急性期、"
        "comprehensive=包括期、chronic=慢性期。comprehensiveは「包括期」の"
        "確定訳ではなく単なる安定キーである点に留意(病床機能報告の4区分"
        "(高度急性期/急性期/回復期/慢性期)とは別の区切り)。日本語原文は "
        "phase_labels を参照し、表示の正本は phase_labels 側である"
    ),
    "phase_labels": "区分キー -> 原典の区分ヘッダーそのままの日本語ラベル(表示用・正本)",
    "areas": "339構想区域の配列(area_codeの昇順)",
    "area_code": "構想区域(二次医療圏)コード(ゼロ埋め4桁の文字列)",
    "flows": "方向キー(inflow/outflow) -> {overall_rate, phases} の対応",
    "flows.<direction>.overall_rate": (
        "patient_flow_total.csvのoverall_rateをそのまま(丸めない)。3区分"
        "(acute/comprehensive/chronic)の合計ではなく、「高度急性期+急性期」の"
        "自区域シェアの余事象(1-acute.self_rate)である点に留意"
        "(known_issues.flow_overall_rate_equals_acute_phase_complement参照)"
    ),
    "flows.<direction>.phases": "区分キー(acute/comprehensive/chronic) -> グループの対応",
    "phases.<phase>.self_rate": (
        "自区域行(partner_area_code==area_code)の率(0〜1、丸めない)。原典に"
        "自区域行が無いグループではnull(流入率×慢性期/流出率×慢性期の各6区域、"
        "計12グループで実測される: 0502/0508/1313/1704/4207/4209)"
    ),
    "phases.<phase>.self_rank": (
        "自区域行の原典の行位置(1始まり)。self_rateがnullのときは同時にnull。"
        "流出率では自区域が1位とは限らない"
    ),
    "phases.<phase>.partners": (
        "自区域の行を除いた相手区域のみの配列。要素は[相手区域コード, 率]の"
        "2要素配列(区域名は含まない。表示側は既にバンドル済みの"
        "area_indicators.jsonから名前を引ける)。原典の並び(率の降順)をそのまま"
        "保つ。原典の注記「一定数以上の患者がいる区域のみ表示」により、"
        "self_rate(存在すれば)とpartnersの合計は1にならないことがある"
        "(打ち切り。残差は表示側で計算でき、このファイルには持たせない)"
    ),
    "phases.<phase>.value_error_count": (
        "そのグループ内でvalue_status=='error'(原典セルがExcelのエラー値"
        "'#VALUE!')の行数。0または1(known_issues."
        "flow_outflow_chronic_value_error_cells参照)"
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


# --- 検証1〜13(小さく分割し、壊れたフィクスチャで単体テストできるようにする) ---


def validate_published_fy(rows, csv_name: str) -> None:
    """検証1"""
    bad = sorted({r["published_fy"] for r in rows} - {"R7"})
    if bad:
        raise SystemExit(f"検証1失敗: {csv_name}にR7以外のpublished_fyがあります: {bad}")


def validate_area_code_sets(flow_codes, total_codes, geo_codes) -> None:
    """検証3"""
    sets = {
        "patient_flow.csv": flow_codes,
        "patient_flow_total.csv": total_codes,
        "area_boundaries_R7.geojson": geo_codes,
    }
    if not (flow_codes == total_codes == geo_codes) or len(flow_codes) != NUM_AREAS:
        all_codes = set().union(*sets.values())
        missing = {name: sorted(all_codes - codes) for name, codes in sets.items()}
        raise SystemExit(
            "検証3失敗: area_codeの集合が3ファイルで一致しないか339件ではありません。"
            f"件数: patient_flow.csv={len(flow_codes)} "
            f"patient_flow_total.csv={len(total_codes)} "
            f"area_boundaries_R7.geojson={len(geo_codes)}。各ファイルに無いコード: {missing}"
        )


def validate_rank_contiguous(flow_rows) -> None:
    """検証2: (area_code, direction, phase, rank)の重複が無く、各グループの
    rankが1から連番であること。"""
    key_counts = Counter(
        (r["area_code"], r["direction"], r["phase"], r["rank"]) for r in flow_rows
    )
    dup = sorted(k for k, n in key_counts.items() if n > 1)
    if dup:
        raise SystemExit(f"検証2失敗: (area_code,direction,phase,rank)が重複しています: {dup[:20]}")

    groups = {}
    for r in flow_rows:
        key = (r["area_code"], r["direction"], r["phase"])
        groups.setdefault(key, []).append(int(r["rank"]))
    bad = []
    for key, ranks in groups.items():
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            bad.append((key, sorted(ranks)))
    if bad:
        raise SystemExit(f"検証2失敗: グループのrankが1からの連番ではありません: {bad[:5]}")


def validate_total_rows_one_per_area_direction(total_rows, area_codes) -> None:
    """検証4: 各area_code×2方向がちょうど1行ずつpatient_flow_total.csvに存在する。"""
    counts = Counter((r["area_code"], r["direction"]) for r in total_rows)
    expected_keys = {(code, ja) for code in area_codes for ja in DIRECTION_LABELS.values()}
    bad_count = sorted(k for k, n in counts.items() if n != 1)
    if set(counts.keys()) != expected_keys or bad_count:
        missing = sorted(expected_keys - set(counts.keys()))
        extra = sorted(set(counts.keys()) - expected_keys)
        raise SystemExit(
            "検証4失敗: 各area_code×2方向がちょうど1行ずつpatient_flow_total.csvに"
            f"存在しません。不足={missing[:10]} 余剰={extra[:10]} 複数行={bad_count[:10]}"
        )


def validate_known_direction_and_phase(flow_rows, total_rows) -> None:
    """検証5"""
    bad_directions = sorted({r["direction"] for r in flow_rows} - set(DIRECTION_LABELS.values()))
    if bad_directions:
        raise SystemExit(f"検証5失敗: patient_flow.csvに未知のdirectionがあります: {bad_directions}")
    bad_directions_total = sorted({r["direction"] for r in total_rows} - set(DIRECTION_LABELS.values()))
    if bad_directions_total:
        raise SystemExit(f"検証5失敗: patient_flow_total.csvに未知のdirectionがあります: {bad_directions_total}")
    bad_phases = sorted({r["phase"] for r in flow_rows} - set(PHASE_LABELS.values()))
    if bad_phases:
        raise SystemExit(f"検証5失敗: 未知のphaseがあります: {bad_phases}")


def validate_value_status_and_parse(flow_rows):
    """検証6: value_statusがobserved/errorの2種のみ。observed行はrateが有限の
    0〜1数値、partner_area_codeが4桁の数字文字列。error行はrateが空文字で
    partner_area_codeも空であること。

    戻り値: 各行に"rate_value"(float|None)を足したリスト(元のキーは保持)。
    """
    parsed = []
    for i, r in enumerate(flow_rows):
        status = r.get("value_status")
        if status not in KNOWN_VALUE_STATUSES:
            raise SystemExit(f"検証6失敗: 未知のvalue_statusがあります(行{i}): {status!r}")
        if status == VALUE_STATUS_OBSERVED:
            raw_rate = r["rate"]
            try:
                rate = float(raw_rate)
            except (TypeError, ValueError):
                raise SystemExit(f"検証6失敗: rateが数値として解釈できません(行{i}): {raw_rate!r}")
            if not math.isfinite(rate) or not (0 <= rate <= 1):
                raise SystemExit(f"検証6失敗: rateが有限の0〜1の数値ではありません(行{i}): {raw_rate!r}")
            partner = r["partner_area_code"]
            if not (isinstance(partner, str) and len(partner) == 4 and partner.isdigit()):
                raise SystemExit(
                    f"検証6失敗: observed行のpartner_area_codeが4桁の数字文字列ではありません(行{i}): {partner!r}"
                )
        else:
            if r["rate"] != "":
                raise SystemExit(f"検証6失敗: error行のrateが空文字ではありません(行{i}): {r['rate']!r}")
            if r["partner_area_code"] != "":
                raise SystemExit(
                    f"検証6失敗: error行のpartner_area_codeが空ではありません(行{i}): {r['partner_area_code']!r}"
                )
            rate = None
        parsed.append({**r, "rate_value": rate})
    return parsed


def validate_partner_membership(parsed_flow_rows, area_codes) -> None:
    """検証7"""
    bad = sorted(
        {
            r["partner_area_code"]
            for r in parsed_flow_rows
            if r["value_status"] == VALUE_STATUS_OBSERVED and r["partner_area_code"] not in area_codes
        }
    )
    if bad:
        raise SystemExit(f"検証7失敗: partner_area_codeが339区域に含まれない行があります: {bad[:20]}")


def validate_rate_non_increasing(all_groups) -> None:
    """検証8: 各グループ内でrank昇順に見たとき率が非増加であること。"""
    for key, rows in all_groups.items():
        rows_sorted = sorted(rows, key=lambda r: int(r["rank"]))
        prev = None
        for r in rows_sorted:
            if r["value_status"] != VALUE_STATUS_OBSERVED:
                continue
            rate = r["rate_value"]
            if prev is not None and rate > prev + 1e-9:
                raise SystemExit(
                    f"検証8失敗: グループ{key}で率が降順ではありません(rank={r['rank']}): 前={prev} 今={rate}"
                )
            prev = rate


def validate_no_self_row_groups(all_groups) -> None:
    """検証9: 自区域行が無いグループの集合が実測どおり(12件)であること。"""
    no_self = set()
    for (area_code, direction_ja, phase_ja), rows in all_groups.items():
        has_self = any(
            r["value_status"] == VALUE_STATUS_OBSERVED and r["partner_area_code"] == area_code for r in rows
        )
        if not has_self:
            no_self.add((direction_ja, phase_ja, area_code))
    if no_self != EXPECTED_NO_SELF_ROW_GROUPS:
        raise SystemExit(
            "検証9失敗: 自区域行が無いグループの集合が実測(12件)と一致しません。"
            f"実際({len(no_self)}件)={sorted(no_self)}"
        )


def validate_self_rate_bound(all_groups) -> None:
    """検証10: 自区域行があるグループでself_rate+Σpartners <= 1+1e-9であること。"""
    for key, rows in all_groups.items():
        area_code = key[0]
        self_row = next(
            (r for r in rows if r["value_status"] == VALUE_STATUS_OBSERVED and r["partner_area_code"] == area_code),
            None,
        )
        if self_row is None:
            continue
        total = self_row["rate_value"] + sum(
            r["rate_value"]
            for r in rows
            if r["value_status"] == VALUE_STATUS_OBSERVED and r["partner_area_code"] != area_code
        )
        if total > 1 + 1e-9:
            raise SystemExit(f"検証10失敗: グループ{key}でself_rate+Σpartnersが1を超えています: {total}")


def validate_overall_rate_matches_acute_complement(total_by_key, all_groups) -> None:
    """検証11: overall_rateが「1-(acuteのself_rate)」と厳密一致すること(678件)。"""
    acute_ja = PHASE_LABELS["acute"]
    for (area_code, direction_ja), overall_rate in total_by_key.items():
        rows = all_groups.get((area_code, direction_ja, acute_ja), [])
        self_row = next(
            (r for r in rows if r["value_status"] == VALUE_STATUS_OBSERVED and r["partner_area_code"] == area_code),
            None,
        )
        if self_row is None:
            raise SystemExit(
                f"検証11失敗: area_code={area_code} direction={direction_ja} の高度急性期+急性期に"
                "自区域行がありません"
                "(known_issues.flow_overall_rate_equals_acute_phase_complementの前提が崩れています)"
            )
        expected = 1 - self_row["rate_value"]
        if overall_rate != expected:
            raise SystemExit(
                f"検証11失敗: area_code={area_code} direction={direction_ja} のoverall_rate"
                f"({overall_rate})が1-acute.self_rate({expected})と一致しません"
                "(known_issues.flow_overall_rate_equals_acute_phase_complementが崩れた可能性があります)"
            )


def validate_area_code_format(rows) -> None:
    """検証12: area_codeが4桁の数字文字列で、上2桁がpref_codeと一致すること。"""
    for r in rows:
        code = r["area_code"]
        if not (len(code) == 4 and code.isdigit()):
            raise SystemExit(f"検証12失敗: area_codeが4桁の数字文字列ではありません: {code!r}")
        if code[:2] != r["pref_code"]:
            raise SystemExit(f"検証12失敗: area_code={code}の上2桁がpref_code={r['pref_code']!r}と一致しません")


def validate_output_materialized(areas, area_codes):
    """検証13: 出力したareasが339件・全てのグループ(2,034)がmaterializeされて
    いること。戻り値: 確認できたグループ数。"""
    if len(areas) != NUM_AREAS:
        raise SystemExit(f"検証13失敗: areasが{NUM_AREAS}件ちょうどではありません(実際{len(areas)}件)")
    codes = [a["area_code"] for a in areas]
    if len(set(codes)) != NUM_AREAS or set(codes) != area_codes:
        raise SystemExit("検証13失敗: areasのarea_code集合が339区域と一致しません")

    group_count = 0
    for a in areas:
        for direction_key in DIRECTIONS:
            flow = a["flows"].get(direction_key)
            if flow is None or "phases" not in flow:
                raise SystemExit(f"検証13失敗: area_code={a['area_code']}にflows.{direction_key}がありません")
            for phase_key in PHASES:
                phase = flow["phases"].get(phase_key)
                if phase is None or set(phase.keys()) != {
                    "self_rate",
                    "self_rank",
                    "partners",
                    "value_error_count",
                }:
                    raise SystemExit(
                        f"検証13失敗: area_code={a['area_code']} direction={direction_key}の"
                        f"phases.{phase_key}の形が想定外です"
                    )
                group_count += 1

    expected_group_count = NUM_AREAS * len(DIRECTIONS) * len(PHASES)
    if group_count != expected_group_count:
        raise SystemExit(
            f"検証13失敗: グループ数が{expected_group_count}件ちょうどではありません(実際{group_count}件)"
        )
    return group_count


def validate_and_index(flow_rows, total_rows, geo_codes):
    """検証1〜12を行い、339区域×2方向×3区分の全2,034グループ(空グループも
    含む)・区域×方向別のoverall_rate・339区域コードの集合を組み立てて返す。

    戻り値: (all_groups, total_by_key, area_codes)
      all_groups: {(area_code, direction_ja, phase_ja): [parsed_row, ...]}
        (parsed_rowはvalidate_value_status_and_parse()が返す辞書。rank未整列)
      total_by_key: {(area_code, direction_ja): overall_rate(float)}
      area_codes: 339件のarea_codeの集合
    """
    validate_published_fy(flow_rows, "patient_flow.csv")
    validate_published_fy(total_rows, "patient_flow_total.csv")

    flow_codes = {r["area_code"] for r in flow_rows}
    total_codes = {r["area_code"] for r in total_rows}
    validate_area_code_sets(flow_codes, total_codes, geo_codes)
    area_codes = set(geo_codes)

    validate_rank_contiguous(flow_rows)
    validate_total_rows_one_per_area_direction(total_rows, area_codes)
    validate_known_direction_and_phase(flow_rows, total_rows)

    parsed_flow_rows = validate_value_status_and_parse(flow_rows)
    validate_partner_membership(parsed_flow_rows, area_codes)

    # 339区域×2方向×3区分=2,034グループを先に用意し、そこへ観測行/エラー行を
    # 積む(原典にデータ行が1行も無いグループも空リストとして必ず存在させる)。
    all_groups = {
        (code, direction_ja, phase_ja): []
        for code in area_codes
        for direction_ja in DIRECTION_LABELS.values()
        for phase_ja in PHASE_LABELS.values()
    }
    for r in parsed_flow_rows:
        all_groups[(r["area_code"], r["direction"], r["phase"])].append(r)

    validate_rate_non_increasing(all_groups)
    validate_no_self_row_groups(all_groups)
    validate_self_rate_bound(all_groups)

    total_by_key = {(r["area_code"], r["direction"]): float(r["overall_rate"]) for r in total_rows}
    validate_overall_rate_matches_acute_complement(total_by_key, all_groups)

    validate_area_code_format(flow_rows)
    validate_area_code_format(total_rows)

    return all_groups, total_by_key, area_codes


def build_areas(all_groups, total_by_key, area_codes):
    """339区域×2方向×3区分の全グループをareas配列へ変換する(area_code昇順)。"""
    areas = []
    for area_code in sorted(area_codes):
        flows = {}
        for direction_key in DIRECTIONS:
            direction_ja = DIRECTION_LABELS[direction_key]
            overall_rate = total_by_key[(area_code, direction_ja)]

            phases_out = {}
            for phase_key in PHASES:
                phase_ja = PHASE_LABELS[phase_key]
                rows = sorted(all_groups[(area_code, direction_ja, phase_ja)], key=lambda r: int(r["rank"]))

                self_rate = None
                self_rank = None
                partners = []
                value_error_count = 0
                for r in rows:
                    if r["value_status"] == VALUE_STATUS_ERROR:
                        value_error_count += 1
                        continue
                    if r["partner_area_code"] == area_code:
                        self_rate = r["rate_value"]
                        self_rank = int(r["rank"])
                    else:
                        partners.append([r["partner_area_code"], r["rate_value"]])

                phases_out[phase_key] = {
                    "self_rate": self_rate,
                    "self_rank": self_rank,
                    "partners": partners,
                    "value_error_count": value_error_count,
                }

            flows[direction_key] = {"overall_rate": overall_rate, "phases": phases_out}

        areas.append({"area_code": area_code, "flows": flows})
    return areas


def build_metadata(flow_meta: dict, total_meta: dict, inputs: list) -> dict:
    flow_source = _select(flow_meta["source"], SOURCE_KEYS)
    total_source = _select(total_meta["source"], SOURCE_KEYS)
    if flow_source != total_source:
        raise SystemExit(
            "patient_flow.csv.meta.json と patient_flow_total.csv.meta.json の"
            "sourceが一致しません(両方とも同一のR7/001723366.xlsxから派生している"
            f"はずです)。flow={flow_source} total={total_source}"
        )

    metadata_source = dict(flow_source)
    metadata_source["derived_via"] = [
        {"csv": "data/processed/patient_flow.csv", "meta": "data/processed/patient_flow.csv.meta.json"},
        {
            "csv": "data/processed/patient_flow_total.csv",
            "meta": "data/processed/patient_flow_total.csv.meta.json",
        },
    ]

    # patient_flow.csvとpatient_flow_total.csvのcaveatは内容が異なる(前者は
    # 「表示分の合計は1にならない・area_basicのoutflow_rate/inflow_rateとは別物」、
    # 後者は「overall_rateは3区分の合計ではない」)ため、入力CSV名をキーにした
    # 辞書として両方をそのまま保持する(build_web_demand.pyと同じ判断)。
    caveat = {
        "patient_flow": flow_meta["processing"]["caveat"],
        "patient_flow_total": total_meta["processing"]["caveat"],
    }

    # 原典側の既知の欠陥は入力CSVのmeta.jsonから拾って集約する(この場で新規に
    # 定義しない)。parse_patient_flow.pyのKNOWN_ISSUESへ1件足せば、キーの有無に
    # 関わらずここを通って表示用データセットと出典欄まで自動で流れる。
    known_issues = list(flow_meta.get("known_issues", [])) + list(total_meta.get("known_issues", []))

    return {
        "title": "構想区域別 患者の流入率・流出率（NDB 2024年度、相手区域別、可視化サイト表示用）",
        "source": metadata_source,
        "processing": {
            "script": "tools/build_web_flow.py",
            "inputs": inputs,
            "steps": [
                "patient_flow.csv・patient_flow_total.csv・area_boundaries_R7.geojson"
                "(area_code集合の一致検証にのみ使用)を読み込み",
                "patient_flow.csv/patient_flow_total.csvの全行がpublished_fy=='R7'"
                "であることを確認(検証1)",
                "(area_code, direction, phase, rank)に重複が無く、各グループの"
                "rankが1から連番であることを確認(検証2)",
                "3ファイルのarea_code集合が完全一致し339件であることを確認(検証3)",
                "各area_code×2方向がちょうど1行ずつpatient_flow_total.csvに"
                "存在することを確認(検証4、339×2=678行)",
                "directionが既知の2種のみ、phaseが既知の3種のみであることを確認"
                "(検証5)",
                "value_statusがobserved/errorの2種のみであり、observed行はrateが"
                "有限の0〜1数値・partner_area_codeが4桁の数字文字列、error行は"
                "rate・partner_area_codeがともに空であることを確認(検証6)",
                "observed行のpartner_area_codeが339区域の集合に含まれることを"
                "確認(検証7)",
                "各グループ内でrank昇順に見たとき率が非増加であることを確認"
                "(検証8)",
                "自区域行が無いグループの集合が実測どおり(流入率×慢性期/"
                "流出率×慢性期の各6区域、計12件)であることを確認(検証9)",
                "自区域行があるグループでself_rate+Σpartners<=1+1e-9であることを"
                "確認(検証10)",
                "overall_rateが「1-(acuteのself_rate)」と厳密一致することを"
                "678件全てで確認(検証11)",
                "area_codeが4桁の数字文字列で、上2桁がpref_codeと一致することを"
                "確認(検証12)",
                "direction/phase(日本語原文)を英字キー(inflow/outflow, "
                "acute/comprehensive/chronic)へ変換し、339区域×2方向×3区分="
                "2,034グループ全てを(データ行が1行も無いグループも含めて)"
                "materializeしてareasを構築(area_code昇順)",
                "出力したareasが339件・全グループ(2,034)がmaterializeされている"
                "ことを確認(検証13)",
            ],
            "caveat": caveat,
        },
        "fields": FIELD_DESCRIPTIONS,
        "known_issues": known_issues,
    }


def dump_json(payload: dict) -> str:
    """`metadata`/`directions`/`direction_labels`/`phases`/`phase_labels`は
    `indent=2`で可読に、`areas`は要素(構想区域)ごとに1行のcompact JSONとして
    直列化する(`tools/build_web_facilities.py`のdump_json()と同じ方針)。
    """
    parts = ["{"]
    for key in ("metadata", "directions", "direction_labels", "phases", "phase_labels"):
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
    """入力2CSV(+境界GeoJSON)を読み込み・検証・変換し、`out_path`へ表示用
    データセットのJSONを書き出す(再現性テストでの再利用のため、出力先を
    引数化している)。

    戻り値: 書き出したファイルのPath。
    """
    flow_rows = _load_csv_rows(PATIENT_FLOW_CSV)
    total_rows = _load_csv_rows(PATIENT_FLOW_TOTAL_CSV)
    geo_codes = _load_geojson_area_codes(AREA_BOUNDARIES_GEOJSON)
    print(
        f"[ok] 入力読み込み: patient_flow.csv={len(flow_rows)}行 "
        f"patient_flow_total.csv={len(total_rows)}行 "
        f"area_boundaries_R7.geojson={len(geo_codes)}区域"
    )

    all_groups, total_by_key, area_codes = validate_and_index(flow_rows, total_rows, geo_codes)
    print(
        "[ok] 検証1〜12: published_fy・rank連番・area_code集合一致(339)・"
        "方向×区域の1行制約(678)・区分/方向の既知性・value_status整合・"
        "相手区域の実在・降順・自区域欠落グループ(12件)・self_rate上限・"
        "overall_rateとの整合・コード整合を確認"
    )

    areas = build_areas(all_groups, total_by_key, area_codes)
    group_count = validate_output_materialized(areas, area_codes)

    partners_total = 0
    no_self_count = 0
    for area in areas:
        for direction_key in DIRECTIONS:
            for phase_key in PHASES:
                phase = area["flows"][direction_key]["phases"][phase_key]
                partners_total += len(phase["partners"])
                if phase["self_rate"] is None:
                    no_self_count += 1
    print(
        f"[ok] areas構築+検証13: {len(areas)}区域 グループ数={group_count} "
        f"partners総要素数={partners_total} 自区域行の無いグループ数={no_self_count}"
    )

    with open(PATIENT_FLOW_META_PATH, "r", encoding="utf-8") as f:
        flow_meta = json.load(f)
    with open(PATIENT_FLOW_TOTAL_META_PATH, "r", encoding="utf-8") as f:
        total_meta = json.load(f)

    inputs = [
        {"path": "data/processed/patient_flow.csv", "sha256": sha256(PATIENT_FLOW_CSV)},
        {"path": "data/processed/patient_flow_total.csv", "sha256": sha256(PATIENT_FLOW_TOTAL_CSV)},
        {
            "path": "data/processed/area_boundaries_R7.geojson",
            "sha256": sha256(AREA_BOUNDARIES_GEOJSON),
        },
    ]
    metadata = build_metadata(flow_meta, total_meta, inputs)

    output = {
        "metadata": metadata,
        "directions": DIRECTIONS,
        "direction_labels": DIRECTION_LABELS,
        "phases": PHASES,
        "phase_labels": PHASE_LABELS,
        "areas": areas,
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = dump_json(output)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    print(f"[ok] 出力: {out_path}")
    print(f"     区域数: {len(areas)} グループ数: {group_count} サイズ: {out_path.stat().st_size:,} bytes")
    print(f"     sha256 = {sha256(out_path)}")

    return out_path


def main() -> None:
    build_and_write(OUT_PATH)


if __name__ == "__main__":
    main()
