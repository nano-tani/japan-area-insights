from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_station_recommendation_uses_only_station_score_components():
    source = (ROOT / "web" / "station-recommend.js").read_text(encoding="utf-8")

    for metric in (
        "price_score",
        "population_score",
        "future_population_score",
        "convenience_score",
        "transport_score",
        "transaction_score",
    ):
        assert metric in source

    assert "income" not in source.lower()
    assert "hazard" not in source.lower()
    assert 'station.eligibility === "eligible"' in source
    assert "1km圏内の物件所在地を意味しません" in source


def test_station_recommendations_link_and_save_without_detail_modal():
    source = (ROOT / "web" / "station-recommend.js").read_text(encoding="utf-8")
    assert 'href="./station/${escapeHtml(station.station_code)}/"' in source
    assert 'data-station-save="${escapeHtml(station.station_code)}"' in source
    assert "townscore:station-cards-rendered" in source
    assert "openStationDetail" not in source


def test_station_query_loads_recommendation_enhancement():
    loader = (ROOT / "web" / "station-query.js").read_text(encoding="utf-8")
    assert "./station-recommend.js" in loader
