from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from japan_area_insights.analysis_schema import ensure_analysis_schema
from japan_area_insights.db import connect, initialize
from japan_area_insights.land_prices import aggregate_land_prices, normalize_xpt002, tiles_for_bbox
from japan_area_insights.sources.reinfolib import BASE_URL, ReinfolibClient

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch XPT002 land-price data for configured areas")
    parser.add_argument("--from-year", type=int, required=True)
    parser.add_argument("--to-year", type=int, required=True)
    parser.add_argument("--zoom", type=int, default=13, choices=[13, 14, 15])
    parser.add_argument("--interval", type=float, default=0.5)
    return parser.parse_args()


def pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current / previous - 1.0) * 100.0, 4)


def recalculate_changes() -> None:
    with connect(DB_PATH) as conn:
        area_ids = [str(row["area_id"]) for row in conn.execute("SELECT area_id FROM areas")]
        for area_id in area_ids:
            rows = conn.execute(
                "SELECT year, official_land_price FROM area_prices WHERE area_id=? ORDER BY year",
                (area_id,),
            ).fetchall()
            prices = {int(row["year"]): row["official_land_price"] for row in rows}
            for year, current in prices.items():
                conn.execute(
                    """
                    UPDATE area_prices SET yoy_change=?, change_3y=?, change_5y=?
                    WHERE area_id=? AND year=?
                    """,
                    (
                        pct_change(current, prices.get(year - 1)),
                        pct_change(current, prices.get(year - 3)),
                        pct_change(current, prices.get(year - 5)),
                        area_id,
                        year,
                    ),
                )


def main() -> None:
    args = parse_args()
    if args.from_year > args.to_year:
        raise SystemExit("--from-year must be <= --to-year")

    initialize(DB_PATH)
    with connect(DB_PATH) as conn:
        ensure_analysis_schema(conn)
    client = ReinfolibClient(min_interval_seconds=max(0.0, args.interval))
    with connect(DB_PATH) as conn:
        area_rows = conn.execute("SELECT area_id, municipality_name FROM areas ORDER BY area_id").fetchall()
    if not area_rows:
        raise SystemExit("No areas found. Run: python scripts/seed_areas.py")

    area_ids = [str(row["area_id"]) for row in area_rows]
    tile_coords = tiles_for_bbox(zoom=args.zoom)

    for year in range(args.from_year, args.to_year + 1):
        hasher = hashlib.sha256()
        all_rows: list[dict] = []
        for classification in (0, 1):
            dedup: dict[str, dict] = {}
            for x, y in tile_coords:
                params = {
                    "response_format": "geojson",
                    "z": args.zoom,
                    "x": x,
                    "y": y,
                    "year": year,
                    "priceClassification": classification,
                }
                payload = client.get_json("XPT002", params)
                hasher.update(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
                for row in normalize_xpt002(
                    payload,
                    allowed_area_ids=area_ids,
                    year=year,
                    price_classification=classification,
                ):
                    dedup[row["point_id"]] = row
            all_rows.extend(dedup.values())

        official = aggregate_land_prices(row for row in all_rows if row["price_classification"] == 0)
        prefectural = aggregate_land_prices(row for row in all_rows if row["price_classification"] == 1)
        fetched_at = datetime.now(timezone.utc).isoformat()

        with connect(DB_PATH) as conn:
            ensure_analysis_schema(conn)
            cursor = conn.execute(
                """
                INSERT INTO data_sources (
                    source_name, dataset_id, source_url, terms_url,
                    published_at, fetched_at, raw_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "国土交通省 不動産情報ライブラリ",
                    f"XPT002:{year}",
                    f"{BASE_URL}/XPT002",
                    "https://www.reinfolib.mlit.go.jp/help/termsOfUse/",
                    None,
                    fetched_at,
                    hasher.hexdigest(),
                ),
            )
            source_id = int(cursor.lastrowid)
            conn.execute("DELETE FROM land_price_points WHERE year=?", (year,))
            if all_rows:
                conn.executemany(
                    """
                    INSERT INTO land_price_points(
                        point_id, area_id, year, price_classification, price,
                        last_year_price, yoy_change, latitude, longitude,
                        use_category, standard_lot_number, residence_display,
                        location_text, cadastral_sqm, building_structure,
                        ground_floors, underground_floors, front_road_type,
                        front_road_azimuth, front_road_width_m, gas_supply,
                        water_supply, sewer_supply, nearest_station,
                        station_distance_m, usage_status, surrounding_land_use,
                        area_division, zoning, fireproof_zone, coverage_ratio,
                        floor_area_ratio, source_id
                    ) VALUES (
                        :point_id, :area_id, :year, :price_classification, :price,
                        :last_year_price, :yoy_change, :latitude, :longitude,
                        :use_category, :standard_lot_number, :residence_display,
                        :location_text, :cadastral_sqm, :building_structure,
                        :ground_floors, :underground_floors, :front_road_type,
                        :front_road_azimuth, :front_road_width_m, :gas_supply,
                        :water_supply, :sewer_supply, :nearest_station,
                        :station_distance_m, :usage_status, :surrounding_land_use,
                        :area_division, :zoning, :fireproof_zone, :coverage_ratio,
                        :floor_area_ratio, :source_id
                    )
                    """,
                    [{**row, "source_id": source_id} for row in all_rows],
                )
            for area_id in area_ids:
                conn.execute(
                    """
                    INSERT INTO area_prices (
                        area_id, year, official_land_price, prefectural_land_price, source_id
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(area_id, year) DO UPDATE SET
                        official_land_price=excluded.official_land_price,
                        prefectural_land_price=excluded.prefectural_land_price,
                        source_id=excluded.source_id
                    """,
                    (
                        area_id,
                        year,
                        official.get(area_id, {}).get("mean_price"),
                        prefectural.get(area_id, {}).get("mean_price"),
                        source_id,
                    ),
                )
        print(f"{year}: {len(all_rows)} land-price points")

    recalculate_changes()


if __name__ == "__main__":
    main()
