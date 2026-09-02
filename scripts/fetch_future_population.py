from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from japan_area_insights.db import connect, initialize
from japan_area_insights.future_population import normalize_future_population
from japan_area_insights.land_prices import tiles_for_bbox
from japan_area_insights.sources.reinfolib import BASE_URL, ReinfolibClient

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch XKT013 future-population 250m meshes for Tokyo 23 wards")
    parser.add_argument("--zoom", type=int, default=12, choices=[11, 12, 13, 14, 15])
    parser.add_argument("--interval", type=float, default=0.3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    initialize(DB_PATH)
    client = ReinfolibClient(min_interval_seconds=max(0.0, args.interval))

    with connect(DB_PATH) as conn:
        area_ids = [str(row["area_id"]) for row in conn.execute("SELECT area_id FROM areas ORDER BY area_id")]
    if not area_ids:
        raise SystemExit("No areas found. Run: python scripts/seed_areas.py")

    allowed = set(area_ids)
    meshes: dict[str, dict] = {}
    digest = hashlib.sha256()
    for x, y in tiles_for_bbox(zoom=args.zoom):
        payload = client.get_json(
            "XKT013",
            {"response_format": "geojson", "z": args.zoom, "x": x, "y": y},
        )
        digest.update(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        for feature in payload.get("features", []) or []:
            props = feature.get("properties") or {}
            area_id = str(props.get("SHICODE") or "").zfill(5)
            mesh_id = str(props.get("MESH_ID") or "").strip()
            if area_id in allowed and mesh_id:
                meshes[mesh_id] = props

    normalized = list(normalize_future_population(meshes.values(), allowed_area_ids=area_ids))
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
                "国土交通省 不動産情報ライブラリ / 国土数値情報 将来推計人口250mメッシュ",
                "XKT013:R6",
                f"{BASE_URL}/XKT013",
                "https://www.reinfolib.mlit.go.jp/help/termsOfUse/",
                None,
                fetched_at,
                digest.hexdigest(),
            ),
        )
        source_id = cursor.lastrowid
        conn.execute(
            "DELETE FROM future_population WHERE area_id IN ({})".format(",".join("?" for _ in area_ids)),
            area_ids,
        )
        conn.executemany(
            """
            INSERT INTO future_population (
                area_id, mesh_id, year, projected_population, retention_rate, source_id
            ) VALUES (
                :area_id, :mesh_id, :year, :projected_population, :retention_rate, :source_id
            )
            """,
            [{**row, "source_id": source_id} for row in normalized],
        )

    print(f"stored {len(meshes)} meshes / {len(normalized)} mesh-year rows from XKT013")


if __name__ == "__main__":
    main()
