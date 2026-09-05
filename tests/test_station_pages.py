from __future__ import annotations

import json
from pathlib import Path

from japan_area_insights.page_quality import station_page_quality
from japan_area_insights.seo_export import export_seo_files
from japan_area_insights.station_page_export import export_station_pages


def _detail(code: str = "123456", *, sources: bool = True) -> dict:
    return {
        "geo_id": f"station:{code}:r1000:v1",
        "station_code": code,
        "name": "テスト中央",
        "primary_area_id": "13101",
        "primary_ward_name": "千代田区",
        "latitude": 35.68,
        "longitude": 139.76,
        "radius_m": 1000,
        "mesh_count": 12,
        "calculation_date": "2026-09-05",
        "price_score": 10,
        "population_score": 12,
        "future_population_score": 14,
        "convenience_score": 8,
        "transport_score": 9,
        "transaction_score": 5,
        "total_score": 58,
        "confidence": "A",
        "eligibility": "eligible",
        "eligibility_reason": None,
        "lines": [{"operator_name": "テスト鉄道", "line_name": "中央線"}],
        "metrics": {
            "future_population_retention_2045": {"value": 96.0},
            "transaction_unit_price_median_latest": {"value": 700000},
            "transaction_unit_price_change": {"value": 12.5},
            "transaction_count_5y": {"value": 100},
            "nearby_station_count": {"value": 3},
            "nearby_line_count": {"value": 2},
            "ridership_daily": {"value": 50000},
            "facility_school_count": {"value": 4},
            "facility_childcare_count": {"value": 8},
            "facility_medical_count": {"value": 20},
            "facility_library_count": {"value": 1},
            "facility_public_facility_count": {"value": 3},
        },
        "future_population": [
            {"year": 2025, "projected_population": 50000, "retention_rate": 100},
            {"year": 2030, "projected_population": 49500, "retention_rate": 99},
            {"year": 2045, "projected_population": 48000, "retention_rate": 96},
        ],
        "transactions": [{"year": 2025, "transaction_count": 20, "median_unit_price": 700000}],
        "sources": (
            [{"source_name": "国土交通省 不動産情報ライブラリ", "dataset_id": "XKT013", "source_url": "https://www.reinfolib.mlit.go.jp/"}]
            if sources else []
        ),
    }


def _write_public_json(root: Path, details: list[dict]) -> Path:
    data = root / "web" / "data"
    station_dir = data / "geo" / "station"
    station_dir.mkdir(parents=True)
    (data / "geo" / "index.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-09-05T00:00:00+00:00",
                "station_areas": [
                    {
                        "station_code": item["station_code"],
                        "name": item["name"],
                        "primary_ward_name": item["primary_ward_name"],
                        "total_score": item["total_score"],
                    }
                    for item in details
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    for item in details:
        (station_dir / f"{item['station_code']}.json").write_text(
            json.dumps(item, ensure_ascii=False), encoding="utf-8"
        )
    return data


def test_station_quality_does_not_require_total_score() -> None:
    detail = _detail()
    detail["total_score"] = None
    detail["eligibility"] = "insufficient_data"
    assert station_page_quality(detail).indexable is True


def test_station_pages_and_sitemap_are_generated(tmp_path: Path) -> None:
    good = _detail("123456", sources=True)
    poor = _detail("654321", sources=False)
    data = _write_public_json(tmp_path, [good, poor])

    stats = export_station_pages(data)
    sitemap_count = export_seo_files(data)

    assert stats.generated_count == 2
    assert stats.indexable_count == 1
    assert stats.noindex_count == 1
    assert sitemap_count == 4

    good_html = (tmp_path / "web" / "station" / "123456" / "index.html").read_text(encoding="utf-8")
    poor_html = (tmp_path / "web" / "station" / "654321" / "index.html").read_text(encoding="utf-8")
    sitemap = (tmp_path / "web" / "sitemap.xml").read_text(encoding="utf-8")
    robots = (tmp_path / "web" / "robots.txt").read_text(encoding="utf-8")

    assert 'meta name="robots" content="index,follow"' in good_html
    assert 'meta name="robots" content="noindex,follow"' in poor_html
    assert "テスト中央駅" in good_html
    assert "https://nano-tani.github.io/japan-area-insights/station/123456/" in sitemap
    assert "https://nano-tani.github.io/japan-area-insights/station/654321/" not in sitemap
    assert "Sitemap: https://nano-tani.github.io/japan-area-insights/sitemap.xml" in robots
