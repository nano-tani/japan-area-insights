from pathlib import Path

from japan_area_insights.export import export_site_data
from japan_area_insights.station_export import export_station_site_data

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"
OUTPUT_DIR = ROOT / "web" / "data"

if __name__ == "__main__":
    export_site_data(DB_PATH, OUTPUT_DIR)
    export_station_site_data(DB_PATH, OUTPUT_DIR)
    print(f"exported: {OUTPUT_DIR}")
