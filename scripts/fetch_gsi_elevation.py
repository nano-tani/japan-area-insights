from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

from japan_area_insights.db import connect, initialize
from japan_area_insights.geo import mesh250_center
from japan_area_insights.sources.gsi import GsiElevationClient, GsiRateLimit
from japan_area_insights.terrain_analysis import (
    compute_ward_terrain_metrics,
    ensure_terrain_schema,
    normalize_elevation,
    upsert_mesh_elevation,
)

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch GSI elevation at populated 250m mesh centers")
    parser.add_argument("--interval", type=float, default=0.15)
    parser.add_argument("--max-meshes", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    initialize(DB_PATH)
    with connect(DB_PATH) as conn:
        ensure_terrain_schema(conn)
        rows = conn.execute(
            """
            SELECT mesh_id,area_id FROM future_population
            WHERE year=2025 AND projected_population>0
            ORDER BY area_id,mesh_id
            """
        ).fetchall()
        meshes = [(str(row["mesh_id"]), str(row["area_id"])) for row in rows]
        if args.max_meshes is not None:
            meshes = meshes[: max(0, args.max_meshes)]
        source_id = int(conn.execute(
            """
            INSERT INTO data_sources(source_name,dataset_id,source_url,terms_url,published_at,fetched_at,raw_hash)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                "国土地理院 / 地理院地図 標高値",
                "GSI:elevation",
                "https://maps.gsi.go.jp/development/elevation_s.html",
                "https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html",
                None,
                datetime.now(timezone.utc).isoformat(),
                None,
            ),
        ).lastrowid)
        if args.max_meshes is None:
            conn.execute("DELETE FROM mesh_terrain_metrics")

    client = GsiElevationClient(min_interval_seconds=max(0.0, args.interval))
    success = 0
    stopped = False
    with connect(DB_PATH) as conn:
        ensure_terrain_schema(conn)
        for index, (mesh_id, area_id) in enumerate(meshes, start=1):
            try:
                lon, lat = mesh250_center(mesh_id)
            except ValueError:
                continue
            try:
                payload = client.elevation(lon, lat)
            except GsiRateLimit as exc:
                print(f"warning: {exc}; retained partial data at {index - 1}/{len(meshes)} meshes")
                stopped = True
                break
            except HTTPError as exc:
                print(f"warning: GSI HTTP {exc.code} for mesh {mesh_id}; continuing")
                continue
            elevation_m, elevation_source = normalize_elevation(payload)
            if elevation_m is None:
                continue
            upsert_mesh_elevation(
                conn,
                mesh_id=mesh_id,
                area_id=area_id,
                elevation_m=elevation_m,
                elevation_source=elevation_source,
                source_id=source_id,
            )
            success += 1
            if index % 200 == 0:
                conn.commit()
                print(f"GSI elevation: {index}/{len(meshes)}, stored={success}")
        conn.commit()
        metrics = compute_ward_terrain_metrics(conn)
    suffix = " (partial: request limit)" if stopped else ""
    print(f"GSI elevation complete{suffix}: target={len(meshes)}, stored={success}, ward_metrics={metrics}")


if __name__ == "__main__":
    main()
