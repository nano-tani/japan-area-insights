from __future__ import annotations

import re
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from .site_config import CUSTOM_DOMAIN, GOOGLE_SITE_VERIFICATION, SITE_URL, absolute_url

GOOGLE_META_RE = re.compile(
    r'\s*<meta\s+name=["\']google-site-verification["\'][^>]*>',
    re.IGNORECASE,
)


def _site_parts(site_url: str):
    return urlparse(site_url.strip())


def deployment_errors(
    web_root: str | Path,
    *,
    site_url: str = SITE_URL,
    custom_domain: str = CUSTOM_DOMAIN,
    google_site_verification: str = GOOGLE_SITE_VERIFICATION,
) -> list[str]:
    root = Path(web_root)
    errors: list[str] = []
    parsed = _site_parts(site_url)
    domain = custom_domain.strip().lower().rstrip(".")

    if parsed.scheme != "https" or not parsed.netloc:
        errors.append("JAI_SITE_URL must be an absolute https URL")

    if domain:
        if parsed.hostname != domain:
            errors.append("JAI_CUSTOM_DOMAIN must match the hostname in JAI_SITE_URL")
        if parsed.path not in ("", "/"):
            errors.append("A custom-domain JAI_SITE_URL must not contain a path prefix")
        cname = root / "CNAME"
        if not cname.exists() or cname.read_text(encoding="utf-8").strip().lower().rstrip(".") != domain:
            errors.append("web/CNAME is missing or does not match JAI_CUSTOM_DOMAIN")

    sitemap = root / "sitemap.xml"
    if not sitemap.exists():
        errors.append("sitemap.xml is missing")
    elif f"<loc>{absolute_url()}</loc>" not in sitemap.read_text(encoding="utf-8"):
        errors.append("sitemap.xml does not contain the configured site root URL")

    robots = root / "robots.txt"
    expected_sitemap = f"Sitemap: {absolute_url('sitemap.xml')}"
    if not robots.exists():
        errors.append("robots.txt is missing")
    elif expected_sitemap not in robots.read_text(encoding="utf-8"):
        errors.append("robots.txt does not point at the configured sitemap URL")

    token = google_site_verification.strip()
    if token:
        homepage = root / "index.html"
        if not homepage.exists():
            errors.append("index.html is missing for Google site verification")
        else:
            expected = f'name="google-site-verification" content="{escape(token, quote=True)}"'
            if expected not in homepage.read_text(encoding="utf-8"):
                errors.append("Google site verification meta tag is missing from index.html")

    return errors


def apply_google_site_verification(web_root: str | Path, token: str = GOOGLE_SITE_VERIFICATION) -> bool:
    root = Path(web_root)
    homepage = root / "index.html"
    if not homepage.exists():
        return False

    html = GOOGLE_META_RE.sub("", homepage.read_text(encoding="utf-8"))
    value = token.strip()
    if value:
        meta = f'  <meta name="google-site-verification" content="{escape(value, quote=True)}">\n'
        if "</head>" not in html:
            raise RuntimeError("index.html has no </head> for Google site verification")
        html = html.replace("</head>", meta + "</head>", 1)
    homepage.write_text(html, encoding="utf-8")
    return bool(value)


def write_custom_domain_file(web_root: str | Path, custom_domain: str = CUSTOM_DOMAIN) -> bool:
    root = Path(web_root)
    cname = root / "CNAME"
    domain = custom_domain.strip().lower().rstrip(".")
    if not domain:
        if cname.exists():
            cname.unlink()
        return False
    if "/" in domain or ":" in domain or " " in domain:
        raise ValueError("JAI_CUSTOM_DOMAIN must be a hostname only")
    cname.write_text(domain + "\n", encoding="utf-8")
    return True


def prepare_deployment_support(web_root: str | Path) -> tuple[bool, bool]:
    cname_written = write_custom_domain_file(web_root)
    verification_written = apply_google_site_verification(web_root)
    return cname_written, verification_written
