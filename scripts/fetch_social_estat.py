from pathlib import Path

from japan_area_insights.analysis_schema import ensure_analysis_schema
from japan_area_insights.db import connect, initialize
from japan_area_insights.estat_social_analysis import fetch_social_metrics
from japan_area_insights.sources.estat import EStatClient

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"

if __name__ == "__main__":
    initialize(DB_PATH)
    client = EStatClient()
    with connect(DB_PATH) as conn:
        ensure_analysis_schema(conn)
        area_ids = [str(row["area_id"]) for row in conn.execute("SELECT area_id FROM areas ORDER BY area_id")]
        count = fetch_social_metrics(client, conn, area_ids)
    print(f"stored {count} housing/labor/education/health/social metrics")
