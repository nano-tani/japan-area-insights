from __future__ import annotations

from datetime import date
from math import ceil, floor
from statistics import median
from typing import Iterable, Mapping

from .analysis_schema import ensure_analysis_schema, upsert_metric

METRIC_VERSION = "detail-v1"


def _median(values: Iterable[float | int | None]) -> float | None:
    cleaned = [float(value) for value in values if value is not None]
    return round(float(median(cleaned)), 2) if cleaned else None


def _percentile(values: Iterable[float | int | None], q: float) -> float | None:
    cleaned = sorted(float(value) for value in values if value is not None)
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return round(cleaned[0], 2)
    position = (len(cleaned) - 1) * q
    lower = floor(position)
    upper = ceil(position)
    if lower == upper:
        result = cleaned[lower]
    else:
        fraction = position - lower
        result = cleaned[lower] + (cleaned[upper] - cleaned[lower]) * fraction
    return round(result, 2)


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


def _contains_any(value: object, tokens: tuple[str, ...]) -> bool:
    text = str(value or "")
    return any(token in text for token in tokens)


def _floor_plan_bucket(value: object) -> str | None:
    text = str(value or "").upper().replace(" ", "")
    if not text:
        return None
    if text in {"1R", "ワンルーム"} or text.startswith(("1K", "1DK")):
        return "compact"
    if text.startswith("1LDK"):
        return "one_ldk"
    if text.startswith("2LDK"):
        return "two_ldk"
    if text.startswith(("3LDK", "4LDK", "5LDK", "6LDK")):
        return "family_large"
    return "other"


def _write_metrics(conn, *, geo_id: str, period: str, source_id: int | None, values: Mapping[str, tuple[float | None, int]], notes: str, preferred: int = 30, minimum: int = 5) -> int:
    written = 0
    for metric_key, (value, sample) in values.items():
        upsert_metric(
            conn,
            geo_id=geo_id,
            metric_key=metric_key,
            period=period,
            value=value,
            sample_size=sample,
            source_id=source_id,
            metric_version=METRIC_VERSION,
            quality_grade=_quality(sample, preferred=preferred, minimum=minimum),
            source_year=period,
            notes=notes,
        )
        written += 1
    return written


def compute_market_metrics(conn, *, from_year: int | None = None, to_year: int | None = None) -> int:
    """Compute analysis-grade ward market metrics from fetched MLIT datasets.

    Transaction metrics use XIT001 municipality-filtered records and never infer
    property coordinates. Land-price metrics use XPT002 official land-price
    points. The core 100-point score is not changed here.
    """
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

        unit_prices = [row["unit_price"] for row in tx if row.get("unit_price") is not None]
        p25 = _percentile(unit_prices, 0.25)
        p75 = _percentile(unit_prices, 0.75)
        areas_sqm = [row["area_sqm"] for row in tx if row.get("area_sqm") is not None]
        building_ages = [
            int(row["year"]) - int(row["building_year"])
            for row in tx
            if row.get("building_year") is not None
            and 0 <= int(row["year"]) - int(row["building_year"]) <= 150
        ]
        road_widths = [row["road_breadth_m"] for row in tx if row.get("road_breadth_m") is not None]
        frontages = [row["frontage_m"] for row in tx if row.get("frontage_m") is not None]
        fars = [row["floor_area_ratio"] for row in tx if row.get("floor_area_ratio") is not None]
        coverage = [row["coverage_ratio"] for row in tx if row.get("coverage_ratio") is not None]

        property_known = [row for row in tx if row.get("property_type")]
        condo_matches = sum("マンション" in str(row["property_type"]) for row in property_known)

        structures = [str(row["structure"]) for row in tx if row.get("structure")]
        rc_matches = sum(_contains_any(value.upper(), ("RC", "ＳＲＣ", "ＲＣ")) for value in structures)
        wood_matches = sum(_contains_any(value, ("木造", "木骨")) for value in structures)
        steel_matches = sum(_contains_any(value, ("鉄骨", "Ｓ造", "S造")) and not _contains_any(value.upper(), ("SRC", "ＳＲＣ")) for value in structures)

        renovations = [str(row["renovation"]) for row in tx if row.get("renovation")]
        renovation_matches = sum(any(token in value for token in ("済", "有", "あり")) for value in renovations)

        shapes = [str(row["land_shape"]) for row in tx if row.get("land_shape")]
        regular_shape_matches = sum(_contains_any(value, ("長方形", "正方形", "ほぼ整形", "台形")) for value in shapes)

        uses = [str(row["use_name"]) for row in tx if row.get("use_name")]
        residential_use_matches = sum("住宅" in value for value in uses)
        commercial_use_matches = sum(_contains_any(value, ("店舗", "事務所", "商業")) for value in uses)

        purposes = [str(row["purpose"]) for row in tx if row.get("purpose")]
        investment_matches = sum(_contains_any(value, ("投資", "収益")) for value in purposes)

        road_known = [float(value) for value in road_widths]
        road_6m_matches = sum(value >= 6.0 for value in road_known)
        age_under_10 = sum(age < 10 for age in building_ages)
        age_30_plus = sum(age >= 30 for age in building_ages)

        floor_plans = [_floor_plan_bucket(row.get("floor_plan")) for row in tx if row.get("floor_plan")]
        floor_plans = [value for value in floor_plans if value]
        compact_matches = sum(value == "compact" for value in floor_plans)
        family_matches = sum(value in {"two_ldk", "family_large"} for value in floor_plans)

        market_values = {
            "market.transaction_count": (float(sample), sample),
            "market.median_unit_price": (_median(unit_prices), len(unit_prices)),
            "market.unit_price_p25": (p25, len(unit_prices)),
            "market.unit_price_p75": (p75, len(unit_prices)),
            "market.unit_price_iqr": ((round(p75 - p25, 2) if p25 is not None and p75 is not None else None), len(unit_prices)),
            "market.median_area_sqm": (_median(areas_sqm), len(areas_sqm)),
            "market.condo_share": (_share(condo_matches, len(property_known)), len(property_known)),
            "market.rc_share": (_share(rc_matches, len(structures)), len(structures)),
            "market.wood_share": (_share(wood_matches, len(structures)), len(structures)),
            "market.steel_share": (_share(steel_matches, len(structures)), len(structures)),
            "market.renovated_share": (_share(renovation_matches, len(renovations)), len(renovations)),
            "market.median_building_age": (_median(building_ages), len(building_ages)),
            "market.building_age_under_10_share": (_share(age_under_10, len(building_ages)), len(building_ages)),
            "market.building_age_30_plus_share": (_share(age_30_plus, len(building_ages)), len(building_ages)),
            "market.median_road_width": (_median(road_widths), len(road_widths)),
            "market.road_6m_plus_share": (_share(road_6m_matches, len(road_known)), len(road_known)),
            "market.median_frontage": (_median(frontages), len(frontages)),
            "market.transaction_far_median": (_median(fars), len(fars)),
            "market.transaction_coverage_ratio_median": (_median(coverage), len(coverage)),
            "market.regular_land_shape_share": (_share(regular_shape_matches, len(shapes)), len(shapes)),
            "market.residential_use_share": (_share(residential_use_matches, len(uses)), len(uses)),
            "market.commercial_use_share": (_share(commercial_use_matches, len(uses)), len(uses)),
            "market.investment_purpose_share": (_share(investment_matches, len(purposes)), len(purposes)),
            "market.compact_floor_plan_share": (_share(compact_matches, len(floor_plans)), len(floor_plans)),
            "market.family_floor_plan_share": (_share(family_matches, len(floor_plans)), len(floor_plans)),
        }
        written += _write_metrics(
            conn,
            geo_id=geo_id,
            period=period,
            source_id=source_id,
            values=market_values,
            notes="XIT001実取引属性から集計。DistrictName等から物件位置は推測していません。",
        )

        land_year_row = conn.execute(
            """
            SELECT MAX(year) AS y FROM land_price_points
            WHERE area_id=? AND year<=? AND price_classification=0
            """,
            (area_id, effective_to + 1),
        ).fetchone()
        if not land_year_row or land_year_row["y"] is None:
            continue

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

        prices = [row["price"] for row in point_rows if row.get("price") is not None]
        station_distances = [float(row["station_distance_m"]) for row in point_rows if row.get("station_distance_m") is not None]
        point_fars = [row["floor_area_ratio"] for row in point_rows if row.get("floor_area_ratio") is not None]
        point_road_widths = [row["front_road_width_m"] for row in point_rows if row.get("front_road_width_m") is not None]
        station_500 = sum(value <= 500 for value in station_distances)
        station_1000 = sum(value <= 1000 for value in station_distances)

        utility_known = [
            row for row in point_rows
            if row.get("gas_supply") is not None and row.get("water_supply") is not None and row.get("sewer_supply") is not None
        ]
        utility_complete = sum(
            int(row["gas_supply"]) == 1 and int(row["water_supply"]) == 1 and int(row["sewer_supply"]) == 1
            for row in utility_known
        )

        zoning_known = [str(row["zoning"]) for row in point_rows if row.get("zoning")]
        residential_zoning = sum(_contains_any(value, ("住居", "住宅")) for value in zoning_known)
        commercial_zoning = sum(_contains_any(value, ("商業", "近隣商業")) for value in zoning_known)
        industrial_zoning = sum(_contains_any(value, ("工業", "準工業")) for value in zoning_known)
        high_far = sum(float(value) >= 400 for value in point_fars)
        fire_known = [str(row["fireproof_zone"]) for row in point_rows if row.get("fireproof_zone")]
        fireproof_matches = sum(_contains_any(value, ("防火", "準防火")) for value in fire_known)

        point_p25 = _percentile(prices, 0.25)
        point_p75 = _percentile(prices, 0.75)
        point_values = {
            "market.land_price_median": (_median(prices), len(prices)),
            "market.land_price_p25": (point_p25, len(prices)),
            "market.land_price_p75": (point_p75, len(prices)),
            "market.land_price_spread_ratio": ((round(point_p75 / point_p25, 3) if point_p25 and point_p75 else None), len(prices)),
            "market.land_price_station_distance": (_median(station_distances), len(station_distances)),
            "market.land_price_within_500m_share": (_share(station_500, len(station_distances)), len(station_distances)),
            "market.land_price_within_1km_share": (_share(station_1000, len(station_distances)), len(station_distances)),
            "market.land_price_far_median": (_median(point_fars), len(point_fars)),
            "market.land_price_high_far_share": (_share(high_far, len(point_fars)), len(point_fars)),
            "market.land_price_road_width_median": (_median(point_road_widths), len(point_road_widths)),
            "market.land_price_utility_complete_share": (_share(utility_complete, len(utility_known)), len(utility_known)),
            "market.land_price_residential_zoning_share": (_share(residential_zoning, len(zoning_known)), len(zoning_known)),
            "market.land_price_commercial_zoning_share": (_share(commercial_zoning, len(zoning_known)), len(zoning_known)),
            "market.land_price_industrial_zoning_share": (_share(industrial_zoning, len(zoning_known)), len(zoning_known)),
            "market.land_price_fireproof_share": (_share(fireproof_matches, len(fire_known)), len(fire_known)),
        }
        written += _write_metrics(
            conn,
            geo_id=geo_id,
            period=str(land_year),
            source_id=point_source_id,
            values=point_values,
            notes="XPT002地価公示ポイント（国土交通省地価公示）から集計。",
            preferred=10,
            minimum=3,
        )
    return written
