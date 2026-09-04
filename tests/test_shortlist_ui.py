from pathlib import Path

from japan_area_insights.explore_export import THEMES

ROOT = Path(__file__).resolve().parents[1]


def test_explore_themes_use_seeded_demographic_metric_keys():
    people = next(theme for theme in THEMES if theme["key"] == "people")
    life = next(theme for theme in THEMES if theme["key"] == "life")

    assert "demographics2020.single_household_share" in people["metrics"]
    assert "household.single_household_share" not in people["metrics"]
    assert "people.child_share" not in life["metrics"]
    assert "people.elderly_share" not in life["metrics"]
    assert "demographics2020.four_plus_household_share" in life["metrics"]


def test_home_loads_shortlist_enhancement_through_existing_script():
    loader = (ROOT / "web" / "ward-links.js").read_text(encoding="utf-8")
    shortlist = (ROOT / "web" / "shortlist.js").read_text(encoding="utf-8")

    assert "./shortlist.js" in loader
    assert "town-score-shortlist-v1" in shortlist
    assert "MAX_ITEMS = 3" in shortlist
    assert "compare-c" in shortlist
    assert "候補に残す" in shortlist
