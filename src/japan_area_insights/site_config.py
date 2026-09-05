from __future__ import annotations

SITE_NAME = "街スコア"
SITE_URL = "https://nano-tani.github.io/japan-area-insights"
SITE_DESCRIPTION = "公的データを使って、駅周辺の現在と将来人口、暮らし、交通、不動産取引を比較する街選びサイト"
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
