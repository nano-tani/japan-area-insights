from __future__ import annotations

import hashlib
import json
import re
from statistics import median
from typing import Any, Mapping

_QUARTER_RE = re.compile(r"第([1-4])四半期")

STATION_TRANSACTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS station_transactions (
    station_group_code TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER,
    transaction_date TEXT,
    municipality_code TEXT,
    district_name TEXT,
    price_category TEXT,
    property_type TEXT,
    total_price REAL,
    unit_price REAL,
    area_sqm REAL,
    source_id INTEGER,
    PRIMARY KEY (station_group_code, transaction_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);
CREATE INDEX IF NOT EXISTS idx_station_transactions_group_year
    ON station_transactions(station_group_code, year);
"""


def ensure_station_transaction_schema(conn) -> None:
    conn.executescript(STATION_TRANSACTION_SCHEMA)


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


def normalize_xit001_station(
    payload: Mapping[str, Any],
    *,
    station_group_code: str,
    year: int,
) -> list[dict[str, Any]]:
    """Normalize XIT001 rows returned by a station-code query.

    A station query can return records from multiple municipalities. The station
    group code is therefore the attribution key; municipality code is retained as
    source metadata and is not used to infer a point location.
    """
    records = payload.get("data", [])
    if records is None:
        return []
    if not isinstance(records, list):
        raise ValueError("XIT001 payload.data must be a list")

    group_code = str(station_group_code).strip()
    if not group_code:
        raise ValueError("station_group_code is required")

    duplicate_counter: dict[str, int] = {}
    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("XIT001 data item must be an object")

        canonical = json.dumps(dict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        duplicate_counter[canonical] = duplicate_counter.get(canonical, 0) + 1
        occurrence = duplicate_counter[canonical]
        tx_id = hashlib.sha256(
            f"XIT001|station|{group_code}|{year}|{canonical}|{occurrence}".encode("utf-8")
        ).hexdigest()[:32]

        total_price = _number(record.get("TradePrice"))
        area_sqm = _number(record.get("Area"))
        unit_price = _number(record.get("UnitPrice"))
        if unit_price is None and total_price is not None and area_sqm and area_sqm > 0:
            unit_price = total_price / area_sqm

        period = str(record.get("Period") or "") or None
        normalized.append(
            {
                "station_group_code": group_code,
                "transaction_id": tx_id,
                "year": int(year),
                "quarter": _quarter(period),
                "transaction_date": period,
                "municipality_code": str(record.get("MunicipalityCode") or "") or None,
                "district_name": str(record.get("DistrictName") or "") or None,
                "price_category": str(record.get("PriceCategory") or "") or None,
                "property_type": str(record.get("Type") or "") or None,
                "total_price": total_price,
                "unit_price": unit_price,
                "area_sqm": area_sqm,
            }
        )
    return normalized


def annual_transaction_summary(rows: list[Mapping[str, Any]]) -> dict[str, float | int | None]:
    unit_prices = [float(row["unit_price"]) for row in rows if row.get("unit_price") is not None]
    return {
        "transaction_count": len(rows),
        "median_unit_price": round(median(unit_prices), 2) if unit_prices else None,
        "priced_transaction_count": len(unit_prices),
    }
