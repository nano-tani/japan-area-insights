from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def table_count(conn: sqlite3.Connection, table: str) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return 0
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the persisted database before publishing public JSON")
    parser.add_argument("--require-stations", action="store_true")
    args = parser.parse_args()

    if not DB_PATH.exists() or DB_PATH.stat().st_size == 0:
        raise SystemExit("refresh database snapshot is missing")

    conn = sqlite3.connect(DB_PATH)
    try:
        checks = {
            "areas": table_count(conn, "areas"),
            "area_prices": table_count(conn, "area_prices"),
            "population": table_count(conn, "population"),
            "future_population": table_count(conn, "future_population"),
        }
        failures = []
        if checks["areas"] != 23:
            failures.append(f"areas={checks['areas']} (expected 23)")
        for table in ("area_prices", "population", "future_population"):
            if checks[table] <= 0:
                failures.append(f"{table}=0")

        if args.require_stations:
            checks["stations"] = table_count(conn, "stations")
            checks["station_transactions"] = table_count(conn, "station_transactions")
            if checks["stations"] <= 0:
                failures.append("stations=0")
            if checks["station_transactions"] <= 0:
                failures.append("station_transactions=0")

        if failures:
            raise SystemExit("refresh database validation failed: " + ", ".join(failures))
        print("refresh database valid: " + ", ".join(f"{key}={value}" for key, value in checks.items()))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
