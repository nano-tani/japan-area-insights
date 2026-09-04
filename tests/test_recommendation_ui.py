from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_homepage_exposes_weighted_recommendation_search():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="recommend"' in html
    assert 'id="recommend-sliders"' in html
    assert 'id="recommend-results"' in html
    assert 'href="#recommend"' in html
    assert "recommend.css" in html
    assert "recommend.js" in html
    assert html.index('id="recommend"') < html.index('id="discover"')


def test_recommendation_has_independent_preferences_and_directions():
    js = (ROOT / "web" / "recommend.js").read_text(encoding="utf-8")
    for key in (
        "affordability",
        "market",
        "population",
        "future",
        "housing",
        "economy",
        "life",
        "transport",
        "urban",
        "resilience",
    ):
        assert f'key: "{key}"' in js
    assert '["market.land_price_median", "lower"]' in js
    assert '["hazard.flood_population_share", "lower"]' in js
    assert '["core.transport_score", "higher"]' in js
    assert 'type="range"' in js
    assert 'min="0" max="5"' in js


def test_recommendation_is_separate_from_core_score_and_handles_missing_data():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "web" / "recommend.js").read_text(encoding="utf-8")
    assert "「一致度」はCore Scoreではありません" in html
    assert "データが欠ける項目は推定せず" in html
    assert "詳細データ更新後に利用可能" in js
    assert "score: weighted / totalWeight" in js
    assert "coverage: coveredWeight / totalWeight * 100" in js
    assert "area_scores" not in js
