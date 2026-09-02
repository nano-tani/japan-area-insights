from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

YEARS = (2020, 2025, 2030, 2035, 2040, 2045, 2050, 2055, 2060, 2065, 2070)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "*", "@", "-", "..."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def rows_from_zip(path: str | Path) -> Iterator[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not members:
            raise ValueError("CSV file not found in archive")
        with archive.open(members[0]) as raw:
            with io.TextIOWrapper(raw, encoding="cp932", newline="") as text:
                yield from csv.DictReader(text)


def normalize_future_population(
    rows: Iterable[Mapping[str, Any]],
    *,
    allowed_area_ids: Iterable[str],
) -> Iterator[dict[str, Any]]:
    allowed = set(allowed_area_ids)
    for row in rows:
        area_id = str(row.get("SHICODE") or "").zfill(5)
        if area_id not in allowed:
            continue
        mesh_id = str(row.get("MESH_ID") or "").strip()
        baseline = _number(row.get("PTN_2020"))
        if not mesh_id or baseline is None:
            continue
        for year in YEARS:
            value = baseline if year == 2020 else _number(row.get(f"PTN_{year}"))
            if value is None:
                continue
            retention = (value / baseline * 100.0) if baseline > 0 else None
            yield {
                "area_id": area_id,
                "mesh_id": mesh_id,
                "year": year,
                "projected_population": value,
                "retention_rate": round(retention, 4) if retention is not None else None,
            }
