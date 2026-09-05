from pathlib import Path

from japan_area_insights.site_deployment import (
    apply_google_site_verification,
    deployment_errors,
    write_custom_domain_file,
)


ROOT = Path(__file__).resolve().parents[1]


def _minimal_web(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")
    return web


def test_custom_domain_and_google_verification_are_validated(tmp_path):
    web = _minimal_web(tmp_path)
    assert write_custom_domain_file(web, "sumizahyo.jp") is True
    assert apply_google_site_verification(web, "verify-token") is True
    (web / "sitemap.xml").write_text(
        '<?xml version="1.0"?><urlset><url><loc>https://sumizahyo.jp/</loc></url></urlset>',
        encoding="utf-8",
    )
    (web / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\nSitemap: https://sumizahyo.jp/sitemap.xml\n",
        encoding="utf-8",
    )

    assert deployment_errors(
        web,
        site_url="https://sumizahyo.jp",
        custom_domain="sumizahyo.jp",
        google_site_verification="verify-token",
    ) == []
    assert (web / "CNAME").read_text(encoding="utf-8").strip() == "sumizahyo.jp"
    assert 'name="google-site-verification" content="verify-token"' in (web / "index.html").read_text(encoding="utf-8")


def test_domain_mismatch_fails_readiness_check(tmp_path):
    web = _minimal_web(tmp_path)
    write_custom_domain_file(web, "sumizahyo.jp")
    (web / "sitemap.xml").write_text(
        '<urlset><url><loc>https://nano-tani.github.io/japan-area-insights/</loc></url></urlset>',
        encoding="utf-8",
    )
    (web / "robots.txt").write_text(
        "Sitemap: https://nano-tani.github.io/japan-area-insights/sitemap.xml\n",
        encoding="utf-8",
    )

    errors = deployment_errors(
        web,
        site_url="https://nano-tani.github.io/japan-area-insights",
        custom_domain="sumizahyo.jp",
    )
    assert "JAI_CUSTOM_DOMAIN must match the hostname in JAI_SITE_URL" in errors
    assert "A custom-domain JAI_SITE_URL must not contain a path prefix" in errors


def test_empty_domain_and_verification_remove_stale_build_artifacts(tmp_path):
    web = _minimal_web(tmp_path)
    write_custom_domain_file(web, "old.example")
    apply_google_site_verification(web, "old-token")

    assert write_custom_domain_file(web, "") is False
    assert apply_google_site_verification(web, "") is False
    assert not (web / "CNAME").exists()
    assert "google-site-verification" not in (web / "index.html").read_text(encoding="utf-8")


def test_pages_workflow_exposes_domain_migration_variables_and_preflight():
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert "JAI_SITE_NAME: ${{ vars.JAI_SITE_NAME }}" in workflow
    assert "JAI_SITE_URL: ${{ vars.JAI_SITE_URL }}" in workflow
    assert "JAI_CUSTOM_DOMAIN: ${{ vars.JAI_CUSTOM_DOMAIN }}" in workflow
    assert "JAI_GOOGLE_SITE_VERIFICATION: ${{ vars.JAI_GOOGLE_SITE_VERIFICATION }}" in workflow
    assert "python scripts/check_deployment_readiness.py" in workflow
