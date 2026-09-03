from __future__ import annotations

import hashlib
from typing import Any, Iterable, Mapping

from .geo import geometry_center, mesh_code_250m


FACILITY_APIS = {
    "XKT006": "school",
    "XKT007": "childcare",
    "XKT010": "medical",
    "XKT017": "library",
    "XKT018": "public_facility",
}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _stable_id(*parts: Any) -> str:
    raw = "|".join(_text(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _area_from_point(
    geometry: Mapping[str, Any] | None,
    mesh_to_area: Mapping[str, str],
) -> str | None:
    center = geometry_center(dict(geometry) if geometry else None)
    if center is None:
        return None
    lon, lat = center
    try:
        return mesh_to_area.get(mesh_code_250m(lon, lat))
    except ValueError:
        return None


def _area_from_address(address: str, area_names: Mapping[str, str]) -> str | None:
    for area_id, name in area_names.items():
        if name and name in address:
            return area_id
    return None


def normalize_facility_features(
    api_id: str,
    payload: Mapping[str, Any],
    *,
    allowed_area_ids: Iterable[str],
    mesh_to_area: Mapping[str, str] | None = None,
    area_names: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    allowed = set(allowed_area_ids)
    mesh_map = mesh_to_area or {}
    names = area_names or {}
    result: dict[str, dict[str, Any]] = {}

    for feature in payload.get("features", []) or []:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        center = geometry_center(geometry)
        lon, lat = center if center is not None else (None, None)

        if api_id == "XKT006":
            area_id = _text(props.get("P29_001")).zfill(5)
            subtype = _text(props.get("P29_003_name_ja"))
            if "幼稚園" in subtype or "こども園" in subtype:
                continue
            facility_type = "school"
            name = _text(props.get("P29_004_ja"))
            address = _text(props.get("P29_005_ja"))
            source_key = props.get("P29_002")
        elif api_id == "XKT007":
            area_id = _text(props.get("administrativeAreaCode")).zfill(5)
            facility_type = "childcare"
            subtype = _text(props.get("schoolClassCode_name_ja")) or "保育園"
            name = _text(props.get("preSchoolName_ja"))
            address = _text(props.get("location_ja"))
            source_key = props.get("schoolCode") or props.get("welfareFacilityMinorClassCode")
        elif api_id == "XKT010":
            facility_type = "medical"
            subtype = _text(props.get("P04_001_name_ja"))
            name = _text(props.get("P04_002_ja"))
            address = _text(props.get("P04_003_ja"))
            area_id = _area_from_point(geometry, mesh_map) or _area_from_address(address, names) or ""
            source_key = props.get("_id")
        elif api_id == "XKT017":
            area_id = _text(props.get("P27_001")).zfill(5)
            facility_type = "library"
            subtype = _text(props.get("P27_004_name_ja")) or _text(props.get("P27_003_name_ja"))
            name = _text(props.get("P27_005_ja"))
            address = _text(props.get("P27_006_ja"))
            source_key = props.get("_id")
        elif api_id == "XKT018":
            area_id = _text(props.get("P05_001")).zfill(5)
            facility_type = "public_facility"
            subtype = _text(props.get("P05_002_name_ja"))
            name = _text(props.get("P05_003_ja"))
            address = _text(props.get("P05_004_ja"))
            source_key = props.get("_id")
        else:
            raise ValueError(f"unsupported facility api: {api_id}")

        if area_id not in allowed or not name:
            continue

        facility_id = _stable_id(api_id, source_key, area_id, name, lon, lat)
        result[facility_id] = {
            "facility_id": facility_id,
            "area_id": area_id,
            "facility_type": facility_type,
            "facility_subtype": subtype or None,
            "facility_name": name,
            "address": address or None,
            "latitude": lat,
            "longitude": lon,
        }

    return list(result.values())
