from pathlib import Path

from japan_area_insights.analysis_export import export_analysis_data
from japan_area_insights.db import connect, initialize
from japan_area_insights.geo import mesh250_center
from japan_area_insights.resilience_analysis import (
    assign_disaster_history_areas,
    compute_resilience_metrics,
    ensure_resilience_schema,
    normalize_disaster_history,
    normalize_evacuation_sites,
)


def _seed(conn):
    conn.execute(
        """
        INSERT INTO areas(area_id,prefecture_code,municipality_code,prefecture_name,municipality_name)
        VALUES ('13101','13','13101','東京都','千代田区')
        """
    )
    conn.execute(
        """
        INSERT INTO geo_units(
            geo_id,geo_type,canonical_code,name,primary_area_id,prefecture_code,
            definition_version,is_active
        ) VALUES ('ward:13101','ward','13101','千代田区','13101','13','ward-v1',1)
        """
    )
    conn.execute(
        "INSERT INTO population(area_id,year,population) VALUES ('13101',2025,100000)"
    )
    for year, population in ((2025, 100.0), (2045, 110.0)):
        conn.execute(
            """
            INSERT INTO future_population(area_id,mesh_id,year,projected_population)
            VALUES ('13101','5339461111',?,?)
            """,
            (year, population),
        )


def test_normalize_xgt001_and_xst001():
    lon, lat = mesh250_center("5339461111")
    site_payload = {
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "common_id": "site-1",
                "prefecture_and_city": "東京都千代田区",
                "facility_name_ja": "テスト避難場所",
                "address_ja": "東京都千代田区丸の内1丁目",
                "flood_flag": True,
                "landslide_flag": False,
                "high_tide_flag": True,
                "earthquake_flag": True,
                "tsunami_flag": False,
                "large_fire_flag": True,
                "inland_flooding_flag": True,
                "volcanic_phenomenon_flag": False,
                "same_address_flag": True,
                "remarks": "テスト",
            },
        }]
    }
    rows = normalize_evacuation_sites(
        site_payload,
        mesh_to_area={"5339461111": "13101"},
        area_names={"13101": "千代田区"},
    )
    assert len(rows) == 1
    assert rows[0]["area_id"] == "13101"
    assert rows[0]["flood_flag"] == 1
    assert rows[0]["tsunami_flag"] == 0
    assert rows[0]["facility_name"] == "テスト避難場所"

    history_payload = {
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [lon - 0.005, lat - 0.005],
                    [lon + 0.005, lat - 0.005],
                    [lon + 0.005, lat + 0.005],
                    [lon - 0.005, lat + 0.005],
                    [lon - 0.005, lat - 0.005],
                ]],
            },
            "properties": {
                "disastertype_code": "11",
                "disaster_name_ja": "浸水",
                "disaster_date": "20200701",
                "disaster_source": "テスト資料",
            },
        }]
    }
    history = normalize_disaster_history(history_payload)
    assert len(history) == 1
    assert history[0]["disastertype_code"] == "11"
    assert history[0]["disaster_date"] == "20200701"
    assert history[0]["geometry_type"] == "Polygon"


def test_resilience_metrics_and_export(tmp_path: Path):
    db_path = tmp_path / "resilience.db"
    initialize(db_path)
    lon, lat = mesh250_center("5339461111")
    with connect(db_path) as conn:
        _seed(conn)
        ensure_resilience_schema(conn)
        source_xgt = conn.execute(
            """
            INSERT INTO data_sources(source_name,dataset_id,source_url,fetched_at)
            VALUES ('test','XGT001','https://example.test/xgt','2026-09-01')
            """
        ).lastrowid
        source_xst = conn.execute(
            """
            INSERT INTO data_sources(source_name,dataset_id,source_url,fetched_at)
            VALUES ('test','XST001','https://example.test/xst','2026-09-01')
            """
        ).lastrowid
        conn.execute(
            """
            INSERT INTO evacuation_sites(
                common_id,area_id,facility_name,address,flood_flag,landslide_flag,
                high_tide_flag,earthquake_flag,tsunami_flag,large_fire_flag,
                inland_flooding_flag,volcanic_phenomenon_flag,same_address_flag,
                latitude,longitude,source_id
            ) VALUES (
                'site-1','13101','テスト避難場所','東京都千代田区',1,0,1,1,0,1,1,0,1,?,?,?
            )
            """,
            (lat, lon, source_xgt),
        )
        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [lon - 0.005, lat - 0.005],
                [lon + 0.005, lat - 0.005],
                [lon + 0.005, lat + 0.005],
                [lon - 0.005, lat + 0.005],
                [lon - 0.005, lat - 0.005],
            ]],
        }
        conn.execute(
            """
            INSERT INTO disaster_history(
                event_id,disastertype_code,disaster_name,disaster_date,disaster_source,
                geometry_type,geometry_json,centroid_lat,centroid_lon,source_id
            ) VALUES ('event-1','11','浸水','20200701','資料','Polygon',?,?,?,?)
            """,
            (__import__('json').dumps(geometry), lat, lon, source_xst),
        )
        assert assign_disaster_history_areas(conn) == 1
        count = compute_resilience_metrics(conn)
        assert count == 17
        metrics = {
            row["metric_key"]: row["value"]
            for row in conn.execute(
                "SELECT metric_key,value FROM geo_metrics WHERE geo_id='ward:13101' AND metric_version='detail-v1'"
            )
        }
        assert metrics["resilience.evacuation_site_count"] == 1
        assert metrics["resilience.evacuation_sites_per_10k"] == 0.1
        assert metrics["resilience.evacuation_flood_count"] == 1
        assert metrics["resilience.evacuation_median_distance"] == 0
        assert metrics["resilience.disaster_history_count"] == 1
        assert metrics["resilience.disaster_history_flood_count"] == 1
        assert metrics["resilience.disaster_history_latest_year"] == 2020

    output = tmp_path / "webdata"
    export_analysis_data(db_path, output)
    payload = __import__('json').loads((output / "analysis" / "ward" / "13101.json").read_text(encoding="utf-8"))
    assert payload["evacuation_sites"][0]["facility_name"] == "テスト避難場所"
    assert payload["disaster_history"][0]["disastertype_code"] == "11"
    assert "resilience" in payload["metrics"]
