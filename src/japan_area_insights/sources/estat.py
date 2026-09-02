from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Mapping

BASE_URL = "https://api.e-stat.go.jp/rest/3.0/app/json"


class EStatClient:
    def __init__(self, app_id: str | None = None) -> None:
        self.app_id = app_id or os.getenv("ESTAT_APP_ID")
        if not self.app_id:
            raise RuntimeError("ESTAT_APP_ID is not set")

    def get_stats_data(self, stats_data_id: str, params: Mapping[str, Any] | None = None) -> Any:
        query = {"appId": self.app_id, "statsDataId": stats_data_id, **(params or {})}
        url = f"{BASE_URL}/getStatsData?{urllib.parse.urlencode(query, doseq=True)}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
