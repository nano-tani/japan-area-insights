from pathlib import Path

from japan_area_insights.analysis_export import export_analysis_data
from japan_area_insights.db import initialize
from japan_area_insights.explore_export import export_explore_data
from japan_area_insights.export import export_site_data
from japan_area_insights.mobility_export import export_commuting_flows
from japan_area_insights.seo_export import export_seo_files
from japan_area_insights.station_context import compute_station_context_metrics
from japan_area_insights.station_export import export_station_site_data
from japan_area_insights.station_page_export import export_station_pages
from japan_area_insights.ward_maps import export_ward_mesh_maps

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"
OUTPUT_DIR = ROOT / "web" / "data"

if __name__ == "__main__":
    initialize(DB_PATH)
    context_metrics = compute_station_context_metrics(DB_PATH)
    export_site_data(DB_PATH, OUTPUT_DIR)
    export_station_site_data(DB_PATH, OUTPUT_DIR)
    export_ward_mesh_maps(DB_PATH, OUTPUT_DIR)
    export_analysis_data(DB_PATH, OUTPUT_DIR)
    export_commuting_flows(DB_PATH, OUTPUT_DIR)
    export_explore_data(DB_PATH, OUTPUT_DIR)
    station_stats = export_station_pages(OUTPUT_DIR)
    sitemap_count = export_seo_files(OUTPUT_DIR)
    print(
        f"site data built: {OUTPUT_DIR}; "
        f"station_context_metrics={context_metrics}; "
        f"station_pages={station_stats.generated_count}; "
        f"sitemap_urls={sitemap_count}"
    )
