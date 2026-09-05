from pathlib import Path

from japan_area_insights.seo_export import export_seo_files
from japan_area_insights.site_trust_links import apply_site_trust_links
from japan_area_insights.station_mesh_export import export_station_mesh_maps_from_public_data
from japan_area_insights.station_page_enhancer import enhance_station_pages
from japan_area_insights.station_page_export import export_station_pages
from japan_area_insights.station_theme_export import export_station_theme_pages
from japan_area_insights.trust_page_export import export_trust_pages

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "web" / "data"

if __name__ == "__main__":
    mesh_maps = export_station_mesh_maps_from_public_data(OUTPUT_DIR)
    stats = export_station_pages(OUTPUT_DIR)
    enhanced = enhance_station_pages(ROOT / "web")
    themes = export_station_theme_pages(OUTPUT_DIR)
    trust_pages = export_trust_pages(OUTPUT_DIR)
    trust_linked = apply_site_trust_links(ROOT / "web")
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
        f"trust_pages={trust_pages} "
        f"trust_linked={trust_linked} "
        f"sitemap_urls={sitemap_count}"
    )
