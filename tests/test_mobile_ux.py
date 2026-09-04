from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STYLES = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
AUDIT = (ROOT / "docs" / "MOBILE_UX_AUDIT.md").read_text(encoding="utf-8")
WARD_LINKS = (ROOT / "web" / "ward-links.js").read_text(encoding="utf-8")
STATION_QUERY = (ROOT / "web" / "station-query.js").read_text(encoding="utf-8")


def test_mobile_controls_avoid_ios_focus_zoom_and_small_touch_targets():
    assert 'input[type="search"]' in STYLES
    assert 'input[type="number"]' in STYLES
    assert 'select { font-size: 16px !important; }' in STYLES
    assert '.recommend-presets button' in STYLES
    assert '.station-recommend-presets button' in STYLES
    assert 'min-height: 44px !important;' in STYLES
    assert '.recommend-slider input[type="range"]' in STYLES
    assert '.station-recommend-slider input[type="range"]' in STYLES


def test_mobile_sticky_navigation_and_dialog_do_not_cover_content():
    assert '.ward-local-nav {' in STYLES
    assert 'position: static !important;' in STYLES
    assert 'scroll-padding-top: 126px;' in STYLES
    assert 'max-height: calc(100dvh - 16px) !important;' in STYLES


def test_mobile_dense_tables_keep_context_without_forcing_full_width():
    assert 'table:has(#ranking-body)' in STYLES
    assert 'table:has(#station-ranking-body)' in STYLES
    assert '.discover-table th:first-child' in STYLES
    assert 'position: sticky;' in STYLES


def test_repeated_static_json_requests_are_coalesced_per_page():
    for script in (WARD_LINKS, STATION_QUERY):
        assert '__townScoreStaticJsonCacheInstalled' in script
        assert 'response.clone()' in script
        assert '/\\/data\\/.+\\.json$/' in script


def test_mobile_accessibility_fallbacks_are_documented_and_enabled():
    assert '@media (hover: none) and (pointer: coarse)' in STYLES
    assert '@media (prefers-reduced-motion: reduce)' in STYLES
    assert 'iPhone Safari' in AUDIT
    assert 'Android Chrome' in AUDIT
    assert 'スマホ改善は表示・操作性・同一ページ内の転送効率だけに限定' in AUDIT
