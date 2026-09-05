from pathlib import Path

from japan_area_insights.seo_export import export_seo_files
from japan_area_insights.station_page_export import export_station_pages

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "web" / "data"

if __name__ == "__main__":
    stats = export_station_pages(OUTPUT_DIR)
    sitemap_count = export_seo_files(OUTPUT_DIR)
    print(
        "public pages built: "
        f"stations={stats.generated_count} "
        f"indexable={stats.indexable_count} "
        f"noindex={stats.noindex_count} "
        f"sitemap_urls={sitemap_count}"
    )
