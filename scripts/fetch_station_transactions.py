from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

from japan_area_insights.db import connect, initialize
from japan_area_insights.sources.reinfolib import BASE_URL, ReinfolibClient
from japan_area_insights.station_areas import STATION_DEFINITION_VERSION
from japan_area_insights.station_transactions import (
    ensure_station_transaction_schema,
    normalize_xit001_station,
)

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch XIT001 transactions by station group code")
    parser.add_argument("--from-year", type=int, required=True)
    parser.add_argument("--to-year", type=int, required=True)
    parser.add_argument("--interval", type=float, default=0.3)
    parser.add_argument("--include-current-year", action="store_true")
    parser.add_argument("--station", action="append", default=[], help="optional six-digit station group code")
    parser.add_argument("--max-stations", type=int, default=None, help="debug limit; omitted means all")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.from_year > args.to_year:
        raise SystemExit("--from-year must be <= --to-year")

    current_year = date.today().year
    effective_to = args.to_year if args.include_current_year else min(args.to_year, current_year - 1)
    if args.from_year > effective_to:
        raise SystemExit("No completed year is inside the requested range")

    initialize(DB_PATH)
    client = ReinfolibClient(min_interval_seconds=max(0.0, args.interval))

    with connect(DB_PATH) as conn:
        ensure_station_transaction_schema(conn)
        rows = conn.execute(
            """
            SELECT canonical_code, name
            FROM geo_units
            WHERE geo_type='station_area' AND definition_version=? AND is_active=1
            ORDER BY canonical_code
            """,
            (STATION_DEFINITION_VERSION,),
        ).fetchall()

    requested = {str(value).strip() for value in args.station if str(value).strip()}
    stations = [
        (str(row["canonical_code"]), str(row["name"]))
        for row in rows
        if not requested or str(row["canonical_code"]) in requested
    ]
    if args.max_stations is not None:
        stations = stations[: max(0, args.max_stations)]
    if not stations:
        raise SystemExit("No active station areas found. Run: python scripts/sync_station_areas.py")

    digest = hashlib.sha256()
    collected: list[dict] = []
    skipped: list[tuple[str, int, int | str]] = []

    for year in range(args.from_year, effective_to + 1):
        year_count = 0
        for index, (group_code, station_name) in enumerate(stations, start=1):
            if len(group_code) != 6 or not group_code.isdigit():
                skipped.append((group_code, year, "invalid"))
                continue
            params = {
                "year": year,
                "station": group_code,
                "priceClassification": "01",
                "language": "ja",
            }
            try:
                payload = client.get_json("XIT001", params)
            except HTTPError as exc:
                # XIT001 returns 404 for a valid station/year pair when no
                # transaction records exist. That is an empty sample, not a
                # failed refresh. 400 is likewise skipped for unsupported or
                # stale group codes discovered in the station master.
                if exc.code in {400, 404}:
                    digest.update(f"HTTP{exc.code}|{year}|{group_code}".encode("utf-8"))
                    skipped.append((group_code, year, exc.code))
                    continue
                raise

            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            digest.update(raw)
            normalized = normalize_xit001_station(
                payload,
                station_group_code=group_code,
                year=year,
            )
            collected.extend(normalized)
            year_count += len(normalized)
            if index % 100 == 0:
                print(f"{year}: {index}/{len(stations)} stations processed")
        print(f"{year}: collected {year_count} station-filtered transactions")

    fetched_at = datetime.now(timezone.utc).isoformat()
    with connect(DB_PATH) as conn:
        ensure_station_transaction_schema(conn)
        cursor = conn.execute(
            """
            INSERT INTO data_sources(
                source_name, dataset_id, source_url, terms_url,
                published_at, fetched_at, raw_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "国土交通省 不動産情報ライブラリ / 駅指定不動産取引価格情報",
                f"XIT001:station:{args.from_year}-{effective_to}:01",
                f"{BASE_URL}/XIT001",
                "https://www.reinfolib.mlit.go.jp/help/termsOfUse/",
                None,
                fetched_at,
                digest.hexdigest(),
            ),
        )
        source_id = int(cursor.lastrowid)

        codes = [code for code, _ in stations]
        placeholders = ",".join("?" for _ in codes)
        conn.execute(
            f"""
            DELETE FROM station_transactions
            WHERE station_group_code IN ({placeholders})
              AND year BETWEEN ? AND ?
            """,
            (*codes, args.from_year, effective_to),
        )
        if collected:
            conn.executemany(
                """
                INSERT INTO station_transactions(
                    station_group_code, transaction_id, year, quarter,
                    transaction_date, municipality_code, district_name,
                    price_category, property_type, total_price,
                    unit_price, area_sqm, source_id
                ) VALUES (
                    :station_group_code, :transaction_id, :year, :quarter,
                    :transaction_date, :municipality_code, :district_name,
                    :price_category, :property_type, :total_price,
                    :unit_price, :area_sqm, :source_id
                )
                ON CONFLICT(station_group_code, transaction_id) DO UPDATE SET
                    year=excluded.year,
                    quarter=excluded.quarter,
                    transaction_date=excluded.transaction_date,
                    municipality_code=excluded.municipality_code,
                    district_name=excluded.district_name,
                    price_category=excluded.price_category,
                    property_type=excluded.property_type,
                    total_price=excluded.total_price,
                    unit_price=excluded.unit_price,
                    area_sqm=excluded.area_sqm,
                    source_id=excluded.source_id
                """,
                [{**row, "source_id": source_id} for row in collected],
            )

    reason_counts: dict[str, int] = {}
    for _, _, reason in skipped:
        key = str(reason)
        reason_counts[key] = reason_counts.get(key, 0) + 1
    print(
        f"stored {len(collected)} station transactions for {len(stations)} station areas "
        f"({args.from_year}-{effective_to}); skipped pairs={len(skipped)} {reason_counts}"
    )


if __name__ == "__main__":
    main()
