from __future__ import annotations

from datetime import date
from statistics import median
from typing import Iterable, Mapping

from .analysis_schema import ensure_analysis_schema, upsert_metric

METRIC_VERSION = "detail-v1"


def _median(values: Iterable[float | int | None]) -> float | None:
    cleaned = [float(value) for value in values if value is not None]
    return round(float(median(cleaned)), 2) if cleaned else None


def _share(matches: int, denominator: int) -> float | None:
    return round(matches / denominator * 100.0, 2) if denominator else None


def _quality(sample_size: int | None, *, preferred: int = 30, minimum: int = 5) -> str:
    if sample_size is None or sample_size < minimum:
        return "D"
    if sample_size >= preferred * 3:
        return "A"
    if sample_size >= preferred:
        return "B"
    return "C"


def compute_market_metrics(conn, *, from_year: int | None = None, to_year: int | None = None) -> int:
    """Compute detailed ward-level market metrics from already fetched MLIT data."""
    ensure_analysis_schema(conn)
    current_complete_year = date.today().year - 1
    available = conn.execute("SELECT MIN(year) AS min_y, MAX(year) AS max_y FROM transactions").fetchone()
    if not available or available["max_y"] is None:
        return 0
    effective_to = min(int(available["max_y"]), to_year or current_complete_year)
    effective_from = from_year or max(int(available["min_y"]), effective_to - 4)
    period = f"{effective_from}-{effective_to}"

    areas = conn.execute("SELECT area_id FROM areas ORDER BY area_id").fetchall()
    written = 0
    for area in areas:
        area_id = str(area["area_id"])
        geo_id = f"ward:{area_id}"
        rows = conn.execute(
            """
            SELECT * FROM transactions
            WHERE area_id=? AND year BETWEEN ? AND ?
              AND (price_category='不動産取引価格情報' OR price_category IS NULL)
            """,
            (area_id, effective_from, effective_to),
        ).fetchall()
        tx = [dict(row) for row in rows]
        source_ids = [int(row["source_id"]) for row in rows if row["source_id"] is not None]
        source_id = max(source_ids) if source_ids else None
        sample = len(tx)

        unit_prices = [row["unit_price"] for row in tx if row["unit_price"] is not None]
        areas_sqm = [row["area_sqm"] for row in tx if row["area_sqm"] is not None]
        building_ages = [
            int(row["year"]) - int(row["building_year"])
            for row in tx
            if row.get("building_year") is not None
            and 0 <= int(row["year"]) - int(row["building_year"]) <= 150
        ]
        road_widths = [row["road_breadth_m"] for row in tx if row.get("road_breadth_m") is not None]
        property_known = [row for row in tx if row.get("property_type")]
        condo_matches = sum("マンション" in str(row["property_type"]) for row in property_known)
        structures = [str(row["structure"]) for row in tx if row.get("structure")]
        rc_matches = sum(("RC" in value.upper()) or ("ＲＣ" in value) or ("ＳＲＣ" in value) for value in structures)
        renovations = [str(row["renovation"]) for row in tx if row.get("renovation")]
        renovation_matches = sum(any(token in value for token in ("済", "有", "あり")) for value in renovations)

        market_values = {
            "market.transaction_count": (float(sample), sample),
            "market.median_unit_price": (_median(unit_prices), len(unit_prices)),
            "market.median_area_sqm": (_median(areas_sqm), len(areas_sqm)),
            "market.condo_share": (_share(condo_matches, len(property_known)), len(property_known)),
            "market.rc_share": (_share(rc_matches, len(structures)), len(structures)),
            "market.renovated_share": (_share(renovation_matches, len(renovations)), len(renovations)),
            "market.median_building_age": (_median(building_ages), len(building_ages)),
            "market.median_road_width": (_median(road_widths), len(road_widths)),
        }
        for metric_key, (value, metric_sample) in market_values.items():
            upsert_metric(
                conn,
                geo_id=geo_id,
                metric_key=metric_key,
                period=period,
                value=value,
                sample_size=metric_sample,
                source_id=source_id,
                metric_version=METRIC_VERSION,
                quality_grade=_quality(metric_sample),
                source_year=period,
                notes="XIT001実取引属性から集計。位置は推測していません。",
            )
            written += 1

        land_year_row = conn.execute(
            """
            SELECT MAX(year) AS y FROM land_price_points
            WHERE area_id=? AND year<=? AND price_classification=0
            """,
            (area_id, effective_to + 1),
        ).fetchone()
        if land_year_row and land_year_row["y"] is not None:
            land_year = int(land_year_row["y"])
            point_rows = [dict(row) for row in conn.execute(
                """
                SELECT * FROM land_price_points
                WHERE area_id=? AND year=? AND price_classification=0
                """,
                (area_id, land_year),
            ).fetchall()]
            point_source_ids = [int(row["source_id"]) for row in point_rows if row.get("source_id") is not None]
            point_source_id = max(point_source_ids) if point_source_ids else None
            station_distances = [row["station_distance_m"] for row in point_rows if row.get("station_distance_m") is not None]
            fars = [row["floor_area_ratio"] for row in point_rows if row.get("floor_area_ratio") is not None]
            utility_known = [
                row for row in point_rows
                if row.get("gas_supply") is not None and row.get("water_supply") is not None and row.get("sewer_supply") is not None
            ]
            utility_complete = sum(
                int(row["gas_supply"]) == 1 and int(row["water_supply"]) == 1 and int(row["sewer_supply"]) == 1
                for row in utility_known
            )
            point_values = {
                "market.land_price_station_distance": (_median(station_distances), len(station_distances)),
                "market.land_price_far_median": (_median(fars), len(fars)),
                "market.land_price_utility_complete_share": (_share(utility_complete, len(utility_known)), len(utility_known)),
            }
            for metric_key, (value, metric_sample) in point_values.items():
                upsert_metric(
                    conn,
                    geo_id=geo_id,
                    metric_key=metric_key,
                    period=str(land_year),
                    value=value,
                    sample_size=metric_sample,
                    source_id=point_source_id,
                    metric_version=METRIC_VERSION,
                    quality_grade=_quality(metric_sample, preferred=10, minimum=3),
                    source_year=str(land_year),
                    notes="XPT002地価公示ポイント（国土交通省地価公示）から集計。",
                )
                written += 1
    return written
