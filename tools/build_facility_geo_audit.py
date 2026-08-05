"""既に付与済みの医療機関座標(P04由来)を、医療情報ネットの公表座標で検算する。

## このスクリプトが答える問い

`tools/build_facility_geo_linkage.py` は `ksj/P04-20`(国土数値情報 医療機関データ、
**令和2年度**)との名寄せで11,760施設中10,244件に座標を与えている。原典の医療機関個票
(`R7/001723127.xlsx`)は**令和7年度**公表で、両者には5年の開きがある。名称が一致しても
その間に移転していれば、**採用した座標は旧所在地を指したままになる**(名寄せは名称の
同一性しか見ておらず、位置の正しさは検証していない)。

そこで、厚労省が別途公表している医療情報ネット(医療機能情報提供制度)の
**公表座標**を参照として、付与済み座標との距離を実測する。

## このスクリプトがやらないこと

**参照側の座標を採用しない。** 出力は監査結果(距離と分類)だけで、
`facility_geo_linkage.csv` の座標は書き換えない。医療情報ネットを座標源として
統合するかは未決で、判断材料と決定の記録は `doc/DECISION_FACILITY_COORDINATES.md`
にある(`doc/REQUIREMENTS.md` §4.3「位置の推測はしない」との関係を含む)。

副産物として、**現在座標が無い1,516件に参照が存在するか**も同じ規則で判定して
出力する(統合を検討する場合の材料。こちらも座標は採らない)。

出力:
- `data/processed/facility_geo_audit.csv`(+ `.meta.json`)
- `doc/FACILITY_GEO_AUDIT.md`
"""

from __future__ import annotations

import csv
import datetime
import io
import math
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.build_facility_geo_linkage import (  # noqa: E402
    AreaIndex,
    address_matches_municipality,
    normalize_facility_name,
)
from tools.lib.provenance import REPO_ROOT, sha256, verify_source, write_csv_with_meta  # noqa: E402

PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DOC_DIR = REPO_ROOT / "doc"

HOSPITAL_ZIP_PATH_IN_REPO = "iryojoho/01-1_hospital_facility_info_20250601.zip"
CLINIC_ZIP_PATH_IN_REPO = "iryojoho/02-1_clinic_facility_info_20250601.zip"

LINKAGE_CSV = PROCESSED_DIR / "facility_geo_linkage.csv"
FACILITY_BASIC_CSV = PROCESSED_DIR / "facility_basic.csv"
AREA_BOUNDARIES_PATH = PROCESSED_DIR / "area_boundaries_R7.geojson"

SOURCE_PAGE = (
    "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iryou/newpage_43373.html"
)
SNAPSHOT_DATE = "2025-06-01"

# --- 参照データ側の列名(定義書 iryojoho/001306376.xlsx の見出しそのまま) ---
COL_ID = "ID"
COL_NAME = "正式名称"
COL_PREF_CODE = "都道府県コード"
COL_ADDRESS = "所在地"
COL_LAT = "所在地座標（緯度）"
COL_LON = "所在地座標（経度）"

# 日本の領域。医療情報ネットの座標欠測センチネルは空欄ではなく `0.0`/`0.0` で、
# 実測4,456件(5.4%)が該当する。範囲判定にしないと静かにギニア湾沖の点を採る。
LAT_MIN, LAT_MAX = 20.0, 46.0
LON_MIN, LON_MAX = 122.0, 154.0

# 距離の区分。実測の分布(中央値13m・90%点65m・99%点977m)から決めている:
# - 100m: 90%点の65mに余裕を持たせた値。同一敷地・同一住所と読める一致。
# - 1,000m: 99%点の977mにほぼ一致。住所表記の粒度の差やジオコーディング誤差では
#   説明しにくく、「2つの公表物が別の場所を指している」と読むべき水準。
AGREE_MAX_M = 100.0
CONFLICT_MIN_M = 1000.0

AUDIT_AGREE = "agree"
AUDIT_MINOR_GAP = "minor_gap"
AUDIT_CONFLICT = "conflict"
AUDIT_NO_REFERENCE = "no_reference"
AUDIT_MISSING_WITH_REFERENCE = "missing_with_reference"
AUDIT_MISSING_WITHOUT_REFERENCE = "missing_without_reference"

AUDIT_LABELS = {
    AUDIT_AGREE: f"付与済み座標と参照座標が{AGREE_MAX_M:.0f}m未満で一致",
    AUDIT_MINOR_GAP: f"{AGREE_MAX_M:.0f}m以上{CONFLICT_MIN_M:.0f}m未満の差",
    AUDIT_CONFLICT: f"{CONFLICT_MIN_M:.0f}m以上離れている(付与済み座標が疑わしい)",
    AUDIT_NO_REFERENCE: "座標は付与済みだが、参照側で一意に確認できず検算できない",
    AUDIT_MISSING_WITH_REFERENCE: "座標が無く、参照側には一意の公表座標がある",
    AUDIT_MISSING_WITHOUT_REFERENCE: "座標が無く、参照側でも一意に確認できない",
}

REF_UNIQUE = "unique"
REF_UNIQUE_MUNICIPALITY_UNVERIFIED = "unique_municipality_unverified"
REF_MUNICIPALITY_MISMATCH = "municipality_mismatch"
REF_AMBIGUOUS = "ambiguous"
REF_NONE = "none"

REF_LABELS = {
    REF_UNIQUE: "同一都道府県内で正規化名が完全一致し市区町村も整合する参照が1件",
    REF_UNIQUE_MUNICIPALITY_UNVERIFIED: (
        "参照は1件だが、原典側の所在地欄が空(病床機能報告が未報告)のため市区町村を検証できない"
    ),
    REF_MUNICIPALITY_MISMATCH: "名称一致の参照はあるが市区町村が整合しない",
    REF_AMBIGUOUS: "名称一致の参照が複数あり一意に絞れない",
    REF_NONE: "同一都道府県内に正規化名が完全一致する参照が無い",
}

OUTPUT_HEADER = [
    "record_id",
    "pref_code",
    "pref_name",
    "area_code",
    "area_name",
    "facility_name",
    "municipality",
    "linkage_match_status",
    "linkage_match_method",
    "current_longitude",
    "current_latitude",
    "reference_status",
    "reference_kind",
    "reference_id",
    "reference_name",
    "reference_address",
    "reference_longitude",
    "reference_latitude",
    "reference_area_code",
    "distance_m",
    "audit_status",
]

FIELDS_AUDIT = {
    "record_id": "医療機関の識別子(facility_basic.csvと同じ。R7-<区域コード>-<原典行番号>。恒久IDではない)",
    "pref_code": "都道府県コード(ゼロ埋め2桁)",
    "pref_name": "都道府県名",
    "area_code": "構想区域コード(ゼロ埋め4桁)",
    "area_name": "構想区域名",
    "facility_name": "医療機関名(原典表記のまま)",
    "municipality": "所在地の市区町村(原典表記のまま。病床機能報告が未報告の施設は空)",
    "linkage_match_status": "facility_geo_linkage.csvのmatch_status(matched/candidate_only/unmatched)",
    "linkage_match_method": "同 match_method(normalized_exact/normalized_suffix/空)",
    "current_longitude": "現在この可視化サイトが使っている経度(P04由来。座標が無い施設は空)",
    "current_latitude": "同 緯度",
    "reference_status": "参照(医療情報ネット)側の同定結果。" + " / ".join(f"{k}={v}" for k, v in REF_LABELS.items()),
    "reference_kind": "参照側の区分(病院/診療所)。同定できなかった場合は空",
    "reference_id": "参照側のID(医療情報ネットのID。恒久IDではない)",
    "reference_name": "参照側の正式名称",
    "reference_address": "参照側の所在地(都道府県名から始まる完全な住所)",
    "reference_longitude": "参照側の公表経度",
    "reference_latitude": "参照側の公表緯度",
    "reference_area_code": "参照座標が落ちる構想区域コード(area_boundaries_R7.geojsonでの点-多角形判定。どの区域にも属さない場合は空)",
    "distance_m": "現在の座標と参照座標の距離(メートル、小数1桁。どちらかが無い場合は空)",
    "audit_status": "監査結果。" + " / ".join(f"{k}={v}" for k, v in AUDIT_LABELS.items()),
}

CAVEAT = (
    "参照した医療情報ネットの座標は厚労省の公表値だが、出典ページ自身が「最新でない情報や"
    "報告誤りの可能性」を明記している。したがって distance_m が大きいことは「付与済み座標が"
    "誤っている」ことの証明ではなく、「2つの公表物が異なる位置を示している」ことの記録である。"
    "また参照側の座標欠測は空欄ではなく 0.0/0.0 で表現されるため、日本の緯度経度の範囲内かで"
    "判定して除外している。"
)

EARTH_RADIUS_M = 6371008.8


def known_issues_for(rows) -> list[dict]:
    """原典側(外部の公表物どうし)の矛盾を構造化して記録する。

    件数は実測から組み立てる(固定値を書くと、入力を差し替えたときに
    記述だけが古くなる)。
    """
    conflicts = [r for r in rows if r.audit_status == AUDIT_CONFLICT]
    if not conflicts:
        return []
    distances = sorted((r.distance_m for r in conflicts), reverse=True)
    checked = sum(1 for r in rows if r.distance_m is not None)
    cross_area = sum(1 for r in conflicts if r.reference_area_code != r.facility["area_code"])
    return [
        {
            "id": "facility_coordinate_conflicts_with_published_reference",
            "scope": {
                "csv": "facility_geo_audit.csv",
                "columns": ["distance_m", "audit_status"],
                "audit_status": AUDIT_CONFLICT,
            },
            "summary": (
                f"医療機関{len(conflicts)}件で、国土数値情報P04-20(令和2年度)由来の付与済み座標と、"
                f"医療情報ネット({SNAPSHOT_DATE}時点)の公表座標が{CONFLICT_MIN_M:.0f}m以上離れている。"
                "厚労省の2つの公表物が同一名称の医療機関について異なる位置を示している状態で、"
                "どちらが正しいかは公表物からは決められない。"
            ),
            "evidence": [
                f"検算できた{checked}件のうち{len(conflicts)}件が{CONFLICT_MIN_M:.0f}m以上離れている"
                f"(最大{distances[0]:,.0f}m、次点{distances[1]:,.0f}m)",
                f"{len(conflicts)}件のうち参照座標が原典の言う構想区域の外に落ちるものは{cross_area}件",
                "住所を突き合わせると、両者が実質同一の住所を指しているのに座標だけが数km離れている例が"
                "複数ある(例: 産科・婦人科久米クリニックは双方とも「いちき串木野市曙町」だが座標は約32km離れている)。"
                "この場合は移転ではなく、いずれかの座標そのものが誤っている",
                "一方で住所自体が異なる例もある(例: 峯苫医院はP04「八代市坂本町坂本」対 参照「八代市渡町」)。"
                "令和2年度と2025年の5年間の移転と解釈できる",
            ],
            "action": (
                "値は補正しない(参照側の座標を採用することは、座標源の統合という未決の要件変更に当たる。"
                "doc/DECISION_FACILITY_COORDINATES.md 参照)。一方で、検算で否定された座標を地図に出し続けることは"
                "「誤った位置に医療機関が表示される」ことを意味するため、表示用データセット"
                "(area_facilities_R7.json)ではこの該当施設の座標を出力せず、一覧には"
                "「地図に表示なし」として全項目とともに残す。監査の全記録はfacility_geo_audit.csvにある"
            ),
        }
    ]


# ===========================================================================
# 1. 参照データ(医療情報ネット)の読み込み
# ===========================================================================


@dataclass(frozen=True)
class ReferencePoint:
    facility_id: str
    kind: str  # 病院 / 診療所
    name: str
    name_normalized: str
    pref_code: str
    address: str
    lon: float
    lat: float


def _read_single_member_csv(zip_path: Path) -> list[dict]:
    """zip内のCSV1本をUTF-8(BOM付き)として読む。

    zipのエントリ名は言語エンコーディングフラグ(0x800)を見て復号を分岐する
    (CLAUDE.md 罠34と同じ理由。無条件にcp437→cp932変換するとUTF-8フラグ付きで壊れる)。
    """
    with zipfile.ZipFile(zip_path) as z:
        members = [i for i in z.infolist() if not i.is_dir()]
        if len(members) != 1:
            raise SystemExit(f"{zip_path.name}: zip内のファイルが1本ではありません({len(members)}本)")
        raw = z.read(members[0].filename)
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


def _usable_coordinate(row: dict):
    """緯度経度を返す。センチネル(0.0/0.0)・数値でない・日本の範囲外はNoneを返す。"""
    lat_raw = (row.get(COL_LAT) or "").strip()
    lon_raw = (row.get(COL_LON) or "").strip()
    if not lat_raw or not lon_raw:
        return None
    try:
        lat = float(lat_raw)
        lon = float(lon_raw)
    except ValueError:
        return None
    if not (LAT_MIN < lat < LAT_MAX and LON_MIN < lon < LON_MAX):
        return None
    return lon, lat


def load_reference_points(hospital_zip: Path, clinic_zip: Path):
    """医療情報ネットの病院票・診療所票を読み、座標が使えるものだけを返す。

    戻り値は (points, stats)。statsは読み込み件数とセンチネル件数(レポート用)。
    """
    points: list[ReferencePoint] = []
    stats = {}
    for kind, path in (("病院", hospital_zip), ("診療所", clinic_zip)):
        rows = _read_single_member_csv(path)
        for col in (COL_ID, COL_NAME, COL_PREF_CODE, COL_ADDRESS, COL_LAT, COL_LON):
            if col not in rows[0]:
                raise SystemExit(f"{path.name}: 期待した列 {col!r} がありません(原典のレイアウト変更)")
        usable = 0
        for row in rows:
            coord = _usable_coordinate(row)
            if coord is None:
                continue
            usable += 1
            points.append(
                ReferencePoint(
                    facility_id=row[COL_ID].strip(),
                    kind=kind,
                    name=row[COL_NAME].strip(),
                    name_normalized=normalize_facility_name(row[COL_NAME]),
                    pref_code=row[COL_PREF_CODE].strip(),
                    address=row[COL_ADDRESS].strip(),
                    lon=coord[0],
                    lat=coord[1],
                )
            )
        stats[kind] = {"total": len(rows), "usable": usable, "sentinel": len(rows) - usable}
    return points, stats


def index_reference_points(points):
    """(都道府県コード, 正規化名) → 参照点のリスト。"""
    index = defaultdict(list)
    for p in points:
        index[(p.pref_code, p.name_normalized)].append(p)
    return dict(index)


# ===========================================================================
# 2. 距離
# ===========================================================================


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """2点間の大円距離(メートル)。"""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


# ===========================================================================
# 3. 監査
# ===========================================================================


def _resolve_reference(facility: dict, linkage: dict, reference_index: dict):
    """1施設について参照を同定する。戻り値は (reference_status, ReferencePoint|None)。

    採用条件は名寄せ本体(build_facility_geo_linkage.py)と同じ保守性で揃える:
    同一都道府県内で正規化名が完全一致し、市区町村も整合し、候補が1件だけ。
    参照側は都道府県コードを列として持っているため、P04で必要だった
    点-多角形判定による都道府県の切り分け(同名市区町村対策)は要らない。
    """
    normalized = linkage.get("facility_name_normalized") or normalize_facility_name(
        facility["facility_name"]
    )
    candidates = reference_index.get((facility["pref_code"], normalized), [])
    if not candidates:
        return REF_NONE, None

    municipality = (facility.get("municipality") or "").strip()
    if not municipality:
        # 病床機能報告が未報告の施設は原典の所在地欄が空で、市区町村を検証できない。
        # 名称と都道府県だけで一意でも「検証できていない」ことを状態として残す。
        if len(candidates) == 1:
            return REF_UNIQUE_MUNICIPALITY_UNVERIFIED, candidates[0]
        return REF_AMBIGUOUS, None

    consistent = [c for c in candidates if address_matches_municipality(c.address, municipality)]
    if len(consistent) == 1:
        return REF_UNIQUE, consistent[0]
    if len(consistent) > 1:
        return REF_AMBIGUOUS, None
    return REF_MUNICIPALITY_MISMATCH, None


def _audit_status(has_coordinate: bool, reference, distance_m):
    if has_coordinate:
        if reference is None:
            return AUDIT_NO_REFERENCE
        if distance_m < AGREE_MAX_M:
            return AUDIT_AGREE
        if distance_m < CONFLICT_MIN_M:
            return AUDIT_MINOR_GAP
        return AUDIT_CONFLICT
    return AUDIT_MISSING_WITH_REFERENCE if reference is not None else AUDIT_MISSING_WITHOUT_REFERENCE


@dataclass
class AuditRow:
    facility: dict
    linkage: dict
    reference_status: str
    reference: object  # ReferencePoint | None
    reference_area_code: object  # str | None
    distance_m: object  # float | None
    audit_status: str

    def to_output(self) -> dict:
        f = self.facility
        lk = self.linkage
        ref = self.reference
        return {
            "record_id": f["record_id"],
            "pref_code": f["pref_code"],
            "pref_name": f["pref_name"],
            "area_code": f["area_code"],
            "area_name": f["area_name"],
            "facility_name": f["facility_name"],
            "municipality": f.get("municipality", ""),
            "linkage_match_status": lk.get("match_status", ""),
            "linkage_match_method": lk.get("match_method", ""),
            "current_longitude": lk.get("longitude", ""),
            "current_latitude": lk.get("latitude", ""),
            "reference_status": self.reference_status,
            "reference_kind": ref.kind if ref else "",
            "reference_id": ref.facility_id if ref else "",
            "reference_name": ref.name if ref else "",
            "reference_address": ref.address if ref else "",
            "reference_longitude": f"{ref.lon:.6f}" if ref else "",
            "reference_latitude": f"{ref.lat:.6f}" if ref else "",
            "reference_area_code": self.reference_area_code or "",
            "distance_m": "" if self.distance_m is None else f"{self.distance_m:.1f}",
            "audit_status": self.audit_status,
        }


def audit_facilities(facilities, linkage_by_record, reference_index, area_index: AreaIndex):
    rows: list[AuditRow] = []
    for facility in facilities:
        linkage = linkage_by_record[facility["record_id"]]
        reference_status, reference = _resolve_reference(facility, linkage, reference_index)

        lon_raw = (linkage.get("longitude") or "").strip()
        lat_raw = (linkage.get("latitude") or "").strip()
        has_coordinate = bool(lon_raw and lat_raw)

        distance = None
        if has_coordinate and reference is not None:
            distance = haversine_m(float(lon_raw), float(lat_raw), reference.lon, reference.lat)

        reference_area_code = (
            area_index.find_area_code(reference.lon, reference.lat) if reference else None
        )
        rows.append(
            AuditRow(
                facility=facility,
                linkage=linkage,
                reference_status=reference_status,
                reference=reference,
                reference_area_code=reference_area_code,
                distance_m=distance,
                audit_status=_audit_status(has_coordinate, reference, distance),
            )
        )
    return rows


# ===========================================================================
# 4. 検証(想定が崩れたら中断する)
# ===========================================================================


def validate(rows, facilities, linkage_by_record):
    checks = []

    def check(label: str, ok: bool, detail: str = ""):
        checks.append((label, ok, detail))
        if not ok:
            raise SystemExit(f"検証失敗: {label}{(' — ' + detail) if detail else ''}")

    check("1. 監査行数が facility_basic.csv と一致する", len(rows) == len(facilities), f"{len(rows)} vs {len(facilities)}")
    check(
        "2. record_id が重複しない",
        len({r.facility["record_id"] for r in rows}) == len(rows),
    )
    check(
        "3. facility_geo_linkage.csv の全record_idを覆う",
        {r.facility["record_id"] for r in rows} == set(linkage_by_record),
    )

    matched = [r for r in rows if r.linkage.get("match_status") == "matched"]
    check(
        "4. matched の全件が座標を持つ(監査対象の定義)",
        all(r.linkage.get("longitude") and r.linkage.get("latitude") for r in matched),
    )
    check(
        "5. matched 以外は座標を持たない",
        all(
            not (r.linkage.get("longitude") or r.linkage.get("latitude"))
            for r in rows
            if r.linkage.get("match_status") != "matched"
        ),
    )
    check(
        "6. 参照ありの行は距離を持つ(座標ありの場合)",
        all(
            (r.distance_m is not None)
            == bool(r.reference is not None and r.linkage.get("match_status") == "matched")
            for r in rows
        ),
    )
    check(
        "7. audit_status が定義済みの値のみ",
        {r.audit_status for r in rows} <= set(AUDIT_LABELS),
        str(sorted({r.audit_status for r in rows} - set(AUDIT_LABELS))),
    )
    check(
        "8. reference_status が定義済みの値のみ",
        {r.reference_status for r in rows} <= set(REF_LABELS),
    )
    check(
        "9. 参照を同定した行は必ず座標を持つ(センチネル除外が効いている)",
        all(
            LAT_MIN < r.reference.lat < LAT_MAX and LON_MIN < r.reference.lon < LON_MAX
            for r in rows
            if r.reference is not None
        ),
    )
    check(
        "10. conflict は距離が閾値以上",
        all(r.distance_m >= CONFLICT_MIN_M for r in rows if r.audit_status == AUDIT_CONFLICT),
    )
    return checks


# ===========================================================================
# 5. レポート
# ===========================================================================


def _pct(n: int, d: int) -> str:
    return "—" if not d else f"{n / d:.1%}"


def _quantile(sorted_values, q: float) -> float:
    if not sorted_values:
        return float("nan")
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * q))
    return sorted_values[idx]


def build_report_markdown(rows, reference_stats, checks) -> str:
    out: list[str] = []
    w = out.append

    w("# 医療機関座標の監査レポート（P04由来の付与済み座標 × 医療情報ネットの公表座標）")
    w("")
    w("このファイルは `python tools/build_facility_geo_audit.py` が生成する。手で編集しないこと。")
    w("再生成コマンド: `PYTHONIOENCODING=utf-8 python tools/build_facility_geo_audit.py`")
    w("")
    w("## 1. 目的")
    w("")
    w(
        "可視化サイトが地図に出している医療機関の座標は、`ksj/P04-20`（国土数値情報 医療機関データ、"
        "**令和2年度**）との名寄せで与えている。原典の医療機関個票（`R7/001723127.xlsx`）は"
        "**令和7年度**公表であり、5年の開きがある。名寄せは名称の同一性しか見ていないため、"
        "**その間に移転した施設には旧所在地の座標が付いたまま**になりうる。"
    )
    w("")
    w(
        f"本レポートは、厚労省が別途公表している医療情報ネット（医療機能情報提供制度、{SNAPSHOT_DATE}時点）の"
        "**公表座標**を参照として、付与済み座標との距離を実測したものである。"
    )
    w("")
    w(
        "**参照側の座標は採用していない。** このスクリプトは `facility_geo_linkage.csv` を書き換えず、"
        "監査結果だけを出力する。医療情報ネットを座標源として統合するかは未決であり、"
        "判断材料と決定は `doc/DECISION_FACILITY_COORDINATES.md` にある。"
    )
    w("")
    w("## 2. 参照データ")
    w("")
    w("| 区分 | 収録件数 | 使える座標 | 座標センチネル（`0.0`/`0.0`） |")
    w("|---|---:|---:|---:|")
    total_all = total_usable = 0
    for kind, s in reference_stats.items():
        total_all += s["total"]
        total_usable += s["usable"]
        w(f"| {kind} | {s['total']:,} | {s['usable']:,} | {s['sentinel']:,} |")
    w(f"| **計** | **{total_all:,}** | **{total_usable:,}** | **{total_all - total_usable:,}** |")
    w("")
    w(
        f"出典: [医療情報ネットのオープンデータについて]({SOURCE_PAGE})（{SNAPSHOT_DATE}時点）。"
        "緯度・経度の列は全行が埋まっているように見えるが、実測で上表の件数が `0.0`/`0.0`（ギニア湾沖）である。"
        "**欠測を「空欄かどうか」で判定すると静かに壊れる**ため、日本の緯度経度の範囲内かで判定している。"
    )
    w("")
    w("## 3. 参照の同定")
    w("")
    w(
        "参照の採用条件は名寄せ本体と同じ保守性で揃えてある: **同一都道府県内で正規化名（`normalize_facility_name()`）が"
        "完全一致し、市区町村も整合し、候補が1件だけ**。参照側は都道府県コード・市区町村コードを列として持ち、"
        "住所も都道府県名から始まる完全な形なので、P04で必要だった点-多角形判定による同名市区町村の切り分けは要らない。"
    )
    w("")
    ref_counts = Counter(r.reference_status for r in rows)
    w("| reference_status | 件数 | 内容 |")
    w("|---|---:|---|")
    for status in (REF_UNIQUE, REF_UNIQUE_MUNICIPALITY_UNVERIFIED, REF_MUNICIPALITY_MISMATCH, REF_AMBIGUOUS, REF_NONE):
        w(f"| {status} | {ref_counts.get(status, 0):,} | {REF_LABELS[status]} |")
    w(f"| **計** | **{len(rows):,}** | |")
    w("")
    w("## 4. 監査結果")
    w("")
    audit_counts = Counter(r.audit_status for r in rows)
    matched_rows = [r for r in rows if r.linkage.get("match_status") == "matched"]
    w(f"地図に点として出ている**座標付与済み {len(matched_rows):,}件**の内訳:")
    w("")
    w("| audit_status | 件数 | 割合 | 内容 |")
    w("|---|---:|---:|---|")
    for status in (AUDIT_AGREE, AUDIT_MINOR_GAP, AUDIT_CONFLICT, AUDIT_NO_REFERENCE):
        n = audit_counts.get(status, 0)
        w(f"| {status} | {n:,} | {_pct(n, len(matched_rows))} | {AUDIT_LABELS[status]} |")
    w(f"| **計** | **{len(matched_rows):,}** | | |")
    w("")
    w("座標が無い施設（参考。統合を検討する場合の材料であり、本レポートでは座標を与えない）:")
    w("")
    w("| audit_status | 件数 | 内容 |")
    w("|---|---:|---|")
    for status in (AUDIT_MISSING_WITH_REFERENCE, AUDIT_MISSING_WITHOUT_REFERENCE):
        w(f"| {status} | {audit_counts.get(status, 0):,} | {AUDIT_LABELS[status]} |")
    w("")

    distances = sorted(r.distance_m for r in rows if r.distance_m is not None)
    if distances:
        w("### 距離の分布（検算できた施設）")
        w("")
        w("| 統計量 | 距離 |")
        w("|---|---:|")
        w(f"| 件数 | {len(distances):,} |")
        for label, q in (("中央値", 0.5), ("75%点", 0.75), ("90%点", 0.90), ("99%点", 0.99)):
            w(f"| {label} | {_quantile(distances, q):,.0f} m |")
        w(f"| 最大 | {distances[-1]:,.0f} m |")
        w("")
        w(
            f"区分の境界（{AGREE_MAX_M:.0f}m・{CONFLICT_MIN_M:.0f}m）はこの分布から決めている。"
            f"{AGREE_MAX_M:.0f}mは90%点に余裕を持たせた値で「同一敷地・同一住所と読める一致」、"
            f"{CONFLICT_MIN_M:.0f}mは99%点にほぼ一致し「住所表記の粒度差やジオコーディング誤差では"
            "説明しにくい水準」を意味する。"
        )
        w("")

    conflicts = sorted(
        (r for r in rows if r.audit_status == AUDIT_CONFLICT),
        key=lambda r: -r.distance_m,
    )
    w(f"## 5. `conflict`（{CONFLICT_MIN_M:.0f}m以上離れている）全{len(conflicts):,}件")
    w("")
    if not conflicts:
        w("該当なし。")
    else:
        cross_area = [r for r in conflicts if r.reference_area_code != r.facility["area_code"]]
        w(
            f"うち、参照座標が原典の言う構想区域の**外**に落ちるものが {len(cross_area):,}件"
            "（`reference_area_code` 列で確認できる）。区域をまたぐ差は、移転か参照側の誤りかの"
            "いずれかであり、名称一致だけでは決められない。"
        )
        w("")
        w(
            "下表の「参照側の所在地」を `facility_geo_linkage.csv` の `p04_address` 列と読み比べると、"
            "この76件は2種類に分かれる:"
        )
        w("")
        w(
            "1. **住所は実質同一なのに座標だけが離れている** — 例: 産科・婦人科久米クリニックは双方とも"
            "「いちき串木野市曙町」だが座標は約32km離れている。この場合は移転ではなく、"
            "**いずれかの座標そのものが誤っている**。"
        )
        w(
            "2. **住所自体が異なる** — 例: 峯苫医院はP04「八代市坂本町坂本」対 参照「八代市渡町」。"
            "令和2年度と2025年の間の移転と解釈できる。"
        )
        w("")
        w(
            "いずれの場合も、**いま地図に出ている点が現在の所在地を指している保証は無い**。"
            "この可視化サイトでの扱いは `facility_geo_audit.csv.meta.json` の `known_issues` に記録してある"
            "（表示用データセットではこの76件の座標を出力せず、一覧には「地図に表示なし」として残す）。"
        )
        w("")
        w("| 距離 | 都道府県 | 構想区域 | 医療機関名 | 原典の市区町村 | 参照側の所在地 | 参照区域 |")
        w("|---:|---|---|---|---|---|---|")
        for r in conflicts:
            f = r.facility
            ref = r.reference
            ref_area = r.reference_area_code or "—"
            same = "同一" if ref_area == f["area_code"] else ref_area
            w(
                f"| {r.distance_m:,.0f} m | {f['pref_name']} | {f['area_name']} | {f['facility_name']} "
                f"| {f['municipality'] or '（空）'} | {ref.address} | {same} |"
            )
    w("")

    w("## 6. 都道府県別")
    w("")
    w("| コード | 都道府県 | 施設数 | 座標付与 | 付与率 | 検算できた | agree | minor_gap | conflict |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    by_pref = defaultdict(list)
    for r in rows:
        by_pref[(r.facility["pref_code"], r.facility["pref_name"])].append(r)
    for (code, name), prows in sorted(by_pref.items()):
        placed = [r for r in prows if r.linkage.get("match_status") == "matched"]
        counts = Counter(r.audit_status for r in prows)
        checked = counts[AUDIT_AGREE] + counts[AUDIT_MINOR_GAP] + counts[AUDIT_CONFLICT]
        w(
            f"| {code} | {name} | {len(prows):,} | {len(placed):,} | {_pct(len(placed), len(prows))} "
            f"| {checked:,} | {counts[AUDIT_AGREE]:,} | {counts[AUDIT_MINOR_GAP]:,} | {counts[AUDIT_CONFLICT]:,} |"
        )
    w("")

    w("## 7. 限界")
    w("")
    w(
        "- **参照が正しいことの保証は無い**。出典ページ自身が「最新でない情報や報告誤りの可能性」を明記している。"
        f"`{AUDIT_CONFLICT}` は「付与済み座標が誤っている」ことの証明ではなく、"
        "**2つの公表物が異なる位置を示している**ことの記録である。"
    )
    w(
        "- **参照側のIDは恒久IDではない**（出典ページに「開設者変更や移転等となった場合……同様のIDは変更とならない場合があります」と明記）。"
        "年度をまたぐ突合のキーには使えない。"
    )
    w(
        f"- **`{AUDIT_NO_REFERENCE}` は「座標が誤っている」ことも「正しい」ことも意味しない**。"
        "名称の表記差・改称・参照側の座標センチネルなどで一意に確認できなかっただけである。"
    )
    w(
        "- 参照の同定は名称の完全一致に限っており、名寄せ本体の接尾一致ティアに相当する緩和は入れていない"
        "（監査は回収率ではなく確度を優先するため）。"
    )
    w("")

    w("## 8. 検証項目")
    w("")
    w("このレポートの生成時に検証し、崩れていれば中断する項目:")
    w("")
    for label, ok, detail in checks:
        w(f"- [{'ok' if ok else 'NG'}] {label}{(' — ' + detail) if detail else ''}")
    w("")
    return "\n".join(out)


# ===========================================================================
# 6. エントリポイント
# ===========================================================================


def build_and_write(out_dir: Path, doc_dir: Path) -> dict:
    hospital_sha = verify_source(HOSPITAL_ZIP_PATH_IN_REPO)
    print(f"[ok] 生データ検証: {HOSPITAL_ZIP_PATH_IN_REPO} = {hospital_sha[:16]}...")
    clinic_sha = verify_source(CLINIC_ZIP_PATH_IN_REPO)
    print(f"[ok] 生データ検証: {CLINIC_ZIP_PATH_IN_REPO} = {clinic_sha[:16]}...")
    linkage_sha = sha256(LINKAGE_CSV)
    basic_sha = sha256(FACILITY_BASIC_CSV)
    boundaries_sha = sha256(AREA_BOUNDARIES_PATH)

    points, reference_stats = load_reference_points(
        REPO_ROOT / HOSPITAL_ZIP_PATH_IN_REPO, REPO_ROOT / CLINIC_ZIP_PATH_IN_REPO
    )
    print(
        f"[ok] 参照データ読み込み: 使える座標 {len(points):,}件 / "
        f"収録 {sum(s['total'] for s in reference_stats.values()):,}件"
    )
    reference_index = index_reference_points(points)

    import json

    with open(AREA_BOUNDARIES_PATH, "r", encoding="utf-8") as f:
        boundaries = json.load(f)
    area_index = AreaIndex(boundaries)
    print(f"[ok] 区域索引: {area_index.area_count}区域")

    with open(FACILITY_BASIC_CSV, "r", encoding="utf-8", newline="") as f:
        facilities = list(csv.DictReader(f))
    with open(LINKAGE_CSV, "r", encoding="utf-8", newline="") as f:
        linkage_by_record = {r["record_id"]: r for r in csv.DictReader(f)}
    print(f"[ok] 監査対象: {len(facilities):,}施設")

    rows = audit_facilities(facilities, linkage_by_record, reference_index, area_index)
    checks = validate(rows, facilities, linkage_by_record)
    counts = Counter(r.audit_status for r in rows)
    print(
        f"[ok] 監査完了: agree={counts[AUDIT_AGREE]} minor_gap={counts[AUDIT_MINOR_GAP]} "
        f"conflict={counts[AUDIT_CONFLICT]} no_reference={counts[AUDIT_NO_REFERENCE]} "
        f"missing_with_reference={counts[AUDIT_MISSING_WITH_REFERENCE]}"
    )

    source = {
        "name": "付与済み医療機関座標(facility_geo_linkage.csv、P04-20由来) × 医療情報ネットの公表座標の検算",
        "inputs": [
            {
                "file": HOSPITAL_ZIP_PATH_IN_REPO,
                "role": f"参照座標(医療情報ネット 病院施設票、{SNAPSHOT_DATE}時点)",
                "source_sha256": hospital_sha,
            },
            {
                "file": CLINIC_ZIP_PATH_IN_REPO,
                "role": f"参照座標(医療情報ネット 診療所施設票、{SNAPSHOT_DATE}時点)",
                "source_sha256": clinic_sha,
            },
            {
                "file": "data/processed/facility_geo_linkage.csv",
                "role": "監査対象(現在この可視化サイトが使っている座標)",
                "source_sha256": linkage_sha,
            },
            {
                "file": "data/processed/facility_basic.csv",
                "role": "医療機関の識別情報(名称・市区町村・区域)",
                "source_sha256": basic_sha,
            },
            {
                "file": "data/processed/area_boundaries_R7.geojson",
                "role": "参照座標がどの構想区域に落ちるかの点-多角形判定",
                "source_sha256": boundaries_sha,
            },
        ],
        "page_url": SOURCE_PAGE,
        "reference_snapshot_date": SNAPSHOT_DATE,
    }
    processing = {
        "script": "tools/build_facility_geo_audit.py",
        "date": datetime.date.today().isoformat(),
        "method": (
            "医療情報ネットの公表座標を参照として、付与済み座標との大円距離を実測する。"
            "参照の同定は同一都道府県内で正規化名が完全一致し市区町村も整合し候補が1件だけの場合のみ"
            f"(名寄せ本体と同じ保守性)。距離は{AGREE_MAX_M:.0f}m未満=agree、{CONFLICT_MIN_M:.0f}m以上=conflictに区分する。"
            "**参照側の座標は採用しない**(このスクリプトはfacility_geo_linkage.csvを書き換えない)"
        ),
        "agree_max_m": AGREE_MAX_M,
        "conflict_min_m": CONFLICT_MIN_M,
        "steps": [
            "verify_source()で医療情報ネットの2つのzipのSHA-256をSHA256SUMSと照合",
            "zip内CSV(UTF-8 BOM付き)を読み、緯度経度が日本の範囲内の行だけを参照点として採る(0.0/0.0のセンチネルを除外)",
            "(都道府県コード, 正規化名)で索引を作る",
            "各医療機関について、同一都道府県内の正規化名完全一致候補を市区町村整合で絞り、1件だけの場合のみ参照として同定する",
            "付与済み座標と参照座標の大円距離(haversine)を計算し、agree/minor_gap/conflictに区分する",
            "参照座標が落ちる構想区域を点-多角形判定で求め、原典の区域と一致するかを列として残す",
        ],
        "caveat": CAVEAT,
    }

    output_dicts = [r.to_output() for r in rows]
    output_tuples = [tuple(d[h] for h in OUTPUT_HEADER) for d in output_dicts]

    csv_path, meta_path = write_csv_with_meta(
        out_dir / "facility_geo_audit.csv",
        OUTPUT_HEADER,
        output_tuples,
        title="医療機関の付与済み座標(P04-20由来)と医療情報ネットの公表座標の検算結果",
        source=source,
        processing=processing,
        fields=FIELDS_AUDIT,
        known_issues=known_issues_for(rows),
    )
    print(f"[ok] 出力: {csv_path} ({len(output_tuples)}行)")

    report_md = build_report_markdown(rows, reference_stats, checks)
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc_path = doc_dir / "FACILITY_GEO_AUDIT.md"
    with open(doc_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(report_md)
    print(f"[ok] 出力: {doc_path}")

    return {"csv": csv_path, "meta": meta_path, "doc": doc_path, "rows": rows}


def main():
    build_and_write(PROCESSED_DIR, DOC_DIR)


if __name__ == "__main__":
    main()
