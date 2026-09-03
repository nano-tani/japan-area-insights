from pathlib import Path

from japan_area_insights.analysis_export import export_analysis_data
from japan_area_insights.db import connect, initialize
from japan_area_insights.terrain_analysis import (
    compute_ward_terrain_metrics,
    ensure_terrain_schema,
    normalize_elevation,
    upsert_mesh_elevation,
)
from japan_area_insights.ward_maps import build_ward_mesh_payload


def _seed(conn):
    conn.execute("INSERT INTO areas(area_id,prefecture_code,municipality_code,prefecture_name,municipality_name) VALUES ('13101','13','13101','東京都','千代田区')")
    conn.execute("INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active) VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)")
    for mesh_id, pop in (("5339461111", 100.0), ("5339461112", 300.0)):
        conn.execute("INSERT INTO future_population(area_id,mesh_id,year,projected_population) VALUES ('13101',?,2025,?)", (mesh_id, pop))
        conn.execute("INSERT INTO future_population(area_id,mesh_id,year,projected_population) VALUES ('13101',?,2045,?)", (mesh_id, pop * 1.1))


def test_normalize_gsi_elevation():
    assert normalize_elevation({"elevation": "12.3", "hsrc": "5m（レーザ）"}) == (12.3, "5m（レーザ）")
    assert normalize_elevation({"elevation": "-----", "hsrc": "-----"}) == (None, None)


def test_terrain_metrics_and_exports(tmp_path: Path):
    db_path = tmp_path / "terrain.db"
    initialize(db_path)
    with connect(db_path) as conn:
        _seed(conn)
        ensure_terrain_schema(conn)
        source_id = conn.execute("INSERT INTO data_sources(source_name,dataset_id,source_url,fetched_at) VALUES ('国土地理院','GSI:elevation','https://example.test','2026-09-01')").lastrowid
        upsert_mesh_elevation(conn, mesh_id="5339461111", area_id="13101", elevation_m=2.0, elevation_source="5m（レーザ）", source_id=source_id)
        upsert_mesh_elevation(conn, mesh_id="5339461112", area_id="13101", elevation_m=12.0, elevation_source="10m", source_id=source_id)
        assert compute_ward_terrain_metrics(conn) == 8
        metrics = {row["metric_key"]: row["value"] for row in conn.execute("SELECT metric_key,value FROM geo_metrics WHERE geo_id='ward:13101'")}
        assert metrics["terrain.elevation_coverage"] == 100
        assert metrics["terrain.elevation_median"] == 7
        assert metrics["terrain.elevation_population_weighted_mean"] == 9.5
        assert metrics["terrain.population_below_5m_share"] == 25
        assert metrics["terrain.population_below_10m_share"] == 25
        map_payload = build_ward_mesh_payload(conn, "13101")
        mesh = next(row for row in map_payload["meshes"] if row["mesh_id"] == "5339461111")
        assert mesh["elevation_m"] == 2
        assert mesh["elevation_source"] == "5m（レーザ）"
        assert map_payload["terrain"]["provider"] == "国土地理院"

    output = tmp_path / "webdata"
    export_analysis_data(db_path, output)
    import json
    payload = json.loads((output / "analysis" / "ward" / "13101.json").read_text(encoding="utf-8"))
    assert "terrain" in payload["metrics"]
    assert len(payload["terrain_sources"]) == 2
    assert payload["terrain_note"]["provider"] == "国土地理院"
