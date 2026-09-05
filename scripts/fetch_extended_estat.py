from __future__ import annotations

from pathlib import Path
from typing import Callable

from japan_area_insights.analysis_schema import ensure_analysis_schema
from japan_area_insights.db import connect, initialize
from japan_area_insights.estat_analysis import fetch_extended_estat
from japan_area_insights.estat_building_starts import fetch_building_starts
from japan_area_insights.estat_census_demographics_2020 import fetch_census_demographics_2020
from japan_area_insights.estat_current_dynamics import fetch_current_dynamics
from japan_area_insights.estat_economic_census_2024 import fetch_economic_census_2024
from japan_area_insights.estat_housing_2023 import fetch_housing_survey_2023
from japan_area_insights.estat_social_analysis import fetch_social_metrics
from japan_area_insights.estat_ssds_full import fetch_ssds_full_catalog
from japan_area_insights.estat_structure_analysis import fetch_structure_metrics
from japan_area_insights.sources.estat import EStatClient

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


def _run_source(conn, name: str, fetcher: Callable[[], int]) -> tuple[int, str | None]:
    """Commit each independent source separately and roll back only its own failure."""
    savepoint = "estat_" + "".join(char if char.isalnum() else "_" for char in name)
    conn.execute(f"SAVEPOINT {savepoint}")
    try:
        count = int(fetcher())
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        conn.commit()
        print(f"e-Stat source ok: {name} stored={count}")
        return count, None
    except Exception as exc:  # keep checking the remaining independent datasets
        conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        conn.execute(f"RELEASE SAVEPOINT {savepoint}")
        conn.commit()
        message = f"{type(exc).__name__}: {exc}"
        print(f"::error title=e-Stat source failed::{name}: {message}")
        return 0, message


if __name__ == "__main__":
    initialize(DB_PATH)
    client = EStatClient()
    failures: list[tuple[str, str]] = []
    total = 0

    with connect(DB_PATH) as conn:
        ensure_analysis_schema(conn)
        conn.commit()
        area_ids = [str(row["area_id"]) for row in conn.execute("SELECT area_id FROM areas ORDER BY area_id")]

        sources: list[tuple[str, Callable[[], int]]] = [
            ("extended", lambda: fetch_extended_estat(client, conn, area_ids)),
            ("social", lambda: fetch_social_metrics(client, conn, area_ids)),
            ("structure", lambda: fetch_structure_metrics(client, conn, area_ids)),
            ("ssds_full", lambda: fetch_ssds_full_catalog(client, conn, area_ids)),
            ("economic_census_2024", lambda: fetch_economic_census_2024(client, conn, area_ids)),
            ("housing_2023", lambda: fetch_housing_survey_2023(client, conn, area_ids)),
            ("census_demographics_2020", lambda: fetch_census_demographics_2020(client, conn, area_ids)),
            ("building_starts", lambda: fetch_building_starts(client, conn, area_ids)),
            ("current_dynamics", lambda: fetch_current_dynamics(client, conn, area_ids)),
        ]

        for name, fetcher in sources:
            count, error = _run_source(conn, name, fetcher)
            total += count
            if error:
                failures.append((name, error))

    print(f"stored {total} extended e-Stat metrics")
    if failures:
        summary = "; ".join(f"{name}={error}" for name, error in failures)
        raise SystemExit(f"extended e-Stat failures: {summary}")
