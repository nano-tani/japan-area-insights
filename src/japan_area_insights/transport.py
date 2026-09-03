from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping

from .geo import geometry_center, mesh_code_250m


LATEST_PASSENGER_YEAR = 2023
LATEST_PASSENGER_FIELD = "S12_057"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "*", "..."}:
        return None
    try:
        number = int(float(text))
    except ValueError:
        return None
    return number if number >= 0 else None


def _stable_id(*parts: Any) -> str:
    raw = "|".join(_text(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_xkt015(
    payload: Mapping[str, Any],
    *,
    allowed_area_ids: Iterable[str],
    mesh_to_area: Mapping[str, str],
) -> list[dict[str, Any]]:
    allowed = set(allowed_area_ids)
    result: dict[str, dict[str, Any]] = {}

    for feature in payload.get("features", []) or []:
        props = feature.get("properties") or {}
        center = geometry_center(feature.get("geometry") or {})
        if center is None:
            continue
        lon, lat = center
        try:
            area_id = mesh_to_area.get(mesh_code_250m(lon, lat))
        except ValueError:
            area_id = None
        if area_id not in allowed:
            continue

        station_name = _text(props.get("S12_001_ja"))
        station_code = _text(props.get("S12_001c"))
        group_code = _text(props.get("S12_001g")) or station_code
        line_name = _text(props.get("S12_003_ja"))
        operator_name = _text(props.get("S12_002_ja"))
        if not station_name:
            continue

        station_id = _stable_id(
            "XKT015", station_code or group_code, operator_name, line_name, lon, lat
        )
        result[station_id] = {
            "station_id": station_id,
            "area_id": area_id,
            "station_code": station_code or None,
            "group_code": group_code or None,
            "station_name": station_name,
            "line_name": line_name or None,
            "operator_name": operator_name or None,
            "passenger_count": _number(props.get(LATEST_PASSENGER_FIELD)),
            "passenger_year": LATEST_PASSENGER_YEAR,
            "latitude": lat,
            "longitude": lon,
        }

    return list(result.values())
