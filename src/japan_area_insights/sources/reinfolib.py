from __future__ import annotations

import gzip
import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any, Mapping

BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external"


class ReinfolibClient:
    def __init__(self, api_key: str | None = None, *, min_interval_seconds: float = 1.0) -> None:
        self.api_key = api_key or os.getenv("REINFOLIB_API_KEY")
        if not self.api_key:
            raise RuntimeError("REINFOLIB_API_KEY is not set")
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._last_request_at = 0.0

    def get_json(self, api_id: str, params: Mapping[str, Any] | None = None) -> Any:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)

        query = urllib.parse.urlencode(params or {}, doseq=True)
        url = f"{BASE_URL}/{api_id}"
        if query:
            url = f"{url}?{query}"

        request = urllib.request.Request(url)
        request.add_header("Ocp-Apim-Subscription-Key", self.api_key)
        request.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
                if "gzip" in (response.headers.get("Content-Encoding") or "").lower():
                    payload = gzip.decompress(payload)
                return json.loads(payload.decode("utf-8"))
        finally:
            self._last_request_at = time.monotonic()
