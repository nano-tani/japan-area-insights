from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

NAV_CSS = '<link rel="stylesheet" href="./navigation.css?v=20260905-5">'
SOURCE_LINK = '<p><a href="https://github.com/nano-tani/japan-area-insights" target="_blank" rel="noreferrer">計算方法・出典 →</a></p>'

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
}

NAV_RE = re.compile(r'<nav class="site-nav"[^>]*>.*?</nav>', re.DOTALL)
NAV_CSS_RE = re.compile(r'\s*<link rel="stylesheet" href="\./navigation\.css[^>]*>')
FOOTER_RE = re.compile(r'(<footer>)(.*?)(</footer>)', re.DOTALL)


def render_nav(page: str) -> str:
    config = PAGES[page]
    lines = ['<nav class="site-nav" aria-label="主要ナビゲーション">']
    for key, label in NAV_ITEMS:
        current = ' aria-current="page"' if key == config["active"] else ""
        lines.append(f'      <a href="{config["hrefs"][key]}"{current}>{label}</a>')
    lines.append("    </nav>")
    return "\n".join(lines)


def ensure_source_link(html: str) -> str:
    match = FOOTER_RE.search(html)
    if not match:
        return html
    body = match.group(2)
    body = re.sub(
        r'\s*<p><a href="https://github\.com/nano-tani/japan-area-insights".*?</a></p>',
        "",
        body,
        flags=re.DOTALL,
    )
    body = body.rstrip() + "\n    " + SOURCE_LINK + "\n  "
    return html[: match.start()] + match.group(1) + body + match.group(3) + html[match.end() :]


def normalize_page(path: Path) -> None:
    html = path.read_text(encoding="utf-8")
    html, replaced = NAV_RE.subn(render_nav(path.name), html, count=1)
    if replaced != 1:
        raise RuntimeError(f"primary navigation not found: {path}")

    html = NAV_CSS_RE.sub("", html)
    html = html.replace("</head>", f"  {NAV_CSS}\n</head>", 1)
    html = ensure_source_link(html)
    path.write_text(html, encoding="utf-8")


def main() -> None:
    for page in PAGES:
        normalize_page(WEB / page)
        print(f"shared chrome applied: {page}")


if __name__ == "__main__":
    main()
