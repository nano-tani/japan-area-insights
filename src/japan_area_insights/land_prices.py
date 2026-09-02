from __future__ import annotations

import math
import re
from collections import defaultdict
from statistics import mean
from typing import Any, Iterable, Mapping

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


def parse_yen_per_sqm(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


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
        rows[point_id] = {
            "point_id": point_id,
            "area_id": area_id,
            "year": int(year),
            "price_classification": int(price_classification),
            "price": price,
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
