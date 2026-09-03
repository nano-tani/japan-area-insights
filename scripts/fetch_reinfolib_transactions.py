from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from japan_area_insights.analysis_schema import ensure_analysis_schema
from japan_area_insights.db import connect, initialize
from japan_area_insights.sources.reinfolib import BASE_URL, ReinfolibClient
from japan_area_insights.transactions import aggregate_transactions, normalize_xit001

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch XIT001 transaction data for configured municipalities")
    parser.add_argument("--from-year", type=int, required=True)
    parser.add_argument("--to-year", type=int, required=True)
    parser.add_argument("--price-classification", choices=["01", "02"], default="01")
    parser.add_argument("--interval", type=float, default=1.0, help="minimum seconds between API requests")
    return parser.parse_args()


def category_name(code: str) -> str:
    return "不動産取引価格情報" if code == "01" else "成約価格情報"


def main() -> None:
    args = parse_args()
    if args.from_year > args.to_year:
        raise SystemExit("--from-year must be <= --to-year")

    initialize(DB_PATH)
    with connect(DB_PATH) as conn:
        ensure_analysis_schema(conn)
    client = ReinfolibClient(min_interval_seconds=max(1.0, args.interval))

    with connect(DB_PATH) as conn:
        areas = conn.execute(
            "SELECT area_id, prefecture_code, municipality_name FROM areas ORDER BY municipality_code"
        ).fetchall()
        if not areas:
            raise SystemExit("No areas found. Run: python scripts/seed_areas.py")

    for year in range(args.from_year, args.to_year + 1):
        for area in areas:
            area_id = str(area["area_id"])
            params = {
                "year": year,
                "area": str(area["prefecture_code"]),
                "city": area_id,
                "priceClassification": args.price_classification,
                "language": "ja",
            }
            payload = client.get_json("XIT001", params)
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            raw_hash = hashlib.sha256(raw).hexdigest()
            rows = normalize_xit001(payload, area_id=area_id, year=year)
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
                        f"XIT001:{year}:{area_id}:{args.price_classification}",
                        f"{BASE_URL}/XIT001",
                        "https://www.reinfolib.mlit.go.jp/help/termsOfUse/",
                        None,
                        fetched_at,
                        raw_hash,
                    ),
                )
                source_id = cursor.lastrowid
                conn.execute(
                    "DELETE FROM transactions WHERE area_id=? AND year=? AND price_category=?",
                    (area_id, year, category_name(args.price_classification)),
                )
                conn.executemany(
                    """
                    INSERT INTO transactions (
                        transaction_id, area_id, year, quarter, transaction_date,
                        price_category, property_type, region, district_name, district_code,
                        total_price, price_per_unit, unit_price, area_sqm,
                        floor_plan, land_shape, frontage_m, total_floor_area_sqm,
                        building_year, structure, use_name, purpose,
                        road_direction, road_classification, road_breadth_m,
                        city_planning, coverage_ratio, floor_area_ratio,
                        renovation, remarks, source_id
                    ) VALUES (
                        :transaction_id, :area_id, :year, :quarter, :transaction_date,
                        :price_category, :property_type, :region, :district_name, :district_code,
                        :total_price, :price_per_unit, :unit_price, :area_sqm,
                        :floor_plan, :land_shape, :frontage_m, :total_floor_area_sqm,
                        :building_year, :structure, :use_name, :purpose,
                        :road_direction, :road_classification, :road_breadth_m,
                        :city_planning, :coverage_ratio, :floor_area_ratio,
                        :renovation, :remarks, :source_id
                    )
                    ON CONFLICT(transaction_id) DO UPDATE SET
                        quarter=excluded.quarter,
                        transaction_date=excluded.transaction_date,
                        price_category=excluded.price_category,
                        property_type=excluded.property_type,
                        region=excluded.region,
                        district_name=excluded.district_name,
                        district_code=excluded.district_code,
                        total_price=excluded.total_price,
                        price_per_unit=excluded.price_per_unit,
                        unit_price=excluded.unit_price,
                        area_sqm=excluded.area_sqm,
                        floor_plan=excluded.floor_plan,
                        land_shape=excluded.land_shape,
                        frontage_m=excluded.frontage_m,
                        total_floor_area_sqm=excluded.total_floor_area_sqm,
                        building_year=excluded.building_year,
                        structure=excluded.structure,
                        use_name=excluded.use_name,
                        purpose=excluded.purpose,
                        road_direction=excluded.road_direction,
                        road_classification=excluded.road_classification,
                        road_breadth_m=excluded.road_breadth_m,
                        city_planning=excluded.city_planning,
                        coverage_ratio=excluded.coverage_ratio,
                        floor_area_ratio=excluded.floor_area_ratio,
                        renovation=excluded.renovation,
                        remarks=excluded.remarks,
                        source_id=excluded.source_id
                    """,
                    [{**row, "source_id": source_id} for row in rows],
                )

                if args.price_classification == "01":
                    agg = aggregate_transactions(rows)
                    conn.execute(
                        """
                        INSERT INTO area_prices (
                            area_id, year, avg_transaction_unit_price,
                            median_transaction_unit_price, transaction_count, source_id
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(area_id, year) DO UPDATE SET
                            avg_transaction_unit_price=excluded.avg_transaction_unit_price,
                            median_transaction_unit_price=excluded.median_transaction_unit_price,
                            transaction_count=excluded.transaction_count,
                            source_id=excluded.source_id
                        """,
                        (
                            area_id,
                            year,
                            agg["avg_transaction_unit_price"],
                            agg["median_transaction_unit_price"],
                            agg["transaction_count"],
                            source_id,
                        ),
                    )

            print(f"{year} {area['municipality_name']}: {len(rows)} transactions")


if __name__ == "__main__":
    main()
