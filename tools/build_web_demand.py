# -*- coding: utf-8 -*-
"""可視化サイトが直接読み込む表示用データセット
`data/processed/area_demand_R7.json` を、既にコミット済みの加工CSV
(`demand_forecast.csv`・`demand_population.csv`)と境界GeoJSON
(`area_boundaries_R7.geojson`、area_codeの一致検証にのみ使用しジオメトリは
読まない)から生成する。

M4「医療需要推計 + 年度スライダー」の Chunk B(データ層のみ)。フロントエンド
(`web/`配下)は別チャンクで扱うため、本スクリプトは`web/`配下には一切触れない。
病床指標の正本(`tools/build_web_data.py` / `data/processed/area_indicators_R7.json`)
も別データセットのため一切変更しない。

処理内容:
  1. `demand_forecast.csv`・`demand_population.csv`・`area_boundaries_R7.geojson`
     (area_codeの一致検証にのみ使用)を読み込む
  2. 検証1〜10(下記)を行い、違反があれば SystemExit で中断する(静かに
     握りつぶさない)
  3. 339区域 × 2区分(在宅（訪問診療）・外来) × 6年度について、
     `demand_forecast.csv` の `demand_category`(日本語ラベル)を英字キー
     (home_care/outpatient)へ変換し、`demand.<区分>[<年の文字列>]` へ格納する
  4. `demand_forecast.csv.meta.json` / `demand_population.csv.meta.json` の
     `source` を実行時に読み込んで引き継ぎ、`metadata.source` を構築する
     (出典情報のハードコードによる二重管理を避ける)
  5. UTF-8・LF・`ensure_ascii=False`・indent=2・末尾改行1つで出力する

検証1〜10:
   1. demand_forecast.csv / demand_population.csv の全行が published_fy == 'R7'
   2. (area_code, demand_category, year) に重複がない
   3. demand_forecast.csv / demand_population.csv / area_boundaries_R7.geojson の
      area_code集合が3つとも完全一致し、要素数がちょうど339
   4. 各area_code×2区分×6年度がちょうど1行ずつ存在する(計 339×2×6 = 4,068)
   5. demand_categoryが既知の2種のみ、yearが既知の6種のみ。year_labelが
      同じyearに対して全行で一貫している(カテゴリ・区域を跨いでも同じ文字列)
   6. receipts_per_monthが全て有限の数値かつ0より大きい(CLAUDE.md「センチネル
      値の罠」。float('nan')・infも弾く)
   7. 基準年(2024)の値が全area×categoryに存在し0でない(検証4で存在は保証
      済みなので、ここでは0でないことのみ確認する。フロント側の2024年度比の
      分母として使うため、ここで担保して表示側の0除算・null分岐を不要にする)
   8. area_codeが4桁の数字文字列で、上2桁がpref_codeと一致する
   9. area_name / pref_nameが2つのCSVの間で一致する
  10. population_2024 / population_2040が正の整数

出力の `demand.<category>` は年をキーとするオブジェクトで、そのキーは
(JSONのオブジェクトキーは文字列のため)西暦4桁の**文字列**である一方、
トップレベルの `years` は整数の配列である。この非対称は `fields` に明記する。

変化率(2024年度比)は出力しない。値のみを出し、比の算出はフロントエンド側で
行う(既存の `web/scripts/sync-data.mjs` が病床指標側で `r_<機能>` をJS側で
算出しているのと同じ分担)。値はCSVの文字列を `float()` したものをそのまま
出す(丸め・整形はしない)。

生成日時は埋め込まない(CLAUDE.md参照。再現性テストが翌日に壊れるため)。

必要環境: Python 3.11+

使い方:
    PYTHONIOENCODING=utf-8 python tools/build_web_demand.py
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

DEMAND_FORECAST_CSV = REPO_ROOT / "data" / "processed" / "demand_forecast.csv"
DEMAND_POPULATION_CSV = REPO_ROOT / "data" / "processed" / "demand_population.csv"
AREA_BOUNDARIES_GEOJSON = REPO_ROOT / "data" / "processed" / "area_boundaries_R7.geojson"
OUT_PATH = REPO_ROOT / "data" / "processed" / "area_demand_R7.json"

DEMAND_FORECAST_META_PATH = Path(str(DEMAND_FORECAST_CSV) + ".meta.json")
DEMAND_POPULATION_META_PATH = Path(str(DEMAND_POPULATION_CSV) + ".meta.json")

CATEGORIES = ["home_care", "outpatient"]
CATEGORY_LABELS = {
    "home_care": "在宅（訪問診療）",
    "outpatient": "外来",
}
# demand_forecast.csv の demand_category は日本語ラベルで格納されている
# (tools/parse_demand_forecast.py の DEMAND_CATEGORY_HOME_CARE/OUTPATIENT
# 参照)。出力スキーマの英字キーへ変換するための逆引き。
DEMAND_CATEGORY_KEY_BY_JA = {ja: key for key, ja in CATEGORY_LABELS.items()}

YEARS = [2024, 2030, 2035, 2040, 2045, 2050]
BASELINE_YEAR = 2024

# メタデータへ引き継ぐ demand_forecast.csv.meta.json / demand_population.csv.meta.json
# の source ブロックのキー。両ファイルとも同一のR7/001728462.xlsxから派生して
# いるため値は一致するはず(main()で照合する)。
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
    "categories": "需要区分の英字キー一覧(表示順)。home_care=在宅（訪問診療）、outpatient=外来",
    "category_labels": "区分キー -> 日本語ラベルの対応(表示用)",
    "years": (
        "対象年(西暦4桁の整数)の配列。areas[].demand.<category>とyear_labelsの"
        "キーは年の**文字列**である点に注意(JSONのオブジェクトキーは文字列のため)"
    ),
    "year_labels": (
        "年の文字列 -> 年度ラベル原文の対応(demand_forecast.csvのyear_labelを"
        "そのまま引き継ぐ)。2024年度のみ「現状投影」が付かず、2030年度以降は"
        "いずれも「現状投影」が付く(原典の区別、fields.receipts_per_month参照)"
    ),
    "baseline_year": (
        "変化率算出の基準年(2024)。areas[].demand.<category>['2024']が"
        "全area×categoryで0でないことをビルド時に検証済み(検証7)"
    ),
    "area_code": "構想区域コード(ゼロ埋め4桁の文字列)",
    "area_name": "構想区域名",
    "pref_code": "都道府県コード(ゼロ埋め2桁の文字列)",
    "pref_name": "都道府県名",
    "population_2024": "2024年度人口(人単位の整数、demand_population.csvのpopulation_2024をそのまま)",
    "population_2040": (
        "2040年人口(人単位の整数、demand_population.csvのpopulation_2040をそのまま。"
        "原典の見出しが「年度」表記のpopulation_2024と「年」表記で混在している点に留意)"
    ),
    "demand": (
        "区分キー(home_care/outpatient) -> {年の文字列(years参照): receipts_per_month}"
        "の対応"
    ),
    "demand.<category>.<year>": (
        "レセプト件数/月(demand_forecast.csvのreceipts_per_monthをそのまま。丸め・"
        "整形はしない)。患者数・人数そのものではない点に留意。年度は2024年度のみ"
        "実績相当で、2030〜2050年度はいずれも「現状投影」(year_labels参照)。"
        "変化率(2024年度比)はこのファイルには含まれず、表示側で算出する"
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


def validate_and_index(forecast_rows, population_rows, geo_codes):
    """検証1〜10を行い、違反があれば SystemExit で中断する。

    戻り値: (demand_by_key, year_label_by_year, population_by_code)
      demand_by_key: {(area_code, demand_category_ja, year(int)): receipts_per_month(float)}
      year_label_by_year: {year(int): year_label(str)}
      population_by_code: {area_code: row(dict)}
    """
    # 検証1: published_fy が全て R7(両CSV)
    bad_fy_forecast = sorted({r["published_fy"] for r in forecast_rows} - {"R7"})
    if bad_fy_forecast:
        raise SystemExit(f"検証1失敗: demand_forecast.csvにR7以外のpublished_fyがあります: {bad_fy_forecast}")
    bad_fy_population = sorted({r["published_fy"] for r in population_rows} - {"R7"})
    if bad_fy_population:
        raise SystemExit(f"検証1失敗: demand_population.csvにR7以外のpublished_fyがあります: {bad_fy_population}")

    # 検証2: (area_code, demand_category, year) の重複なし
    key_counts = Counter((r["area_code"], r["demand_category"], r["year"]) for r in forecast_rows)
    dup = sorted(k for k, n in key_counts.items() if n > 1)
    if dup:
        raise SystemExit(f"検証2失敗: (area_code,demand_category,year)が重複しています: {dup[:20]}")

    # 検証3: 3ファイルのarea_code集合が完全一致し339件
    forecast_codes = {r["area_code"] for r in forecast_rows}
    population_codes = {r["area_code"] for r in population_rows}
    sets = {
        "demand_forecast.csv": forecast_codes,
        "demand_population.csv": population_codes,
        "area_boundaries_R7.geojson": geo_codes,
    }
    all_codes = set().union(*sets.values())
    if not (forecast_codes == population_codes == geo_codes) or len(forecast_codes) != 339:
        missing = {name: sorted(all_codes - codes) for name, codes in sets.items()}
        raise SystemExit(
            "検証3失敗: area_codeの集合が3ファイルで一致しないか339件ではありません。"
            f"件数: demand_forecast.csv={len(forecast_codes)} "
            f"demand_population.csv={len(population_codes)} "
            f"area_boundaries_R7.geojson={len(geo_codes)}。各ファイルに無いコード: {missing}"
        )

    # 検証4: 各area_code×2区分×6年度がちょうど1行ずつ存在する(計339×2×6=4068)
    expected_triples = {
        (code, ja, year) for code in forecast_codes for ja in DEMAND_CATEGORY_KEY_BY_JA for year in YEARS
    }
    actual_triples = set()
    for r in forecast_rows:
        try:
            year = int(r["year"])
        except (TypeError, ValueError):
            raise SystemExit(f"検証4失敗: yearが整数として解釈できません: {r}")
        actual_triples.add((r["area_code"], r["demand_category"], year))
    if len(forecast_rows) != len(expected_triples) or actual_triples != expected_triples:
        raise SystemExit(
            "検証4失敗: area_code×区分×年度が339×2×6="
            f"{len(expected_triples)}件ちょうどではありません(実際{len(forecast_rows)}件)。"
            f"不足={sorted(expected_triples - actual_triples)[:10]} "
            f"余剰={sorted(actual_triples - expected_triples)[:10]}"
        )

    # 検証5: demand_categoryが既知の2種のみ、yearが既知の6種のみ。year_labelが
    # 同じyearに対して全行で一貫している(カテゴリ・区域を跨いでも同じ文字列)
    bad_categories = sorted({r["demand_category"] for r in forecast_rows} - set(DEMAND_CATEGORY_KEY_BY_JA))
    if bad_categories:
        raise SystemExit(f"検証5失敗: 未知のdemand_categoryがあります: {bad_categories}")
    year_label_by_year = {}
    for r in forecast_rows:
        year = int(r["year"])
        if year not in YEARS:
            raise SystemExit(f"検証5失敗: 未知のyearがあります: {year}")
        label = r["year_label"]
        if year in year_label_by_year and year_label_by_year[year] != label:
            raise SystemExit(
                f"検証5失敗: year={year}のyear_labelが行によって揺れています: "
                f"{year_label_by_year[year]!r} != {label!r}"
            )
        year_label_by_year[year] = label
    missing_years = sorted(set(YEARS) - set(year_label_by_year))
    if missing_years:
        raise SystemExit(f"検証5失敗: year_labelが1件も無いyearがあります: {missing_years}")

    # 検証6: receipts_per_monthが全て有限の数値かつ0より大きい(CLAUDE.md
    # 「センチネル値の罠」。'XXX'等の非数値混入やnan/infを静かに通さない)
    demand_by_key = {}
    for r in forecast_rows:
        try:
            value = float(r["receipts_per_month"])
        except (TypeError, ValueError):
            raise SystemExit(f"検証6失敗: receipts_per_monthが数値として解釈できません: {r}")
        if not math.isfinite(value) or not (value > 0):
            raise SystemExit(f"検証6失敗: receipts_per_monthが有限の正の数値ではありません: {r}")
        demand_by_key[(r["area_code"], r["demand_category"], int(r["year"]))] = value

    # 検証7: 基準年(2024)の値が全area×categoryに存在し0でない(検証4で存在は
    # 保証済みなので、ここでは0でないことのみ確認する)
    for code in forecast_codes:
        for ja in DEMAND_CATEGORY_KEY_BY_JA:
            value = demand_by_key[(code, ja, BASELINE_YEAR)]
            if value == 0:
                raise SystemExit(
                    f"検証7失敗: area_code={code} demand_category={ja} の基準年"
                    f"({BASELINE_YEAR})の値が0です(表示側の2024年度比の分母に使えません)"
                )

    # 検証8: area_codeが4桁の数字文字列、上2桁がpref_codeと一致
    population_by_code = {}
    for r in population_rows:
        code = r["area_code"]
        if not (len(code) == 4 and code.isdigit()):
            raise SystemExit(f"検証8失敗: area_codeが4桁の数字文字列ではありません: {code!r}")
        if code[:2] != r["pref_code"]:
            raise SystemExit(
                f"検証8失敗: area_code={code}の上2桁がpref_code={r['pref_code']!r}と一致しません"
            )
        population_by_code[code] = r

    # 検証9: area_name / pref_nameがdemand_forecast.csvとdemand_population.csvの間で一致
    forecast_names = {}
    for r in forecast_rows:
        key = r["area_code"]
        val = (r["area_name"], r["pref_code"], r["pref_name"])
        if key in forecast_names and forecast_names[key] != val:
            raise SystemExit(
                f"検証9失敗: demand_forecast.csv内でarea_code={key}のarea_name/pref_nameが"
                f"行によって揺れています: {forecast_names[key]} != {val}"
            )
        forecast_names[key] = val
    for code, val in forecast_names.items():
        population_row = population_by_code[code]
        population_val = (
            population_row["area_name"],
            population_row["pref_code"],
            population_row["pref_name"],
        )
        if val != population_val:
            raise SystemExit(
                f"検証9失敗: area_code={code}のarea_name/pref_nameがdemand_forecast.csv{val}と"
                f"demand_population.csv{population_val}で不一致です"
            )

    # 検証10: population_2024 / population_2040が正の整数
    for r in population_rows:
        for field_name in ("population_2024", "population_2040"):
            raw = r[field_name]
            try:
                value = int(raw)
            except (TypeError, ValueError):
                raise SystemExit(f"検証10失敗: {field_name}が整数として解釈できません: {r}")
            if value != float(raw) or value <= 0:
                raise SystemExit(f"検証10失敗: {field_name}が正の整数ではありません: {r}")

    return demand_by_key, year_label_by_year, population_by_code


def build_areas(demand_by_key, population_by_code):
    areas = []
    for area_code in sorted(population_by_code):
        population_row = population_by_code[area_code]

        demand = {}
        for category_key in CATEGORIES:
            ja = CATEGORY_LABELS[category_key]
            demand[category_key] = {
                str(year): demand_by_key[(area_code, ja, year)] for year in YEARS
            }

        area = {
            "area_code": area_code,
            "area_name": population_row["area_name"],
            "pref_code": population_row["pref_code"],
            "pref_name": population_row["pref_name"],
            "population_2024": int(population_row["population_2024"]),
            "population_2040": int(population_row["population_2040"]),
            "demand": demand,
        }
        areas.append(area)
    return areas


def build_metadata(forecast_meta: dict, population_meta: dict, inputs: list) -> dict:
    forecast_source = _select(forecast_meta["source"], SOURCE_KEYS)
    population_source = _select(population_meta["source"], SOURCE_KEYS)
    if forecast_source != population_source:
        raise SystemExit(
            "demand_forecast.csv.meta.json と demand_population.csv.meta.json の"
            "sourceが一致しません(両方とも同一のR7/001728462.xlsxから派生している"
            f"はずです)。forecast={forecast_source} population={population_source}"
        )

    metadata_source = dict(forecast_source)
    metadata_source["derived_via"] = [
        {
            "csv": "data/processed/demand_forecast.csv",
            "meta": "data/processed/demand_forecast.csv.meta.json",
        },
        {
            "csv": "data/processed/demand_population.csv",
            "meta": "data/processed/demand_population.csv.meta.json",
        },
    ]

    # demand_forecast.csv と demand_population.csv の caveat は内容が異なる
    # (前者は「receipts_per_monthは患者数ではない・2024年度以外は現状投影」、
    # 後者は「population_2024/population_2040の年度/年表記が原典の見出しで
    # 混在している」)。どちらか一方を選ぶと他方の注記が失われるため、
    # 入力CSV名をキーにした辞書として両方をそのまま保持する。
    caveat = {
        "demand_forecast": forecast_meta["processing"]["caveat"],
        "demand_population": population_meta["processing"]["caveat"],
    }

    return {
        "title": (
            "構想区域別 医療需要推計（在宅（訪問診療）・外来のレセプト件数/月、"
            "2024〜2050年度、可視化サイト表示用）"
        ),
        "source": metadata_source,
        "processing": {
            "script": "tools/build_web_demand.py",
            "inputs": inputs,
            "steps": [
                "demand_forecast.csv・demand_population.csv・"
                "area_boundaries_R7.geojsonを読み込み",
                "demand_forecast.csv/demand_population.csvの全行が"
                "published_fy=='R7'であることを確認(検証1)",
                "(area_code, demand_category, year)の重複がないことを確認(検証2)",
                "3ファイルのarea_code集合が完全一致し339件であることを確認(検証3)",
                "各area_code×2区分×6年度がちょうど1行ずつ存在することを確認"
                "(検証4、339×2×6=4068セル)",
                "demand_categoryが既知の2種のみ、yearが既知の6種のみであり、"
                "year_labelが同じyearに対して全行で一貫していることを確認(検証5)",
                "receipts_per_monthが全て有限の正の数値であることを確認(検証6)",
                "基準年(2024)の値が全area×区分に存在し0でないことを確認"
                "(検証7。表示側の2024年度比の分母として使うため)",
                "area_codeが4桁の数字文字列で、上2桁がpref_codeと一致することを"
                "確認(検証8)",
                "area_name/pref_nameがdemand_forecast.csvとdemand_population.csvの"
                "間で一致することを確認(検証9)",
                "population_2024/population_2040が正の整数であることを確認(検証10)",
                "demand_category(在宅（訪問診療）/外来)を英字キー"
                "(home_care/outpatient)へ変換し、demand.<区分>[<年の文字列>]へ格納",
                "area_codeの昇順(文字列ソート)でareasを整列",
            ],
            "caveat": caveat,
        },
        "fields": FIELD_DESCRIPTIONS,
    }


def build_and_write(out_path: Path) -> Path:
    """入力3ファイルを読み込み・検証・変換し、`out_path`へ表示用データセットの
    JSONを書き出す(再現性テストでの再利用のため、出力先を引数化している)。

    戻り値: 書き出したファイルのPath。
    """
    forecast_rows = _load_csv_rows(DEMAND_FORECAST_CSV)
    population_rows = _load_csv_rows(DEMAND_POPULATION_CSV)
    geo_codes = _load_geojson_area_codes(AREA_BOUNDARIES_GEOJSON)
    print(
        f"[ok] 入力読み込み: demand_forecast.csv={len(forecast_rows)}行 "
        f"demand_population.csv={len(population_rows)}行 "
        f"area_boundaries_R7.geojson={len(geo_codes)}区域"
    )

    demand_by_key, year_label_by_year, population_by_code = validate_and_index(
        forecast_rows, population_rows, geo_codes
    )
    print(
        "[ok] 検証1〜10: published_fy・重複なし・area_code集合一致(339)・"
        "区域×区分×年度の存在(4068)・区分/年の既知性・数値妥当性・基準年非ゼロ・"
        "コード整合・名称整合・人口整合を確認"
    )

    areas = build_areas(demand_by_key, population_by_code)
    print(f"[ok] areas構築: {len(areas)}区域")

    with open(DEMAND_FORECAST_META_PATH, "r", encoding="utf-8") as f:
        forecast_meta = json.load(f)
    with open(DEMAND_POPULATION_META_PATH, "r", encoding="utf-8") as f:
        population_meta = json.load(f)

    inputs = [
        {"path": "data/processed/demand_forecast.csv", "sha256": sha256(DEMAND_FORECAST_CSV)},
        {"path": "data/processed/demand_population.csv", "sha256": sha256(DEMAND_POPULATION_CSV)},
        {
            "path": "data/processed/area_boundaries_R7.geojson",
            "sha256": sha256(AREA_BOUNDARIES_GEOJSON),
        },
    ]
    metadata = build_metadata(forecast_meta, population_meta, inputs)

    output = {
        "metadata": metadata,
        "categories": CATEGORIES,
        "category_labels": CATEGORY_LABELS,
        "years": YEARS,
        "year_labels": {str(year): year_label_by_year[year] for year in YEARS},
        "baseline_year": BASELINE_YEAR,
        "areas": areas,
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[ok] 出力: {out_path}")
    print(f"     区域数: {len(areas)}")
    print(f"     サイズ: {out_path.stat().st_size:,} bytes")
    print(f"     sha256 = {sha256(out_path)}")

    return out_path


def main() -> None:
    build_and_write(OUT_PATH)


if __name__ == "__main__":
    main()
