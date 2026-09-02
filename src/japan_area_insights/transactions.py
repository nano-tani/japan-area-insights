from __future__ import annotations

import hashlib
import json
import re
from statistics import mean, median
from typing import Any, Mapping

_QUARTER_RE = re.compile(r"第([1-4])四半期")


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _quarter(period: str | None) -> int | None:
    if not period:
        return None
    match = _QUARTER_RE.search(period)
    return int(match.group(1)) if match else None


def normalize_xit001(payload: Mapping[str, Any], *, area_id: str, year: int) -> list[dict[str, Any]]:
    """Normalize an XIT001 response without inventing missing values."""
    records = payload.get("data", [])
    if records is None:
        return []
    if not isinstance(records, list):
        raise ValueError("XIT001 payload.data must be a list")

    duplicate_counter: dict[str, int] = {}
    normalized: list[dict[str, Any]] = []

    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("XIT001 data item must be an object")

        municipality_code = str(record.get("MunicipalityCode") or "")
        if municipality_code and municipality_code != area_id:
            raise ValueError(f"unexpected MunicipalityCode: {municipality_code} != {area_id}")

        canonical = json.dumps(dict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        duplicate_counter[canonical] = duplicate_counter.get(canonical, 0) + 1
        occurrence = duplicate_counter[canonical]
        tx_id = hashlib.sha256(f"XIT001|{area_id}|{year}|{canonical}|{occurrence}".encode("utf-8")).hexdigest()[:32]

        total_price = _number(record.get("TradePrice"))
        area_sqm = _number(record.get("Area"))
        unit_price = _number(record.get("UnitPrice"))
        if unit_price is None and total_price is not None and area_sqm and area_sqm > 0:
            unit_price = total_price / area_sqm

        period = str(record.get("Period") or "") or None
        normalized.append(
            {
                "transaction_id": tx_id,
                "area_id": area_id,
                "year": int(year),
                "quarter": _quarter(period),
                "transaction_date": period,
                "price_category": str(record.get("PriceCategory") or "") or None,
                "property_type": str(record.get("Type") or "") or None,
                "district_name": str(record.get("DistrictName") or "") or None,
                "total_price": total_price,
                "unit_price": unit_price,
                "area_sqm": area_sqm,
            }
        )

    return normalized


def aggregate_transactions(rows: list[Mapping[str, Any]]) -> dict[str, float | int | None]:
    unit_prices = [float(row["unit_price"]) for row in rows if row.get("unit_price") is not None]
    return {
        "transaction_count": len(rows),
        "avg_transaction_unit_price": round(mean(unit_prices), 2) if unit_prices else None,
        "median_transaction_unit_price": round(median(unit_prices), 2) if unit_prices else None,
    }
