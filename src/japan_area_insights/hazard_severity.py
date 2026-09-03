from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from .analysis_schema import ensure_analysis_schema
from .geo import mesh250_center
from .spatial_analysis import geometry_bbox, point_in_geometry

SEVERITY_SCHEMA = """
CREATE TABLE IF NOT EXISTS geo_exposure_bands (
    geo_id TEXT NOT NULL,
    layer_key TEXT NOT NULL,
    period TEXT NOT NULL,
    band_key TEXT NOT NULL,
    band_label TEXT NOT NULL,
    band_order REAL,
    exposed_mesh_count INTEGER NOT NULL,
    exposed_population REAL NOT NULL,
    total_population REAL NOT NULL,
    population_share REAL,
    source_id INTEGER,
    calculated_at TEXT NOT NULL,
    PRIMARY KEY (geo_id, layer_key, period, band_key),
    FOREIGN KEY (geo_id) REFERENCES geo_units(geo_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);
CREATE INDEX IF NOT EXISTS idx_geo_exposure_bands_layer
    ON geo_exposure_bands(layer_key, period, band_order);
"""

FLOOD_DEPTH_LABELS = {
    1: "0m以上0.5m未満",
    2: "0.5m以上3.0m未満",
    3: "3.0m以上5.0m未満",
    4: "5.0m以上10.0m未満",
    5: "10.0m以上20.0m未満",
    6: "20.0m以上",
}

SEDIMENT_ZONE_LABELS = {
    1: "土砂災害警戒区域（指定済）",
    2: "土砂災害特別警戒区域（指定済）",
    3: "土砂災害警戒区域（指定前）",
    4: "土砂災害特別警戒区域（指定前）",
}

SEDIMENT_PHENOMENON_LABELS = {
    1: "急傾斜地の崩壊",
    2: "土石流",
    3: "地滑り",
}


def ensure_severity_schema(conn) -> None:
    ensure_analysis_schema(conn)
    conn.executescript(SEVERITY_SCHEMA)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _depth_lower_bound(label: Any) -> float:
    text = str(label or "")
    numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", text)]
    if not numbers:
        return 0.0
    # Strings are normally "3m以上 〜 5m未満". The first value is the lower bound.
    return numbers[0]


def _band_flood(props: Mapping[str, Any]) -> tuple[str, str, float] | None:
    value = _number(props.get("A31a_205"))
    if value is None:
        return None
    rank = int(value)
    label = FLOOD_DEPTH_LABELS.get(rank, f"浸水深ランク{rank}")
    return f"rank_{rank}", label, float(rank)


def _band_depth_text(props: Mapping[str, Any], key: str) -> tuple[str, str, float] | None:
    label = str(props.get(key) or "").strip()
    if not label:
        return None
    order = _depth_lower_bound(label)
    band_key = re.sub(r"\W+", "_", label, flags=re.UNICODE).strip("_") or "unknown"
    return band_key, label, order


def _band_liquefaction(props: Mapping[str, Any]) -> tuple[str, str, float] | None:
    level = _number(props.get("liquefaction_tendency_level"))
    note = str(props.get("note") or "").strip()
    if level is None and not note:
        return None
    numeric = int(level) if level is not None else 0
    label = note or f"液状化発生傾向レベル{numeric}"
    return f"level_{numeric}", label, float(numeric)


def _band_embankment(props: Mapping[str, Any]) -> tuple[str, str, float] | None:
    label = str(props.get("embankment_classification") or "").strip()
    if not label:
        return None
    key = "valley_fill" if "谷埋" in label else "other_fill"
    return key, label, 0.0


def _band_sediment(props: Mapping[str, Any]) -> tuple[str, str, float] | None:
    zone_value = _number(props.get("A33_002"))
    if zone_value is None:
        return None
    zone = int(zone_value)
    phenomenon_value = _number(props.get("A33_001"))
    phenomenon = int(phenomenon_value) if phenomenon_value is not None else None
    zone_label = SEDIMENT_ZONE_LABELS.get(zone, f"区域区分{zone}")
    phenomenon_label = SEDIMENT_PHENOMENON_LABELS.get(phenomenon, "")
    label = f"{zone_label}・{phenomenon_label}" if phenomenon_label else zone_label
    # Special warning zones outrank warning zones. Designation status is retained in the key/label.
    order = 2.0 if zone in {2, 4} else 1.0
    return f"zone_{zone}_phenomenon_{phenomenon or 0}", label, order


BandParser = Callable[[Mapping[str, Any]], tuple[str, str, float] | None]

LAYER_RULES: dict[str, tuple[str, BandParser, bool]] = {
    # layer_key: (api_id, parser, choose-single-highest-band-per-mesh)
    "flood": ("XKT026", _band_flood, True),
    "storm_surge": ("XKT027", lambda props: _band_depth_text(props, "A49_003"), True),
    "tsunami": ("XKT028", lambda props: _band_depth_text(props, "A40_003"), True),
    "sediment_disaster": ("XKT029", _band_sediment, True),
    "liquefaction": ("XKT025", _band_liquefaction, True),
    "large_fill": ("XKT020", _band_embankment, False),
}


def _bucket_range(bbox: tuple[float, float, float, float], scale: int = 100) -> list[tuple[int, int]]:
    west, south, east, north = bbox
    return [
        (x, y)
        for x in range(math.floor(west * scale), math.floor(east * scale) + 1)
        for y in range(math.floor(south * scale), math.floor(north * scale) + 1)
    ]


def _layer_features(conn, api_id: str, parser: BandParser):
    parsed = []
    for row in conn.execute(
        "SELECT geometry_json,geometry_type,properties_json,source_id FROM spatial_features WHERE api_id=?",
        (api_id,),
    ):
        if row["geometry_type"] not in {"Polygon", "MultiPolygon"}:
            continue
        geometry = json.loads(row["geometry_json"])
        bbox = geometry_bbox(geometry)
        if not bbox:
            continue
        props = json.loads(row["properties_json"])
        band = parser(props)
        if band:
            parsed.append((geometry, bbox, band, row["source_id"]))
    return parsed


def compute_hazard_severity_bands(conn) -> int:
    """Compute hazard/category population bands from official source attributes.

    A mesh is represented by its center, matching the existing binary exposure
    semantics. Flood, storm-surge, tsunami and sediment zones use the strongest
    overlapping official category at that mesh. No score is produced.
    """
    ensure_severity_schema(conn)
    conn.execute("DELETE FROM geo_exposure_bands")
    written = 0
    calculated_at = datetime.now(timezone.utc).isoformat()

    area_rows = conn.execute("SELECT area_id FROM areas ORDER BY area_id").fetchall()
    population_by_area: dict[str, list[tuple[str, float, float, float, float]]] = {}
    for area_row in area_rows:
        area_id = str(area_row["area_id"])
        rows = conn.execute(
            """
            SELECT mesh_id,
                   MAX(CASE WHEN year=2025 THEN projected_population END) AS pop2025,
                   MAX(CASE WHEN year=2045 THEN projected_population END) AS pop2045
            FROM future_population WHERE area_id=? GROUP BY mesh_id
            """,
            (area_id,),
        ).fetchall()
        meshes = []
        for row in rows:
            try:
                lon, lat = mesh250_center(str(row["mesh_id"]))
            except ValueError:
                continue
            meshes.append((str(row["mesh_id"]), lon, lat, float(row["pop2025"] or 0), float(row["pop2045"] or 0)))
        population_by_area[area_id] = meshes

    for layer_key, (api_id, parser, choose_highest) in LAYER_RULES.items():
        features = _layer_features(conn, api_id, parser)
        if not features:
            continue
        buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
        for index, (_, bbox, _, _) in enumerate(features):
            for bucket in _bucket_range(bbox):
                buckets[bucket].append(index)
        source_ids = [int(feature[3]) for feature in features if feature[3] is not None]
        source_id = max(source_ids) if source_ids else None

        for area_id, meshes in population_by_area.items():
            if not meshes:
                continue
            mesh_bands: dict[str, list[tuple[str, str, float]]] = {}
            for mesh_id, lon, lat, _, _ in meshes:
                candidates = buckets.get((math.floor(lon * 100), math.floor(lat * 100)), [])
                matches = [
                    features[index][2]
                    for index in candidates
                    if point_in_geometry(lon, lat, features[index][0])
                ]
                if not matches:
                    continue
                if choose_highest:
                    best = max(matches, key=lambda band: band[2])
                    mesh_bands[mesh_id] = [best]
                else:
                    unique = {band[0]: band for band in matches}
                    mesh_bands[mesh_id] = list(unique.values())

            for period, pop_index in (("2025", 3), ("2045", 4)):
                total_population = sum(mesh[pop_index] for mesh in meshes)
                grouped: dict[str, dict[str, Any]] = {}
                for mesh in meshes:
                    for band_key, band_label, band_order in mesh_bands.get(mesh[0], []):
                        row = grouped.setdefault(
                            band_key,
                            {"label": band_label, "order": band_order, "mesh_count": 0, "population": 0.0},
                        )
                        row["mesh_count"] += 1
                        row["population"] += mesh[pop_index]
                for band_key, band in grouped.items():
                    exposed_population = float(band["population"])
                    share = round(exposed_population / total_population * 100.0, 3) if total_population > 0 else None
                    conn.execute(
                        """
                        INSERT INTO geo_exposure_bands(
                            geo_id,layer_key,period,band_key,band_label,band_order,
                            exposed_mesh_count,exposed_population,total_population,
                            population_share,source_id,calculated_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            f"ward:{area_id}", layer_key, period, band_key,
                            str(band["label"]), float(band["order"]), int(band["mesh_count"]),
                            round(exposed_population, 2), round(total_population, 2), share,
                            source_id, calculated_at,
                        ),
                    )
                    written += 1
    return written
