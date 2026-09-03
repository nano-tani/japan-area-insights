from pathlib import Path

from japan_area_insights.analysis_export import export_analysis_data
from japan_area_insights.export import export_site_data
from japan_area_insights.station_export import export_station_site_data
from japan_area_insights.ward_maps import export_ward_mesh_maps

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"
OUTPUT_DIR = ROOT / "web" / "data"

if __name__ == "__main__":
    export_site_data(DB_PATH, OUTPUT_DIR)
    export_station_site_data(DB_PATH, OUTPUT_DIR)
    export_ward_mesh_maps(DB_PATH, OUTPUT_DIR)
    export_analysis_data(DB_PATH, OUTPUT_DIR)
    print(f"exported: {OUTPUT_DIR}")
