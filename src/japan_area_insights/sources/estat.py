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

    def _get(self, endpoint: str, params: Mapping[str, Any]) -> Any:
        query = {"appId": self.app_id, **params}
        url = f"{BASE_URL}/{endpoint}?{urllib.parse.urlencode(query, doseq=True)}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_stats_data(self, stats_data_id: str, params: Mapping[str, Any] | None = None) -> Any:
        return self._get("getStatsData", {"statsDataId": stats_data_id, **(params or {})})

    def get_meta_info(self, stats_data_id: str, params: Mapping[str, Any] | None = None) -> Any:
        return self._get("getMetaInfo", {"statsDataId": stats_data_id, **(params or {})})

    def get_stats_data_all(
        self,
        stats_data_id: str,
        params: Mapping[str, Any] | None = None,
        *,
        page_size: int = 100000,
        max_rows: int = 500000,
    ) -> Any:
        """Fetch paginated getStatsData output and merge VALUE rows.

        The caller should still use category/area filters for very large tables;
        ``max_rows`` prevents accidentally downloading an unbounded national cube.
        """
        base = dict(params or {})
        base["limit"] = min(max(1, int(page_size)), 100000)
        start = 1
        merged: Any | None = None
        collected: list[Any] = []
        while True:
            payload = self.get_stats_data(stats_data_id, {**base, "startPosition": start})
            statistical = payload.get("GET_STATS_DATA", {}).get("STATISTICAL_DATA", {})
            result_inf = statistical.get("RESULT_INF", {}) or {}
            data_inf = statistical.get("DATA_INF", {}) or {}
            values = data_inf.get("VALUE", [])
            if isinstance(values, dict):
                values = [values]
            values = list(values or [])
            collected.extend(values)
            if len(collected) > max_rows:
                raise RuntimeError(
                    f"e-Stat result exceeded max_rows={max_rows}; add narrower filters for {stats_data_id}"
                )
            if merged is None:
                merged = payload
            total = int(result_inf.get("TOTAL_NUMBER") or len(collected))
            to_number = int(result_inf.get("TO_NUMBER") or len(collected))
            if to_number >= total or not values:
                break
            start = to_number + 1

        if merged is None:
            return self.get_stats_data(stats_data_id, base)
        statistical = merged["GET_STATS_DATA"]["STATISTICAL_DATA"]
        statistical.setdefault("DATA_INF", {})["VALUE"] = collected
        statistical.setdefault("RESULT_INF", {})["FROM_NUMBER"] = 1 if collected else 0
        statistical["RESULT_INF"]["TO_NUMBER"] = len(collected)
        statistical["RESULT_INF"]["TOTAL_NUMBER"] = len(collected)
        return merged
