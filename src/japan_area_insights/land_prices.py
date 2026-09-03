from __future__ import annotations

import math
import re
from collections import defaultdict
from statistics import mean
from typing import Any, Iterable, Mapping

from .geo import geometry_center

TOKYO_23_BBOX = (139.55, 35.52, 139.93, 35.83)


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    lat = max(-85.05112878, min(85.05112878, lat))
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tiles_for_bbox(
    bbox: tuple[float, float, float, float] = TOKYO_23_BBOX,
    *,
    zoom: int = 13,
) -> list[tuple[int, int]]:
    west, south, east, north = bbox
    x0, y0 = lonlat_to_tile(west, north, zoom)
    x1, y1 = lonlat_to_tile(east, south, zoom)
    return [(x, y) for x in range(min(x0, x1), max(x0, x1) + 1) for y in range(min(y0, y1), max(y0, y1) + 1)]


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _boolint(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "有", "あり"}:
        return 1
    if text in {"false", "0", "no", "無", "なし"}:
        return 0
    return None


def parse_yen_per_sqm(value: Any) -> float | None:
    return _number(value)


def normalize_xpt002(
    payload: Mapping[str, Any],
    *,
    allowed_area_ids: Iterable[str],
    year: int,
    price_classification: int,
) -> list[dict[str, Any]]:
    allowed = set(allowed_area_ids)
    rows: dict[str, dict[str, Any]] = {}
    for feature in payload.get("features", []) or []:
        props = feature.get("properties") or {}
        area_id = str(props.get("city_code") or "")
        if area_id not in allowed:
            continue
        price = parse_yen_per_sqm(props.get("u_current_years_price_ja"))
        if price is None or price <= 0:
            continue
        point_id = str(props.get("point_id") or f"{area_id}:{props.get('standard_lot_number_ja', '')}:{price}")
        center = geometry_center(feature.get("geometry"))
        longitude = center[0] if center else None
        latitude = center[1] if center else None
        rows[point_id] = {
            "point_id": point_id,
            "area_id": area_id,
            "year": int(year),
            "price_classification": int(price_classification),
            "price": price,
            "last_year_price": _number(props.get("last_years_price")),
            "yoy_change": _number(props.get("year_on_year_change_rate")),
            "latitude": latitude,
            "longitude": longitude,
            "use_category": str(props.get("use_category_name_ja") or "") or None,
            "standard_lot_number": str(props.get("standard_lot_number_ja") or "") or None,
            "residence_display": str(props.get("residence_display_name_ja") or "") or None,
            "location_text": str(props.get("location") or props.get("location_number_ja") or "") or None,
            "cadastral_sqm": _number(props.get("u_cadastral_ja")),
            "building_structure": str(props.get("building_structure_name_ja") or "") or None,
            "ground_floors": _integer(props.get("u_ground_hierarchy_ja")),
            "underground_floors": _integer(props.get("u_underground_hierarchy_ja")),
            "front_road_type": str(props.get("front_road_name_ja") or "") or None,
            "front_road_azimuth": str(props.get("front_road_azimuth_name_ja") or "") or None,
            # API examples express front_road_width as decimetres (200 => 20.0m).
            "front_road_width_m": (
                _number(props.get("front_road_width")) / 10.0
                if _number(props.get("front_road_width")) is not None
                else None
            ),
            "gas_supply": _boolint(props.get("gas_supply_availability")),
            "water_supply": _boolint(props.get("water_supply_availability")),
            "sewer_supply": _boolint(props.get("sewer_supply_availability")),
            "nearest_station": str(props.get("nearest_station_name_ja") or "") or None,
            "station_distance_m": _number(props.get("u_road_distance_to_nearest_station_name_ja")),
            "usage_status": str(props.get("usage_status_name_ja") or "") or None,
            "surrounding_land_use": str(props.get("current_usage_status_of_surrounding_land_name_ja") or "") or None,
            "area_division": str(props.get("area_division_name_ja") or "") or None,
            "zoning": str(props.get("regulations_use_category_name_ja") or "") or None,
            "fireproof_zone": str(props.get("regulations_fireproof_name_ja") or "") or None,
            "coverage_ratio": _number(props.get("u_regulations_building_coverage_ratio_ja")),
            "floor_area_ratio": _number(props.get("u_regulations_floor_area_ratio_ja")),
        }
    return list(rows.values())


def aggregate_land_prices(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, float | int | None]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        price = row.get("price")
        if price is not None:
            grouped[str(row["area_id"])].append(float(price))
    return {
        area_id: {
            "mean_price": round(mean(prices), 2) if prices else None,
            "point_count": len(prices),
        }
        for area_id, prices in grouped.items()
    }
