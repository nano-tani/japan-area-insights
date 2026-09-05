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
    assert "DECISION SUMMARY" in compare
    assert "長く住みたい" in compare
    assert "価格と将来性" in compare
    assert 'meta name="robots" content="noindex,follow"' in page
    assert page.index("station-shortlist.js") < page.index("station-compare.js")
    assert "station-decision.css" in page
    assert "station-compare-summary.css" in page


def test_station_search_links_to_indexable_theme_rankings():
    page = (ROOT / "web" / "stations.html").read_text(encoding="utf-8")
    assert "総合点ではなく目的から探す" in page
    assert "./ranking/future-population/" in page
    assert "./ranking/price-and-future/" in page
    assert "./ranking/future-and-safety/" in page
