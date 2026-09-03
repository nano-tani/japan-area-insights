from __future__ import annotations

from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.geo import mesh_code_250m
from japan_area_insights.geography import sync_geo_foundation
from japan_area_insights.station_areas import (
    STATION_DEFINITION_VERSION,
    compute_station_scores,
    station_geo_id,
    sync_station_areas,
)
from japan_area_insights.station_transactions import ensure_station_transaction_schema


def _seed_area(conn, area_id: str, name: str) -> None:
    conn.execute(
        """
        INSERT INTO areas(
            area_id, prefecture_code, municipality_code,
            prefecture_name, municipality_name
        ) VALUES (?, '13', ?, '東京都', ?)
        """,
        (area_id, area_id, name),
    )


def _seed_future(conn, area_id: str, mesh_id: str, p2020: int, p2025: int, p2045: int) -> None:
    for year, population in ((2020, p2020), (2025, p2025), (2045, p2045)):
        conn.execute(
            """
            INSERT INTO future_population(area_id, mesh_id, year, projected_population)
            VALUES (?, ?, ?, ?)
            """,
            (area_id, mesh_id, year, population),
        )


def _seed_station(
    conn,
    *,
    station_id: str,
    area_id: str,
    group_code: str,
    name: str,
    line: str,
    lon: float,
    lat: float,
    passengers: int,
) -> None:
    conn.execute(
        """
        INSERT INTO stations(
            station_id, area_id, station_code, group_code,
            station_name, line_name, operator_name,
            passenger_count, passenger_year, latitude, longitude
        ) VALUES (?, ?, ?, ?, ?, ?, 'テスト鉄道', ?, 2023, ?, ?)
        """,
        (station_id, area_id, group_code, group_code, name, line, passengers, lat, lon),
    )


def test_station_area_can_cross_ward_boundary(tmp_path: Path) -> None:
    db_path = tmp_path / "cross.db"
    initialize(db_path)
    lat = 35.65
    lon_a = 139.700
    lon_b = 139.705
    mesh_a = mesh_code_250m(lon_a, lat)
    mesh_b = mesh_code_250m(lon_b, lat)
    assert mesh_a != mesh_b

    with connect(db_path) as conn:
        _seed_area(conn, "13113", "渋谷区")
        _seed_area(conn, "13110", "目黒区")
        _seed_future(conn, "13113", mesh_a, 100, 100, 100)
        _seed_future(conn, "13110", mesh_b, 100, 100, 100)
        _seed_station(
            conn,
            station_id="s-cross",
            area_id="13113",
            group_code="000001",
            name="境界駅",
            line="A線",
            lon=(lon_a + lon_b) / 2.0,
            lat=lat,
            passengers=10000,
        )

    sync_geo_foundation(db_path)
    stats = sync_station_areas(db_path)
    assert stats.station_area_count == 1

    with connect(db_path) as conn:
        unit = conn.execute(
            "SELECT * FROM geo_units WHERE geo_id=?",
            (station_geo_id("000001"),),
        ).fetchone()
        mapped = {
            row["mesh_id"]
            for row in conn.execute(
                "SELECT mesh_id FROM geo_unit_meshes WHERE geo_id=?",
                (station_geo_id("000001"),),
            )
        }

    assert unit is not None
    assert unit["geo_type"] == "station_area"
    assert unit["definition_version"] == STATION_DEFINITION_VERSION
    assert unit["parent_geo_id"] is None
    assert {mesh_a, mesh_b}.issubset(mapped)


def test_station_scores_are_station_only_and_gate_total(tmp_path: Path) -> None:
    db_path = tmp_path / "scores.db"
    initialize(db_path)
    coords = {
        "000101": (139.70, 35.65),
        "000202": (139.76, 35.71),
    }
    meshes = {code: mesh_code_250m(lon, lat) for code, (lon, lat) in coords.items()}

    with connect(db_path) as conn:
        _seed_area(conn, "13113", "渋谷区")
        _seed_future(conn, "13113", meshes["000101"], 100, 110, 121)
        _seed_future(conn, "13113", meshes["000202"], 100, 90, 72)

        lon, lat = coords["000101"]
        _seed_station(
            conn,
            station_id="a-1",
            area_id="13113",
            group_code="000101",
            name="A駅",
            line="A線",
            lon=lon,
            lat=lat,
            passengers=50000,
        )
        _seed_station(
            conn,
            station_id="a-2",
            area_id="13113",
            group_code="000101",
            name="A駅",
            line="B線",
            lon=lon,
            lat=lat,
            passengers=50000,
        )

        lon, lat = coords["000202"]
        _seed_station(
            conn,
            station_id="b-1",
            area_id="13113",
            group_code="000202",
            name="B駅",
            line="C線",
            lon=lon,
            lat=lat,
            passengers=10000,
        )

        facility_types = ("school", "childcare", "medical", "library", "public_facility")
        for facility_type in facility_types:
            lon, lat = coords["000101"]
            for index in range(3):
                conn.execute(
                    """
                    INSERT INTO facilities(
                        facility_id, area_id, facility_type, facility_name, latitude, longitude
                    ) VALUES (?, '13113', ?, ?, ?, ?)
                    """,
                    (f"a-{facility_type}-{index}", facility_type, f"A-{index}", lat, lon),
                )
            lon, lat = coords["000202"]
            conn.execute(
                """
                INSERT INTO facilities(
                    facility_id, area_id, facility_type, facility_name, latitude, longitude
                ) VALUES (?, '13113', ?, 'B', ?, ?)
                """,
                (f"b-{facility_type}", facility_type, lat, lon),
            )

    sync_geo_foundation(db_path)
    sync_station_areas(db_path)

    with connect(db_path) as conn:
        ensure_station_transaction_schema(conn)
        for group_code, per_year, rows_per_year in (
            ("000101", {2021: 100, 2022: 105, 2023: 110, 2024: 115, 2025: 120}, 8),
            ("000202", {2023: 100, 2024: 98, 2025: 95}, 2),
        ):
            for year, unit_price in per_year.items():
                for index in range(rows_per_year):
                    conn.execute(
                        """
                        INSERT INTO station_transactions(
                            station_group_code, transaction_id, year,
                            price_category, property_type, unit_price, area_sqm
                        ) VALUES (?, ?, ?, '不動産取引価格情報', '中古マンション等', ?, 50)
                        """,
                        (
                            group_code,
                            f"{group_code}-{year}-{index}",
                            year,
                            unit_price + index,
                        ),
                    )

    stats = compute_station_scores(db_path, calculation_date="2026-09-04")
    assert stats.station_area_count == 2
    assert stats.eligible_count == 1
    assert stats.partially_scored_count == 2

    with connect(db_path) as conn:
        a = conn.execute(
            "SELECT * FROM geo_scores WHERE geo_id=? ORDER BY calculation_date DESC LIMIT 1",
            (station_geo_id("000101"),),
        ).fetchone()
        b = conn.execute(
            "SELECT * FROM geo_scores WHERE geo_id=? ORDER BY calculation_date DESC LIMIT 1",
            (station_geo_id("000202"),),
        ).fetchone()
        a_metrics = {
            row["metric_key"]: row["value"]
            for row in conn.execute(
                "SELECT metric_key, value FROM geo_metrics WHERE geo_id=?",
                (station_geo_id("000101"),),
            )
        }

    assert a["peer_group"] == "tokyo23:station_area:r1000"
    assert a["eligibility"] == "eligible"
    assert a["total_score"] is not None
    assert b["eligibility"] == "insufficient_data"
    assert b["total_score"] is None
    assert "30件未満" in b["eligibility_reason"]
    assert a["population_score"] > b["population_score"]
    assert a["future_population_score"] > b["future_population_score"]
    assert a_metrics["transaction_count_5y"] == 40
    assert a_metrics["price_year_count"] == 5
    assert a_metrics["mesh_count"] >= 1
