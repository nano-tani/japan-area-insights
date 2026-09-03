from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.facilities import FACILITY_APIS, normalize_facility_features
from japan_area_insights.land_prices import tiles_for_bbox
from japan_area_insights.sources.reinfolib import BASE_URL, ReinfolibClient

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"

DATASET_LABELS = {
    "XKT006": "学校（令和5年度）",
    "XKT007": "保育園・幼稚園等（令和5年度）",
    "XKT010": "医療機関（令和2年度）",
    "XKT017": "図書館（文化施設・平成25年度）",
    "XKT018": "市区町村役場及び集会施設等（令和4年度）",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch public facilities for Tokyo 23 wards")
    parser.add_argument("--zoom", type=int, default=13, choices=[13, 14, 15])
    parser.add_argument("--interval", type=float, default=0.3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    initialize(DB_PATH)
    client = ReinfolibClient(min_interval_seconds=max(0.0, args.interval))

    with connect(DB_PATH) as conn:
        areas = conn.execute(
            "SELECT area_id, municipality_name FROM areas ORDER BY area_id"
        ).fetchall()
        mesh_rows = conn.execute(
            "SELECT DISTINCT mesh_id, area_id FROM future_population"
        ).fetchall()

    if not areas:
        raise SystemExit("No areas found. Run: python scripts/seed_areas.py")

    area_ids = [str(row["area_id"]) for row in areas]
    area_names = {str(row["area_id"]): str(row["municipality_name"]) for row in areas}
    mesh_to_area = {str(row["mesh_id"]): str(row["area_id"]) for row in mesh_rows}

    for api_id, facility_type in FACILITY_APIS.items():
        digest = hashlib.sha256()
        collected: dict[str, dict] = {}

        for x, y in tiles_for_bbox(zoom=args.zoom):
            payload = client.get_json(
                api_id,
                {"response_format": "geojson", "z": args.zoom, "x": x, "y": y},
            )
            digest.update(
                json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            )
            for row in normalize_facility_features(
                api_id,
                payload,
                allowed_area_ids=area_ids,
                mesh_to_area=mesh_to_area,
                area_names=area_names,
            ):
                collected[row["facility_id"]] = row

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
                    "国土交通省 不動産情報ライブラリ / 国土数値情報",
                    f"{api_id}:{DATASET_LABELS[api_id]}",
                    f"{BASE_URL}/{api_id}",
                    "https://www.reinfolib.mlit.go.jp/help/termsOfUse/",
                    None,
                    fetched_at,
                    digest.hexdigest(),
                ),
            )
            source_id = cursor.lastrowid
            conn.execute("DELETE FROM facilities WHERE facility_type=?", (facility_type,))
            conn.executemany(
                """
                INSERT INTO facilities (
                    facility_id, area_id, facility_type, facility_subtype,
                    facility_name, address, latitude, longitude, source_id
                ) VALUES (
                    :facility_id, :area_id, :facility_type, :facility_subtype,
                    :facility_name, :address, :latitude, :longitude, :source_id
                )
                """,
                [{**row, "source_id": source_id} for row in collected.values()],
            )

        print(f"{api_id}: stored {len(collected)} {facility_type} facilities")


if __name__ == "__main__":
    main()
