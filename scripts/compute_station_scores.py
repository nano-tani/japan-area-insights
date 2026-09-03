from pathlib import Path

from japan_area_insights.station_areas import compute_station_scores

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


if __name__ == "__main__":
    stats = compute_station_scores(DB_PATH)
    print(
        f"station areas: {stats.station_area_count}, "
        f"eligible totals: {stats.eligible_count}, "
        f"partially scored: {stats.partially_scored_count}"
    )
