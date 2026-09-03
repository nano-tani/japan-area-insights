from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

BASE_URL = "https://www.j-shis.bosai.go.jp/map/api"


class JShisRateLimit(RuntimeError):
    """Raised when J-SHIS refuses further requests for the current run."""


class JShisClient:
    def __init__(self, *, min_interval_seconds: float = 0.2, retries: int = 2) -> None:
        self.min_interval_seconds = max(0.0, float(min_interval_seconds))
        self.retries = max(0, int(retries))
        self._last_request_at = 0.0

    def get_json(self, path: str, params: Mapping[str, Any]) -> Any:
        query = urllib.parse.urlencode(params)
        url = f"{BASE_URL}/{path.lstrip('/')}?{query}"
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json, application/geo+json",
                    "User-Agent": "japan-area-insights/1.0 (+https://github.com/nano-tani/japan-area-insights)",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    raw = response.read().decode("utf-8")
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                if exc.code == 403:
                    raise JShisRateLimit("J-SHIS returned HTTP 403; stopping this partial refresh") from exc
                if exc.code == 404:
                    return None
                last_error = exc
                if exc.code == 429 and attempt >= self.retries:
                    raise JShisRateLimit("J-SHIS returned HTTP 429; stopping this partial refresh") from exc
                if exc.code not in {429, 500, 502, 503, 504} or attempt >= self.retries:
                    raise
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise
            finally:
                self._last_request_at = time.monotonic()
            time.sleep(1.5 * (attempt + 1))
        if last_error:
            raise last_error
        return None
