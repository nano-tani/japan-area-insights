from __future__ import annotations

import json
from pathlib import Path

from .db import connect
from .estat_census_mobility import ensure_commuting_schema


def export_commuting_flows(db_path: str | Path, output_dir: str | Path, *, top_n: int = 15) -> None:
    output = Path(output_dir) / "analysis" / "mobility"
    output.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        ensure_commuting_schema(conn)
        areas = conn.execute("SELECT area_id,municipality_name FROM areas ORDER BY area_id").fetchall()
        for area in areas:
            area_id = str(area["area_id"])
            payload = {
                "area_id": area_id,
                "municipality_name": area["municipality_name"],
                "year": 2020,
                "flow_type": "work_school",
                "note": "2020年国勢調査の市区町村間通勤・通学OD。区外セルのみを表示します。",
                "outbound": [],
                "inbound": [],
            }
            for direction in ("outbound", "inbound"):
                rows = conn.execute(
                    """
                    SELECT counterpart_code,counterpart_name,count
                    FROM commuting_flows
                    WHERE ward_area_id=? AND direction=? AND year=2020
                    ORDER BY count DESC,counterpart_code
                    LIMIT ?
                    """,
                    (area_id, direction, int(top_n)),
                ).fetchall()
                payload[direction] = [
                    {
                        "counterpart_code": str(row["counterpart_code"]),
                        "counterpart_name": row["counterpart_name"],
                        "count": round(float(row["count"]), 2),
                    }
                    for row in rows
                ]
            (output / f"{area_id}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
