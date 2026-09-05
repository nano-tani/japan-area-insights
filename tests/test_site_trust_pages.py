from pathlib import Path

from japan_area_insights.legal_page_export import export_legal_pages
from japan_area_insights.site_trust_links import apply_site_trust_links
from japan_area_insights.trust_page_export import export_trust_pages


ROOT = Path(__file__).resolve().parents[1]


def test_trust_pages_are_generated_with_public_methodology_and_sources(tmp_path):
    data_dir = tmp_path / "web" / "data"
    data_dir.mkdir(parents=True)

    assert export_trust_pages(data_dir) == 2
    methodology = (tmp_path / "web" / "methodology" / "index.html").read_text(encoding="utf-8")
    sources = (tmp_path / "web" / "sources" / "index.html").read_text(encoding="utf-8")

    assert "駅エリアは駅中心1km圏" in methodology
    assert "総合100点は参考値" in methodology
    assert "将来人口60%" in methodology
    assert "AIは説明文の補助" in methodology
    assert "XIT001" in sources
    assert "XKT013" in sources
    assert "J-SHIS" in sources
    assert "国土地理院" in sources


def test_legal_pages_cover_operator_privacy_and_advertising_policy(tmp_path):
    data_dir = tmp_path / "web" / "data"
    data_dir.mkdir(parents=True)

    assert export_legal_pages(data_dir) == 3
    about = (tmp_path / "web" / "about" / "index.html").read_text(encoding="utf-8")
    privacy = (tmp_path / "web" / "privacy" / "index.html").read_text(encoding="utf-8")
    advertising = (tmp_path / "web" / "advertising" / "index.html").read_text(encoding="utf-8")

    assert "行政機関・不動産会社の公式サービスではありません" in about
    assert "広告と評価ロジックを分離する" in about
    assert "localStorage" in privacy
    assert "アクセス解析・広告を導入する場合" in privacy
    assert "順位やおすすめを広告で変えない" in advertising
    assert 'rel=\"sponsored\"' in advertising


def test_site_trust_links_use_correct_relative_paths(tmp_path):
    web_root = tmp_path / "web"
    nested = web_root / "station" / "001" / "index.html"
    nested.parent.mkdir(parents=True)
    nested.write_text(
        '<html><body><footer><p><a href="https://github.com/nano-tani/japan-area-insights">計算方法・出典 →</a></p></footer></body></html>',
        encoding="utf-8",
    )

    assert apply_site_trust_links(web_root) == 1
    html = nested.read_text(encoding="utf-8")
    assert 'href="../../about/"' in html
    assert 'href="../../methodology/"' in html
    assert 'href="../../sources/"' in html
    assert 'href="../../advertising/"' in html
    assert 'href="../../privacy/"' in html
    assert html.count("data-site-trust-links") == 1


def test_site_config_supports_future_brand_and_domain_switch():
    source = (ROOT / "src" / "japan_area_insights" / "site_config.py").read_text(encoding="utf-8")
    assert 'os.getenv("JAI_SITE_NAME"' in source
    assert 'os.getenv("JAI_SITE_URL"' in source
    assert "DEFAULT_SITE_URL" in source


def test_seo_export_includes_trust_pages():
    source = (ROOT / "src" / "japan_area_insights" / "seo_export.py").read_text(encoding="utf-8")
    assert '"about/"' in source
    assert '"methodology/"' in source
    assert '"sources/"' in source
    assert '"advertising/"' in source
    assert '"privacy/"' in source
