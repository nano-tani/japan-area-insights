from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.future_population import normalize_future_population, rows_from_zip

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import MLIT 250m future-population CSV ZIP for Tokyo")
    parser.add_argument("zip_path", type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    if not args.zip_path.exists():
        raise SystemExit(f"file not found: {args.zip_path}")

    initialize(DB_PATH)
    with connect(DB_PATH) as conn:
        area_ids = [str(row["area_id"]) for row in conn.execute("SELECT area_id FROM areas ORDER BY area_id")]
    if not area_ids:
        raise SystemExit("No areas found. Run: python scripts/seed_areas.py")

    raw_hash = sha256_file(args.zip_path)
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
                "国土数値情報 250mメッシュ別将来推計人口（R6国政局推計）",
                "250m_mesh_suikei_2024_csv_13",
                "https://nlftp.mlit.go.jp/ksj/old/datalist/old_KsjTmplt-m250r6.html",
                "https://nlftp.mlit.go.jp/ksj/other/yakkan.html",
                "2025-02-05",
                fetched_at,
                raw_hash,
            ),
        )
        source_id = cursor.lastrowid
        conn.execute(
            "DELETE FROM future_population WHERE area_id IN ({})".format(",".join("?" for _ in area_ids)),
            area_ids,
        )

        batch: list[dict] = []
        count = 0
        for row in normalize_future_population(rows_from_zip(args.zip_path), allowed_area_ids=area_ids):
            batch.append({**row, "source_id": source_id})
            if len(batch) >= 5000:
                conn.executemany(
                    """
                    INSERT INTO future_population (
                        area_id, mesh_id, year, projected_population, retention_rate, source_id
                    ) VALUES (
                        :area_id, :mesh_id, :year, :projected_population, :retention_rate, :source_id
                    )
                    """,
                    batch,
                )
                count += len(batch)
                batch.clear()
        if batch:
            conn.executemany(
                """
                INSERT INTO future_population (
                    area_id, mesh_id, year, projected_population, retention_rate, source_id
                ) VALUES (
                    :area_id, :mesh_id, :year, :projected_population, :retention_rate, :source_id
                )
                """,
                batch,
            )
            count += len(batch)
    print(f"stored {count} future-population mesh-year rows")


if __name__ == "__main__":
    main()
