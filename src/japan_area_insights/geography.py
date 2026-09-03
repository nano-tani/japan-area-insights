from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .db import connect, initialize
from .geo import mesh250_center

GEO_DEFINITION_VERSION = "v1"


def ward_geo_id(area_id: str) -> str:
    return f"ward:{area_id}"


def mesh_geo_id(mesh_id: str) -> str:
    return f"mesh250:{mesh_id}"


@dataclass(frozen=True)
class GeoSyncStats:
    ward_count: int
    mesh_count: int
    mapping_count: int


def sync_geo_foundation(
    db_path: str | Path,
    *,
    definition_version: str = GEO_DEFINITION_VERSION,
) -> GeoSyncStats:
    """Sync ward and 250m mesh geo units from existing area/future-population data.

    Existing `areas` remains the compatibility source for wards. XKT013-derived
    `future_population` supplies the authoritative mesh -> ward ownership used by
    the first geographic foundation version.
    """
    initialize(db_path)

    with connect(db_path) as conn:
        areas = conn.execute(
            """
            SELECT area_id, prefecture_code, municipality_name, latitude, longitude
            FROM areas
            ORDER BY area_id
            """
        ).fetchall()

        mesh_rows = conn.execute(
            """
            SELECT mesh_id, MIN(area_id) AS area_id, COUNT(DISTINCT area_id) AS area_count
            FROM future_population
            GROUP BY mesh_id
            ORDER BY mesh_id
            """
        ).fetchall()

        conflicts = [str(row["mesh_id"]) for row in mesh_rows if int(row["area_count"]) != 1]
        if conflicts:
            preview = ", ".join(conflicts[:5])
            raise ValueError(f"250m mesh belongs to multiple wards: {preview}")

        conn.execute(
            "UPDATE geo_units SET is_active=0 WHERE geo_type='ward' AND definition_version=?",
            (definition_version,),
        )
        conn.execute(
            "UPDATE geo_units SET is_active=0 WHERE geo_type='mesh250' AND definition_version=?",
            (definition_version,),
        )

        for row in areas:
            area_id = str(row["area_id"])
            conn.execute(
                """
                INSERT INTO geo_units (
                    geo_id, geo_type, canonical_code, name, parent_geo_id,
                    primary_area_id, prefecture_code, latitude, longitude,
                    radius_m, definition_version, is_active
                ) VALUES (?, 'ward', ?, ?, NULL, ?, ?, ?, ?, NULL, ?, 1)
                ON CONFLICT(geo_id) DO UPDATE SET
                    geo_type=excluded.geo_type,
                    canonical_code=excluded.canonical_code,
                    name=excluded.name,
                    parent_geo_id=NULL,
                    primary_area_id=excluded.primary_area_id,
                    prefecture_code=excluded.prefecture_code,
                    latitude=excluded.latitude,
                    longitude=excluded.longitude,
                    radius_m=NULL,
                    definition_version=excluded.definition_version,
                    is_active=1
                """,
                (
                    ward_geo_id(area_id),
                    area_id,
                    str(row["municipality_name"]),
                    area_id,
                    str(row["prefecture_code"]),
                    row["latitude"],
                    row["longitude"],
                    definition_version,
                ),
            )

        for row in mesh_rows:
            mesh_id = str(row["mesh_id"])
            area_id = str(row["area_id"])
            longitude, latitude = mesh250_center(mesh_id)
            conn.execute(
                """
                INSERT INTO geo_units (
                    geo_id, geo_type, canonical_code, name, parent_geo_id,
                    primary_area_id, prefecture_code, latitude, longitude,
                    radius_m, definition_version, is_active
                ) VALUES (?, 'mesh250', ?, ?, ?, ?, ?, ?, ?, NULL, ?, 1)
                ON CONFLICT(geo_id) DO UPDATE SET
                    geo_type=excluded.geo_type,
                    canonical_code=excluded.canonical_code,
                    name=excluded.name,
                    parent_geo_id=excluded.parent_geo_id,
                    primary_area_id=excluded.primary_area_id,
                    prefecture_code=excluded.prefecture_code,
                    latitude=excluded.latitude,
                    longitude=excluded.longitude,
                    radius_m=NULL,
                    definition_version=excluded.definition_version,
                    is_active=1
                """,
                (
                    mesh_geo_id(mesh_id),
                    mesh_id,
                    mesh_id,
                    ward_geo_id(area_id),
                    area_id,
                    area_id[:2],
                    latitude,
                    longitude,
                    definition_version,
                ),
            )

        conn.execute(
            """
            DELETE FROM geo_unit_meshes
            WHERE geo_id IN (
                SELECT geo_id FROM geo_units
                WHERE definition_version=? AND geo_type IN ('ward', 'mesh250')
            )
            """,
            (definition_version,),
        )

        mapping_rows: list[tuple[str, str, float, str, None]] = []
        for row in mesh_rows:
            mesh_id = str(row["mesh_id"])
            area_id = str(row["area_id"])
            mapping_rows.append((ward_geo_id(area_id), mesh_id, 1.0, "xkt013_shicode", None))
            mapping_rows.append((mesh_geo_id(mesh_id), mesh_id, 1.0, "self", None))

        if mapping_rows:
            conn.executemany(
                """
                INSERT INTO geo_unit_meshes (geo_id, mesh_id, weight, method, distance_m)
                VALUES (?, ?, ?, ?, ?)
                """,
                mapping_rows,
            )

        active_wards = conn.execute(
            "SELECT COUNT(*) FROM geo_units WHERE geo_type='ward' AND definition_version=? AND is_active=1",
            (definition_version,),
        ).fetchone()[0]
        active_meshes = conn.execute(
            "SELECT COUNT(*) FROM geo_units WHERE geo_type='mesh250' AND definition_version=? AND is_active=1",
            (definition_version,),
        ).fetchone()[0]
        mappings = conn.execute(
            """
            SELECT COUNT(*)
            FROM geo_unit_meshes gum
            JOIN geo_units gu ON gu.geo_id=gum.geo_id
            WHERE gu.definition_version=? AND gu.geo_type IN ('ward', 'mesh250')
            """,
            (definition_version,),
        ).fetchone()[0]

    return GeoSyncStats(
        ward_count=int(active_wards),
        mesh_count=int(active_meshes),
        mapping_count=int(mappings),
    )
