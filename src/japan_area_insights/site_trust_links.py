from __future__ import annotations

import re
from pathlib import Path

GITHUB_URL = "https://github.com/nano-tani/japan-area-insights"
FOOTER_RE = re.compile(r"(<footer>)(.*?)(</footer>)", re.DOTALL)
OLD_SOURCE_RE = re.compile(
    r'\s*<p><a href="https://github\.com/nano-tani/japan-area-insights".*?</a></p>',
    re.DOTALL,
)
TRUST_RE = re.compile(r'\s*<p class="site-trust-links" data-site-trust-links>.*?</p>', re.DOTALL)


def _prefix_for(path: Path, web_root: Path) -> str:
    relative = path.relative_to(web_root)
    depth = max(0, len(relative.parts) - 1)
    return "../" * depth if depth else "./"


def trust_links_html(prefix: str) -> str:
    return (
        '<p class="site-trust-links" data-site-trust-links>'
        f'<a href="{prefix}about/">運営について</a><span> / </span>'
        f'<a href="{prefix}methodology/">計算方法</a><span> / </span>'
        f'<a href="{prefix}sources/">データ出典</a><span> / </span>'
        f'<a href="{prefix}advertising/">広告について</a><span> / </span>'
        f'<a href="{prefix}privacy/">プライバシー</a><span> / </span>'
        f'<a href="{GITHUB_URL}" target="_blank" rel="noreferrer">コード</a>'
        '</p>'
    )


def enhance_page(path: Path, web_root: Path) -> bool:
    html = path.read_text(encoding="utf-8")
    match = FOOTER_RE.search(html)
    if not match:
        return False
    body = TRUST_RE.sub("", match.group(2))
    body = OLD_SOURCE_RE.sub("", body)
    body = body.rstrip() + "\n    " + trust_links_html(_prefix_for(path, web_root)) + "\n  "
    updated = html[: match.start()] + match.group(1) + body + match.group(3) + html[match.end() :]
    path.write_text(updated, encoding="utf-8")
    return True


def apply_site_trust_links(web_root: str | Path) -> int:
    root = Path(web_root)
    count = 0
    for path in sorted(root.rglob("*.html")):
        if enhance_page(path, root):
            count += 1
    return count
