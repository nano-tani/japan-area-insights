from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

ELEVATION_URL = "https://cyberjapandata2.gsi.go.jp/general/dem/scripts/getelevation.php"


class GsiRateLimit(RuntimeError):
    pass


class GsiElevationClient:
    def __init__(self, *, min_interval_seconds: float = 0.15, retries: int = 2) -> None:
        self.min_interval_seconds = max(0.0, float(min_interval_seconds))
        self.retries = max(0, int(retries))
        self._last_request_at = 0.0

    def elevation(self, lon: float, lat: float) -> dict[str, Any] | None:
        query = urllib.parse.urlencode({"lon": f"{lon:.8f}", "lat": f"{lat:.8f}", "outtype": "JSON"})
        url = f"{ELEVATION_URL}?{query}"
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)
            request = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": "japan-area-insights/1.0 (+https://github.com/nano-tani/japan-area-insights)"},
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    if str(payload.get("elevation") or "") == "-----":
                        return None
                    return payload
            except urllib.error.HTTPError as exc:
                if exc.code in {403, 429}:
                    if attempt >= self.retries:
                        raise GsiRateLimit(f"GSI elevation service returned HTTP {exc.code}") from exc
                    last_error = exc
                elif exc.code == 404:
                    return None
                else:
                    last_error = exc
                    if exc.code not in {500, 502, 503, 504} or attempt >= self.retries:
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
