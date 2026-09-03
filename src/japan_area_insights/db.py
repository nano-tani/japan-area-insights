from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS areas (
    area_id TEXT PRIMARY KEY,
    prefecture_code TEXT NOT NULL,
    municipality_code TEXT NOT NULL UNIQUE,
    prefecture_name TEXT NOT NULL,
    municipality_name TEXT NOT NULL,
    latitude REAL,
    longitude REAL
);

CREATE TABLE IF NOT EXISTS area_prices (
    area_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    official_land_price REAL,
    prefectural_land_price REAL,
    avg_transaction_unit_price REAL,
    median_transaction_unit_price REAL,
    yoy_change REAL,
    change_3y REAL,
    change_5y REAL,
    transaction_count INTEGER,
    source_id INTEGER,
    PRIMARY KEY (area_id, year),
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER,
    transaction_date TEXT,
    price_category TEXT,
    property_type TEXT,
    district_name TEXT,
    total_price REAL,
    unit_price REAL,
    area_sqm REAL,
    source_id INTEGER,
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);

CREATE INDEX IF NOT EXISTS idx_transactions_area_year ON transactions(area_id, year);

CREATE TABLE IF NOT EXISTS population (
    area_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    population INTEGER,
    households INTEGER,
    population_change_rate REAL,
    household_change_rate REAL,
    age_0_19 INTEGER,
    age_20_39 INTEGER,
    age_40_64 INTEGER,
    age_65_plus INTEGER,
    single_households INTEGER,
    source_id INTEGER,
    PRIMARY KEY (area_id, year),
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);

CREATE TABLE IF NOT EXISTS future_population (
    area_id TEXT NOT NULL,
    mesh_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    projected_population REAL,
    retention_rate REAL,
    source_id INTEGER,
    PRIMARY KEY (area_id, mesh_id, year),
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);

CREATE TABLE IF NOT EXISTS facilities (
    facility_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL,
    facility_type TEXT NOT NULL,
    facility_subtype TEXT,
    facility_name TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    source_id INTEGER,
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);

CREATE INDEX IF NOT EXISTS idx_facilities_area_type ON facilities(area_id, facility_type);

CREATE TABLE IF NOT EXISTS stations (
    station_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL,
    station_code TEXT,
    group_code TEXT,
    station_name TEXT NOT NULL,
    line_name TEXT,
    operator_name TEXT,
    passenger_count INTEGER,
    passenger_year INTEGER,
    latitude REAL,
    longitude REAL,
    source_id INTEGER,
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);

CREATE INDEX IF NOT EXISTS idx_stations_area ON stations(area_id);

CREATE TABLE IF NOT EXISTS urban_planning (
    planning_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL,
    planning_type TEXT NOT NULL,
    planning_name TEXT,
    source_id INTEGER,
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);

CREATE TABLE IF NOT EXISTS hazards (
    hazard_id TEXT PRIMARY KEY,
    area_id TEXT NOT NULL,
    hazard_type TEXT NOT NULL,
    risk_label TEXT,
    source_id INTEGER,
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);

CREATE TABLE IF NOT EXISTS area_scores (
    area_id TEXT NOT NULL,
    calculation_date TEXT NOT NULL,
    price_score REAL,
    population_score REAL,
    future_population_score REAL,
    convenience_score REAL,
    transport_score REAL,
    transaction_score REAL,
    total_score REAL,
    confidence TEXT NOT NULL,
    data_completeness REAL,
    score_version TEXT NOT NULL,
    PRIMARY KEY (area_id, calculation_date, score_version),
    FOREIGN KEY (area_id) REFERENCES areas(area_id)
);

CREATE TABLE IF NOT EXISTS ai_summaries (
    area_id TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    model_name TEXT,
    summary TEXT NOT NULL,
    PRIMARY KEY (area_id, input_hash),
    FOREIGN KEY (area_id) REFERENCES areas(area_id)
);

CREATE TABLE IF NOT EXISTS data_sources (
    source_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    dataset_id TEXT,
    source_url TEXT NOT NULL,
    terms_url TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    raw_hash TEXT
);
"""

MIGRATION_COLUMNS = {
    "facilities": {
        "facility_subtype": "TEXT",
        "address": "TEXT",
    },
    "stations": {
        "station_code": "TEXT",
        "group_code": "TEXT",
        "operator_name": "TEXT",
        "passenger_count": "INTEGER",
        "passenger_year": "INTEGER",
    },
}


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_columns(conn: sqlite3.Connection) -> None:
    for table, columns in MIGRATION_COLUMNS.items():
        existing = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}
        for column, declaration in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def initialize(db_path: str | Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _ensure_columns(conn)
