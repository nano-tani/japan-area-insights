from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.population import CENSUS_2025_CHANGE_ID, CENSUS_2025_TOTAL_ID, normalize_census_2025
from japan_area_insights.sources.estat import BASE_URL, EStatClient

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def main() -> None:
    initialize(DB_PATH)
    client = EStatClient()
    with connect(DB_PATH) as conn:
        area_ids = [str(row["area_id"]) for row in conn.execute("SELECT area_id FROM areas ORDER BY area_id")]
    if not area_ids:
        raise SystemExit("No areas found. Run: python scripts/seed_areas.py")

    params = {"limit": 100000}
    total_payload = client.get_stats_data(CENSUS_2025_TOTAL_ID, params)
    change_payload = client.get_stats_data(CENSUS_2025_CHANGE_ID, params)
    rows = normalize_census_2025(total_payload, change_payload, area_ids)
    raw = json.dumps([total_payload, change_payload], ensure_ascii=False, sort_keys=True).encode("utf-8")
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
                "政府統計の総合窓口 e-Stat / 令和7年国勢調査 速報集計",
                f"{CENSUS_2025_TOTAL_ID},{CENSUS_2025_CHANGE_ID}",
                "https://www.e-stat.go.jp/stat-search/database?statdisp_id=0004050417",
                "https://www.e-stat.go.jp/terms-of-use",
                "2026-05-29",
                fetched_at,
                hashlib.sha256(raw).hexdigest(),
            ),
        )
        source_id = cursor.lastrowid
        for row in rows:
            conn.execute(
                """
                INSERT INTO population (
                    area_id, year, population, households,
                    population_change_rate, household_change_rate, source_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(area_id, year) DO UPDATE SET
                    population=excluded.population,
                    households=excluded.households,
                    population_change_rate=excluded.population_change_rate,
                    household_change_rate=excluded.household_change_rate,
                    source_id=excluded.source_id
                """,
                (
                    row["area_id"],
                    row["year"],
                    row["population"],
                    row["households"],
                    row["population_change_rate"],
                    row["household_change_rate"],
                    source_id,
                ),
            )
    print(f"stored {len(rows)} population rows from {BASE_URL}")


if __name__ == "__main__":
    main()
