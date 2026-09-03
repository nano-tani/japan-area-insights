from __future__ import annotations

from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.geo import mesh250_center, mesh_code_250m
from japan_area_insights.geography import mesh_geo_id, sync_geo_foundation, ward_geo_id


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


def test_mesh250_center_round_trip() -> None:
    mesh_id = "5438234312"
    lon, lat = mesh250_center(mesh_id)
    assert mesh_code_250m(lon, lat) == mesh_id


def test_geo_foundation_syncs_wards_and_meshes(tmp_path: Path) -> None:
    db_path = tmp_path / "geo.db"
    initialize(db_path)
    with connect(db_path) as conn:
        _seed_area(conn, "13101", "千代田区")
        _seed_area(conn, "13102", "中央区")
        for year, population in ((2025, 100), (2045, 110)):
            conn.execute(
                """
                INSERT INTO future_population(area_id, mesh_id, year, projected_population)
                VALUES ('13101', '5339461111', ?, ?)
                """,
                (year, population),
            )
        conn.execute(
            """
            INSERT INTO future_population(area_id, mesh_id, year, projected_population)
            VALUES ('13102', '5339461112', 2025, 200)
            """
        )

    stats = sync_geo_foundation(db_path)
    assert stats.ward_count == 2
    assert stats.mesh_count == 2
    assert stats.mapping_count == 4

    with connect(db_path) as conn:
        ward = conn.execute(
            "SELECT * FROM geo_units WHERE geo_id=?",
            (ward_geo_id("13101"),),
        ).fetchone()
        mesh = conn.execute(
            "SELECT * FROM geo_units WHERE geo_id=?",
            (mesh_geo_id("5339461111"),),
        ).fetchone()
        ward_mapping = conn.execute(
            "SELECT * FROM geo_unit_meshes WHERE geo_id=? AND mesh_id='5339461111'",
            (ward_geo_id("13101"),),
        ).fetchone()
        self_mapping = conn.execute(
            "SELECT * FROM geo_unit_meshes WHERE geo_id=? AND mesh_id='5339461111'",
            (mesh_geo_id("5339461111"),),
        ).fetchone()

    assert ward is not None
    assert ward["geo_type"] == "ward"
    assert ward["canonical_code"] == "13101"
    assert mesh is not None
    assert mesh["geo_type"] == "mesh250"
    assert mesh["parent_geo_id"] == ward_geo_id("13101")
    assert mesh["primary_area_id"] == "13101"
    assert mesh["latitude"] is not None
    assert mesh["longitude"] is not None
    assert ward_mapping["method"] == "xkt013_shicode"
    assert self_mapping["method"] == "self"

    second = sync_geo_foundation(db_path)
    assert second == stats


def test_geo_foundation_deactivates_stale_meshes(tmp_path: Path) -> None:
    db_path = tmp_path / "stale.db"
    initialize(db_path)
    with connect(db_path) as conn:
        _seed_area(conn, "13101", "千代田区")
        conn.execute(
            """
            INSERT INTO future_population(area_id, mesh_id, year, projected_population)
            VALUES ('13101', '5339461111', 2025, 100)
            """
        )

    sync_geo_foundation(db_path)

    with connect(db_path) as conn:
        conn.execute("DELETE FROM future_population WHERE mesh_id='5339461111'")

    stats = sync_geo_foundation(db_path)
    assert stats.ward_count == 1
    assert stats.mesh_count == 0
    assert stats.mapping_count == 0

    with connect(db_path) as conn:
        stale = conn.execute(
            "SELECT is_active FROM geo_units WHERE geo_id=?",
            (mesh_geo_id("5339461111"),),
        ).fetchone()
        mapping_count = conn.execute(
            "SELECT COUNT(*) FROM geo_unit_meshes WHERE geo_id=?",
            (mesh_geo_id("5339461111"),),
        ).fetchone()[0]

    assert stale["is_active"] == 0
    assert mapping_count == 0


def test_geo_tables_exist_on_initialize(tmp_path: Path) -> None:
    db_path = tmp_path / "schema.db"
    initialize(db_path)
    with connect(db_path) as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"geo_units", "geo_unit_meshes", "geo_metrics", "geo_scores"}.issubset(tables)
