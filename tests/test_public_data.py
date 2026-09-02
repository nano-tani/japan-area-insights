from __future__ import annotations

import json
import zipfile
from pathlib import Path

from japan_area_insights.compute_scores import compute_partial_scores
from japan_area_insights.db import connect, initialize
from japan_area_insights.future_population import normalize_future_population, rows_from_zip
from japan_area_insights.land_prices import aggregate_land_prices, normalize_xpt002, parse_yen_per_sqm, tiles_for_bbox
from japan_area_insights.population import normalize_census_2025


def estat_payload(values: list[dict], labels: dict[str, dict[str, str]]) -> dict:
    class_obj = []
    for dimension, mapping in labels.items():
        class_obj.append(
            {
                "@id": dimension,
                "CLASS": [{"@code": code, "@name": name} for code, name in mapping.items()],
            }
        )
    return {
        "GET_STATS_DATA": {
            "STATISTICAL_DATA": {
                "CLASS_INF": {"CLASS_OBJ": class_obj},
                "DATA_INF": {"VALUE": values},
            }
        }
    }


def test_land_price_normalization() -> None:
    payload = {
        "features": [
            {
                "properties": {
                    "point_id": "p1",
                    "city_code": "13101",
                    "u_current_years_price_ja": "1,250,000円/㎡",
                }
            },
            {
                "properties": {
                    "point_id": "p2",
                    "city_code": "99999",
                    "u_current_years_price_ja": "100000",
                }
            },
        ]
    }
    rows = normalize_xpt002(payload, allowed_area_ids=["13101"], year=2026, price_classification=0)
    assert len(rows) == 1
    assert rows[0]["price"] == 1_250_000
    assert parse_yen_per_sqm("850,000円/㎡") == 850_000
    assert aggregate_land_prices(rows)["13101"]["mean_price"] == 1_250_000


def test_tiles_are_nonempty_and_unique() -> None:
    tiles = tiles_for_bbox()
    assert tiles
    assert len(tiles) == len(set(tiles))


def test_census_2025_normalization() -> None:
    total_payload = estat_payload(
        [{"@area": "13101", "@tab": "01", "@cat01": "0", "$": "70123"}],
        {"area": {"13101": "千代田区"}, "tab": {"01": "人口"}, "cat01": {"0": "総数"}},
    )
    change_payload = estat_payload(
        [
            {"@area": "13101", "@tab": "a", "$": "66680"},
            {"@area": "13101", "@tab": "b", "$": "40100"},
            {"@area": "13101", "@tab": "c", "$": "37000"},
            {"@area": "13101", "@tab": "d", "$": "5.2"},
            {"@area": "13101", "@tab": "e", "$": "8.4"},
        ],
        {
            "area": {"13101": "千代田区"},
            "tab": {
                "a": "2020年（令和２年）の人口（組替）",
                "b": "世帯数",
                "c": "2020年（令和2年）の世帯数（組替）",
                "d": "5年間の人口増減率",
                "e": "5年間の世帯増減率",
            },
        },
    )
    rows = normalize_census_2025(total_payload, change_payload, ["13101"])
    by_year = {row["year"]: row for row in rows}
    assert by_year[2020]["population"] == 66680
    assert by_year[2025]["population"] == 70123
    assert by_year[2025]["households"] == 40100
    assert by_year[2025]["population_change_rate"] == 5.2


def test_future_population_zip_and_normalization(tmp_path: Path) -> None:
    csv_text = "MESH_ID,SHICODE,PTN_2020,PTN_2025,PTN_2030,PTN_2035,PTN_2040,PTN_2045,PTN_2050,PTN_2055,PTN_2060,PTN_2065,PTN_2070\n5339461111,13101,100,98,96,94,92,90,88,86,84,82,80\n5339461112,99999,10,9,8,7,6,5,4,3,2,1,0\n"
    zip_path = tmp_path / "future.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("future.csv", csv_text.encode("cp932"))

    rows = list(normalize_future_population(rows_from_zip(zip_path), allowed_area_ids=["13101"]))
    assert len(rows) == 11
    assert rows[0]["year"] == 2020
    assert rows[-1]["year"] == 2070
    assert rows[-1]["projected_population"] == 80
    assert rows[-1]["retention_rate"] == 80.0


def test_partial_scores_are_stored_without_fake_total(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    initialize(db_path)
    with connect(db_path) as conn:
        for area_id, name in (("13101", "千代田区"), ("13102", "中央区")):
            conn.execute(
                "INSERT INTO areas(area_id,prefecture_code,municipality_code,prefecture_name,municipality_name) VALUES(?,?,?,?,?)",
                (area_id, "13", area_id, "東京都", name),
            )
        conn.execute("INSERT INTO area_prices(area_id,year,change_5y,transaction_count) VALUES('13101',2025,20,100)")
        conn.execute("INSERT INTO area_prices(area_id,year,change_5y,transaction_count) VALUES('13102',2025,5,50)")
        conn.execute("INSERT INTO population(area_id,year,population_change_rate) VALUES('13101',2025,4)")
        conn.execute("INSERT INTO population(area_id,year,population_change_rate) VALUES('13102',2025,-1)")
        for area_id, p2025, p2045 in (("13101", 100, 110), ("13102", 100, 80)):
            conn.execute("INSERT INTO future_population(area_id,mesh_id,year,projected_population) VALUES(?,?,?,?)", (area_id, "m1", 2025, p2025))
            conn.execute("INSERT INTO future_population(area_id,mesh_id,year,projected_population) VALUES(?,?,?,?)", (area_id, "m1", 2045, p2045))

    compute_partial_scores(db_path, calculation_date="2026-09-02")
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM area_scores ORDER BY area_id").fetchall()
    assert len(rows) == 2
    assert rows[0]["price_score"] > rows[1]["price_score"]
    assert rows[0]["future_population_score"] > rows[1]["future_population_score"]
    assert rows[0]["total_score"] is None
