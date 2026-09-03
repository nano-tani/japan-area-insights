from pathlib import Path

from japan_area_insights.analysis_schema import ensure_analysis_schema
from japan_area_insights.db import connect, initialize
from japan_area_insights.detailed_analysis import compute_market_metrics

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"

if __name__ == "__main__":
    initialize(DB_PATH)
    with connect(DB_PATH) as conn:
        ensure_analysis_schema(conn)
        count = compute_market_metrics(conn)
    print(f"computed {count} detailed market metrics")
