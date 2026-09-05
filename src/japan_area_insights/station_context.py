from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

from .analysis_schema import ensure_analysis_schema
from .db import connect
from .geo import mesh250_center
from .jshis_analysis import ensure_jshis_schema
from .spatial_analysis import geometry_bbox, point_in_geometry
from .station_areas import STATION_DEFINITION_VERSION, STATION_METRIC_VERSION
from .terrain_analysis import ensure_terrain_schema

HAZARD_APIS = {
    "XKT020": ("large_fill", "hazard_large_fill_population_share"),
    "XKT025": ("liquefaction", "hazard_liquefaction_population_share"),
    "XKT026": ("flood", "hazard_flood_population_share"),
    "XKT027": ("storm_surge", "hazard_storm_surge_population_share"),
    "XKT028": ("tsunami", "hazard_tsunami_population_share"),
    "XKT029": ("sediment_disaster", "hazard_sediment_disaster_population_share"),
}

CONTEXT_METRIC_KEYS = {
    "terrain_elevation_coverage",
    "terrain_elevation_median",
    "terrain_elevation_p10",
    "terrain_elevation_p90",
    "terrain_elevation_population_weighted_mean",
    "terrain_population_below_5m_share",
    "seismic_ground_coverage",
    "seismic_hazard_coverage",
    "seismic_arv_median",
    "seismic_30y_5lower_probability",
    "seismic_30y_5upper_probability",
    "seismic_30y_6lower_probability",
    "seismic_30y_6upper_probability",
    "hazard_large_fill_population_share",
    "hazard_liquefaction_population_share",
    "hazard_flood_population_share",
    "hazard_flood_3m_plus_population_share",
    "hazard_storm_surge_population_share",
    "hazard_tsunami_population_share",
    "hazard_sediment_disaster_population_share",
}

def _percentile(values: Iterable[float], q: float) -> float | None:
    vals = sorted(float(value) for value in values)
    if not vals:
        return None
    if len(vals) == 1:
        return round(vals[0], 3)
    position = (len(vals) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    value = vals[lo] if lo == hi else vals[lo] + (vals[hi] - vals[lo]) * (position - lo)
    return round(value, 3)

def _weighted(rows: list[Mapping[str, Any]], key: str, *, probability: bool = False) -> float | None:
    usable = [
        row for row in rows
        if row.get(key) is not None and float(row.get("population_2025") or 0) > 0
    ]
    weight = sum(float(row["population_2025"]) for row in usable)
    if weight <= 0:
        return None
    value = sum(float(row[key]) * float(row["population_2025"]) for row in usable) / weight
    if probability:
        value *= 100.0
    return round(value, 3)

def _bucket_range(bbox: tuple[float, float, float, float], scale: int = 100):
    west, south, east, north = bbox
    for x in range(math.floor(west * scale), math.floor(east * scale) + 1):
        for y in range(math.floor(south * scale), math.floor(north * scale) + 1):
            yield (x, y)

def _station_mesh_rows(conn) -> dict[str, list[dict[str, Any]]]:
    rows = conn.execute(
        """
        WITH pop AS (
            SELECT mesh_id,
                   MAX(CASE WHEN year=2025 THEN projected_population END) AS population_2025
            FROM future_population
            GROUP BY mesh_id
        )
        SELECT gu.geo_id, gum.mesh_id, COALESCE(pop.population_2025, 0) AS population_2025,
               mtm.elevation_m, mtm.source_id AS terrain_source_id,
               msm.ground_version, msm.hazard_version, msm.arv,
               msm.t30_i45_ps, msm.t30_i50_ps, msm.t30_i55_ps, msm.t30_i60_ps,
               msm.source_ground_id, msm.source_hazard_id
        FROM geo_units gu
        JOIN geo_unit_meshes gum ON gum.geo_id=gu.geo_id
        LEFT JOIN pop ON pop.mesh_id=gum.mesh_id
        LEFT JOIN mesh_terrain_metrics mtm ON mtm.mesh_id=gum.mesh_id
        LEFT JOIN mesh_seismic_metrics msm ON msm.mesh_id=gum.mesh_id
        WHERE gu.geo_type='station_area'
          AND gu.definition_version=?
          AND gu.is_active=1
        ORDER BY gu.geo_id, gum.mesh_id
        """,
        (STATION_DEFINITION_VERSION,),
    ).fetchall()
    by_geo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        item = dict(row)
        try:
            lon, lat = mesh250_center(str(item["mesh_id"]))
        except ValueError:
            continue
        item["longitude"] = lon
        item["latitude"] = lat
        by_geo[str(item["geo_id"])].append(item)
    return by_geo

def _insert_metric(
    conn,
    *,
    geo_id: str,
    key: str,
    value: float | None,
    period: str,
    sample_size: int,
    source_id: int | None,
    calculated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO geo_metrics(
            geo_id,metric_key,period,value,sample_size,source_id,metric_version,calculated_at
        ) VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(geo_id,metric_key,period,metric_version) DO UPDATE SET
            value=excluded.value,
            sample_size=excluded.sample_size,
            source_id=excluded.source_id,
            calculated_at=excluded.calculated_at
        """,
        (
            geo_id, key, period, value, sample_size, source_id,
            STATION_METRIC_VERSION, calculated_at,
        ),
    )

def compute_station_context_metrics(db_path: str | Path) -> int:
    """Compute non-scored terrain, seismic and official hazard context for station 1km areas.

    Every value is an aggregation of the station area's existing 250m mesh mapping.
    Hazard shares use the mesh center as the representative point, matching the ward
    exposure semantics. These values are context indicators, not an individual
    property safety judgement and are never folded into the total station score.
    """
    written = 0
    calculated_at = datetime.now(timezone.utc).isoformat()
    with connect(db_path) as conn:
        ensure_analysis_schema(conn)
        ensure_terrain_schema(conn)
        ensure_jshis_schema(conn)
        by_geo = _station_mesh_rows(conn)
        if not by_geo:
            return 0

        placeholders = ",".join("?" for _ in CONTEXT_METRIC_KEYS)
        conn.execute(
            f"""
            DELETE FROM geo_metrics
            WHERE metric_version=?
              AND metric_key IN ({placeholders})
              AND geo_id IN (
                  SELECT geo_id FROM geo_units
                  WHERE geo_type='station_area' AND definition_version=? AND is_active=1
              )
            """,
            (STATION_METRIC_VERSION, *sorted(CONTEXT_METRIC_KEYS), STATION_DEFINITION_VERSION),
        )

        for geo_id, rows in by_geo.items():
            total = len(rows)
            terrain_rows = [row for row in rows if row.get("elevation_m") is not None]
            terrain_source_ids = [
                int(row["terrain_source_id"]) for row in terrain_rows
                if row.get("terrain_source_id") is not None
            ]
            terrain_source_id = max(terrain_source_ids) if terrain_source_ids else None
            elevations = [float(row["elevation_m"]) for row in terrain_rows]
            terrain_pop = sum(float(row["population_2025"] or 0) for row in terrain_rows)
            weighted_elevation = (
                sum(float(row["elevation_m"]) * float(row["population_2025"] or 0) for row in terrain_rows)
                / terrain_pop if terrain_pop > 0 else None
            )
            below5 = sum(
                float(row["population_2025"] or 0)
                for row in terrain_rows if float(row["elevation_m"]) < 5.0
            )
            terrain_values = {
                "terrain_elevation_coverage": round(len(terrain_rows) / total * 100.0, 3) if total else None,
                "terrain_elevation_median": round(float(median(elevations)), 3) if elevations else None,
                "terrain_elevation_p10": _percentile(elevations, 0.10),
                "terrain_elevation_p90": _percentile(elevations, 0.90),
                "terrain_elevation_population_weighted_mean": round(weighted_elevation, 3) if weighted_elevation is not None else None,
                "terrain_population_below_5m_share": round(below5 / terrain_pop * 100.0, 3) if terrain_pop > 0 else None,
            }
            for key, value in terrain_values.items():
                _insert_metric(
                    conn, geo_id=geo_id, key=key, value=value, period="current",
                    sample_size=len(terrain_rows), source_id=terrain_source_id,
                    calculated_at=calculated_at,
                )
                written += 1

            ground_rows = [row for row in rows if row.get("ground_version")]
            hazard_rows = [row for row in rows if row.get("hazard_version")]
            ground_source_ids = [
                int(row["source_ground_id"]) for row in ground_rows
                if row.get("source_ground_id") is not None
            ]
            seismic_source_ids = [
                int(row["source_hazard_id"]) for row in hazard_rows
                if row.get("source_hazard_id") is not None
            ]
            ground_source_id = max(ground_source_ids) if ground_source_ids else None
            seismic_source_id = max(seismic_source_ids) if seismic_source_ids else None
            seismic_values = {
                "seismic_ground_coverage": round(len(ground_rows) / total * 100.0, 3) if total else None,
                "seismic_hazard_coverage": round(len(hazard_rows) / total * 100.0, 3) if total else None,
                "seismic_arv_median": round(float(median([float(row["arv"]) for row in ground_rows if row.get("arv") is not None])), 3)
                    if any(row.get("arv") is not None for row in ground_rows) else None,
                "seismic_30y_5lower_probability": _weighted(hazard_rows, "t30_i45_ps", probability=True),
                "seismic_30y_5upper_probability": _weighted(hazard_rows, "t30_i50_ps", probability=True),
                "seismic_30y_6lower_probability": _weighted(hazard_rows, "t30_i55_ps", probability=True),
                "seismic_30y_6upper_probability": _weighted(hazard_rows, "t30_i60_ps", probability=True),
            }
            for key, value in seismic_values.items():
                is_ground = key in {"seismic_ground_coverage", "seismic_arv_median"}
                source_id = ground_source_id if is_ground else seismic_source_id
                _insert_metric(
                    conn, geo_id=geo_id, key=key, value=value, period="Y2024",
                    sample_size=len(ground_rows) if is_ground else len(hazard_rows),
                    source_id=source_id, calculated_at=calculated_at,
                )
                written += 1

        for api_id, (_, metric_key) in HAZARD_APIS.items():
            feature_rows = conn.execute(
                """
                SELECT geometry_json,geometry_type,properties_json,source_id
                FROM spatial_features
                WHERE api_id=?
                """,
                (api_id,),
            ).fetchall()
            features: list[tuple[dict[str, Any], tuple[float, float, float, float], dict[str, Any], int | None]] = []
            for row in feature_rows:
                if row["geometry_type"] not in {"Polygon", "MultiPolygon"}:
                    continue
                geometry = json.loads(row["geometry_json"])
                bbox = geometry_bbox(geometry)
                if not bbox:
                    continue
                props = json.loads(row["properties_json"] or "{}")
                features.append((geometry, bbox, props, int(row["source_id"]) if row["source_id"] is not None else None))
            if not features:
                continue

            buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
            for index, (_, bbox, _, _) in enumerate(features):
                for bucket in _bucket_range(bbox):
                    buckets[bucket].append(index)
            source_ids = [row[3] for row in features if row[3] is not None]
            source_id = max(source_ids) if source_ids else None

            for geo_id, rows in by_geo.items():
                total_population = sum(float(row["population_2025"] or 0) for row in rows)
                exposed_population = 0.0
                exposed_meshes = 0
                flood_3m_population = 0.0
                flood_3m_meshes = 0
                for row in rows:
                    lon = float(row["longitude"])
                    lat = float(row["latitude"])
                    candidates = buckets.get((math.floor(lon * 100), math.floor(lat * 100)), [])
                    matches = [
                        features[index]
                        for index in candidates
                        if point_in_geometry(lon, lat, features[index][0])
                    ]
                    if not matches:
                        continue
                    pop = float(row["population_2025"] or 0)
                    exposed_population += pop
                    exposed_meshes += 1
                    if api_id == "XKT026":
                        ranks = []
                        for match in matches:
                            try:
                                ranks.append(int(float(match[2].get("A31a_205"))))
                            except (TypeError, ValueError):
                                pass
                        if ranks and max(ranks) >= 3:
                            flood_3m_population += pop
                            flood_3m_meshes += 1

                share = round(exposed_population / total_population * 100.0, 3) if total_population > 0 else None
                _insert_metric(
                    conn, geo_id=geo_id, key=metric_key, value=share, period="2025",
                    sample_size=exposed_meshes, source_id=source_id, calculated_at=calculated_at,
                )
                written += 1
                if api_id == "XKT026":
                    severe_share = round(flood_3m_population / total_population * 100.0, 3) if total_population > 0 else None
                    _insert_metric(
                        conn, geo_id=geo_id, key="hazard_flood_3m_plus_population_share",
                        value=severe_share, period="2025", sample_size=flood_3m_meshes,
                        source_id=source_id, calculated_at=calculated_at,
                    )
                    written += 1
    return written
