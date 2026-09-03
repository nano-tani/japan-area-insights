from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.land_prices import tiles_for_bbox
from japan_area_insights.sources.reinfolib import BASE_URL, ReinfolibClient
from japan_area_insights.transport import normalize_xkt015

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch station/ridership data for Tokyo 23 wards")
    parser.add_argument("--zoom", type=int, default=12, choices=[11, 12, 13, 14, 15])
    parser.add_argument("--interval", type=float, default=0.3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    initialize(DB_PATH)
    client = ReinfolibClient(min_interval_seconds=max(0.0, args.interval))

    with connect(DB_PATH) as conn:
        area_ids = [str(row["area_id"]) for row in conn.execute("SELECT area_id FROM areas ORDER BY area_id")]
        mesh_rows = conn.execute(
            "SELECT DISTINCT mesh_id, area_id FROM future_population"
        ).fetchall()

    if not area_ids:
        raise SystemExit("No areas found. Run: python scripts/seed_areas.py")
    if not mesh_rows:
        raise SystemExit("Future-population meshes are required before transport attribution")

    mesh_to_area = {str(row["mesh_id"]): str(row["area_id"]) for row in mesh_rows}
    digest = hashlib.sha256()
    collected: dict[str, dict] = {}

    for x, y in tiles_for_bbox(zoom=args.zoom):
        payload = client.get_json(
            "XKT015",
            {"response_format": "geojson", "z": args.zoom, "x": x, "y": y},
        )
        digest.update(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        for row in normalize_xkt015(
            payload,
            allowed_area_ids=area_ids,
            mesh_to_area=mesh_to_area,
        ):
            collected[row["station_id"]] = row

    fetched_at = datetime.now(timezone.utc).isoformat()
    with connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO data_sources (
                source_name, dataset_id, source_url, terms_url,
                published_at, fetched_at, raw_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "国土交通省 不動産情報ライブラリ / 国土数値情報 駅別乗降客数",
                "XKT015:令和5年度",
                f"{BASE_URL}/XKT015",
                "https://www.reinfolib.mlit.go.jp/help/termsOfUse/",
                None,
                fetched_at,
                digest.hexdigest(),
            ),
        )
        source_id = cursor.lastrowid
        conn.execute("DELETE FROM stations")
        conn.executemany(
            """
            INSERT INTO stations (
                station_id, area_id, station_code, group_code,
                station_name, line_name, operator_name,
                passenger_count, passenger_year, latitude, longitude, source_id
            ) VALUES (
                :station_id, :area_id, :station_code, :group_code,
                :station_name, :line_name, :operator_name,
                :passenger_count, :passenger_year, :latitude, :longitude, :source_id
            )
            """,
            [{**row, "source_id": source_id} for row in collected.values()],
        )

    print(f"XKT015: stored {len(collected)} station-line records")


if __name__ == "__main__":
    main()
