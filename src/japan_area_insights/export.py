from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .db import connect


def _rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


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
            detail["future_population"] = _rows(
                conn,
                """
                SELECT year, SUM(projected_population) AS projected_population
                FROM future_population WHERE area_id=?
                GROUP BY year ORDER BY year
                """,
                (area_id,),
            )
            detail["facilities"] = _rows(
                conn,
                "SELECT facility_type, COUNT(*) AS count FROM facilities WHERE area_id=? GROUP BY facility_type ORDER BY facility_type",
                (area_id,),
            )
            detail["stations"] = _rows(conn, "SELECT station_name, line_name FROM stations WHERE area_id=? ORDER BY station_name", (area_id,))
            detail["hazards"] = _rows(conn, "SELECT hazard_type, risk_label, source_id FROM hazards WHERE area_id=? ORDER BY hazard_type", (area_id,))
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
                ORDER BY ds.source_name
                """,
                (area_id, area_id, area_id, area_id, area_id, area_id),
            )
            (area_dir / f"{area_id}.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")

    ranked = [area for area in areas if area.get("total_score") is not None]
    ranked.sort(key=lambda x: (-float(x["total_score"]), x["area_id"]))

    output.mkdir(parents=True, exist_ok=True)
    (output / "areas.json").write_text(json.dumps(areas, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "rankings.json").write_text(json.dumps({"total_score": ranked}, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "meta.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "area_count": len(areas),
                "scored_area_count": len(ranked),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
