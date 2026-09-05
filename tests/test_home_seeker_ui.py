from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_homepage_leads_with_home_seeker_recommendation_flow():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "<span>あなたに合う街を</span><span>公的データから探す</span>" in html
    assert "おすすめから探す" in html
    assert "home-choice.css" in html
    assert html.index('id="recommend"') < html.index('id="name-search"')
    assert html.index('id="name-search"') < html.index('id="discover"')
    assert html.index('id="recommend"') < html.index('id="ranking-title"')
    assert "候補を2地域まで絞ったら" in html
    assert "ランキングは参考情報です" in html


def test_station_page_is_framed_as_a_place_to_live_search():
    html = (ROOT / "web" / "stations.html").read_text(encoding="utf-8")
    assert "<span>駅から</span><span>住む街を探す</span>" in html
    assert "気になる駅を検索" in html
    assert "候補の2駅を比べる" in html
    assert "おすすめから探す" in html


def test_ward_detail_supports_decision_not_just_ranking():
    html = (ROOT / "web" / "ward.html").read_text(encoding="utf-8")
    assert "住む街として、まず見る数字" in html
    assert "候補に残す前に、詳しく確認する" in html
    assert "特定地域への居住・購入・投資を推奨するものではありません" in html


def test_shared_navigation_source_is_centralized():
    script = (ROOT / "scripts" / "apply_shared_chrome.py").read_text(encoding="utf-8")
    assert '("recommend", "おすすめから探す")' in script
    assert '("search", "街・駅名から探す")' in script
    assert '("discover", "条件で探す")' in script
    assert '"index.html"' in script
    assert '"stations.html"' in script
    assert '"ward.html"' in script
    assert '"station-compare.html"' in script
    assert "trust_links_html" in script
    assert "JAI_SITE_NAME" in (ROOT / "src" / "japan_area_insights" / "site_config.py").read_text(encoding="utf-8")
