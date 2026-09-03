from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

from japan_area_insights.db import connect, initialize
from japan_area_insights.geo import mesh250_center
from japan_area_insights.jshis_analysis import (
    GROUND_VERSION,
    HAZARD_VERSION,
    compute_ward_seismic_metrics,
    ensure_jshis_schema,
    normalize_ground_payload,
    normalize_hazard_payload,
    upsert_mesh_seismic,
)
from japan_area_insights.sources.jshis import JShisClient, JShisRateLimit

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch J-SHIS 250m surface-ground and probabilistic seismic hazard data")
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--max-meshes", type=int, default=None, help="debug/partial limit")
    parser.add_argument("--ground-version", default=GROUND_VERSION)
    parser.add_argument("--hazard-version", default=HAZARD_VERSION)
    return parser.parse_args()


def _source(conn, *, dataset_id: str, title: str, url: str, version: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO data_sources(
            source_name,dataset_id,source_url,terms_url,published_at,fetched_at,raw_hash
        ) VALUES (?,?,?,?,?,?,?)
        """,
        (
            f"防災科学技術研究所 J-SHIS（地震ハザードステーション） / {title}",
            dataset_id,
            url,
            "https://www.j-shis.bosai.go.jp/agreement",
            version,
            datetime.now(timezone.utc).isoformat(),
            None,
        ),
    )
    return int(cursor.lastrowid)


def main() -> None:
    args = parse_args()
    initialize(DB_PATH)
    with connect(DB_PATH) as conn:
        ensure_jshis_schema(conn)
        rows = conn.execute(
            """
            SELECT fp.mesh_id,fp.area_id,fp.projected_population
            FROM future_population fp
            WHERE fp.year=2025 AND fp.projected_population>0
            ORDER BY fp.area_id,fp.mesh_id
            """
        ).fetchall()
        meshes = [(str(row["mesh_id"]), str(row["area_id"])) for row in rows]
        if args.max_meshes is not None:
            meshes = meshes[: max(0, args.max_meshes)]
        source_ground_id = _source(
            conn,
            dataset_id=f"J-SHIS:sstrct:{args.ground_version}",
            title=f"表層地盤250mメッシュ {args.ground_version}",
            url="https://www.j-shis.bosai.go.jp/api-sstruct-meshinfo",
            version=args.ground_version,
        )
        source_hazard_id = _source(
            conn,
            dataset_id=f"J-SHIS:pshm:{args.hazard_version}:AVR:TTL_MTTL",
            title=f"確率論的地震動予測地図 {args.hazard_version}",
            url="https://www.j-shis.bosai.go.jp/api-pshm-meshinfo",
            version=args.hazard_version,
        )

    if not meshes:
        print("no populated 2025 meshes; skipping J-SHIS")
        return

    client = JShisClient(min_interval_seconds=max(0.0, args.interval))
    ground_success = 0
    hazard_success = 0
    stopped_for_limit = False

    with connect(DB_PATH) as conn:
        ensure_jshis_schema(conn)
        # A full refresh starts from a clean J-SHIS snapshot. Partial API-limit
        # results are still retained in this run and explicitly graded by coverage.
        if args.max_meshes is None:
            conn.execute("DELETE FROM mesh_seismic_metrics")

        for index, (mesh_id, area_id) in enumerate(meshes, start=1):
            try:
                lon, lat = mesh250_center(mesh_id)
            except ValueError:
                continue
            position = f"{lon:.8f},{lat:.8f}"
            ground = None
            hazard = None
            try:
                ground_payload = client.get_json(
                    f"sstrct/{args.ground_version}/meshinfo.geojson",
                    {"position": position, "epsg": 4326},
                )
                ground = normalize_ground_payload(ground_payload)
                if ground:
                    ground_success += 1

                hazard_payload = client.get_json(
                    f"pshm/{args.hazard_version}/AVR/TTL_MTTL/meshinfo.geojson",
                    {"position": position, "epsg": 4326},
                )
                hazard = normalize_hazard_payload(hazard_payload)
                if hazard:
                    hazard_success += 1
            except JShisRateLimit as exc:
                print(f"warning: {exc}; retained partial data at {index - 1}/{len(meshes)} meshes")
                stopped_for_limit = True
                break
            except HTTPError as exc:
                # Individual unavailable meshes should not abort a nationwide public-data refresh.
                print(f"warning: J-SHIS HTTP {exc.code} for mesh {mesh_id}; continuing")

            upsert_mesh_seismic(
                conn,
                mesh_id=mesh_id,
                area_id=area_id,
                ground=ground,
                hazard=hazard,
                source_ground_id=source_ground_id,
                source_hazard_id=source_hazard_id,
                ground_version=args.ground_version,
                hazard_version=args.hazard_version,
            )
            if index % 100 == 0:
                conn.commit()
                print(f"J-SHIS: {index}/{len(meshes)} meshes, ground={ground_success}, hazard={hazard_success}")

        conn.commit()
        metric_count = compute_ward_seismic_metrics(conn)

    suffix = " (partial: request limit)" if stopped_for_limit else ""
    print(
        f"J-SHIS complete{suffix}: target={len(meshes)}, ground={ground_success}, "
        f"hazard={hazard_success}, ward_metrics={metric_count}"
    )


if __name__ == "__main__":
    main()
