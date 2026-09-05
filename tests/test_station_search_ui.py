from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_station_search_results_are_directly_below_search():
    html = (ROOT / "web" / "stations.html").read_text(encoding="utf-8")
    search_input = html.index('id="station-search"')
    results = html.index('id="station-search-results"')
    recommendations = html.index('class="insight-strip"')
    assert search_input < results < recommendations
    assert html.index("stations.js") < html.index("station-search-results.js") < html.index("station-query.js")


def test_station_search_prioritizes_exact_name_and_links_to_static_page():
    search_js = (ROOT / "web" / "station-search-results.js").read_text(encoding="utf-8")
    query_js = (ROOT / "web" / "station-query.js").read_text(encoding="utf-8")
    assert "if (name === query) return 0" in search_js
    assert "insightStrip.hidden = true" in search_js
    assert 'href="./station/${escapeHtml(station.station_code)}/"' in search_js
    assert 'data-station-save="${escapeHtml(station.station_code)}"' in search_js
    assert "scrollIntoView" not in query_js


def test_station_discovery_loads_shared_shortlist_controls():
    html = (ROOT / "web" / "stations.html").read_text(encoding="utf-8")
    assert "station-shortlist.css" in html
    assert html.index("station-shortlist.js") < html.index("station-shortlist-ui.js")
    shortlist = (ROOT / "web" / "station-shortlist.js").read_text(encoding="utf-8")
    shortlist_ui = (ROOT / "web" / "station-shortlist-ui.js").read_text(encoding="utf-8")
    assert 'MAX_ITEMS = 3' in shortlist
    assert "townscore:station-shortlist" in shortlist
    assert "station-compare.html" in shortlist_ui
    assert "townscore:station-cards-rendered" in shortlist_ui
