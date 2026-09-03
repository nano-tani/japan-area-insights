from pathlib import Path

from japan_area_insights.station_areas import sync_station_areas

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"


if __name__ == "__main__":
    stats = sync_station_areas(DB_PATH)
    print(
        f"station areas: {stats.station_area_count}, "
        f"station-mesh mappings: {stats.mapping_count}"
    )
