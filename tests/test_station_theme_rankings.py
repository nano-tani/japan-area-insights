from __future__ import annotations

import json
from pathlib import Path

from japan_area_insights.seo_export import export_seo_files
from japan_area_insights.station_theme_export import export_station_theme_pages


def _detail(code: str, name: str, *, future_score: float, price_score: float, flood: float, quake: float) -> dict:
    return {
        "station_code": code,
        "name": name,
        "primary_ward_name": "テスト区",
        "latitude": 35.7,
        "longitude": 139.7,
        "mesh_count": 8,
        "future_population_score": future_score,
        "price_score": price_score,
        "convenience_score": 10,
        "transport_score": 10,
        "transaction_score": 5,
        "confidence": "A",
        "metrics": {
            "future_population_retention_2045": {"value": 100 + future_score},
            "transaction_unit_price_change": {"value": price_score},
            "hazard_flood_population_share": {"value": flood},
            "seismic_30y_6lower_probability": {"value": quake},
            "facility_medical_count": {"value": 10},
            "nearby_station_count": {"value": 2},
        },
        "future_population": [
            {"year": 2025, "projected_population": 50000},
            {"year": 2045, "projected_population": 50000 + future_score * 100},
        ],
        "sources": [{"source_name": "テスト公的データ"}],
    }


def test_theme_rankings_are_generated_and_added_to_sitemap(tmp_path: Path) -> None:
    data_dir = tmp_path / "web" / "data"
    station_dir = data_dir / "geo" / "station"
    station_dir.mkdir(parents=True)
    details = [
        _detail("100001", "未来", future_score=20, price_score=12, flood=10, quake=30),
        _detail("100002", "市場", future_score=12, price_score=20, flood=40, quake=60),
    ]
    for detail in details:
        (station_dir / f"{detail['station_code']}.json").write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
    (data_dir / "geo" / "index.json").write_text(
        json.dumps({"generated_at": "2026-09-05T00:00:00+00:00", "station_areas": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    stats = export_station_theme_pages(data_dir)
    sitemap_count = export_seo_files(data_dir)

    assert stats.generated_pages == 4
    assert stats.ranked_stations == 6
    future_html = (tmp_path / "web" / "ranking" / "future-population" / "index.html").read_text(encoding="utf-8")
    safety_html = (tmp_path / "web" / "ranking" / "future-and-safety" / "index.html").read_text(encoding="utf-8")
    sitemap = (tmp_path / "web" / "sitemap.xml").read_text(encoding="utf-8")
    assert future_html.index("未来駅") < future_html.index("市場駅")
    assert "洪水曝露人口" in safety_html
    assert "30年 震度6弱以上" in safety_html
    assert "ranking/future-population/" in sitemap
    assert "ranking/price-and-future/" in sitemap
    assert "ranking/future-and-safety/" in sitemap
    assert sitemap_count == 7
