from __future__ import annotations

import argparse
import http.client
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

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
COMPONENTS = ("all", "ground", "hazard")

GROUND_COLUMNS = (
    "ground_version",
    "microtopography_code",
    "microtopography_name",
    "avs",
    "arv",
    "avs_eb",
    "avs_ref",
    "source_ground_id",
)
HAZARD_COLUMNS = (
    "hazard_version",
    "t30_i45_ps",
    "t30_i50_ps",
    "t30_i55_ps",
    "t30_i60_ps",
    "t30_p03_si",
    "t30_p06_si",
    "t30_p03_sv",
    "t30_p06_sv",
    "source_hazard_id",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch J-SHIS 250m surface-ground and probabilistic seismic hazard data")
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--max-meshes", type=int, default=None, help="debug/partial limit")
    parser.add_argument("--component", choices=COMPONENTS, default="all")
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


def _reset_component(conn, component: str) -> None:
    if component == "all":
        conn.execute("DELETE FROM mesh_seismic_metrics")
        return
    columns = GROUND_COLUMNS if component == "ground" else HAZARD_COLUMNS
    assignments = ", ".join(f"{column}=NULL" for column in columns)
    conn.execute(f"UPDATE mesh_seismic_metrics SET {assignments}")


def _transient_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


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

        source_ground_id = None
        source_hazard_id = None
        if args.component in {"all", "ground"}:
            source_ground_id = _source(
                conn,
                dataset_id=f"J-SHIS:sstrct:{args.ground_version}",
                title=f"表層地盤250mメッシュ {args.ground_version}",
                url="https://www.j-shis.bosai.go.jp/api-sstruct-meshinfo",
                version=args.ground_version,
            )
        if args.component in {"all", "hazard"}:
            source_hazard_id = _source(
                conn,
                dataset_id=f"J-SHIS:pshm:{args.hazard_version}:AVR:TTL_MTTL",
                title=f"確率論的地震動予測地図 {args.hazard_version}",
                url="https://www.j-shis.bosai.go.jp/api-pshm-meshinfo",
                version=args.hazard_version,
            )
        conn.commit()

    if not meshes:
        print("no populated 2025 meshes; skipping J-SHIS")
        return

    client = JShisClient(min_interval_seconds=max(0.0, args.interval))
    ground_success = 0
    hazard_success = 0
    request_failures = 0
    stopped_for_limit = False

    with connect(DB_PATH) as conn:
        ensure_jshis_schema(conn)
        # Full component runs replace only the component they own. This allows
        # ground and hazard to run in separate Actions jobs without erasing each other.
        if args.max_meshes is None:
            _reset_component(conn, args.component)
            conn.commit()

        for index, (mesh_id, area_id) in enumerate(meshes, start=1):
            try:
                lon, lat = mesh250_center(mesh_id)
            except ValueError:
                continue
            position = f"{lon:.8f},{lat:.8f}"
            ground = None
            hazard = None
            try:
                if args.component in {"all", "ground"}:
                    ground_payload = client.get_json(
                        f"sstrct/{args.ground_version}/meshinfo.geojson",
                        {"position": position, "epsg": 4326},
                    )
                    ground = normalize_ground_payload(ground_payload)
                    if ground:
                        ground_success += 1

                if args.component in {"all", "hazard"}:
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
            except urllib.error.HTTPError as exc:
                request_failures += 1
                print(f"warning: J-SHIS HTTP {exc.code} for mesh {mesh_id}; continuing")
            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                http.client.RemoteDisconnected,
            ) as exc:
                request_failures += 1
                print(f"warning: J-SHIS request failed for mesh {mesh_id}: {_transient_error(exc)}; continuing")

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
                print(
                    f"J-SHIS {args.component}: {index}/{len(meshes)} meshes, "
                    f"ground={ground_success}, hazard={hazard_success}, failures={request_failures}"
                )

        conn.commit()
        metric_count = compute_ward_seismic_metrics(conn)

    suffix = " (partial: request limit)" if stopped_for_limit else ""
    print(
        f"J-SHIS {args.component} complete{suffix}: target={len(meshes)}, "
        f"ground={ground_success}, hazard={hazard_success}, failures={request_failures}, "
        f"ward_metrics={metric_count}"
    )


if __name__ == "__main__":
    main()
