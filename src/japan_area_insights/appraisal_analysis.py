from __future__ import annotations

import hashlib
import json
from statistics import median
from typing import Any, Iterable, Mapping

from .analysis_schema import ensure_analysis_schema, upsert_metric

METRIC_VERSION = "detail-v1"
DIVISIONS = ("00", "03", "05", "07", "09", "10", "13", "20")

APPRAISAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS appraisal_records (
    appraisal_id TEXT NOT NULL,
    area_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    division TEXT NOT NULL,
    public_price REAL,
    inheritance_road_value REAL,
    comparison_price REAL,
    income_price REAL,
    cost_price REAL,
    development_price REAL,
    capitalization_rate REAL,
    latitude REAL,
    longitude REAL,
    raw_json TEXT NOT NULL,
    source_id INTEGER,
    PRIMARY KEY (appraisal_id, year, division),
    FOREIGN KEY (area_id) REFERENCES areas(area_id),
    FOREIGN KEY (source_id) REFERENCES data_sources(source_id)
);
CREATE INDEX IF NOT EXISTS idx_appraisal_area_year ON appraisal_records(area_id, year);
"""

DEFINITIONS = [
    ("market.appraisal_count", "market", "鑑定評価書件数", "件", "neutral", "ward", "reinfolib_xct001", 1, "XCT001鑑定評価書の標準地件数"),
    ("market.appraisal_public_price_median", "market", "鑑定標準地価格中央値", "円/㎡", "neutral", "ward", "reinfolib_xct001", 3, "鑑定評価書の1㎡当たり価格中央値"),
    ("market.appraisal_comparison_price_median", "market", "比準価格中央値", "円/㎡", "neutral", "ward", "reinfolib_xct001", 3, "取引事例比較法の比準価格中央値"),
    ("market.appraisal_income_price_median", "market", "収益価格中央値", "円/㎡", "neutral", "ward", "reinfolib_xct001", 3, "収益還元法が適用され価格が正数の標準地の中央値"),
    ("market.appraisal_income_method_share", "market", "収益価格算定あり比率", "%", "neutral", "ward", "reinfolib_xct001", 3, "収益価格が正数の鑑定評価書比率"),
    ("market.inheritance_road_value_ratio", "market", "相続税路線価/公示価格中央値", "%", "neutral", "ward", "reinfolib_xct001", 3, "相続税路線価を1㎡当たり価格で除した比率の中央値"),
]


def ensure_appraisal_schema(conn) -> None:
    ensure_analysis_schema(conn)
    conn.executescript(APPRAISAL_SCHEMA)
    conn.execute(
        """
        INSERT INTO dataset_catalog(
            dataset_key,provider,api_id,category,title,source_vintage,
            granularity,refresh_mode,enabled,notes
        ) VALUES ('reinfolib_xct001','国土交通省 不動産情報ライブラリ','XCT001','market',
                  '鑑定評価書情報','直近5年','appraisal_point','extended',1,
                  '全属性をraw_jsonで保持し主要価格手法を正規化')
        ON CONFLICT(dataset_key) DO UPDATE SET source_vintage=excluded.source_vintage,notes=excluded.notes
        """
    )
    conn.executemany(
        """
        INSERT INTO metric_definitions(
            metric_key,category,label,unit,direction,granularity,
            source_dataset_key,min_sample_size,description
        ) VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(metric_key) DO UPDATE SET label=excluded.label,unit=excluded.unit,description=excluded.description
        """,
        DEFINITIONS,
    )


def _num(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _records(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("data", "results", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
        # Some responses may be a single record object.
        if "価格時点" in payload:
            return [payload]
    return []


def _first(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def normalize_appraisals(payload: Any, *, year: int, division: str, allowed_area_ids: Iterable[str]) -> list[dict[str, Any]]:
    allowed = set(map(str, allowed_area_ids))
    result: list[dict[str, Any]] = []
    for record in _records(payload):
        pref = str(_first(record, "標準地番号　市区町村コード　県コード", "標準地番号 市区町村コード 県コード") or "").zfill(2)
        city = str(_first(record, "標準地番号　市区町村コード　市区町村コード", "標準地番号 市区町村コード 市区町村コード") or "").zfill(3)
        area_id = f"{pref}{city}" if pref.strip("0") or city.strip("0") else ""
        if area_id not in allowed:
            continue
        raw = json.dumps(dict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        appraisal_id = hashlib.sha256(f"XCT001|{year}|{division}|{raw}".encode("utf-8")).hexdigest()[:32]
        result.append({
            "appraisal_id": appraisal_id,
            "area_id": area_id,
            "year": int(year),
            "division": division,
            "public_price": _num(_first(record, "1㎡当たりの価格")),
            "inheritance_road_value": _num(_first(record, "路線価　相続税路線価", "路線価 相続税路線価")),
            "comparison_price": _num(_first(record, "鑑定評価手法の適用 取引事例比較法比準価格")),
            "income_price": _num(_first(record, "鑑定評価手法の適用 収益還元法 収益価格")),
            "cost_price": _num(_first(record, "鑑定評価手法の適用 原価法 積算価格")),
            "development_price": _num(_first(record, "鑑定評価手法の適用 開発法 開発法による価格")),
            "capitalization_rate": _num(_first(record, "収益価格算定内訳還元利回り")),
            "latitude": _num(_first(record, "緯度")),
            "longitude": _num(_first(record, "経度")),
            "raw_json": raw,
        })
    return result


def _med(values: Iterable[float | None]) -> float | None:
    vals = [float(value) for value in values if value is not None and float(value) > 0]
    return round(float(median(vals)), 2) if vals else None


def compute_appraisal_metrics(conn) -> int:
    ensure_appraisal_schema(conn)
    year_row = conn.execute("SELECT MAX(year) AS y FROM appraisal_records").fetchone()
    if not year_row or year_row["y"] is None:
        return 0
    year = int(year_row["y"])
    written = 0
    for area in conn.execute("SELECT area_id FROM areas ORDER BY area_id"):
        area_id = str(area["area_id"])
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM appraisal_records WHERE area_id=? AND year=?",
            (area_id, year),
        ).fetchall()]
        if not rows:
            continue
        source_ids = [int(row["source_id"]) for row in rows if row.get("source_id") is not None]
        source_id = max(source_ids) if source_ids else None
        income_positive = [row for row in rows if row.get("income_price") is not None and float(row["income_price"]) > 0]
        ratios = [
            float(row["inheritance_road_value"]) / float(row["public_price"]) * 100.0
            for row in rows
            if row.get("inheritance_road_value") not in (None, 0) and row.get("public_price") not in (None, 0)
        ]
        metrics = {
            "market.appraisal_count": (float(len(rows)), len(rows)),
            "market.appraisal_public_price_median": (_med(row.get("public_price") for row in rows), len(rows)),
            "market.appraisal_comparison_price_median": (_med(row.get("comparison_price") for row in rows), len(rows)),
            "market.appraisal_income_price_median": (_med(row.get("income_price") for row in income_positive), len(income_positive)),
            "market.appraisal_income_method_share": (round(len(income_positive) / len(rows) * 100.0, 2), len(rows)),
            "market.inheritance_road_value_ratio": (_med(ratios), len(ratios)),
        }
        for metric_key, (value, sample) in metrics.items():
            quality = "A" if sample >= 30 else "B" if sample >= 10 else "C" if sample >= 3 else "D"
            upsert_metric(
                conn,
                geo_id=f"ward:{area_id}",
                metric_key=metric_key,
                period=str(year),
                value=value,
                sample_size=sample,
                source_id=source_id,
                metric_version=METRIC_VERSION,
                quality_grade=quality,
                source_year=str(year),
                notes="XCT001鑑定評価書。0または空欄の価格手法は中央値から除外。",
            )
            written += 1
    return written
