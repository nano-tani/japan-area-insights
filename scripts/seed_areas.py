from __future__ import annotations

import json
from pathlib import Path

from japan_area_insights.db import connect, initialize

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"
AREAS_PATH = ROOT / "config" / "areas_tokyo23.json"


def main() -> None:
    initialize(DB_PATH)
    areas = json.loads(AREAS_PATH.read_text(encoding="utf-8"))
    with connect(DB_PATH) as conn:
        conn.executemany(
            """
            INSERT INTO areas (
                area_id, prefecture_code, municipality_code,
                prefecture_name, municipality_name, latitude, longitude
            ) VALUES (
                :area_id, :prefecture_code, :municipality_code,
                :prefecture_name, :municipality_name, :latitude, :longitude
            )
            ON CONFLICT(area_id) DO UPDATE SET
                prefecture_code=excluded.prefecture_code,
                municipality_code=excluded.municipality_code,
                prefecture_name=excluded.prefecture_name,
                municipality_name=excluded.municipality_name,
                latitude=excluded.latitude,
                longitude=excluded.longitude
            """,
            [
                {
                    **area,
                    "latitude": area.get("latitude"),
                    "longitude": area.get("longitude"),
                }
                for area in areas
            ],
        )
    print(f"seeded {len(areas)} areas")


if __name__ == "__main__":
    main()
