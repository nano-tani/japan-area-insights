from __future__ import annotations

from datetime import datetime, timezone
from math import ceil, floor
from typing import Any, Iterable, Mapping

from .analysis_schema import ensure_analysis_schema, upsert_metric

METRIC_VERSION = "detail-v1"

TERRAIN_SCHEMA = """
CREATE TABLE IF NOT EXISTS mesh_terrain_metrics (
    mesh_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL,
    elevation_m REAL,
    elevation_source TEXT,
    source_id INTEGER,
    fetched_at TEXT,
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);
CREATE INDEX IF NOT EXISTS idx_mesh_terrain_area ON mesh_terrain_metrics(area_id);
"""

DATASET = (
    "gsi_elevation",
    "国土地理院",
    "GSI:elevation",
    "terrain",
    "地理院地図 標高値",
    "随時更新",
    "mesh250_center",
    "extended",
    1,
    "250mメッシュ中心点の標高。地点ごとに利用可能な最も精度の高いDEMが返される。",
)

DEFINITIONS = [
    ("terrain.elevation_coverage", "terrain", "標高データ取得率", "%", "higher", "ward", "gsi_elevation", 1, "2025人口がある250mメッシュ中心で標高を取得できた比率"),
    ("terrain.elevation_median", "terrain", "メッシュ中心標高中央値", "m", "neutral", "ward", "gsi_elevation", 1, "250mメッシュ中心点標高の中央値"),
    ("terrain.elevation_population_weighted_mean", "terrain", "人口加重平均標高", "m", "neutral", "ward", "gsi_elevation", 1, "250mメッシュ中心標高を2025推計人口で加重平均"),
    ("terrain.elevation_p10", "terrain", "標高10%点", "m", "neutral", "ward", "gsi_elevation", 1, "取得済みメッシュ中心標高の10パーセンタイル"),
    ("terrain.elevation_p90", "terrain", "標高90%点", "m", "neutral", "ward", "gsi_elevation", 1, "取得済みメッシュ中心標高の90パーセンタイル"),
    ("terrain.elevation_p90_p10_range", "terrain", "標高P90-P10差", "m", "neutral", "ward", "gsi_elevation", 1, "区内の起伏感をみる参考値。90%点−10%点"),
    ("terrain.population_below_5m_share", "terrain", "標高5m未満人口比率", "%", "neutral", "ward", "gsi_elevation", 1, "標高取得済み250mメッシュの2025推計人口のうち中心標高5m未満の比率"),
    ("terrain.population_below_10m_share", "terrain", "標高10m未満人口比率", "%", "neutral", "ward", "gsi_elevation", 1, "標高取得済み250mメッシュの2025推計人口のうち中心標高10m未満の比率"),
]


def ensure_terrain_schema(conn) -> None:
    ensure_analysis_schema(conn)
    conn.executescript(TERRAIN_SCHEMA)
    conn.execute(
        """
        INSERT INTO dataset_catalog(dataset_key,provider,api_id,category,title,source_vintage,granularity,refresh_mode,enabled,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(dataset_key) DO UPDATE SET title=excluded.title,source_vintage=excluded.source_vintage,notes=excluded.notes
        """,
        DATASET,
    )
    conn.executemany(
        """
        INSERT INTO metric_definitions(metric_key,category,label,unit,direction,granularity,source_dataset_key,min_sample_size,description)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(metric_key) DO UPDATE SET label=excluded.label,unit=excluded.unit,description=excluded.description
        """,
        DEFINITIONS,
    )


def normalize_elevation(payload: Mapping[str, Any] | None) -> tuple[float | None, str | None]:
    if not payload:
        return None, None
    value = payload.get("elevation")
    if value in (None, "", "-----"):
        return None, None
    try:
        elevation = float(value)
    except (TypeError, ValueError):
        return None, None
    source = str(payload.get("hsrc") or "") or None
    return elevation, source


def upsert_mesh_elevation(conn, *, mesh_id: str, area_id: str, elevation_m: float, elevation_source: str | None, source_id: int) -> None:
    ensure_terrain_schema(conn)
    conn.execute(
        """
        INSERT INTO mesh_terrain_metrics(mesh_id,area_id,elevation_m,elevation_source,source_id,fetched_at)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(mesh_id) DO UPDATE SET
            area_id=excluded.area_id,elevation_m=excluded.elevation_m,
            elevation_source=excluded.elevation_source,source_id=excluded.source_id,
            fetched_at=excluded.fetched_at
        """,
        (mesh_id, area_id, elevation_m, elevation_source, source_id, datetime.now(timezone.utc).isoformat()),
    )


def _percentile(values: Iterable[float], q: float) -> float | None:
    vals = sorted(float(value) for value in values)
    if not vals:
        return None
    if len(vals) == 1:
        return round(vals[0], 3)
    position = (len(vals) - 1) * q
    lo, hi = floor(position), ceil(position)
    result = vals[lo] if lo == hi else vals[lo] + (vals[hi] - vals[lo]) * (position - lo)
    return round(result, 3)


def _grade(coverage: float) -> str:
    if coverage >= 95:
        return "A"
    if coverage >= 80:
        return "B"
    if coverage >= 50:
        return "C"
    return "D"


def compute_ward_terrain_metrics(conn) -> int:
    ensure_terrain_schema(conn)
    written = 0
    for area in conn.execute("SELECT area_id FROM areas ORDER BY area_id"):
        area_id = str(area["area_id"])
        rows = [dict(row) for row in conn.execute(
            """
            SELECT fp.mesh_id,fp.projected_population AS population_2025,
                   mtm.elevation_m,mtm.elevation_source,mtm.source_id
            FROM future_population fp
            LEFT JOIN mesh_terrain_metrics mtm ON mtm.mesh_id=fp.mesh_id
            WHERE fp.area_id=? AND fp.year=2025 AND fp.projected_population>0
            ORDER BY fp.mesh_id
            """,
            (area_id,),
        ).fetchall()]
        if not rows:
            continue
        usable = [row for row in rows if row.get("elevation_m") is not None]
        coverage = len(usable) / len(rows) * 100.0
        grade = _grade(coverage)
        elevations = [float(row["elevation_m"]) for row in usable]
        p10 = _percentile(elevations, 0.10)
        p50 = _percentile(elevations, 0.50)
        p90 = _percentile(elevations, 0.90)
        pop_total = sum(float(row["population_2025"]) for row in usable)
        weighted = (
            sum(float(row["elevation_m"]) * float(row["population_2025"]) for row in usable) / pop_total
            if pop_total > 0 else None
        )
        below5 = sum(float(row["population_2025"]) for row in usable if float(row["elevation_m"]) < 5.0)
        below10 = sum(float(row["population_2025"]) for row in usable if float(row["elevation_m"]) < 10.0)
        source_ids = [int(row["source_id"]) for row in usable if row.get("source_id") is not None]
        source_id = max(source_ids) if source_ids else None
        values = {
            "terrain.elevation_coverage": round(coverage, 3),
            "terrain.elevation_median": p50,
            "terrain.elevation_population_weighted_mean": round(weighted, 3) if weighted is not None else None,
            "terrain.elevation_p10": p10,
            "terrain.elevation_p90": p90,
            "terrain.elevation_p90_p10_range": round(p90 - p10, 3) if p90 is not None and p10 is not None else None,
            "terrain.population_below_5m_share": round(below5 / pop_total * 100.0, 3) if pop_total > 0 else None,
            "terrain.population_below_10m_share": round(below10 / pop_total * 100.0, 3) if pop_total > 0 else None,
        }
        for metric_key, value in values.items():
            upsert_metric(
                conn,
                geo_id=f"ward:{area_id}",metric_key=metric_key,period="current",
                value=value,sample_size=len(usable),source_id=source_id,
                metric_version=METRIC_VERSION,quality_grade=grade,source_year="current",
                is_estimate=0,
                notes="国土地理院標高値。250mメッシュ中心点の代表値で、メッシュ内の最低/最高標高を表すものではありません。",
            )
            written += 1
    return written


def elevation_source_distribution(conn, area_id: str) -> list[dict[str, Any]]:
    ensure_terrain_schema(conn)
    rows = conn.execute(
        """
        SELECT COALESCE(mtm.elevation_source,'不明') AS elevation_source,
               COUNT(*) AS mesh_count,
               SUM(COALESCE(fp.projected_population,0)) AS population_2025
        FROM future_population fp
        JOIN mesh_terrain_metrics mtm ON mtm.mesh_id=fp.mesh_id
        WHERE fp.area_id=? AND fp.year=2025
        GROUP BY COALESCE(mtm.elevation_source,'不明')
        ORDER BY population_2025 DESC,mesh_count DESC,elevation_source
        """,
        (area_id,),
    ).fetchall()
    total_pop = sum(float(row["population_2025"] or 0) for row in rows)
    return [
        {
            "source": row["elevation_source"],
            "mesh_count": int(row["mesh_count"]),
            "population_2025": round(float(row["population_2025"] or 0), 2),
            "population_share": round(float(row["population_2025"] or 0) / total_pop * 100.0, 3) if total_pop > 0 else None,
        }
        for row in rows
    ]
