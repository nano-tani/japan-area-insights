from pathlib import Path

from japan_area_insights.seo_export import export_seo_files
from japan_area_insights.station_mesh_export import export_station_mesh_maps_from_public_data
from japan_area_insights.station_page_enhancer import enhance_station_pages
from japan_area_insights.station_page_export import export_station_pages
from japan_area_insights.station_theme_export import export_station_theme_pages

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "web" / "data"

if __name__ == "__main__":
    mesh_maps = export_station_mesh_maps_from_public_data(OUTPUT_DIR)
    stats = export_station_pages(OUTPUT_DIR)
    enhanced = enhance_station_pages(ROOT / "web")
    themes = export_station_theme_pages(OUTPUT_DIR)
    sitemap_count = export_seo_files(OUTPUT_DIR)
    print(
        "public pages built: "
        f"stations={stats.generated_count} "
        f"indexable={stats.indexable_count} "
        f"noindex={stats.noindex_count} "
        f"station_mesh_maps={mesh_maps} "
        f"enhanced={enhanced} "
        f"theme_pages={themes.generated_pages} "
        f"theme_rows={themes.ranked_stations} "
        f"sitemap_urls={sitemap_count}"
    )
