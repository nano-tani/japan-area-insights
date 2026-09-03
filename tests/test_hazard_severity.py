import json
from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.geo import mesh250_center
from japan_area_insights.hazard_severity import compute_hazard_severity_bands, ensure_severity_schema


def _polygon(lon: float, lat: float):
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon - 0.004, lat - 0.004],
            [lon + 0.004, lat - 0.004],
            [lon + 0.004, lat + 0.004],
            [lon - 0.004, lat + 0.004],
            [lon - 0.004, lat - 0.004],
        ]],
    }


def _seed(conn):
    conn.execute(
        "INSERT INTO areas(area_id,prefecture_code,municipality_code,prefecture_name,municipality_name) VALUES ('13101','13','13101','東京都','千代田区')"
    )
    conn.execute(
        """
        INSERT INTO geo_units(geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,definition_version,is_active)
        VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)
        """
    )
    for year, pop in ((2025, 100.0), (2045, 120.0)):
        conn.execute(
            "INSERT INTO future_population(area_id,mesh_id,year,projected_population) VALUES ('13101','5339461111',?,?)",
            (year, pop),
        )
    return mesh250_center("5339461111")


def _insert_feature(conn, api_id, feature_id, layer_key, props, geometry, source_id):
    lon, lat = mesh250_center("5339461111")
    conn.execute(
        """
        INSERT INTO spatial_features(
            api_id,feature_id,layer_key,category,area_id,geometry_type,
            geometry_json,properties_json,centroid_lat,centroid_lon,source_id
        ) VALUES (?,?,?,?,?,'Polygon',?,?,?,?,?)
        """,
        (
            api_id, feature_id, layer_key, "hazard", "13101",
            json.dumps(geometry), json.dumps(props), lat, lon, source_id,
        ),
    )


def test_hazard_severity_uses_strongest_overlapping_official_band(tmp_path: Path):
    db_path = tmp_path / "severity.db"
    initialize(db_path)
    with connect(db_path) as conn:
        lon, lat = _seed(conn)
        ensure_severity_schema(conn)
        source_id = conn.execute(
            "INSERT INTO data_sources(source_name,dataset_id,source_url,fetched_at) VALUES ('test','hazards','https://example.test','2026-09-01')"
        ).lastrowid
        geometry = _polygon(lon, lat)
        _insert_feature(conn, "XKT026", "flood2", "flood", {"A31a_205": 2}, geometry, source_id)
        _insert_feature(conn, "XKT026", "flood3", "flood", {"A31a_205": 3}, geometry, source_id)
        _insert_feature(conn, "XKT027", "surge", "storm_surge", {"A49_003": "3m以上5m未満"}, geometry, source_id)
        _insert_feature(conn, "XKT028", "tsunami", "tsunami", {"A40_003": "1m以上2m未満"}, geometry, source_id)
        _insert_feature(conn, "XKT029", "sediment", "sediment_disaster", {"A33_001": 1, "A33_002": 2}, geometry, source_id)
        _insert_feature(conn, "XKT025", "liq", "liquefaction", {"liquefaction_tendency_level": 5, "note": "液状化しにくい"}, geometry, source_id)
        _insert_feature(conn, "XKT020", "fill", "large_fill", {"embankment_classification": "谷埋め型"}, geometry, source_id)

        count = compute_hazard_severity_bands(conn)
        assert count == 12  # six layer bands x 2025/2045

        flood = conn.execute(
            "SELECT * FROM geo_exposure_bands WHERE geo_id='ward:13101' AND layer_key='flood' AND period='2025'"
        ).fetchall()
        assert len(flood) == 1
        assert flood[0]["band_key"] == "rank_3"
        assert flood[0]["band_label"] == "3.0m以上5.0m未満"
        assert flood[0]["exposed_population"] == 100
        assert flood[0]["population_share"] == 100

        sediment = conn.execute(
            "SELECT * FROM geo_exposure_bands WHERE layer_key='sediment_disaster' AND period='2025'"
        ).fetchone()
        assert "土砂災害特別警戒区域" in sediment["band_label"]
        assert "急傾斜地の崩壊" in sediment["band_label"]

        liquid = conn.execute(
            "SELECT * FROM geo_exposure_bands WHERE layer_key='liquefaction' AND period='2025'"
        ).fetchone()
        assert liquid["band_label"] == "液状化しにくい"

        fill = conn.execute(
            "SELECT * FROM geo_exposure_bands WHERE layer_key='large_fill' AND period='2045'"
        ).fetchone()
        assert fill["band_label"] == "谷埋め型"
        assert fill["exposed_population"] == 120
