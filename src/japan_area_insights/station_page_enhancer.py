from __future__ import annotations

from pathlib import Path

ASSETS = (
    ("station-context.css", '<link rel="stylesheet" href="../../station-context.css?v=20260905-1">', "head"),
    ("station-decision.css", '<link rel="stylesheet" href="../../station-decision.css?v=20260905-1">', "head"),
    ("station-context.js", '<script src="../../station-context.js?v=20260905-1" defer></script>', "body"),
    ("station-shortlist.js", '<script src="../../station-shortlist.js?v=20260905-1" defer></script>', "body"),
    ("station-decision.js", '<script src="../../station-decision.js?v=20260905-2" defer></script>', "body"),
)


def enhance_station_pages(web_root: str | Path) -> int:
    root = Path(web_root)
    station_root = root / "station"
    if not station_root.exists():
        return 0
    count = 0
    for page in sorted(station_root.glob("[0-9]*/index.html")):
        html = page.read_text(encoding="utf-8")
        for marker, tag, location in ASSETS:
            if marker in html:
                continue
            if location == "head":
                html = html.replace("</head>", f"  {tag}\n</head>", 1)
            else:
                html = html.replace("</body>", f"  {tag}\n</body>", 1)
        page.write_text(html, encoding="utf-8")
        count += 1
    return count
