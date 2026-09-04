from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_homepage_leads_with_home_seeker_recommendation_flow():
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "あなたに合う街を、" in html
    assert "おすすめ検索をはじめる" in html
    assert "home-choice.css" in html
    assert html.index('id="recommend"') < html.index('id="name-search"')
    assert html.index('id="name-search"') < html.index('id="discover"')
    assert html.index('id="recommend"') < html.index('id="ranking-title"')
    assert "候補を2地域まで絞ったら" in html
    assert "ランキングは参考情報です" in html


def test_station_page_is_framed_as_a_place_to_live_search():
    html = (ROOT / "web" / "stations.html").read_text(encoding="utf-8")
    assert "駅から、<br>住む街を探す。" in html
    assert "気になる駅を検索" in html
    assert "候補の2駅を比べる" in html
    assert "おすすめから探す" in html


def test_ward_detail_supports_decision_not_just_ranking():
    html = (ROOT / "web" / "ward.html").read_text(encoding="utf-8")
    assert "住む街として、まず見る数字" in html
    assert "候補に残す前に、詳しく確認する" in html
    assert "特定地域への居住・購入・投資を推奨するものではありません" in html
