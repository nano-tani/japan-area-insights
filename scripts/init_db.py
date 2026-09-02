from pathlib import Path

from japan_area_insights.db import initialize

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"

if __name__ == "__main__":
    initialize(DB_PATH)
    print(f"initialized: {DB_PATH}")
