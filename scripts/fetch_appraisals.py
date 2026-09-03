from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

from japan_area_insights.appraisal_analysis import (
    DIVISIONS,
    compute_appraisal_metrics,
    ensure_appraisal_schema,
    normalize_appraisals,
)
from japan_area_insights.db import connect, initialize
from japan_area_insights.sources.reinfolib import BASE_URL, ReinfolibClient

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch XCT001 appraisal reports for configured wards")
    parser.add_argument("--from-year", type=int, default=2022)
    parser.add_argument("--to-year", type=int, default=2026)
    parser.add_argument("--interval", type=float, default=0.5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    initialize(DB_PATH)
    client = ReinfolibClient(min_interval_seconds=max(0.0, args.interval))
    with connect(DB_PATH) as conn:
        ensure_appraisal_schema(conn)
        area_ids = [str(row["area_id"]) for row in conn.execute("SELECT area_id FROM areas ORDER BY area_id")]
        prefectures = sorted({str(row["prefecture_code"]) for row in conn.execute("SELECT prefecture_code FROM areas")})
    if not area_ids:
        raise SystemExit("No areas found. Run: python scripts/seed_areas.py")

    # XCT001 exposes a rolling five-year window. A 404 means that the requested
    # year/division has no available data and should not stop the refresh.
    start = max(2022, args.from_year, args.to_year - 4)
    end = args.to_year
    stored = 0
    for year in range(start, end + 1):
        for division in DIVISIONS:
            try:
                payload = client.get_json(
                    "XCT001",
                    {"year": year, "area": ",".join(prefectures), "division": division},
                )
            except HTTPError as exc:
                if exc.code == 404:
                    print(f"XCT001 {year} division={division}: no data")
                    continue
                raise
            rows = normalize_appraisals(payload, year=year, division=division, allowed_area_ids=area_ids)
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            with connect(DB_PATH) as conn:
                ensure_appraisal_schema(conn)
                cursor = conn.execute(
                    """
                    INSERT INTO data_sources(
                        source_name,dataset_id,source_url,terms_url,published_at,fetched_at,raw_hash
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        "国土交通省 不動産情報ライブラリ / 鑑定評価書情報",
                        f"XCT001:{year}:{division}",
                        f"{BASE_URL}/XCT001",
                        "https://www.reinfolib.mlit.go.jp/help/termsOfUse/",
                        None,
                        datetime.now(timezone.utc).isoformat(),
                        hashlib.sha256(raw).hexdigest(),
                    ),
                )
                source_id = int(cursor.lastrowid)
                conn.execute("DELETE FROM appraisal_records WHERE year=? AND division=?", (year, division))
                if rows:
                    conn.executemany(
                        """
                        INSERT INTO appraisal_records(
                            appraisal_id,area_id,year,division,public_price,
                            inheritance_road_value,comparison_price,income_price,cost_price,
                            development_price,capitalization_rate,latitude,longitude,raw_json,source_id
                        ) VALUES (
                            :appraisal_id,:area_id,:year,:division,:public_price,
                            :inheritance_road_value,:comparison_price,:income_price,:cost_price,
                            :development_price,:capitalization_rate,:latitude,:longitude,:raw_json,:source_id
                        )
                        """,
                        [{**row, "source_id": source_id} for row in rows],
                    )
            stored += len(rows)
            print(f"XCT001 {year} division={division}: {len(rows)} Tokyo-ward records")

    with connect(DB_PATH) as conn:
        metrics = compute_appraisal_metrics(conn)
    print(f"stored {stored} appraisal records; computed {metrics} appraisal metrics")


if __name__ == "__main__":
    main()
