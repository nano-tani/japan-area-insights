from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class PageQuality:
    indexable: bool
    reasons: tuple[str, ...]


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _future_value(detail: Mapping[str, Any], year: int) -> float | None:
    for row in detail.get("future_population", []) or []:
        if int(row.get("year") or 0) == year:
            return _number(row.get("projected_population"))
    return None


def _metric_value(detail: Mapping[str, Any], key: str) -> float | None:
    item = (detail.get("metrics") or {}).get(key) or {}
    return _number(item.get("value"))


def station_page_quality(detail: Mapping[str, Any]) -> PageQuality:
    """Return the SEO indexability decision for one station page.

    A total score is deliberately not required. A station page can still be useful
    when transaction history is too sparse for the reference score, as long as the
    spatial definition, future population and at least one living/transport signal
    are present with source lineage.
    """
    reasons: list[str] = []

    if not str(detail.get("station_code") or "").strip():
        reasons.append("station_code_missing")
    if not str(detail.get("name") or "").strip():
        reasons.append("station_name_missing")
    if _number(detail.get("latitude")) is None or _number(detail.get("longitude")) is None:
        reasons.append("station_coordinates_missing")
    if int(_number(detail.get("mesh_count")) or 0) <= 0:
        reasons.append("station_meshes_missing")

    for year in (2025, 2045):
        value = _future_value(detail, year)
        if value is None or value <= 0:
            reasons.append(f"future_population_{year}_missing")

    has_living_signal = any(
        (_metric_value(detail, f"facility_{kind}_count") or 0) > 0
        for kind in ("school", "childcare", "medical", "library", "public_facility")
    )
    has_transport_signal = any(
        (_metric_value(detail, key) or 0) > 0
        for key in ("nearby_station_count", "nearby_line_count", "ridership_daily")
    )
    if not (has_living_signal or has_transport_signal):
        reasons.append("living_transport_context_missing")

    if not (detail.get("sources") or []):
        reasons.append("source_lineage_missing")

    return PageQuality(indexable=not reasons, reasons=tuple(reasons))
