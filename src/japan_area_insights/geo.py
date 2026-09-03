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


def mesh250_center(mesh_id: str) -> tuple[float, float]:
    """Return the center lon/lat of a 10-digit Japanese 250m mesh code."""
    code = str(mesh_id).strip()
    if len(code) != 10 or not code.isdigit():
        raise ValueError(f"invalid 250m mesh code: {mesh_id!r}")

    first_lat = int(code[0:2])
    first_lon = int(code[2:4])
    second_lat = int(code[4])
    second_lon = int(code[5])
    third_lat = int(code[6])
    third_lon = int(code[7])
    half = int(code[8])
    quarter = int(code[9])

    if second_lat > 7 or second_lon > 7 or half not in {1, 2, 3, 4} or quarter not in {1, 2, 3, 4}:
        raise ValueError(f"invalid 250m mesh code: {mesh_id!r}")

    lat_minutes = first_lat * 40.0 + second_lat * 5.0 + third_lat * 0.5
    lon_degrees = 100 + first_lon
    lon_minutes = second_lon * 7.5 + third_lon * 0.75

    if half in {3, 4}:
        lat_minutes += 15.0 / 60.0
    if half in {2, 4}:
        lon_minutes += 22.5 / 60.0
    if quarter in {3, 4}:
        lat_minutes += 7.5 / 60.0
    if quarter in {2, 4}:
        lon_minutes += 11.25 / 60.0

    # Quarter-grid size is 7.5 seconds latitude x 11.25 seconds longitude.
    lat_minutes += 3.75 / 60.0
    lon_minutes += 5.625 / 60.0

    latitude = lat_minutes / 60.0
    longitude = lon_degrees + lon_minutes / 60.0
    return longitude, latitude
