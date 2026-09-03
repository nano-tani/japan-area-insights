from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .analysis_catalog import DATASET_CATALOG, METRIC_DEFINITIONS, REINFOLIB_SPATIAL_LAYERS

TRANSACTION_DETAIL_COLUMNS = {
    "region": "TEXT",
    "price_per_unit": "REAL",
    "floor_plan": "TEXT",
    "land_shape": "TEXT",
    "frontage_m": "REAL",
    "total_floor_area_sqm": "REAL",
    "building_year": "INTEGER",
    "structure": "TEXT",
    "use_name": "TEXT",
    "purpose": "TEXT",
    "road_direction": "TEXT",
    "road_classification": "TEXT",
    "road_breadth_m": "REAL",
    "city_planning": "TEXT",
    "coverage_ratio": "REAL",
    "floor_area_ratio": "REAL",
    "renovation": "TEXT",
    "remarks": "TEXT",
    "district_code": "TEXT",
}

ANALYSIS_SCHEMA = """
CREATE TABLE IF NOT EXISTS dataset_catalog (
    dataset_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    api_id TEXT,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    source_vintage TEXT,
    granularity TEXT NOT NULL,
    refresh_mode TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS metric_definitions (
    metric_key TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    label TEXT NOT NULL,
    unit TEXT,
    direction TEXT NOT NULL,
    granularity TEXT NOT NULL,
    source_dataset_key TEXT,
    min_sample_size INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    FOREIGN KEY (source_dataset_key) REFERENCES dataset_catalog(dataset_key)
);

CREATE TABLE IF NOT EXISTS metric_quality (
    geo_id TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    period TEXT NOT NULL,
    metric_version TEXT NOT NULL,
    quality_grade TEXT NOT NULL,
    source_year TEXT,
    sample_size INTEGER,
    is_estimate INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (geo_id, metric_key, period, metric_version),
    FOREIGN KEY (geo_id) REFERENCES geo_units(geo_id),
    FOREIGN KEY (metric_key) REFERENCES metric_definitions(metric_key)
);

CREATE TABLE IF NOT EXISTS land_price_points (
    point_id TEXT NOT NULL,
    area_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    price_classification INTEGER NOT NULL,
    price REAL,
    last_year_price REAL,
    yoy_change REAL,
    latitude REAL,
    longitude REAL,
    use_category TEXT,
    standard_lot_number TEXT,
    residence_display TEXT,
    location_text TEXT,
    cadastral_sqm REAL,
    building_structure TEXT,
    ground_floors INTEGER,
    underground_floors INTEGER,
    front_road_type TEXT,
    front_road_azimuth TEXT,
    front_road_width_m REAL,
    gas_supply INTEGER,
    water_supply INTEGER,
    sewer_supply INTEGER,
    nearest_station TEXT,
    station_distance_m REAL,
    usage_status TEXT,
    surrounding_land_use TEXT,
    area_division TEXT,
    zoning TEXT,
    fireproof_zone TEXT,
    coverage_ratio REAL,
    floor_area_ratio REAL,
    source_id INTEGER,
    PRIMARY KEY (point_id, year, price_classification),
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);

CREATE INDEX IF NOT EXISTS idx_land_price_points_area_year
    ON land_price_points(area_id, year, price_classification);

CREATE TABLE IF NOT EXISTS spatial_features (
    api_id TEXT NOT NULL,
    feature_id TEXT NOT NULL,
    layer_key TEXT NOT NULL,
    category TEXT NOT NULL,
    area_id TEXT,
    geometry_type TEXT,
    geometry_json TEXT NOT NULL,
    properties_json TEXT NOT NULL,
    centroid_lat REAL,
    centroid_lon REAL,
    source_id INTEGER,
    PRIMARY KEY (api_id, feature_id),
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);

CREATE INDEX IF NOT EXISTS idx_spatial_features_layer_area
    ON spatial_features(layer_key, area_id);

CREATE TABLE IF NOT EXISTS geo_exposures (
    geo_id TEXT NOT NULL,
    layer_key TEXT NOT NULL,
    period TEXT NOT NULL,
    exposed_mesh_count INTEGER,
    total_mesh_count INTEGER,
    exposed_population REAL,
    total_population REAL,
    population_share REAL,
    feature_count INTEGER,
    source_id INTEGER,
    calculated_at TEXT NOT NULL,
    PRIMARY KEY (geo_id, layer_key, period),
    FOREIGN KEY (geo_id) REFERENCES geo_units(geo_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);
"""


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, declaration in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def ensure_analysis_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(ANALYSIS_SCHEMA)
    _ensure_columns(conn, "transactions", TRANSACTION_DETAIL_COLUMNS)
    _ensure_columns(conn, "station_transactions", TRANSACTION_DETAIL_COLUMNS)

    conn.executemany(
        """
        INSERT INTO dataset_catalog(
            dataset_key, provider, api_id, category, title,
            source_vintage, granularity, refresh_mode, enabled, notes
        ) VALUES (
            :dataset_key, :provider, :api_id, :category, :title,
            :source_vintage, :granularity, :refresh_mode, :enabled, :notes
        )
        ON CONFLICT(dataset_key) DO UPDATE SET
            provider=excluded.provider,
            api_id=excluded.api_id,
            category=excluded.category,
            title=excluded.title,
            source_vintage=excluded.source_vintage,
            granularity=excluded.granularity,
            refresh_mode=excluded.refresh_mode,
            enabled=excluded.enabled,
            notes=excluded.notes
        """,
        DATASET_CATALOG,
    )

    # Register all generic Reinfolib GIS layers in the same catalog.
    spatial_catalog = [
        {
            "dataset_key": f"reinfolib_{api_id.lower()}",
            "provider": "国土交通省 不動産情報ライブラリ",
            "api_id": api_id,
            "category": category,
            "title": title,
            "source_vintage": vintage,
            "granularity": "spatial",
            "refresh_mode": "extended",
            "enabled": 1,
            "notes": "250mメッシュ中心との重なりで区域曝露を集計",
        }
        for api_id, (layer_key, category, title, vintage) in REINFOLIB_SPATIAL_LAYERS.items()
    ]
    conn.executemany(
        """
        INSERT INTO dataset_catalog(
            dataset_key, provider, api_id, category, title,
            source_vintage, granularity, refresh_mode, enabled, notes
        ) VALUES (
            :dataset_key, :provider, :api_id, :category, :title,
            :source_vintage, :granularity, :refresh_mode, :enabled, :notes
        )
        ON CONFLICT(dataset_key) DO UPDATE SET
            source_vintage=excluded.source_vintage,
            title=excluded.title,
            category=excluded.category,
            notes=excluded.notes
        """,
        spatial_catalog,
    )

    conn.executemany(
        """
        INSERT INTO metric_definitions(
            metric_key, category, label, unit, direction, granularity,
            source_dataset_key, min_sample_size, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(metric_key) DO UPDATE SET
            category=excluded.category,
            label=excluded.label,
            unit=excluded.unit,
            direction=excluded.direction,
            granularity=excluded.granularity,
            source_dataset_key=excluded.source_dataset_key,
            min_sample_size=excluded.min_sample_size,
            description=excluded.description
        """,
        METRIC_DEFINITIONS,
    )


def upsert_metric(
    conn: sqlite3.Connection,
    *,
    geo_id: str,
    metric_key: str,
    period: str,
    value: float | int | None,
    sample_size: int | None,
    source_id: int | None,
    metric_version: str,
    quality_grade: str,
    source_year: str | None = None,
    is_estimate: bool = False,
    notes: str | None = None,
) -> None:
    calculated_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO geo_metrics(
            geo_id, metric_key, period, value, sample_size,
            source_id, metric_version, calculated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(geo_id, metric_key, period, metric_version) DO UPDATE SET
            value=excluded.value,
            sample_size=excluded.sample_size,
            source_id=excluded.source_id,
            calculated_at=excluded.calculated_at
        """,
        (geo_id, metric_key, period, value, sample_size, source_id, metric_version, calculated_at),
    )
    conn.execute(
        """
        INSERT INTO metric_quality(
            geo_id, metric_key, period, metric_version, quality_grade,
            source_year, sample_size, is_estimate, notes, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(geo_id, metric_key, period, metric_version) DO UPDATE SET
            quality_grade=excluded.quality_grade,
            source_year=excluded.source_year,
            sample_size=excluded.sample_size,
            is_estimate=excluded.is_estimate,
            notes=excluded.notes,
            updated_at=excluded.updated_at
        """,
        (
            geo_id,
            metric_key,
            period,
            metric_version,
            quality_grade,
            source_year,
            sample_size,
            1 if is_estimate else 0,
            notes,
            calculated_at,
        ),
    )
