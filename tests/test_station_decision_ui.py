from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_station_decision_assets_cover_shortlist_nearby_and_compare():
    store = (ROOT / "web" / "station-shortlist.js").read_text(encoding="utf-8")
    script = (ROOT / "web" / "station-decision.js").read_text(encoding="utf-8")
    compare = (ROOT / "web" / "station-compare.js").read_text(encoding="utf-8")
    page = (ROOT / "web" / "station-compare.html").read_text(encoding="utf-8")

    assert "town-score-station-shortlist-v1" in store
    assert "window.StationShortlist" in store
    assert "haversineKm" in script
    assert "station-compare.html" in script
    assert "この駅周辺の物件を検索" in script
    assert "window.StationShortlist" in script
    assert "window.StationShortlist" in compare
    assert "hazard_flood_population_share" in compare
    assert "seismic_30y_6lower_probability" in compare
    assert 'meta name="robots" content="noindex,follow"' in page
    assert page.index("station-shortlist.js") < page.index("station-compare.js")
    assert "station-decision.css" in page
