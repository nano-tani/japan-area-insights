from __future__ import annotations

import os

DEFAULT_SITE_NAME = "街スコア"
DEFAULT_SITE_URL = "https://nano-tani.github.io/japan-area-insights"
DEFAULT_SITE_DESCRIPTION = "公的データを使って、駅周辺の現在と将来人口、暮らし、交通、不動産取引を比較する街選びサイト"

# Keep the current public brand/domain as safe defaults, while allowing a future
# independent-domain or brand migration without editing every exporter/template.
SITE_NAME = os.getenv("JAI_SITE_NAME", DEFAULT_SITE_NAME).strip() or DEFAULT_SITE_NAME
SITE_URL = os.getenv("JAI_SITE_URL", DEFAULT_SITE_URL).strip().rstrip("/") or DEFAULT_SITE_URL
SITE_DESCRIPTION = os.getenv("JAI_SITE_DESCRIPTION", DEFAULT_SITE_DESCRIPTION).strip() or DEFAULT_SITE_DESCRIPTION
SITE_LANGUAGE = "ja"


def absolute_url(path: str = "") -> str:
    base = SITE_URL.rstrip("/")
    if not path:
        return f"{base}/"
    return f"{base}/{path.lstrip('/')}"


def station_path(station_code: str) -> str:
    return f"station/{str(station_code).strip()}/"


def station_url(station_code: str) -> str:
    return absolute_url(station_path(station_code))
