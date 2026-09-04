from pathlib import Path

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

if __name__ == "__main__":
    initialize(DB_PATH)
    client = EStatClient()
    with connect(DB_PATH) as conn:
        ensure_analysis_schema(conn)
        area_ids = [str(row["area_id"]) for row in conn.execute("SELECT area_id FROM areas ORDER BY area_id")]
        count = fetch_extended_estat(client, conn, area_ids)
        count += fetch_social_metrics(client, conn, area_ids)
        count += fetch_structure_metrics(client, conn, area_ids)
        count += fetch_ssds_full_catalog(client, conn, area_ids)
        count += fetch_economic_census_2024(client, conn, area_ids)
        count += fetch_housing_survey_2023(client, conn, area_ids)
        count += fetch_census_demographics_2020(client, conn, area_ids)
        count += fetch_building_starts(client, conn, area_ids)
        count += fetch_current_dynamics(client, conn, area_ids)
    print(f"stored {count} extended e-Stat metrics")
