from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from statistics import median
from typing import Any, Iterable, Mapping

from .analysis_schema import ensure_analysis_schema, upsert_metric
from .geo import geometry_center, mesh250_center, mesh_code_250m
from .spatial_analysis import point_in_geometry

METRIC_VERSION = "detail-v1"

RESILIENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS evacuation_sites (
    common_id TEXT PRIMARY KEY,
    area_id TEXT,
    prefecture_and_city TEXT,
    facility_name TEXT NOT NULL,
    address TEXT,
    flood_flag INTEGER,
    landslide_flag INTEGER,
    high_tide_flag INTEGER,
    earthquake_flag INTEGER,
    tsunami_flag INTEGER,
    large_fire_flag INTEGER,
    inland_flooding_flag INTEGER,
    volcanic_phenomenon_flag INTEGER,
    same_address_flag INTEGER,
    remarks TEXT,
    latitude REAL,
    longitude REAL,
    source_id INTEGER,
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);
CREATE INDEX IF NOT EXISTS idx_evacuation_sites_area ON evacuation_sites(area_id);

CREATE TABLE IF NOT EXISTS disaster_history (
    event_id TEXT PRIMARY KEY,
    disastertype_code TEXT,
    disaster_name TEXT,
    disaster_date TEXT,
    disaster_source TEXT,
    geometry_type TEXT,
    geometry_json TEXT NOT NULL,
    centroid_lat REAL,
    centroid_lon REAL,
    source_id INTEGER,
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);
CREATE TABLE IF NOT EXISTS disaster_history_areas (
    event_id TEXT NOT NULL,
    area_id TEXT NOT NULL,
    PRIMARY KEY (event_id, area_id),
    FOREIGN KEY (event_id) REFERENCES disaster_history(event_id) ON DELETE CASCADE,
    FOREIGN KEY (area_id) REFERENCES areas(area_id)
);
CREATE INDEX IF NOT EXISTS idx_disaster_history_area ON disaster_history_areas(area_id);
"""

DATASETS = [
    ("reinfolib_xgt001", "国土交通省 不動産情報ライブラリ", "XGT001", "resilience", "指定緊急避難場所", "令和8年6月12日時点", "point", "extended", 1, "最新かつ詳細な状況は市町村確認が必要"),
    ("reinfolib_xst001", "国土交通省 不動産情報ライブラリ", "XST001", "resilience", "国土調査 災害履歴", "土地履歴調査", "spatial", "extended", 1, "調査済み地域・収集できた資料の履歴であり全災害を網羅しない"),
]

DEFINITIONS = [
    ("resilience.evacuation_site_count", "resilience", "指定緊急避難場所数", "箇所", "neutral", "ward", "reinfolib_xgt001", 1, "区内の指定緊急避難場所数"),
    ("resilience.evacuation_sites_per_10k", "resilience", "人口1万人当たり避難場所", "箇所/万人", "higher", "ward", "reinfolib_xgt001", 1, "指定緊急避難場所数÷最新人口×1万人"),
    ("resilience.evacuation_flood_count", "resilience", "洪水対応避難場所", "箇所", "neutral", "ward", "reinfolib_xgt001", 1, "洪水フラグがtrueの指定緊急避難場所"),
    ("resilience.evacuation_landslide_count", "resilience", "土砂対応避難場所", "箇所", "neutral", "ward", "reinfolib_xgt001", 1, "崖崩れ・土石流・地滑り対応避難場所"),
    ("resilience.evacuation_high_tide_count", "resilience", "高潮対応避難場所", "箇所", "neutral", "ward", "reinfolib_xgt001", 1, "高潮対応避難場所"),
    ("resilience.evacuation_earthquake_count", "resilience", "地震対応避難場所", "箇所", "neutral", "ward", "reinfolib_xgt001", 1, "地震対応避難場所"),
    ("resilience.evacuation_tsunami_count", "resilience", "津波対応避難場所", "箇所", "neutral", "ward", "reinfolib_xgt001", 1, "津波対応避難場所"),
    ("resilience.evacuation_large_fire_count", "resilience", "大規模火災対応避難場所", "箇所", "neutral", "ward", "reinfolib_xgt001", 1, "大規模な火事対応避難場所"),
    ("resilience.evacuation_inland_flood_count", "resilience", "内水氾濫対応避難場所", "箇所", "neutral", "ward", "reinfolib_xgt001", 1, "内水氾濫対応避難場所"),
    ("resilience.evacuation_median_distance", "resilience", "避難場所までの250m人口メッシュ距離中央値", "m", "lower", "ward", "reinfolib_xgt001", 1, "2025人口がある250mメッシュ中心から最寄り指定緊急避難場所までの直線距離中央値"),
    ("resilience.evacuation_flood_median_distance", "resilience", "洪水対応避難場所距離中央値", "m", "lower", "ward", "reinfolib_xgt001", 1, "2025人口がある250mメッシュ中心から最寄り洪水対応避難場所までの直線距離中央値"),
    ("resilience.disaster_history_count", "resilience", "災害履歴件数", "件", "neutral", "ward", "reinfolib_xst001", 1, "国土調査の災害履歴。全災害の網羅を意味しない"),
    ("resilience.disaster_history_flood_count", "resilience", "水害履歴件数", "件", "neutral", "ward", "reinfolib_xst001", 1, "災害分類11〜14の履歴件数"),
    ("resilience.disaster_history_slope_count", "resilience", "土砂災害履歴件数", "件", "neutral", "ward", "reinfolib_xst001", 1, "災害分類21〜24・34の履歴件数"),
    ("resilience.disaster_history_liquefaction_count", "resilience", "液状化履歴件数", "件", "neutral", "ward", "reinfolib_xst001", 1, "災害分類33の履歴件数"),
    ("resilience.disaster_history_tsunami_count", "resilience", "津波履歴件数", "件", "neutral", "ward", "reinfolib_xst001", 1, "災害分類37・38の履歴件数"),
    ("resilience.disaster_history_latest_year", "resilience", "記録上の最新災害年", "年", "neutral", "ward", "reinfolib_xst001", 1, "国土調査災害履歴に記録された最新年。全災害の網羅を意味しない"),
]


def ensure_resilience_schema(conn) -> None:
    ensure_analysis_schema(conn)
    conn.executescript(RESILIENCE_SCHEMA)
    conn.executemany(
        """
        INSERT INTO dataset_catalog(dataset_key,provider,api_id,category,title,source_vintage,granularity,refresh_mode,enabled,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(dataset_key) DO UPDATE SET title=excluded.title,source_vintage=excluded.source_vintage,notes=excluded.notes
        """,
        DATASETS,
    )
    conn.executemany(
        """
        INSERT INTO metric_definitions(metric_key,category,label,unit,direction,granularity,source_dataset_key,min_sample_size,description)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(metric_key) DO UPDATE SET label=excluded.label,unit=excluded.unit,description=excluded.description
        """,
        DEFINITIONS,
    )


def _boolint(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    return 1 if str(value).strip().lower() in {"1", "true", "yes", "有", "あり"} else 0


def _area_from_address(address: str, area_names: Mapping[str, str]) -> str | None:
    for area_id, name in area_names.items():
        if name and name in address:
            return area_id
    return None


def normalize_evacuation_sites(
    payload: Mapping[str, Any],
    *,
    mesh_to_area: Mapping[str, str],
    area_names: Mapping[str, str],
) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for feature in payload.get("features", []) or []:
        props = feature.get("properties") or {}
        center = geometry_center(feature.get("geometry") or {})
        if not center:
            continue
        lon, lat = center
        area_id = None
        try:
            area_id = mesh_to_area.get(mesh_code_250m(lon, lat))
        except ValueError:
            pass
        address = str(props.get("address_ja") or "")
        area_id = area_id or _area_from_address(address, area_names)
        if area_id not in area_names:
            continue
        common_id = str(props.get("common_id") or "").strip()
        if not common_id:
            raw = json.dumps(feature, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            common_id = hashlib.sha256(f"XGT001|{raw}".encode("utf-8")).hexdigest()[:32]
        result[common_id] = {
            "common_id": common_id,
            "area_id": area_id,
            "prefecture_and_city": str(props.get("prefecture_and_city") or "") or None,
            "facility_name": str(props.get("facility_name_ja") or "") or common_id,
            "address": address or None,
            "flood_flag": _boolint(props.get("flood_flag")),
            "landslide_flag": _boolint(props.get("landslide_flag")),
            "high_tide_flag": _boolint(props.get("high_tide_flag")),
            "earthquake_flag": _boolint(props.get("earthquake_flag")),
            "tsunami_flag": _boolint(props.get("tsunami_flag")),
            "large_fire_flag": _boolint(props.get("large_fire_flag")),
            "inland_flooding_flag": _boolint(props.get("inland_flooding_flag")),
            "volcanic_phenomenon_flag": _boolint(props.get("volcanic_phenomenon_flag")),
            "same_address_flag": _boolint(props.get("same_address_flag")),
            "remarks": str(props.get("remarks") or "") or None,
            "latitude": lat,
            "longitude": lon,
        }
    return list(result.values())


def normalize_disaster_history(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for feature in payload.get("features", []) or []:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        if not geometry:
            continue
        raw = json.dumps(feature, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        event_id = hashlib.sha256(f"XST001|{raw}".encode("utf-8")).hexdigest()[:32]
        center = geometry_center(geometry)
        result[event_id] = {
            "event_id": event_id,
            "disastertype_code": str(props.get("disastertype_code") or "") or None,
            "disaster_name": str(props.get("disaster_name_ja") or "") or None,
            "disaster_date": str(props.get("disaster_date") or "") or None,
            "disaster_source": str(props.get("disaster_source") or "") or None,
            "geometry_type": str(geometry.get("type") or "") or None,
            "geometry_json": json.dumps(geometry, ensure_ascii=False, separators=(",", ":")),
            "centroid_lat": center[1] if center else None,
            "centroid_lon": center[0] if center else None,
        }
    return list(result.values())


def assign_disaster_history_areas(conn) -> int:
    ensure_resilience_schema(conn)
    conn.execute("DELETE FROM disaster_history_areas")
    mesh_rows = conn.execute(
        "SELECT DISTINCT mesh_id, area_id FROM future_population WHERE year=2025"
    ).fetchall()
    meshes: list[tuple[str, str, float, float]] = []
    mesh_lookup: dict[str, str] = {}
    for row in mesh_rows:
        mesh_id = str(row["mesh_id"])
        area_id = str(row["area_id"])
        mesh_lookup[mesh_id] = area_id
        try:
            lon, lat = mesh250_center(mesh_id)
        except ValueError:
            continue
        meshes.append((mesh_id, area_id, lon, lat))

    pairs: set[tuple[str, str]] = set()
    for row in conn.execute("SELECT * FROM disaster_history"):
        event_id = str(row["event_id"])
        geometry = json.loads(row["geometry_json"])
        kind = str(row["geometry_type"] or "")
        areas: set[str] = set()
        if kind in {"Polygon", "MultiPolygon"}:
            for _, area_id, lon, lat in meshes:
                if point_in_geometry(lon, lat, geometry):
                    areas.add(area_id)
        else:
            lon = row["centroid_lon"]
            lat = row["centroid_lat"]
            if lon is not None and lat is not None:
                try:
                    area_id = mesh_lookup.get(mesh_code_250m(float(lon), float(lat)))
                except ValueError:
                    area_id = None
                if area_id:
                    areas.add(area_id)
        for area_id in areas:
            pairs.add((event_id, area_id))
    if pairs:
        conn.executemany(
            "INSERT OR IGNORE INTO disaster_history_areas(event_id,area_id) VALUES (?,?)",
            sorted(pairs),
        )
    return len(pairs)


def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _median_nearest(meshes: list[tuple[float, float]], sites: list[tuple[float, float]]) -> float | None:
    if not meshes or not sites:
        return None
    values = [
        min(_haversine_m(lon, lat, site_lon, site_lat) for site_lon, site_lat in sites)
        for lon, lat in meshes
    ]
    return round(float(median(values)), 1)


def _latest_population(conn, area_id: str) -> float | None:
    row = conn.execute(
        "SELECT population FROM population WHERE area_id=? AND population IS NOT NULL ORDER BY year DESC LIMIT 1",
        (area_id,),
    ).fetchone()
    return float(row["population"]) if row and row["population"] is not None else None


def _year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"(\d{4})", value)
    if not match:
        return None
    year = int(match.group(1))
    return year if year > 0 else None


def compute_resilience_metrics(conn) -> int:
    ensure_resilience_schema(conn)
    written = 0
    now_period = "2026"
    all_sites = [dict(row) for row in conn.execute("SELECT * FROM evacuation_sites")]
    all_site_points = [(float(row["longitude"]), float(row["latitude"])) for row in all_sites if row["longitude"] is not None and row["latitude"] is not None]
    flood_site_points = [(float(row["longitude"]), float(row["latitude"])) for row in all_sites if row["flood_flag"] and row["longitude"] is not None and row["latitude"] is not None]

    source_xgt = conn.execute("SELECT MAX(source_id) AS id FROM evacuation_sites").fetchone()
    source_xst = conn.execute("SELECT MAX(source_id) AS id FROM disaster_history").fetchone()
    source_xgt_id = int(source_xgt["id"]) if source_xgt and source_xgt["id"] is not None else None
    source_xst_id = int(source_xst["id"]) if source_xst and source_xst["id"] is not None else None

    for area in conn.execute("SELECT area_id FROM areas ORDER BY area_id"):
        area_id = str(area["area_id"])
        geo_id = f"ward:{area_id}"
        sites = [row for row in all_sites if str(row.get("area_id") or "") == area_id]
        population = _latest_population(conn, area_id)
        mesh_points: list[tuple[float, float]] = []
        for row in conn.execute(
            "SELECT mesh_id, projected_population FROM future_population WHERE area_id=? AND year=2025 AND projected_population>0",
            (area_id,),
        ):
            try:
                mesh_points.append(mesh250_center(str(row["mesh_id"])))
            except ValueError:
                pass

        site_values = {
            "resilience.evacuation_site_count": float(len(sites)),
            "resilience.evacuation_sites_per_10k": (len(sites) / population * 10000.0 if population and population > 0 else None),
            "resilience.evacuation_flood_count": float(sum(int(row["flood_flag"] or 0) for row in sites)),
            "resilience.evacuation_landslide_count": float(sum(int(row["landslide_flag"] or 0) for row in sites)),
            "resilience.evacuation_high_tide_count": float(sum(int(row["high_tide_flag"] or 0) for row in sites)),
            "resilience.evacuation_earthquake_count": float(sum(int(row["earthquake_flag"] or 0) for row in sites)),
            "resilience.evacuation_tsunami_count": float(sum(int(row["tsunami_flag"] or 0) for row in sites)),
            "resilience.evacuation_large_fire_count": float(sum(int(row["large_fire_flag"] or 0) for row in sites)),
            "resilience.evacuation_inland_flood_count": float(sum(int(row["inland_flooding_flag"] or 0) for row in sites)),
            "resilience.evacuation_median_distance": _median_nearest(mesh_points, all_site_points),
            "resilience.evacuation_flood_median_distance": _median_nearest(mesh_points, flood_site_points),
        }
        for metric_key, value in site_values.items():
            upsert_metric(
                conn,
                geo_id=geo_id,
                metric_key=metric_key,
                period=now_period,
                value=round(value, 3) if value is not None else None,
                sample_size=len(sites),
                source_id=source_xgt_id,
                metric_version=METRIC_VERSION,
                quality_grade="A" if sites else "D",
                source_year="2026-06-12",
                notes="XGT001指定緊急避難場所。最新かつ詳細な状況は当該市町村で確認が必要。距離は250mメッシュ中心からの直線距離。",
            )
            written += 1

        history = [dict(row) for row in conn.execute(
            """
            SELECT dh.* FROM disaster_history dh
            JOIN disaster_history_areas dha ON dha.event_id=dh.event_id
            WHERE dha.area_id=?
            """,
            (area_id,),
        )]
        codes = [str(row.get("disastertype_code") or "") for row in history]
        years = [year for year in (_year(row.get("disaster_date")) for row in history) if year is not None]
        history_values = {
            "resilience.disaster_history_count": float(len(history)),
            "resilience.disaster_history_flood_count": float(sum(code in {"11", "12", "13", "14"} for code in codes)),
            "resilience.disaster_history_slope_count": float(sum(code in {"21", "22", "23", "24", "34"} for code in codes)),
            "resilience.disaster_history_liquefaction_count": float(sum(code == "33" for code in codes)),
            "resilience.disaster_history_tsunami_count": float(sum(code in {"37", "38"} for code in codes)),
            "resilience.disaster_history_latest_year": float(max(years)) if years else None,
        }
        for metric_key, value in history_values.items():
            upsert_metric(
                conn,
                geo_id=geo_id,
                metric_key=metric_key,
                period="history",
                value=value,
                sample_size=len(history),
                source_id=source_xst_id,
                metric_version=METRIC_VERSION,
                quality_grade="C" if history else "D",
                source_year="土地履歴調査",
                notes="XST001国土調査災害履歴。調査済み地域・収集資料に基づき、地域の全災害を網羅するデータではありません。",
            )
            written += 1
    return written
