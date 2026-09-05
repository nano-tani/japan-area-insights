from __future__ import annotations

import re
from pathlib import Path

from japan_area_insights.site_config import DEFAULT_SITE_NAME, SITE_NAME
from japan_area_insights.site_trust_links import trust_links_html

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

NAV_CSS = '<link rel="stylesheet" href="./navigation.css?v=20260905-5">'

NAV_ITEMS = (
    ("recommend", "おすすめから探す"),
    ("search", "街・駅名から探す"),
    ("discover", "条件で探す"),
)

PAGES = {
    "index.html": {
        "active": "recommend",
        "hrefs": {
            "recommend": "#recommend",
            "search": "#name-search",
            "discover": "#discover",
        },
    },
    "stations.html": {
        "active": "search",
        "hrefs": {
            "recommend": "./#recommend",
            "search": "./stations.html",
            "discover": "./#discover",
        },
    },
    "ward.html": {
        "active": "search",
        "hrefs": {
            "recommend": "./#recommend",
            "search": "./#name-search",
            "discover": "./#discover",
        },
    },
    "station-compare.html": {
        "active": "search",
        "hrefs": {
            "recommend": "./#recommend",
            "search": "./stations.html",
            "discover": "./#discover",
        },
    },
}

NAV_RE = re.compile(r'<nav class="site-nav"[^>]*>.*?</nav>', re.DOTALL)
NAV_CSS_RE = re.compile(r'\s*<link rel="stylesheet" href="\./navigation\.css[^>]*>')
FOOTER_RE = re.compile(r'(<footer>)(.*?)(</footer>)', re.DOTALL)
OLD_SOURCE_RE = re.compile(
    r'\s*<p><a href="https://github\.com/nano-tani/japan-area-insights".*?</a></p>',
    re.DOTALL,
)
TRUST_RE = re.compile(r'\s*<p class="site-trust-links" data-site-trust-links>.*?</p>', re.DOTALL)


def render_nav(page: str) -> str:
    config = PAGES[page]
    lines = ['<nav class="site-nav" aria-label="主要ナビゲーション">']
    for key, label in NAV_ITEMS:
        current = ' aria-current="page"' if key == config["active"] else ""
        lines.append(f'      <a href="{config["hrefs"][key]}"{current}>{label}</a>')
    lines.append("    </nav>")
    return "\n".join(lines)


def ensure_trust_links(html: str) -> str:
    match = FOOTER_RE.search(html)
    if not match:
        return html
    body = TRUST_RE.sub("", match.group(2))
    body = OLD_SOURCE_RE.sub("", body)
    body = body.rstrip() + "\n    " + trust_links_html("./") + "\n  "
    return html[: match.start()] + match.group(1) + body + match.group(3) + html[match.end() :]


def normalize_page(path: Path) -> None:
    html = path.read_text(encoding="utf-8")
    # A future brand switch can be performed through JAI_SITE_NAME without
    # manually editing each static top-level page.
    if SITE_NAME != DEFAULT_SITE_NAME:
        html = html.replace(DEFAULT_SITE_NAME, SITE_NAME)

    html, replaced = NAV_RE.subn(render_nav(path.name), html, count=1)
    if replaced != 1:
        raise RuntimeError(f"primary navigation not found: {path}")

    html = NAV_CSS_RE.sub("", html)
    html = html.replace("</head>", f"  {NAV_CSS}\n</head>", 1)
    html = ensure_trust_links(html)
    path.write_text(html, encoding="utf-8")


def main() -> None:
    for page in PAGES:
        path = WEB / page
        if not path.exists():
            continue
        normalize_page(path)
        print(f"shared chrome applied: {page}")


if __name__ == "__main__":
    main()
