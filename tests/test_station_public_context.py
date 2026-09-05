from __future__ import annotations

import json

from japan_area_insights.station_mesh_export import export_station_mesh_maps_from_public_data
from japan_area_insights.station_page_enhancer import enhance_station_pages


def test_public_station_mesh_export_uses_published_ward_meshes(tmp_path):
    data_dir = tmp_path / "web" / "data"
    (data_dir / "geo").mkdir(parents=True)
    ward_dir = data_dir / "map" / "ward" / "13122"
    ward_dir.mkdir(parents=True)

    (data_dir / "geo" / "index.json").write_text(
        json.dumps(
            {
                "station_areas": [
                    {
                        "station_code": "003274",
                        "name": "お花茶屋",
                        "primary_ward_name": "葛飾区",
                        "latitude": 35.715625,
                        "longitude": 139.8515625,
                        "radius_m": 1000,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (ward_dir / "mesh250.json").write_text(
        json.dumps(
            {
                "terrain": {"provider": "国土地理院"},
                "seismic": {"provider": "防災科学技術研究所 J-SHIS"},
                "meshes": [
                    {
                        "mesh_id": "5339465833",
                        "longitude": 139.8515625,
                        "latitude": 35.715625,
                        "population_2025": 100.0,
                        "population_2045": 110.0,
                        "retention_2045": 110.0,
                        "elevation_m": 4.0,
                        "earthquake_probability_30y_5lower": 90.0,
                        "earthquake_probability_30y_5upper": 80.0,
                        "earthquake_probability_30y_6lower": 60.0,
                        "earthquake_probability_30y_6upper": 30.0,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert export_station_mesh_maps_from_public_data(data_dir) == 1
    path = data_dir / "map" / "station" / "003274" / "mesh250.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["summary"]["mesh_count"] == 1
    assert payload["summary"]["retention_2045_area"] == 110.0
    assert payload["summary"]["terrain"]["elevation_population_weighted_mean"] == 4.0
    assert payload["summary"]["terrain"]["population_below_5m_share"] == 100.0
    assert payload["summary"]["seismic"]["earthquake_probability_30y_6lower_population_weighted"] == 60.0


def test_station_page_enhancer_is_idempotent(tmp_path):
    web_root = tmp_path / "web"
    page_dir = web_root / "station" / "003274"
    page_dir.mkdir(parents=True)
    page = page_dir / "index.html"
    page.write_text("<html><head></head><body><main></main></body></html>", encoding="utf-8")

    assert enhance_station_pages(web_root) == 1
    assert enhance_station_pages(web_root) == 1
    html = page.read_text(encoding="utf-8")
    assert html.count("station-context.css") == 1
    assert html.count("station-context.js") == 1
    assert html.count("station-decision.css") == 1
    assert html.count("station-decision.js") == 1
