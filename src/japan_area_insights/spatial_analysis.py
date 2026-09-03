from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .analysis_catalog import REINFOLIB_SPATIAL_LAYERS
from .analysis_schema import ensure_analysis_schema
from .geo import geometry_center, mesh250_center, mesh_code_250m


def _feature_id(api_id: str, feature: Mapping[str, Any]) -> str:
    props = feature.get("properties") or {}
    for key in (
        "id", "ID", "feature_id", "OBJECTID", "objectid", "gid", "code",
        "A29_001", "A48_001", "P29_001", "N03_007",
    ):
        value = props.get(key)
        if value not in (None, ""):
            return hashlib.sha256(f"{api_id}|{key}|{value}".encode()).hexdigest()[:32]
    canonical = json.dumps(feature, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{api_id}|{canonical}".encode("utf-8")).hexdigest()[:32]


def _walk_points(value: Any, points: list[tuple[float, float]]) -> None:
    if (
        isinstance(value, (list, tuple))
        and len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        points.append((float(value[0]), float(value[1])))
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _walk_points(child, points)


def geometry_bbox(geometry: Mapping[str, Any] | None) -> tuple[float, float, float, float] | None:
    if not geometry:
        return None
    points: list[tuple[float, float]] = []
    _walk_points(geometry.get("coordinates"), points)
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _point_in_ring(lon: float, lat: float, ring: list[Any]) -> bool:
    inside = False
    if len(ring) < 3:
        return False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = float(ring[i][0]), float(ring[i][1])
        xj, yj = float(ring[j][0]), float(ring[j][1])
        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _point_in_polygon(lon: float, lat: float, polygon: list[Any]) -> bool:
    if not polygon or not _point_in_ring(lon, lat, polygon[0]):
        return False
    return not any(_point_in_ring(lon, lat, hole) for hole in polygon[1:])


def point_in_geometry(lon: float, lat: float, geometry: Mapping[str, Any] | None) -> bool:
    if not geometry:
        return False
    kind = str(geometry.get("type") or "")
    coordinates = geometry.get("coordinates") or []
    if kind == "Polygon":
        return _point_in_polygon(lon, lat, coordinates)
    if kind == "MultiPolygon":
        return any(_point_in_polygon(lon, lat, polygon) for polygon in coordinates)
    return False


def normalize_spatial_features(
    api_id: str,
    payload: Mapping[str, Any],
    *,
    mesh_to_area: Mapping[str, str],
    allowed_area_ids: Iterable[str],
) -> list[dict[str, Any]]:
    if api_id not in REINFOLIB_SPATIAL_LAYERS:
        raise ValueError(f"unsupported extended spatial API: {api_id}")
    layer_key, category, _, _ = REINFOLIB_SPATIAL_LAYERS[api_id]
    allowed = set(map(str, allowed_area_ids))
    result: dict[str, dict[str, Any]] = {}
    for feature in payload.get("features", []) or []:
        if not isinstance(feature, Mapping):
            continue
        geometry = feature.get("geometry") or {}
        props = feature.get("properties") or {}
        center = geometry_center(geometry)
        area_id: str | None = None
        if center:
            try:
                area_id = mesh_to_area.get(mesh_code_250m(center[0], center[1]))
            except ValueError:
                area_id = None
        # Keep cross-boundary polygons even when their centroid is outside a ward;
        # exposure is calculated against mesh centers later.
        bbox = geometry_bbox(geometry)
        if not bbox:
            continue
        tokyo_bbox = (139.50, 35.45, 140.00, 35.90)
        if bbox[2] < tokyo_bbox[0] or bbox[0] > tokyo_bbox[2] or bbox[3] < tokyo_bbox[1] or bbox[1] > tokyo_bbox[3]:
            continue
        if area_id is not None and area_id not in allowed:
            area_id = None
        fid = _feature_id(api_id, feature)
        result[fid] = {
            "api_id": api_id,
            "feature_id": fid,
            "layer_key": layer_key,
            "category": category,
            "area_id": area_id,
            "geometry_type": str(geometry.get("type") or "") or None,
            "geometry_json": json.dumps(geometry, ensure_ascii=False, separators=(",", ":")),
            "properties_json": json.dumps(props, ensure_ascii=False, separators=(",", ":")),
            "centroid_lat": center[1] if center else None,
            "centroid_lon": center[0] if center else None,
        }
    return list(result.values())


def _bucket_range(bbox: tuple[float, float, float, float], scale: int = 100) -> Iterable[tuple[int, int]]:
    west, south, east, north = bbox
    x0, x1 = math.floor(west * scale), math.floor(east * scale)
    y0, y1 = math.floor(south * scale), math.floor(north * scale)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            yield x, y


def compute_layer_exposures(conn, api_id: str, *, source_id: int | None = None) -> int:
    """Summarize polygon layer coverage using 250m mesh centers.

    This is deliberately an exposure indicator, not a hazard score.  A mesh is
    counted when its center lies inside at least one polygon from the layer.
    """
    ensure_analysis_schema(conn)
    if api_id not in REINFOLIB_SPATIAL_LAYERS:
        return 0
    layer_key, category, _, vintage = REINFOLIB_SPATIAL_LAYERS[api_id]
    feature_rows = conn.execute(
        "SELECT geometry_json, geometry_type, area_id FROM spatial_features WHERE api_id=?",
        (api_id,),
    ).fetchall()
    polygon_features: list[tuple[dict[str, Any], tuple[float, float, float, float]]] = []
    for row in feature_rows:
        if row["geometry_type"] not in {"Polygon", "MultiPolygon"}:
            continue
        geometry = json.loads(row["geometry_json"])
        bbox = geometry_bbox(geometry)
        if bbox:
            polygon_features.append((geometry, bbox))

    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, (_, bbox) in enumerate(polygon_features):
        for bucket in _bucket_range(bbox):
            buckets[bucket].append(index)

    area_rows = conn.execute("SELECT area_id FROM areas ORDER BY area_id").fetchall()
    written = 0
    now = datetime.now(timezone.utc).isoformat()
    for area_row in area_rows:
        area_id = str(area_row["area_id"])
        geo_id = f"ward:{area_id}"
        pop_rows = conn.execute(
            """
            SELECT mesh_id,
                   MAX(CASE WHEN year=2025 THEN projected_population END) AS pop2025,
                   MAX(CASE WHEN year=2045 THEN projected_population END) AS pop2045
            FROM future_population
            WHERE area_id=?
            GROUP BY mesh_id
            """,
            (area_id,),
        ).fetchall()
        meshes: list[tuple[str, float, float, float, float]] = []
        for row in pop_rows:
            try:
                lon, lat = mesh250_center(str(row["mesh_id"]))
            except ValueError:
                continue
            meshes.append((str(row["mesh_id"]), lon, lat, float(row["pop2025"] or 0), float(row["pop2045"] or 0)))
        if not meshes:
            continue

        exposed: set[str] = set()
        for mesh_id, lon, lat, _, _ in meshes:
            candidates = buckets.get((math.floor(lon * 100), math.floor(lat * 100)), [])
            if any(point_in_geometry(lon, lat, polygon_features[index][0]) for index in candidates):
                exposed.add(mesh_id)

        feature_count = conn.execute(
            "SELECT COUNT(*) FROM spatial_features WHERE api_id=? AND area_id=?",
            (api_id, area_id),
        ).fetchone()[0]
        for period, pop_index in (("2025", 3), ("2045", 4)):
            total_pop = sum(mesh[pop_index] for mesh in meshes)
            exposed_pop = sum(mesh[pop_index] for mesh in meshes if mesh[0] in exposed)
            share = round(exposed_pop / total_pop * 100.0, 3) if total_pop > 0 else None
            conn.execute(
                """
                INSERT INTO geo_exposures(
                    geo_id, layer_key, period, exposed_mesh_count, total_mesh_count,
                    exposed_population, total_population, population_share,
                    feature_count, source_id, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(geo_id, layer_key, period) DO UPDATE SET
                    exposed_mesh_count=excluded.exposed_mesh_count,
                    total_mesh_count=excluded.total_mesh_count,
                    exposed_population=excluded.exposed_population,
                    total_population=excluded.total_population,
                    population_share=excluded.population_share,
                    feature_count=excluded.feature_count,
                    source_id=excluded.source_id,
                    calculated_at=excluded.calculated_at
                """,
                (
                    geo_id,
                    layer_key,
                    period,
                    len(exposed),
                    len(meshes),
                    round(exposed_pop, 2),
                    round(total_pop, 2),
                    share,
                    int(feature_count),
                    source_id,
                    now,
                ),
            )
            written += 1
    return written
