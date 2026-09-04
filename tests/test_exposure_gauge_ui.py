from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_urban_and_hazard_exposures_use_compact_gauges():
    html = (ROOT / "web" / "ward.html").read_text(encoding="utf-8")
    js = (ROOT / "web" / "ward-analysis.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "exposure-gauges.css").read_text(encoding="utf-8")

    assert "exposure-gauges.css" in html
    assert 'class="exposure-grid"' in js
    assert 'class="exposure-tile' in js
    assert 'class="exposure-gauge' in js
    assert "M12 56 A48 48 0 0 1 108 56" in js
    assert "exposure-row" not in js

    assert "都市計画・生活圏</strong> 250mメッシュ対象率" in js
    assert "防災</strong> 2025人口曝露率" in js
    assert "低いほど曝露人口が少ない" in js

    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in css


def test_hazard_band_details_are_collapsed_by_default():
    js = (ROOT / "web" / "ward-analysis.js").read_text(encoding="utf-8")

    assert '<details class="exposure-details">' in js
    assert "内訳を見る" in js
    assert "exposure-detail-row" in js
