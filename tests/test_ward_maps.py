from __future__ import annotations

from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.ward_maps import build_ward_mesh_payload, export_ward_mesh_maps


def _seed_area(conn) -> None:
    conn.execute(
        """
        INSERT INTO areas(
            area_id, prefecture_code, municipality_code,
            prefecture_name, municipality_name
        ) VALUES ('13101', '13', '13101', '東京都', '千代田区')
        """
    )


def test_build_ward_mesh_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "ward-map.db"
    initialize(db_path)
    with connect(db_path) as conn:
        _seed_area(conn)
        conn.executemany(
            """
            INSERT INTO future_population(area_id, mesh_id, year, projected_population)
            VALUES ('13101', '5339461111', ?, ?)
            """,
            [(2025, 100.0), (2045, 80.0)],
        )
        conn.execute(
            """
            INSERT INTO stations(
                station_id, area_id, group_code, station_name,
                latitude, longitude, passenger_count
            ) VALUES ('s1', '13101', 'g1', 'テスト駅', 35.68, 139.76, 12345)
            """
        )
        payload = build_ward_mesh_payload(conn, '13101')

    assert payload['area_id'] == '13101'
    assert payload['summary']['mesh_count'] == 1
    assert payload['summary']['retention_2045_area'] == 80.0
    assert payload['meshes'][0]['population_2025'] == 100.0
    assert payload['meshes'][0]['population_2045'] == 80.0
    assert payload['meshes'][0]['retention_2045'] == 80.0
    assert payload['bounds'] is not None
    assert payload['stations'][0]['name'] == 'テスト駅'


def test_export_ward_mesh_maps_creates_empty_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "empty-map.db"
    output = tmp_path / "web-data"
    initialize(db_path)
    with connect(db_path) as conn:
        _seed_area(conn)

    export_ward_mesh_maps(db_path, output)
    path = output / 'map' / 'ward' / '13101' / 'mesh250.json'
    assert path.exists()
    assert '"mesh_count": 0' in path.read_text(encoding='utf-8')
