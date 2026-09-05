from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
from statistics import median
from typing import Any

def _distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6_371_008.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return radius * 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))

def _weighted(meshes: list[dict[str, Any]], key: str) -> float | None:
    usable = [
        mesh for mesh in meshes
        if mesh.get(key) is not None and float(mesh.get("population_2025") or 0) > 0
    ]
    weight = sum(float(mesh["population_2025"]) for mesh in usable)
    if weight <= 0:
        return None
    return round(
        sum(float(mesh[key]) * float(mesh["population_2025"]) for mesh in usable) / weight,
        3,
    )

def _summary(meshes: list[dict[str, Any]]) -> dict[str, Any]:
    pop2025 = [float(mesh["population_2025"]) for mesh in meshes if mesh.get("population_2025") is not None]
    pop2045 = [float(mesh["population_2045"]) for mesh in meshes if mesh.get("population_2045") is not None]
    retention = [float(mesh["retention_2045"]) for mesh in meshes if mesh.get("retention_2045") is not None]
    elevations = [float(mesh["elevation_m"]) for mesh in meshes if mesh.get("elevation_m") is not None]
    terrain_pop = sum(float(mesh.get("population_2025") or 0) for mesh in meshes if mesh.get("elevation_m") is not None)
    below5 = sum(
        float(mesh.get("population_2025") or 0)
        for mesh in meshes
        if mesh.get("elevation_m") is not None and float(mesh["elevation_m"]) < 5.0
    )
    seismic_usable = [mesh for mesh in meshes if mesh.get("earthquake_probability_30y_6lower") is not None]
    return {
        "mesh_count": len(meshes),
        "population_2025_total": round(sum(pop2025), 2) if pop2025 else None,
        "population_2045_total": round(sum(pop2045), 2) if pop2045 else None,
        "retention_2045_area": round(sum(pop2045) / sum(pop2025) * 100.0, 2)
            if pop2025 and pop2045 and sum(pop2025) > 0 else None,
        "retention_2045_mesh_median": round(float(median(retention)), 2) if retention else None,
        "terrain": {
            "coverage": round(len(elevations) / len(meshes) * 100.0, 2) if meshes else None,
            "elevation_median": round(float(median(elevations)), 2) if elevations else None,
            "elevation_population_weighted_mean": _weighted(meshes, "elevation_m"),
            "population_below_5m_share": round(below5 / terrain_pop * 100.0, 2) if terrain_pop > 0 else None,
        },
        "seismic": {
            "coverage": round(len(seismic_usable) / len(meshes) * 100.0, 2) if meshes else None,
            "earthquake_probability_30y_5lower_population_weighted": _weighted(meshes, "earthquake_probability_30y_5lower"),
            "earthquake_probability_30y_5upper_population_weighted": _weighted(meshes, "earthquake_probability_30y_5upper"),
            "earthquake_probability_30y_6lower_population_weighted": _weighted(meshes, "earthquake_probability_30y_6lower"),
            "earthquake_probability_30y_6upper_population_weighted": _weighted(meshes, "earthquake_probability_30y_6upper"),
        },
    }

def export_station_mesh_maps_from_public_data(output_dir: str | Path) -> int:
    """Build station 1km mesh snapshots from already-published ward mesh JSON.

    This deliberately reuses the same 250m mesh-center radius definition as the
    database station areas, so GitHub Pages can materialize station maps without
    shipping the SQLite database in the deployment artifact.
    """
    data_dir = Path(output_dir)
    station_index = data_dir / "geo" / "index.json"
    ward_root = data_dir / "map" / "ward"
    target_root = data_dir / "map" / "station"
    target_root.mkdir(parents=True, exist_ok=True)
    if not station_index.exists() or not ward_root.exists():
        return 0

    index = json.loads(station_index.read_text(encoding="utf-8"))
    by_mesh: dict[str, dict[str, Any]] = {}
    terrain_meta: dict[str, Any] = {}
    seismic_meta: dict[str, Any] = {}
    for path in sorted(ward_root.glob("*/mesh250.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        terrain_meta = terrain_meta or dict(payload.get("terrain") or {})
        seismic_meta = seismic_meta or dict(payload.get("seismic") or {})
        for mesh in payload.get("meshes", []) or []:
            mesh_id = str(mesh.get("mesh_id") or "")
            if mesh_id:
                by_mesh.setdefault(mesh_id, mesh)

    stations = index.get("station_areas", []) or []
    valid_codes = {str(row.get("station_code") or "") for row in stations}
    for child in target_root.iterdir():
        if child.is_dir() and child.name not in valid_codes:
            shutil.rmtree(child)
        elif child.is_file() and child.suffix == ".json":
            child.unlink()

    all_meshes = list(by_mesh.values())
    written = 0
    for station in stations:
        code = str(station.get("station_code") or "").strip()
        if not code or station.get("latitude") is None or station.get("longitude") is None:
            continue
        lat = float(station["latitude"])
        lon = float(station["longitude"])
        radius = int(station.get("radius_m") or 1000)
        lat_delta = radius / 111_320.0 * 1.10
        lon_delta = radius / (111_320.0 * max(0.2, math.cos(math.radians(lat)))) * 1.10
        selected = []
        for mesh in all_meshes:
            mesh_lat = float(mesh["latitude"])
            mesh_lon = float(mesh["longitude"])
            if abs(mesh_lat - lat) > lat_delta or abs(mesh_lon - lon) > lon_delta:
                continue
            if _distance_m(lon, lat, mesh_lon, mesh_lat) <= radius:
                selected.append(mesh)
        selected.sort(key=lambda row: (float(row["latitude"]), float(row["longitude"]), str(row.get("mesh_id") or "")))
        payload = {
            "station_code": code,
            "name": station.get("name"),
            "primary_ward_name": station.get("primary_ward_name"),
            "latitude": lat,
            "longitude": lon,
            "radius_m": radius,
            "mesh_size": "250m",
            "derived_from": "published ward mesh250 snapshots",
            "summary": _summary(selected),
            "terrain": {
                **terrain_meta,
                "note": "駅1km圏に含まれる250mメッシュ中心点の標高。個別物件やメッシュ内の最低・最高標高ではありません。",
            },
            "seismic": {
                **seismic_meta,
                "note": "駅1km圏に含まれる250m代表値・確率論モデル。個別地点の安全性や将来の発生を保証しません。",
            },
            "meshes": selected,
        }
        station_dir = target_root / code
        station_dir.mkdir(parents=True, exist_ok=True)
        (station_dir / "mesh250.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        written += 1
    return written
