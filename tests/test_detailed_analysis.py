from pathlib import Path

from japan_area_insights.analysis_export import export_analysis_data
from japan_area_insights.analysis_schema import ensure_analysis_schema
from japan_area_insights.db import connect, initialize
from japan_area_insights.detailed_analysis import compute_market_metrics
from japan_area_insights.land_prices import normalize_xpt002
from japan_area_insights.spatial_analysis import point_in_geometry
from japan_area_insights.transactions import normalize_xit001


def _seed_area(conn):
    conn.execute(
        """
        INSERT INTO areas(area_id, prefecture_code, municipality_code, prefecture_name, municipality_name)
        VALUES ('13101', '13', '13101', '東京都', '千代田区')
        """
    )
    conn.execute(
        """
        INSERT INTO geo_units(
            geo_id, geo_type, canonical_code, name, primary_area_id,
            prefecture_code, definition_version, is_active
        ) VALUES ('ward:13101', 'ward', '13101', '千代田区', '13101', '13', 'ward-v1', 1)
        """
    )


def test_xit001_preserves_detailed_attributes():
    payload = {
        "data": [{
            "PriceCategory": "不動産取引価格情報",
            "Type": "中古マンション等",
            "Region": "住宅地",
            "MunicipalityCode": "13101",
            "DistrictName": "丸の内",
            "DistrictCode": "131010001",
            "TradePrice": "60000000",
            "Area": "60",
            "BuildingYear": "2015年",
            "Structure": "ＲＣ",
            "FloorPlan": "2LDK",
            "Renovation": "改装済",
            "Breadth": "8",
            "Frontage": "9",
            "LandShape": "長方形",
            "Use": "住宅",
            "Purpose": "投資",
            "CityPlanning": "商業地域",
            "CoverageRatio": "80",
            "FloorAreaRatio": "600",
            "Period": "2025年第2四半期",
        }]
    }
    row = normalize_xit001(payload, area_id="13101", year=2025)[0]
    assert row["building_year"] == 2015
    assert row["structure"] == "ＲＣ"
    assert row["floor_plan"] == "2LDK"
    assert row["road_breadth_m"] == 8.0
    assert row["frontage_m"] == 9.0
    assert row["floor_area_ratio"] == 600.0
    assert row["district_code"] == "131010001"


def test_xpt002_preserves_point_context():
    payload = {
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [139.75, 35.68]},
            "properties": {
                "point_id": 123,
                "city_code": "13101",
                "u_current_years_price_ja": "3,100,000(円/㎡)",
                "last_years_price": 2820000,
                "year_on_year_change_rate": "7.6",
                "front_road_width": 200,
                "gas_supply_availability": True,
                "water_supply_availability": True,
                "sewer_supply_availability": True,
                "nearest_station_name_ja": "大手町",
                "u_road_distance_to_nearest_station_name_ja": "150m",
                "regulations_use_category_name_ja": "商業地域",
                "regulations_fireproof_name_ja": "防火地域",
                "u_regulations_floor_area_ratio_ja": "800(%)",
            },
        }]
    }
    row = normalize_xpt002(payload, allowed_area_ids=["13101"], year=2025, price_classification=0)[0]
    assert row["price"] == 3_100_000
    assert row["front_road_width_m"] == 20.0
    assert row["station_distance_m"] == 150
    assert row["floor_area_ratio"] == 800
    assert row["gas_supply"] == 1
    assert row["fireproof_zone"] == "防火地域"
    assert row["longitude"] == 139.75


def test_compute_market_metrics_and_export(tmp_path: Path):
    db_path = tmp_path / "test.db"
    initialize(db_path)
    with connect(db_path) as conn:
        _seed_area(conn)
        ensure_analysis_schema(conn)
        source_id = conn.execute(
            """
            INSERT INTO data_sources(source_name, dataset_id, source_url, fetched_at)
            VALUES ('test', 'XIT001', 'https://example.test', '2026-01-01')
            """
        ).lastrowid
        rows = [
            ("a", 2024, 1_000_000, 50, "中古マンション等", 2014, "ＲＣ", "改装済", 8, 9, "長方形", "住宅", "投資", "1K", 600, 80),
            ("b", 2025, 1_200_000, 60, "中古マンション等", 2015, "ＳＲＣ", "未改装", 10, 10, "正方形", "住宅", "自己利用", "2LDK", 600, 80),
            ("c", 2025, 800_000, 70, "宅地(土地と建物)", 1985, "木造", None, 4, 5, "不整形", "店舗", "自己利用", "3LDK", 200, 60),
        ]
        for tx_id, year, unit, area, kind, built, structure, renovation, width, frontage, shape, use_name, purpose, plan, far, coverage in rows:
            conn.execute(
                """
                INSERT INTO transactions(
                    transaction_id, area_id, year, price_category, property_type,
                    total_price, unit_price, area_sqm, building_year, structure,
                    renovation, road_breadth_m, frontage_m, land_shape, use_name,
                    purpose, floor_plan, floor_area_ratio, coverage_ratio, source_id
                ) VALUES (?, '13101', ?, '不動産取引価格情報', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (tx_id, year, kind, unit * area, unit, area, built, structure, renovation, width, frontage, shape, use_name, purpose, plan, far, coverage, source_id),
            )
        point_rows = [
            ("p1", 800_000, 100, 600, 12, "商業地域", "防火地域"),
            ("p2", 1_000_000, 300, 800, 20, "商業地域", "防火地域"),
            ("p3", 1_200_000, 1200, 200, 6, "第一種住居地域", "準防火地域"),
        ]
        for point_id, price, distance, far, width, zoning, fireproof in point_rows:
            conn.execute(
                """
                INSERT INTO land_price_points(
                    point_id, area_id, year, price_classification, price,
                    station_distance_m, floor_area_ratio, front_road_width_m,
                    zoning, fireproof_zone, gas_supply, water_supply, sewer_supply, source_id
                ) VALUES (?, '13101', 2025, 0, ?, ?, ?, ?, ?, ?, 1, 1, 1, ?)
                """,
                (point_id, price, distance, far, width, zoning, fireproof, source_id),
            )
        count = compute_market_metrics(conn, from_year=2024, to_year=2025)
        assert count == 40
        metrics = {
            row["metric_key"]: row["value"]
            for row in conn.execute("SELECT metric_key, value FROM geo_metrics WHERE geo_id='ward:13101'")
        }
        assert metrics["market.transaction_count"] == 3
        assert metrics["market.median_unit_price"] == 1_000_000
        assert metrics["market.unit_price_p25"] == 900_000
        assert metrics["market.unit_price_p75"] == 1_100_000
        assert round(metrics["market.condo_share"], 2) == 66.67
        assert round(metrics["market.road_6m_plus_share"], 2) == 66.67
        assert round(metrics["market.investment_purpose_share"], 2) == 33.33
        assert round(metrics["market.family_floor_plan_share"], 2) == 66.67
        assert metrics["market.land_price_median"] == 1_000_000
        assert metrics["market.land_price_station_distance"] == 300
        assert round(metrics["market.land_price_within_500m_share"], 2) == 66.67
        assert metrics["market.land_price_utility_complete_share"] == 100

    output = tmp_path / "webdata"
    export_analysis_data(db_path, output)
    assert (output / "analysis" / "ward" / "13101.json").exists()
    assert (output / "analysis" / "catalog.json").exists()


def test_point_in_polygon_and_hole():
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [[139.0, 35.0], [140.0, 35.0], [140.0, 36.0], [139.0, 36.0], [139.0, 35.0]],
            [[139.4, 35.4], [139.6, 35.4], [139.6, 35.6], [139.4, 35.6], [139.4, 35.4]],
        ],
    }
    assert point_in_geometry(139.2, 35.2, polygon)
    assert not point_in_geometry(139.5, 35.5, polygon)
    assert not point_in_geometry(140.2, 35.5, polygon)
