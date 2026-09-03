from __future__ import annotations

from typing import Any


def geometry_center(geometry: dict[str, Any] | None) -> tuple[float, float] | None:
    """Return a representative lon/lat for simple GeoJSON geometries."""
    if not geometry:
        return None
    coordinates = geometry.get("coordinates")
    if coordinates is None:
        return None

    points: list[tuple[float, float]] = []

    def walk(value: Any) -> None:
        if (
            isinstance(value, (list, tuple))
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            points.append((float(value[0]), float(value[1])))
            return
        if isinstance(value, (list, tuple)):
            for child in value:
                walk(child)

    walk(coordinates)
    if not points:
        return None
    lon = sum(point[0] for point in points) / len(points)
    lat = sum(point[1] for point in points) / len(points)
    return lon, lat


def mesh_code_250m(lon: float, lat: float) -> str:
    """Return the 10-digit Japanese quarter-grid (about 250m) mesh code."""
    if not (100.0 <= lon < 180.0 and 0.0 <= lat < 66.6666667):
        raise ValueError("coordinate is outside the supported Japanese mesh range")

    first_lat = int(lat * 1.5)
    first_lon = int(lon) - 100

    lat_minutes = lat * 60.0 - first_lat * 40.0
    lon_minutes = (lon - int(lon)) * 60.0

    second_lat = min(7, int(lat_minutes / 5.0))
    second_lon = min(7, int(lon_minutes / 7.5))

    lat_minutes -= second_lat * 5.0
    lon_minutes -= second_lon * 7.5

    third_lat = min(9, int(lat_minutes / 0.5))
    third_lon = min(9, int(lon_minutes / 0.75))

    lat_seconds = (lat_minutes - third_lat * 0.5) * 60.0
    lon_seconds = (lon_minutes - third_lon * 0.75) * 60.0

    half_north = lat_seconds >= 15.0
    half_east = lon_seconds >= 22.5
    half = 1 + int(half_east) + 2 * int(half_north)

    if half_north:
        lat_seconds -= 15.0
    if half_east:
        lon_seconds -= 22.5

    quarter_north = lat_seconds >= 7.5
    quarter_east = lon_seconds >= 11.25
    quarter = 1 + int(quarter_east) + 2 * int(quarter_north)

    return (
        f"{first_lat:02d}{first_lon:02d}"
        f"{second_lat}{second_lon}{third_lat}{third_lon}{half}{quarter}"
    )
