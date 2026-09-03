from __future__ import annotations

import json
from pathlib import Path

from .analysis_schema import ensure_analysis_schema
from .db import connect
from .hazard_severity import ensure_severity_schema
from .resilience_analysis import ensure_resilience_schema


def _rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def export_analysis_data(db_path: str | Path, output_dir: str | Path) -> None:
    output = Path(output_dir)
    ward_dir = output / "analysis" / "ward"
    ward_dir.mkdir(parents=True, exist_ok=True)

    with connect(db_path) as conn:
        ensure_analysis_schema(conn)
        ensure_resilience_schema(conn)
        ensure_severity_schema(conn)
        areas = _rows(conn, "SELECT area_id, municipality_name FROM areas ORDER BY area_id")
        definitions = _rows(
            conn,
            """
            SELECT metric_key, category, label, unit, direction, granularity,
                   source_dataset_key, min_sample_size, description
            FROM metric_definitions ORDER BY category, metric_key
            """,
        )
        datasets = _rows(
            conn,
            """
            SELECT dataset_key, provider, api_id, category, title,
                   source_vintage, granularity, refresh_mode, enabled, notes
            FROM dataset_catalog ORDER BY category, dataset_key
            """,
        )
        definition_map = {row["metric_key"]: row for row in definitions}

        for area in areas:
            area_id = str(area["area_id"])
            geo_id = f"ward:{area_id}"
            metric_rows = _rows(
                conn,
                """
                SELECT gm.metric_key, gm.period, gm.value, gm.sample_size,
                       gm.source_id, gm.metric_version, gm.calculated_at,
                       mq.quality_grade, mq.source_year, mq.is_estimate, mq.notes,
                       ds.source_name, ds.dataset_id, ds.source_url
                FROM geo_metrics gm
                LEFT JOIN metric_quality mq
                  ON mq.geo_id=gm.geo_id AND mq.metric_key=gm.metric_key
                 AND mq.period=gm.period AND mq.metric_version=gm.metric_version
                LEFT JOIN data_sources ds ON ds.source_id=gm.source_id
                WHERE gm.geo_id=? AND gm.metric_version='detail-v1'
                ORDER BY gm.metric_key, gm.period
                """,
                (geo_id,),
            )
            metrics: dict[str, list[dict]] = {}
            for row in metric_rows:
                definition = definition_map.get(row["metric_key"], {})
                item = {
                    **row,
                    "label": definition.get("label", row["metric_key"]),
                    "category": definition.get("category", "other"),
                    "unit": definition.get("unit"),
                    "direction": definition.get("direction", "neutral"),
                    "description": definition.get("description"),
                }
                metrics.setdefault(item["category"], []).append(item)

            exposures = _rows(
                conn,
                """
                SELECT ge.layer_key, ge.period, ge.exposed_mesh_count, ge.total_mesh_count,
                       ge.exposed_population, ge.total_population, ge.population_share,
                       ge.feature_count, ge.calculated_at,
                       sf.category,
                       dc.title, dc.source_vintage, dc.api_id,
                       ds.source_name, ds.dataset_id, ds.source_url
                FROM geo_exposures ge
                LEFT JOIN (
                    SELECT layer_key, MIN(category) AS category
                    FROM spatial_features GROUP BY layer_key
                ) sf ON sf.layer_key=ge.layer_key
                LEFT JOIN dataset_catalog dc
                  ON dc.api_id=(SELECT MIN(api_id) FROM spatial_features s2 WHERE s2.layer_key=ge.layer_key)
                LEFT JOIN data_sources ds ON ds.source_id=ge.source_id
                WHERE ge.geo_id=?
                ORDER BY COALESCE(sf.category, 'other'), ge.layer_key, ge.period
                """,
                (geo_id,),
            )
            for exposure in exposures:
                total_mesh = exposure.get("total_mesh_count") or 0
                exposed_mesh = exposure.get("exposed_mesh_count") or 0
                exposure["mesh_share"] = round(exposed_mesh / total_mesh * 100.0, 3) if total_mesh else None

            exposure_bands = _rows(
                conn,
                """
                SELECT geb.layer_key,geb.period,geb.band_key,geb.band_label,geb.band_order,
                       geb.exposed_mesh_count,geb.exposed_population,geb.total_population,
                       geb.population_share,geb.calculated_at,
                       dc.title,dc.source_vintage,dc.api_id,
                       ds.source_name,ds.dataset_id,ds.source_url
                FROM geo_exposure_bands geb
                LEFT JOIN dataset_catalog dc
                  ON dc.api_id=(SELECT MIN(api_id) FROM spatial_features sf WHERE sf.layer_key=geb.layer_key)
                LEFT JOIN data_sources ds ON ds.source_id=geb.source_id
                WHERE geb.geo_id=?
                ORDER BY geb.layer_key,geb.period,geb.band_order,geb.band_key
                """,
                (geo_id,),
            )

            evacuation_sites = _rows(
                conn,
                """
                SELECT common_id,facility_name,address,flood_flag,landslide_flag,
                       high_tide_flag,earthquake_flag,tsunami_flag,large_fire_flag,
                       inland_flooding_flag,volcanic_phenomenon_flag,same_address_flag,
                       remarks,latitude,longitude
                FROM evacuation_sites WHERE area_id=? ORDER BY facility_name,common_id
                """,
                (area_id,),
            )
            disaster_history = _rows(
                conn,
                """
                SELECT dh.event_id,dh.disastertype_code,dh.disaster_name,dh.disaster_date,
                       dh.disaster_source,dh.geometry_type,dh.centroid_lat,dh.centroid_lon
                FROM disaster_history dh
                JOIN disaster_history_areas dha ON dha.event_id=dh.event_id
                WHERE dha.area_id=?
                ORDER BY dh.disaster_date DESC,dh.disastertype_code,dh.event_id
                """,
                (area_id,),
            )

            payload = {
                "area_id": area_id,
                "municipality_name": area["municipality_name"],
                "metric_version": "detail-v1",
                "metrics": metrics,
                "exposures": exposures,
                "exposure_bands": exposure_bands,
                "evacuation_sites": evacuation_sites,
                "disaster_history": disaster_history,
            }
            (ward_dir / f"{area_id}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        catalog_dir = output / "analysis"
        catalog_dir.mkdir(parents=True, exist_ok=True)
        (catalog_dir / "catalog.json").write_text(
            json.dumps({"datasets": datasets, "metrics": definitions}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
