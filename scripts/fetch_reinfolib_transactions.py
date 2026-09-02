from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.sources.reinfolib import BASE_URL, ReinfolibClient
from japan_area_insights.transactions import aggregate_transactions, normalize_xit001

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch XIT001 transaction data for Tokyo 23 wards")
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
    client = ReinfolibClient(min_interval_seconds=max(1.0, args.interval))

    with connect(DB_PATH) as conn:
        areas = conn.execute("SELECT area_id, municipality_name FROM areas ORDER BY municipality_code").fetchall()
        if not areas:
            raise SystemExit("No areas found. Run: python scripts/seed_areas.py")

    for year in range(args.from_year, args.to_year + 1):
        for area in areas:
            area_id = area["area_id"]
            params = {
                "year": year,
                "area": "13",
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
                        None,
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
                        price_category, property_type, district_name,
                        total_price, unit_price, area_sqm, source_id
                    ) VALUES (
                        :transaction_id, :area_id, :year, :quarter, :transaction_date,
                        :price_category, :property_type, :district_name,
                        :total_price, :unit_price, :area_sqm, :source_id
                    )
                    ON CONFLICT(transaction_id) DO UPDATE SET
                        quarter=excluded.quarter,
                        transaction_date=excluded.transaction_date,
                        price_category=excluded.price_category,
                        property_type=excluded.property_type,
                        district_name=excluded.district_name,
                        total_price=excluded.total_price,
                        unit_price=excluded.unit_price,
                        area_sqm=excluded.area_sqm,
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
