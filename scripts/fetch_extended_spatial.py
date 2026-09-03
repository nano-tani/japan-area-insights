from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

from japan_area_insights.analysis_catalog import REINFOLIB_SPATIAL_LAYERS
from japan_area_insights.analysis_schema import ensure_analysis_schema
from japan_area_insights.db import connect, initialize
from japan_area_insights.hazard_severity import compute_hazard_severity_bands
from japan_area_insights.land_prices import tiles_for_bbox
from japan_area_insights.sources.reinfolib import BASE_URL, ReinfolibClient
from japan_area_insights.spatial_analysis import compute_layer_exposures, normalize_spatial_features

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"

# Some API manuals require a higher minimum zoom than the generic urban layers.
# The workflow accepts a base zoom and raises only the layers that require it.
API_MIN_ZOOM = {
    "XKT026": 14,  # flood maximum-scale inundation
    "XKT027": 13,  # storm surge
    "XKT028": 14,  # tsunami inundation
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch extended Reinfolib urban/hazard GIS layers")
    parser.add_argument("--zoom", type=int, default=12, choices=[11, 12, 13, 14, 15])
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--api", action="append", default=[], help="optional XKTxxx; repeat to select multiple")
    parser.add_argument("--strict", action="store_true", help="fail instead of skipping unsupported tile/API responses")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    requested = [value.upper() for value in args.api if value]
    api_ids = requested or list(REINFOLIB_SPATIAL_LAYERS)
    unknown = [api_id for api_id in api_ids if api_id not in REINFOLIB_SPATIAL_LAYERS]
    if unknown:
        raise SystemExit(f"unsupported API(s): {', '.join(unknown)}")

    initialize(DB_PATH)
    with connect(DB_PATH) as conn:
        ensure_analysis_schema(conn)
        area_ids = [str(row["area_id"]) for row in conn.execute("SELECT area_id FROM areas ORDER BY area_id")]
        mesh_to_area = {
            str(row["mesh_id"]): str(row["area_id"])
            for row in conn.execute("SELECT DISTINCT mesh_id, area_id FROM future_population")
        }
    if not mesh_to_area:
        raise SystemExit("future_population is empty; fetch XKT013 before extended spatial analysis")

    client = ReinfolibClient(min_interval_seconds=max(0.0, args.interval))
    total_stored = 0

    for api_id in api_ids:
        layer_key, category, title, vintage = REINFOLIB_SPATIAL_LAYERS[api_id]
        effective_zoom = max(args.zoom, API_MIN_ZOOM.get(api_id, args.zoom))
        tiles = tiles_for_bbox(zoom=effective_zoom)
        digest = hashlib.sha256()
        collected: dict[str, dict] = {}
        skipped = 0
        for x, y in tiles:
            try:
                payload = client.get_json(
                    api_id,
                    {"response_format": "geojson", "z": effective_zoom, "x": x, "y": y},
                )
            except HTTPError as exc:
                if not args.strict and exc.code in {400, 404, 422}:
                    skipped += 1
                    continue
                raise
            digest.update(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
            for row in normalize_spatial_features(
                api_id,
                payload,
                mesh_to_area=mesh_to_area,
                allowed_area_ids=area_ids,
            ):
                collected[row["feature_id"]] = row

        fetched_at = datetime.now(timezone.utc).isoformat()
        with connect(DB_PATH) as conn:
            ensure_analysis_schema(conn)
            cursor = conn.execute(
                """
                INSERT INTO data_sources(
                    source_name, dataset_id, source_url, terms_url,
                    published_at, fetched_at, raw_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "国土交通省 不動産情報ライブラリ",
                    f"{api_id}:{vintage}",
                    f"{BASE_URL}/{api_id}",
                    "https://www.reinfolib.mlit.go.jp/help/termsOfUse/",
                    None,
                    fetched_at,
                    digest.hexdigest(),
                ),
            )
            source_id = int(cursor.lastrowid)
            conn.execute("DELETE FROM spatial_features WHERE api_id=?", (api_id,))
            if collected:
                conn.executemany(
                    """
                    INSERT INTO spatial_features(
                        api_id, feature_id, layer_key, category, area_id,
                        geometry_type, geometry_json, properties_json,
                        centroid_lat, centroid_lon, source_id
                    ) VALUES (
                        :api_id, :feature_id, :layer_key, :category, :area_id,
                        :geometry_type, :geometry_json, :properties_json,
                        :centroid_lat, :centroid_lon, :source_id
                    )
                    """,
                    [{**row, "source_id": source_id} for row in collected.values()],
                )
            exposure_rows = compute_layer_exposures(conn, api_id, source_id=source_id)
        total_stored += len(collected)
        print(
            f"{api_id} {title}: z={effective_zoom}, stored {len(collected)} features, "
            f"{exposure_rows} exposure rows, skipped tiles={skipped}"
        )

    with connect(DB_PATH) as conn:
        severity_rows = compute_hazard_severity_bands(conn)
    print(f"stored {total_stored} extended spatial features; computed {severity_rows} severity-band rows")


if __name__ == "__main__":
    main()
