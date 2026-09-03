from pathlib import Path

from japan_area_insights.geography import sync_geo_foundation

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"

if __name__ == "__main__":
    stats = sync_geo_foundation(DB_PATH)
    print(
        f"geo foundation synced: wards={stats.ward_count}, "
        f"meshes={stats.mesh_count}, mappings={stats.mapping_count}"
    )
