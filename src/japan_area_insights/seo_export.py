from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

from .page_quality import station_page_quality
from .site_config import absolute_url, station_url


STATIC_PATHS = (
    "ranking/",
    "ranking/future-population/",
    "ranking/price-and-future/",
    "ranking/future-and-safety/",
    "methodology/",
    "sources/",
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def export_seo_files(output_dir: str | Path) -> int:
    data_dir = Path(output_dir)
    web_root = data_dir.parent
    index_path = data_dir / "geo" / "index.json"
    station_dir = data_dir / "geo" / "station"

    urls = [absolute_url(), absolute_url("stations.html"), absolute_url("station/")]
    for relative in STATIC_PATHS:
        index_file = web_root / relative / "index.html"
        if index_file.exists():
            urls.append(absolute_url(relative))

    lastmod = None
    if index_path.exists():
        payload = _load_json(index_path)
        generated_at = str(payload.get("generated_at") or "")
        lastmod = generated_at[:10] if len(generated_at) >= 10 else None
        for row in payload.get("station_areas", []) or []:
            code = str(row.get("station_code") or "").strip()
            path = station_dir / f"{code}.json"
            if not code or not path.exists():
                continue
            detail = _load_json(path)
            if station_page_quality(detail).indexable:
                urls.append(station_url(code))

    entries = []
    for url in urls:
        lastmod_xml = f"<lastmod>{escape(lastmod)}</lastmod>" if lastmod else ""
        entries.append(f"<url><loc>{escape(url)}</loc>{lastmod_xml}</url>")
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  '
        + "\n  ".join(entries)
        + "\n</urlset>\n"
    )
    (web_root / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (web_root / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\n" f"Sitemap: {absolute_url('sitemap.xml')}\n",
        encoding="utf-8",
    )
    return len(urls)
