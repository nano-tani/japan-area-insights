from __future__ import annotations

from pathlib import Path

CSS_LINK = '<link rel="stylesheet" href="../../station-context.css?v=20260905-1">'
JS_SCRIPT = '<script src="../../station-context.js?v=20260905-1" defer></script>'


def enhance_station_pages(web_root: str | Path) -> int:
    root = Path(web_root)
    station_root = root / "station"
    if not station_root.exists():
        return 0
    count = 0
    for page in sorted(station_root.glob("[0-9]*/index.html")):
        html = page.read_text(encoding="utf-8")
        if "station-context.css" not in html:
            html = html.replace("</head>", f"  {CSS_LINK}\n</head>", 1)
        if "station-context.js" not in html:
            html = html.replace("</body>", f"  {JS_SCRIPT}\n</body>", 1)
        page.write_text(html, encoding="utf-8")
        count += 1
    return count
