from pathlib import Path

from japan_area_insights.compute_scores import compute_partial_scores

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "area_insights.db"

if __name__ == "__main__":
    compute_partial_scores(DB_PATH)
    print("scores updated")
