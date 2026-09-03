from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .db import connect


def _rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _rank(areas: list[dict], key: str) -> list[dict]:
    ranked = [area for area in areas if area.get(key) is not None]
    ranked.sort(key=lambda x: (-float(x[key]), x["area_id"]))
    return ranked


def _transport_summary(stations: list[dict]) -> dict[str, int | None]:
    groups: set[str] = set()
    lines: set[str] = set()
    passenger_by_group: dict[str, int] = {}
    passenger_years: set[int] = set()

    for row in stations:
        group = str(row.get("group_code") or row.get("station_id") or "")
        if group:
            groups.add(group)
        if row.get("line_name"):
            lines.add(str(row["line_name"]))
        if row.get("passenger_count") is not None and group:
            count = int(row["passenger_count"])
            passenger_by_group[group] = max(passenger_by_group.get(group, 0), count)
        if row.get("passenger_year") is not None:
            passenger_years.add(int(row["passenger_year"]))

    return {
        "station_count": len(groups),
        "line_count": len(lines),
        "passenger_count": sum(passenger_by_group.values()) if passenger_by_group else None,
        "passenger_year": max(passenger_years) if passenger_years else None,
    }


def export_site_data(db_path: str | Path, output_dir: str | Path) -> None:
    output = Path(output_dir)
    area_dir = output / "area"
    area_dir.mkdir(parents=True, exist_ok=True)

    with connect(db_path) as conn:
        areas = _rows(
            conn,
            """
            SELECT
                a.area_id, a.prefecture_name, a.municipality_name,
                s.calculation_date, s.price_score, s.population_score,
                s.future_population_score, s.convenience_score,
                s.transport_score, s.transaction_score, s.total_score,
                s.confidence, s.data_completeness, s.score_version
            FROM areas a
            LEFT JOIN area_scores s ON s.rowid = (
                SELECT x.rowid FROM area_scores x
                WHERE x.area_id = a.area_id
                ORDER BY x.calculation_date DESC, x.rowid DESC
                LIMIT 1
            )
            ORDER BY a.municipality_code
            """,
        )

        for area in areas:
            area_id = area["area_id"]
            detail = dict(area)
            detail["prices"] = _rows(conn, "SELECT * FROM area_prices WHERE area_id=? ORDER BY year", (area_id,))
            detail["population"] = _rows(conn, "SELECT * FROM population WHERE area_id=? ORDER BY year", (area_id,))

            future_rows = _rows(
                conn,
                """
                SELECT year, SUM(projected_population) AS projected_population
                FROM future_population WHERE area_id=?
                GROUP BY year ORDER BY year
                """,
                (area_id,),
            )
            baseline = next((row["projected_population"] for row in future_rows if row["year"] == 2025), None)
            for row in future_rows:
                value = row.get("projected_population")
                row["retention_rate"] = (
                    round(float(value) / float(baseline) * 100.0, 2)
                    if value is not None and baseline not in (None, 0)
                    else None
                )
            detail["future_population"] = future_rows

            detail["facilities"] = _rows(
                conn,
                """
                SELECT facility_type, COUNT(*) AS count
                FROM facilities WHERE area_id=?
                GROUP BY facility_type ORDER BY facility_type
                """,
                (area_id,),
            )

            station_rows = _rows(
                conn,
                """
                SELECT station_id, station_code, group_code, station_name, line_name,
                       operator_name, passenger_count, passenger_year
                FROM stations WHERE area_id=?
                ORDER BY station_name, line_name
                """,
                (area_id,),
            )
            detail["stations"] = station_rows
            detail["transport_summary"] = _transport_summary(station_rows)

            detail["hazards"] = _rows(
                conn,
                "SELECT hazard_type, risk_label, source_id FROM hazards WHERE area_id=? ORDER BY hazard_type",
                (area_id,),
            )
            detail["sources"] = _rows(
                conn,
                """
                SELECT DISTINCT ds.source_id, ds.source_name, ds.dataset_id, ds.source_url,
                       ds.terms_url, ds.published_at, ds.fetched_at
                FROM data_sources ds
                WHERE ds.source_id IN (
                    SELECT source_id FROM area_prices WHERE area_id=? AND source_id IS NOT NULL
                    UNION SELECT source_id FROM population WHERE area_id=? AND source_id IS NOT NULL
                    UNION SELECT source_id FROM future_population WHERE area_id=? AND source_id IS NOT NULL
                    UNION SELECT source_id FROM facilities WHERE area_id=? AND source_id IS NOT NULL
                    UNION SELECT source_id FROM stations WHERE area_id=? AND source_id IS NOT NULL
                    UNION SELECT source_id FROM hazards WHERE area_id=? AND source_id IS NOT NULL
                )
                ORDER BY ds.source_name, ds.dataset_id
                """,
                (area_id, area_id, area_id, area_id, area_id, area_id),
            )
            (area_dir / f"{area_id}.json").write_text(
                json.dumps(detail, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    rankings = {
        "total_score": _rank(areas, "total_score"),
        "price_score": _rank(areas, "price_score"),
        "population_score": _rank(areas, "population_score"),
        "future_population_score": _rank(areas, "future_population_score"),
        "convenience_score": _rank(areas, "convenience_score"),
        "transport_score": _rank(areas, "transport_score"),
        "transaction_score": _rank(areas, "transaction_score"),
    }

    output.mkdir(parents=True, exist_ok=True)
    (output / "areas.json").write_text(
        json.dumps(areas, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output / "rankings.json").write_text(
        json.dumps(rankings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    component_keys = (
        "price_score",
        "population_score",
        "future_population_score",
        "convenience_score",
        "transport_score",
        "transaction_score",
    )
    (output / "meta.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "area_count": len(areas),
                "scored_area_count": len(rankings["total_score"]),
                "partially_scored_area_count": sum(
                    any(area.get(key) is not None for key in component_keys)
                    for area in areas
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
