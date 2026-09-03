from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import connect
from .geo import mesh250_center
from .jshis_analysis import ensure_jshis_schema
from .terrain_analysis import ensure_terrain_schema

MESH_LAT_DEG = 7.5 / 3600.0
MESH_LON_DEG = 11.25 / 3600.0
MAP_YEARS = (2025, 2045)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def build_ward_mesh_payload(conn, area_id: str) -> dict[str, Any]:
    ensure_jshis_schema(conn)
    ensure_terrain_schema(conn)
    rows = conn.execute(
        """
        SELECT fp.mesh_id, fp.year, fp.projected_population,
               msm.microtopography_name,msm.avs,msm.arv,
               msm.t30_i45_ps,msm.t30_i50_ps,msm.t30_i55_ps,msm.t30_i60_ps,
               msm.t30_p03_si,msm.t30_p06_si,
               mtm.elevation_m,mtm.elevation_source
        FROM future_population fp
        LEFT JOIN mesh_seismic_metrics msm ON msm.mesh_id=fp.mesh_id
        LEFT JOIN mesh_terrain_metrics mtm ON mtm.mesh_id=fp.mesh_id
        WHERE fp.area_id=? AND fp.year IN (2025, 2045)
        ORDER BY fp.mesh_id, fp.year
        """,
        (area_id,),
    ).fetchall()

    by_mesh: dict[str, dict[str, Any]] = {}
    for row in rows:
        mesh_id = str(row["mesh_id"])
        item = by_mesh.setdefault(mesh_id, {"population": {}})
        item["population"][int(row["year"])] = _number(row["projected_population"])
        for key in (
            "microtopography_name", "avs", "arv",
            "t30_i45_ps", "t30_i50_ps", "t30_i55_ps", "t30_i60_ps",
            "t30_p03_si", "t30_p06_si", "elevation_m", "elevation_source",
        ):
            if row[key] is not None:
                item[key] = row[key]

    meshes: list[dict[str, Any]] = []
    longitudes: list[float] = []
    latitudes: list[float] = []
    for mesh_id, item in by_mesh.items():
        values = item["population"]
        try:
            longitude, latitude = mesh250_center(mesh_id)
        except ValueError:
            continue
        pop_2025 = values.get(2025)
        pop_2045 = values.get(2045)
        retention = round(pop_2045 / pop_2025 * 100.0, 2) if pop_2025 not in (None, 0) and pop_2045 is not None else None
        meshes.append({
            "mesh_id": mesh_id,
            "longitude": round(longitude, 7),
            "latitude": round(latitude, 7),
            "population_2025": pop_2025,
            "population_2045": pop_2045,
            "retention_2045": retention,
            "elevation_m": _number(item.get("elevation_m")),
            "elevation_source": item.get("elevation_source"),
            "microtopography": item.get("microtopography_name"),
            "avs30": _number(item.get("avs")),
            "amplification_arv": _number(item.get("arv")),
            "earthquake_probability_30y_5lower": round(float(item["t30_i45_ps"]) * 100.0, 3) if item.get("t30_i45_ps") is not None else None,
            "earthquake_probability_30y_5upper": round(float(item["t30_i50_ps"]) * 100.0, 3) if item.get("t30_i50_ps") is not None else None,
            "earthquake_probability_30y_6lower": round(float(item["t30_i55_ps"]) * 100.0, 3) if item.get("t30_i55_ps") is not None else None,
            "earthquake_probability_30y_6upper": round(float(item["t30_i60_ps"]) * 100.0, 3) if item.get("t30_i60_ps") is not None else None,
            "earthquake_intensity_30y_p03": _number(item.get("t30_p03_si")),
            "earthquake_intensity_30y_p06": _number(item.get("t30_p06_si")),
        })
        longitudes.append(longitude)
        latitudes.append(latitude)

    station_rows = conn.execute(
        """
        SELECT station_id, group_code, station_name, latitude, longitude, passenger_count
        FROM stations
        WHERE area_id=? AND latitude IS NOT NULL AND longitude IS NOT NULL
        ORDER BY station_name, station_id
        """,
        (area_id,),
    ).fetchall()
    stations_by_group: dict[str, dict[str, Any]] = {}
    for row in station_rows:
        key = str(row["group_code"] or row["station_id"])
        candidate = {
            "group_code": key,
            "name": str(row["station_name"]),
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "passenger_count": int(row["passenger_count"]) if row["passenger_count"] is not None else None,
        }
        existing = stations_by_group.get(key)
        if existing is None:
            stations_by_group[key] = candidate
        elif candidate["passenger_count"] is not None:
            previous = existing.get("passenger_count")
            if previous is None or candidate["passenger_count"] > previous:
                existing["passenger_count"] = candidate["passenger_count"]

    bounds = None
    if longitudes and latitudes:
        bounds = {
            "west": min(longitudes) - MESH_LON_DEG / 2.0,
            "east": max(longitudes) + MESH_LON_DEG / 2.0,
            "south": min(latitudes) - MESH_LAT_DEG / 2.0,
            "north": max(latitudes) + MESH_LAT_DEG / 2.0,
        }

    values_2025 = [m["population_2025"] for m in meshes if m["population_2025"] is not None]
    values_2045 = [m["population_2045"] for m in meshes if m["population_2045"] is not None]
    retention_values = [m["retention_2045"] for m in meshes if m["retention_2045"] is not None]

    return {
        "area_id": area_id,
        "mesh_size": "250m",
        "years": list(MAP_YEARS),
        "bounds": bounds,
        "summary": {
            "mesh_count": len(meshes),
            "population_2025_total": round(sum(values_2025), 2) if values_2025 else None,
            "population_2045_total": round(sum(values_2045), 2) if values_2045 else None,
            "retention_2045_area": round(sum(values_2045) / sum(values_2025) * 100.0, 2) if values_2025 and values_2045 and sum(values_2025) != 0 else None,
            "retention_2045_mesh_median": round(sorted(retention_values)[len(retention_values) // 2], 2) if retention_values else None,
        },
        "terrain": {
            "provider": "国土地理院",
            "note": "250mメッシュ中心点の標高。メッシュ内の最低・最高標高を示すものではありません。",
        },
        "seismic": {
            "provider": "防災科学技術研究所 J-SHIS（地震ハザードステーション）",
            "ground_version": "V4",
            "hazard_version": "Y2024",
            "note": "250m代表値・確率論モデル。個別地点の安全性や将来の発生を保証しません。",
        },
        "meshes": meshes,
        "stations": list(stations_by_group.values()),
    }


def export_ward_mesh_maps(db_path: str | Path, output_dir: str | Path) -> None:
    output = Path(output_dir) / "map" / "ward"
    output.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        ensure_jshis_schema(conn)
        ensure_terrain_schema(conn)
        area_ids = [str(row["area_id"]) for row in conn.execute("SELECT area_id FROM areas ORDER BY area_id")]
        for area_id in area_ids:
            area_dir = output / area_id
            area_dir.mkdir(parents=True, exist_ok=True)
            payload = build_ward_mesh_payload(conn, area_id)
            (area_dir / "mesh250.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
