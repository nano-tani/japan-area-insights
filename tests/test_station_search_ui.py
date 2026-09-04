from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_station_search_results_are_directly_below_search():
    html = (ROOT / "web" / "stations.html").read_text(encoding="utf-8")
    search_input = html.index('id="station-search"')
    results = html.index('id="station-search-results"')
    recommendations = html.index('class="insight-strip"')
    assert search_input < results < recommendations
    assert html.index("stations.js") < html.index("station-search-results.js") < html.index("station-query.js")


def test_station_search_prioritizes_exact_name_and_does_not_scroll_to_ranking():
    search_js = (ROOT / "web" / "station-search-results.js").read_text(encoding="utf-8")
    query_js = (ROOT / "web" / "station-query.js").read_text(encoding="utf-8")
    assert "if (name === query) return 0" in search_js
    assert "insightStrip.hidden = true" in search_js
    assert "openStationDetail" in search_js
    assert "scrollIntoView" not in query_js
