from __future__ import annotations

import json

from japan_area_insights.analysis_schema import ensure_analysis_schema
from japan_area_insights.db import connect, initialize
from japan_area_insights.jshis_analysis import ensure_jshis_schema
from japan_area_insights.station_context import compute_station_context_metrics
from japan_area_insights.terrain_analysis import ensure_terrain_schema


MESH_ID = "5339465833"
LON = 139.8515625
LAT = 35.715625
GEO_ID = "station:003274:r1000:v1"


def _insert_base(conn) -> None:
    conn.execute(
        """
        INSERT INTO areas(
            area_id,prefecture_code,municipality_code,prefecture_name,municipality_name,latitude,longitude
        ) VALUES ('13122','13','13122','東京都','葛飾区',35.74,139.85)
        """
    )
    conn.execute(
        """
        INSERT INTO geo_units(
            geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,
            latitude,longitude,radius_m,definition_version,is_active
        ) VALUES (?, 'station_area','003274','お花茶屋','13122','13',?,?,1000,'r1000:v1',1)
        """,
        (GEO_ID, LAT, LON),
    )
    conn.execute(
        "INSERT INTO geo_unit_meshes(geo_id,mesh_id,weight,method,distance_m) VALUES (?,?,?,?,?)",
        (GEO_ID, MESH_ID, 1.0, "station_radius_center", 0.0),
    )
    conn.execute(
        """
        INSERT INTO future_population(area_id,mesh_id,year,projected_population,retention_rate,source_id)
        VALUES ('13122',?,2025,100.0,100.0,NULL)
        """,
        (MESH_ID,),
    )


def test_station_context_metrics_include_terrain_seismic_and_flood(tmp_path):
    db_path = tmp_path / "test.db"
    initialize(db_path)
    with connect(db_path) as conn:
        _insert_base(conn)
        ensure_analysis_schema(conn)
        ensure_terrain_schema(conn)
        ensure_jshis_schema(conn)
        conn.execute(
            """
            INSERT INTO mesh_terrain_metrics(mesh_id,area_id,elevation_m,elevation_source,source_id,fetched_at)
            VALUES (?, '13122', 3.0, '5m（レーザ）', NULL, '2026-09-05T00:00:00+00:00')
            """,
            (MESH_ID,),
        )
        conn.execute(
            """
            INSERT INTO mesh_seismic_metrics(
                mesh_id,area_id,ground_version,microtopography_code,microtopography_name,
                avs,arv,hazard_version,t30_i45_ps,t30_i50_ps,t30_i55_ps,t30_i60_ps,
                source_ground_id,source_hazard_id,fetched_at
            ) VALUES (?, '13122','V4','1','テスト地形',250,1.4,'Y2024',0.9,0.8,0.6,0.3,NULL,NULL,'2026-09-05T00:00:00+00:00')
            """,
            (MESH_ID,),
        )
        polygon = {
            "type": "Polygon",
            "coordinates": [[
                [LON - 0.01, LAT - 0.01],
                [LON + 0.01, LAT - 0.01],
                [LON + 0.01, LAT + 0.01],
                [LON - 0.01, LAT + 0.01],
                [LON - 0.01, LAT - 0.01],
            ]],
        }
        conn.execute(
            """
            INSERT INTO spatial_features(
                api_id,feature_id,layer_key,category,area_id,geometry_type,
                geometry_json,properties_json,centroid_lat,centroid_lon,source_id
            ) VALUES ('XKT026','flood-test','flood','hazard','13122','Polygon',?,?,?,?,NULL)
            """,
            (json.dumps(polygon), json.dumps({"A31a_205": 3}), LAT, LON),
        )

    written = compute_station_context_metrics(db_path)
    assert written > 0

    with connect(db_path) as conn:
        values = {
            row["metric_key"]: row["value"]
            for row in conn.execute(
                """
                SELECT metric_key,value FROM geo_metrics
                WHERE geo_id=? AND metric_version='station-metrics-v0.1'
                """,
                (GEO_ID,),
            )
        }

    assert values["terrain_elevation_population_weighted_mean"] == 3.0
    assert values["terrain_population_below_5m_share"] == 100.0
    assert values["seismic_30y_6lower_probability"] == 60.0
    assert values["hazard_flood_population_share"] == 100.0
    assert values["hazard_flood_3m_plus_population_share"] == 100.0
