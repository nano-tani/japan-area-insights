from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

from japan_area_insights.db import connect, initialize
from japan_area_insights.land_prices import tiles_for_bbox
from japan_area_insights.resilience_analysis import (
    assign_disaster_history_areas,
    compute_resilience_metrics,
    ensure_resilience_schema,
    normalize_disaster_history,
    normalize_evacuation_sites,
)
from japan_area_insights.sources.reinfolib import BASE_URL, ReinfolibClient

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch XGT001 evacuation sites and XST001 disaster history")
    parser.add_argument("--zoom", type=int, default=12, choices=[11, 12, 13, 14, 15])
    parser.add_argument("--interval", type=float, default=0.2)
    return parser.parse_args()


def _fetch_tiles(client: ReinfolibClient, api_id: str, zoom: int) -> tuple[list[dict], str, int]:
    features: list[dict] = []
    digest = hashlib.sha256()
    skipped = 0
    for x, y in tiles_for_bbox(zoom=zoom):
        try:
            payload = client.get_json(
                api_id,
                {"response_format": "geojson", "z": zoom, "x": x, "y": y},
            )
        except HTTPError as exc:
            if exc.code in {400, 404, 422}:
                skipped += 1
                continue
            raise
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest.update(raw)
        features.extend(payload.get("features", []) or [])
    return features, digest.hexdigest(), skipped


def _source(conn, api_id: str, title: str, raw_hash: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO data_sources(
            source_name,dataset_id,source_url,terms_url,published_at,fetched_at,raw_hash
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (
            f"国土交通省 不動産情報ライブラリ / {title}",
            api_id,
            f"{BASE_URL}/{api_id}",
            "https://www.reinfolib.mlit.go.jp/help/termsOfUse/",
            None,
            datetime.now(timezone.utc).isoformat(),
            raw_hash,
        ),
    )
    return int(cursor.lastrowid)


def main() -> None:
    args = parse_args()
    initialize(DB_PATH)
    with connect(DB_PATH) as conn:
        ensure_resilience_schema(conn)
        area_names = {str(row["area_id"]): str(row["municipality_name"]) for row in conn.execute("SELECT area_id,municipality_name FROM areas")}
        mesh_to_area = {
            str(row["mesh_id"]): str(row["area_id"])
            for row in conn.execute("SELECT DISTINCT mesh_id,area_id FROM future_population")
        }
    if not mesh_to_area:
        raise SystemExit("future_population is empty; fetch XKT013 before resilience data")

    client = ReinfolibClient(min_interval_seconds=max(0.0, args.interval))

    xgt_features, xgt_hash, xgt_skipped = _fetch_tiles(client, "XGT001", args.zoom)
    evacuation_rows = normalize_evacuation_sites(
        {"features": xgt_features},
        mesh_to_area=mesh_to_area,
        area_names=area_names,
    )
    with connect(DB_PATH) as conn:
        ensure_resilience_schema(conn)
        source_id = _source(conn, "XGT001", "指定緊急避難場所", xgt_hash)
        conn.execute("DELETE FROM evacuation_sites")
        if evacuation_rows:
            conn.executemany(
                """
                INSERT INTO evacuation_sites(
                    common_id,area_id,prefecture_and_city,facility_name,address,
                    flood_flag,landslide_flag,high_tide_flag,earthquake_flag,tsunami_flag,
                    large_fire_flag,inland_flooding_flag,volcanic_phenomenon_flag,same_address_flag,
                    remarks,latitude,longitude,source_id
                ) VALUES (
                    :common_id,:area_id,:prefecture_and_city,:facility_name,:address,
                    :flood_flag,:landslide_flag,:high_tide_flag,:earthquake_flag,:tsunami_flag,
                    :large_fire_flag,:inland_flooding_flag,:volcanic_phenomenon_flag,:same_address_flag,
                    :remarks,:latitude,:longitude,:source_id
                )
                """,
                [{**row, "source_id": source_id} for row in evacuation_rows],
            )
    print(f"XGT001: stored {len(evacuation_rows)} sites; skipped tiles={xgt_skipped}")

    xst_features, xst_hash, xst_skipped = _fetch_tiles(client, "XST001", args.zoom)
    history_rows = normalize_disaster_history({"features": xst_features})
    with connect(DB_PATH) as conn:
        ensure_resilience_schema(conn)
        source_id = _source(conn, "XST001", "国土調査 災害履歴", xst_hash)
        conn.execute("DELETE FROM disaster_history_areas")
        conn.execute("DELETE FROM disaster_history")
        if history_rows:
            conn.executemany(
                """
                INSERT INTO disaster_history(
                    event_id,disastertype_code,disaster_name,disaster_date,disaster_source,
                    geometry_type,geometry_json,centroid_lat,centroid_lon,source_id
                ) VALUES (
                    :event_id,:disastertype_code,:disaster_name,:disaster_date,:disaster_source,
                    :geometry_type,:geometry_json,:centroid_lat,:centroid_lon,:source_id
                )
                """,
                [{**row, "source_id": source_id} for row in history_rows],
            )
        links = assign_disaster_history_areas(conn)
        metrics = compute_resilience_metrics(conn)
    print(f"XST001: stored {len(history_rows)} features; ward links={links}; skipped tiles={xst_skipped}")
    print(f"computed {metrics} resilience metrics")


if __name__ == "__main__":
    main()
