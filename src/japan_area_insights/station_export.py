from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from .db import connect
from .station_areas import (
    STATION_DEFINITION_VERSION,
    STATION_METRIC_VERSION,
    STATION_PEER_GROUP,
    STATION_RADIUS_M,
    STATION_SCORE_VERSION,
)
from .station_transactions import ensure_station_transaction_schema


def _rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _rank(rows: list[dict], key: str) -> list[dict]:
    result = [row for row in rows if row.get(key) is not None]
    result.sort(key=lambda row: (-float(row[key]), str(row["station_code"])))
    return result


def _annual_transactions(conn, station_code: str) -> list[dict]:
    by_year: dict[int, list] = {}
    for row in conn.execute(
        """
        SELECT year, unit_price
        FROM station_transactions
        WHERE station_group_code=?
        ORDER BY year
        """,
        (station_code,),
    ):
        by_year.setdefault(int(row["year"]), []).append(row)

    result: list[dict] = []
    for year, rows in sorted(by_year.items()):
        unit_prices = [float(row["unit_price"]) for row in rows if row["unit_price"] is not None]
        result.append(
            {
                "year": year,
                "transaction_count": len(rows),
                "priced_transaction_count": len(unit_prices),
                "median_unit_price": round(median(unit_prices), 2) if unit_prices else None,
            }
        )
    return result


def export_station_site_data(db_path: str | Path, output_dir: str | Path) -> None:
    output = Path(output_dir)
    geo_dir = output / "geo"
    station_dir = geo_dir / "station"
    rankings_dir = output / "rankings"
    station_dir.mkdir(parents=True, exist_ok=True)
    rankings_dir.mkdir(parents=True, exist_ok=True)

    for stale in station_dir.glob("*.json"):
        stale.unlink()

    with connect(db_path) as conn:
        ensure_station_transaction_schema(conn)
        stations = _rows(
            conn,
            """
            SELECT
                gu.geo_id,
                gu.canonical_code AS station_code,
                gu.name,
                gu.primary_area_id,
                a.municipality_name AS primary_ward_name,
                gu.latitude,
                gu.longitude,
                gu.radius_m,
                gs.calculation_date,
                gs.price_score,
                gs.population_score,
                gs.future_population_score,
                gs.convenience_score,
                gs.transport_score,
                gs.transaction_score,
                gs.total_score,
                gs.confidence,
                gs.data_completeness,
                gs.score_version,
                gs.eligibility,
                gs.eligibility_reason
            FROM geo_units gu
            LEFT JOIN areas a ON a.area_id=gu.primary_area_id
            LEFT JOIN geo_scores gs ON gs.rowid=(
                SELECT x.rowid FROM geo_scores x
                WHERE x.geo_id=gu.geo_id AND x.peer_group=?
                ORDER BY x.calculation_date DESC, x.rowid DESC
                LIMIT 1
            )
            WHERE gu.geo_type='station_area'
              AND gu.definition_version=?
              AND gu.is_active=1
            ORDER BY gu.name, gu.canonical_code
            """,
            (STATION_PEER_GROUP, STATION_DEFINITION_VERSION),
        )

        for station in stations:
            geo_id = str(station["geo_id"])
            station_code = str(station["station_code"])
            detail = dict(station)

            center_lines = _rows(
                conn,
                """
                SELECT station_name, line_name, operator_name,
                       passenger_count, passenger_year, source_id
                FROM stations
                WHERE COALESCE(group_code, station_code)=?
                ORDER BY operator_name, line_name
                """,
                (station_code,),
            )
            detail["lines"] = center_lines

            metric_rows = _rows(
                conn,
                """
                SELECT metric_key, period, value, sample_size, source_id,
                       metric_version, calculated_at
                FROM geo_metrics
                WHERE geo_id=? AND metric_version=?
                ORDER BY metric_key
                """,
                (geo_id, STATION_METRIC_VERSION),
            )
            detail["metrics"] = {row["metric_key"]: row for row in metric_rows}

            detail["future_population"] = _rows(
                conn,
                """
                SELECT fp.year, SUM(fp.projected_population * gum.weight) AS projected_population
                FROM geo_unit_meshes gum
                JOIN future_population fp ON fp.mesh_id=gum.mesh_id
                WHERE gum.geo_id=?
                GROUP BY fp.year
                ORDER BY fp.year
                """,
                (geo_id,),
            )
            p2025 = next(
                (row["projected_population"] for row in detail["future_population"] if row["year"] == 2025),
                None,
            )
            for row in detail["future_population"]:
                value = row.get("projected_population")
                row["retention_rate"] = (
                    round(float(value) / float(p2025) * 100.0, 2)
                    if value is not None and p2025 not in (None, 0)
                    else None
                )

            detail["transactions"] = _annual_transactions(conn, station_code)
            detail["mesh_count"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM geo_unit_meshes WHERE geo_id=?",
                    (geo_id,),
                ).fetchone()[0]
            )

            source_ids = {
                int(row["source_id"])
                for row in metric_rows
                if row.get("source_id") is not None
            }
            source_ids.update(
                int(row["source_id"])
                for row in center_lines
                if row.get("source_id") is not None
            )
            if source_ids:
                placeholders = ",".join("?" for _ in source_ids)
                detail["sources"] = _rows(
                    conn,
                    f"""
                    SELECT source_id, source_name, dataset_id, source_url,
                           terms_url, published_at, fetched_at
                    FROM data_sources
                    WHERE source_id IN ({placeholders})
                    ORDER BY source_name, dataset_id
                    """,
                    tuple(sorted(source_ids)),
                )
            else:
                detail["sources"] = []

            (station_dir / f"{station_code}.json").write_text(
                json.dumps(detail, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    rankings = {
        "total_score": _rank(stations, "total_score"),
        "price_score": _rank(stations, "price_score"),
        "population_score": _rank(stations, "population_score"),
        "future_population_score": _rank(stations, "future_population_score"),
        "convenience_score": _rank(stations, "convenience_score"),
        "transport_score": _rank(stations, "transport_score"),
        "transaction_score": _rank(stations, "transaction_score"),
    }
    generated_at = datetime.now(timezone.utc).isoformat()

    (geo_dir / "index.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "station_definition": {
                    "radius_m": STATION_RADIUS_M,
                    "definition_version": STATION_DEFINITION_VERSION,
                    "metric_version": STATION_METRIC_VERSION,
                    "score_version": STATION_SCORE_VERSION,
                    "peer_group": STATION_PEER_GROUP,
                    "population_note": "人口動向はXKT013の2020年人口から2025年推計人口への変化を暫定利用",
                    "transaction_note": "価格・取引はXIT001を駅グループコードで検索した取引を集計。1km圏内の物件位置を意味しない",
                },
                "station_area_count": len(stations),
                "eligible_station_count": len(rankings["total_score"]),
                "station_areas": stations,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (rankings_dir / "station.json").write_text(
        json.dumps(rankings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
